"""Joining the merge queue: a person's two ways in, Let it land and Land it (#21, #108).

A ticket is Landing, and so in the queue, when its pull request is ready, it
carries no `wayfarer:held` or `wayfarer:asked`, its checks are green or absent,
and it is approved when auto-merge is off (`read_model.derive_state`). A person
changes one of those facts on GitHub, and the read brings the ticket into line.
Nothing about joining is stored: a comment and a label are the whole of it
(ADR-0002).

**Let it land** is for a Held ticket with a pull request: its draft is marked
ready and the label comes off. Marking it ready by hand on GitHub counts the
same, and the label left behind is cleared, since Wayfarer is the only writer of
`wayfarer:*`. A hold is stale only when the pull request became ready after the
ticket was held: some holds, such as reaping an orphan, leave a ready pull
request as it was, and those stand.

**Land it** is for a clean, green pull request waiting in review with auto-merge
off. It cannot be an approving review, as #21 first had it: Wayfarer writes with
the person's token, so the person authored every pull request Wayfarer opened,
and GitHub refuses an author's approval (`422`). So it is a **Land it comment**
on the ticket, naming the pull request in a hidden marker, which counts as
approval when the person whose token Wayfarer holds wrote it, and wrote nothing
else in it: other comments under the same token carry text a session wrote,
such as a failed check's output, so a marker inside one approves nothing. An
approving review on GitHub counts the same. Like a GitHub approval by default,
it is not withdrawn by a later push: the queue re-tests whatever it lands.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any

from wayfarer.github import GitHub, GitHubError
from wayfarer.models import Checks, PullRequest, Ticket, TicketState
from wayfarer.settings import Settings
from wayfarer.stream import Store as Stream

if TYPE_CHECKING:
    from wayfarer.read_model import Event

__all__ = ["HELD", "Joining", "for_approval", "land_it_comment", "landed_by", "mark_ready"]

HELD = "wayfarer:held"

# Only GraphQL can mark a draft ready, and it takes the pull request's node id.
_PULL_ID = """
query PullId($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) { pullRequest(number: $number) { id } }
}
"""
_TO_READY = """
mutation ToReady($id: ID!) {
  markPullRequestReadyForReview(input: {pullRequestId: $id}) { pullRequest { isDraft } }
}
"""

# When each suspect ticket was held, and when its pull request last became ready.
# Asked only for a Held ticket whose pull request reads ready, which is rare: nested
# in the effort's own read, these would cost a point per ticket (ADR-0003).
_WHEN = """
query Stale($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {%s
  }
}
"""
_SUSPECT = """
    t%(ticket)d: issue(number: %(ticket)d) {
      timelineItems(itemTypes: [LABELED_EVENT], last: 100) {
        nodes { ... on LabeledEvent { createdAt label { name } } }
      }
    }
    p%(pull)d: pullRequest(number: %(pull)d) {
      createdAt
      timelineItems(itemTypes: [READY_FOR_REVIEW_EVENT], last: 1) {
        nodes { ... on ReadyForReviewEvent { createdAt } }
      }
    }"""

_log = logging.getLogger(__name__)


async def mark_ready(github: GitHub, pull: int) -> None:
    """Mark draft pull request `pull` ready for review."""
    found = (await github.query(_PULL_ID, number=pull))["repository"]
    await github.mutate(_TO_READY, id=found["pullRequest"]["id"])


def for_approval(ticket: Ticket, auto_merge: bool) -> PullRequest | None:
    """Its pull request, when that is clean and green and waiting only on the person,
    because auto-merge is off."""
    pull = ticket.pull_request
    waiting = (
        not auto_merge
        and ticket.state is TicketState.IN_REVIEW
        and pull is not None
        and not pull.draft
        and pull.checks in (None, Checks.PASSING)
        and not pull.approved
    )
    return pull if waiting else None


def land_it_comment(pull: int) -> str:
    """The Land it comment approving pull request `pull`: its words, then its marker."""
    said = f"Land it: #{pull} is approved to land, from Wayfarer."
    return f'{said}\n\n<!-- wayfarer:land-it {{"pull": {pull}}} -->\n'


def landed_by(timeline: Sequence[Event], pull: int, viewer: str) -> bool:
    """Whether `viewer` said Land it for pull request `pull` on a ticket's `timeline`:
    a comment of theirs that is the Land it comment and nothing else."""
    said = land_it_comment(pull).strip()
    return any(
        e.kind == "IssueComment" and e.actor == viewer and (e.body or "").strip() == said
        for e in timeline
    )


class Joining:
    """A person's commands into the merge queue, and the stale hold a hand-readied draft
    leaves. Each command acts only on a ticket as the page last read it, in the state
    it is for."""

    def __init__(self, github: GitHub, stream: Stream, settings: Settings) -> None:
        self._github = github
        self._stream = stream
        self._settings = settings
        # A hold GitHub would not take off is tried again only once its ticket reads
        # differently: each write sets off a read, and each read would try again.
        self._refused: dict[int, Ticket] = {}

    async def let_it_land(self, ticket: int) -> None:
        """Mark a Held ticket's draft ready and take its hold off, so it joins the queue."""
        read = self._stream.get(f"ticket:{ticket}")
        if not isinstance(read, Ticket) or read.state is not TicketState.HELD:
            return
        pull = read.pull_request
        if pull is None or pull.merged:
            return
        try:
            if pull.draft:
                await mark_ready(self._github, pull.number)
            await self._unhold(ticket)
        except GitHubError:
            _log.warning("Ticket #%s could not be let land.", ticket, exc_info=True)

    async def land_it(self, ticket: int) -> None:
        """Approve a clean, green pull request waiting in review, so it joins the queue."""
        read = self._stream.get(f"ticket:{ticket}")
        if not isinstance(read, Ticket):
            return
        pull = for_approval(read, self._settings.auto_merge)
        if pull is None:
            return
        try:
            body = {"body": land_it_comment(pull.number)}
            await self._github.write("POST", f"/issues/{ticket}/comments", body)
        except GitHubError:
            _log.warning("Ticket #%s could not be approved to land.", ticket, exc_info=True)

    async def clear_stale(self, tickets: Iterable[Ticket]) -> None:
        """Take the hold off every Held ticket whose pull request a person marked ready
        after it was held."""
        suspects = [
            ticket
            for ticket in tickets
            if ticket.state is TicketState.HELD
            and ticket.pull_request is not None
            and not ticket.pull_request.draft
            and not ticket.pull_request.merged
            and self._refused.get(ticket.number) != ticket
        ]
        if not suspects:
            return
        try:
            stale = await self._stale(suspects)
        except GitHubError:
            _log.warning("Whether a hold is stale could not be read.", exc_info=True)
            return
        for ticket in stale:
            try:
                await self._unhold(ticket.number)
            except GitHubError:
                _log.warning("Ticket #%s's stale hold stays.", ticket.number, exc_info=True)
                self._refused[ticket.number] = ticket
            else:
                self._refused.pop(ticket.number, None)

    async def _stale(self, suspects: list[Ticket]) -> list[Ticket]:
        """Those of `suspects` whose pull request became ready after they were last held."""
        pulls = {t.number: t.pull_request.number for t in suspects if t.pull_request}
        aliases = "".join(_SUSPECT % {"ticket": t, "pull": p} for t, p in pulls.items())
        repository = (await self._github.query(_WHEN % aliases))["repository"]
        stale = []
        for ticket in suspects:
            held = _last_held(repository[f"t{ticket.number}"])
            ready = _ready_at(repository[f"p{pulls[ticket.number]}"])
            if held is None or ready > held:
                stale.append(ticket)
        return stale

    async def _unhold(self, ticket: int) -> None:
        await self._github.write("DELETE", f"/issues/{ticket}/labels/{HELD}", {})


def _last_held(issue: dict[str, Any]) -> datetime | None:
    held = [e["createdAt"] for e in issue["timelineItems"]["nodes"] if e["label"]["name"] == HELD]
    return datetime.fromisoformat(held[-1]) if held else None


def _ready_at(pull: dict[str, Any]) -> datetime:
    # A pull request that opened ready has no event: it was ready when opened.
    events = pull["timelineItems"]["nodes"]
    return datetime.fromisoformat(events[-1]["createdAt"] if events else pull["createdAt"])
