"""Joining the merge queue: a person's two ways in, Let it land and Land it (#21, #108).

A ticket is Landing, and so in the queue, when its pull request is ready, it
carries no `wayfarer:held` or `wayfarer:asked`, its checks are green or absent,
and it is approved when auto-merge is off (`read_model.derive_state`). A person
changes one of those facts on GitHub, and the read brings the ticket into line.

**Let it land** is for a Held ticket with a pull request: its draft is marked
ready and the label comes off. Marking it ready by hand on GitHub counts the
same, and the label left behind is cleared, since Wayfarer is the only writer of
`wayfarer:*` and never holds a ticket whose pull request is ready.

**Land it** is for a clean, green pull request waiting in review with auto-merge
off. It cannot be an approving review, as #21 first had it: Wayfarer writes with
the person's token, so the person authored every pull request Wayfarer opened,
and GitHub refuses an author's approval (`422`). So it is a **Land it comment**
on the ticket, carrying a hidden marker naming the pull request, which counts as
approval when the person whose token Wayfarer holds wrote it. An approving
review on GitHub counts the same. Like a GitHub approval by default, it is not
withdrawn by a later push: the queue re-tests whatever it lands.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from wayfarer.github import GitHub, GitHubError
from wayfarer.models import Checks, Ticket, TicketState
from wayfarer.settings import Settings
from wayfarer.stream import Store as Stream

if TYPE_CHECKING:
    from wayfarer.read_model import Event

__all__ = ["HELD", "Joining", "land_it_comment", "landed_by", "mark_ready"]

HELD = "wayfarer:held"

_LAND_IT = re.compile(r"<!-- wayfarer:land-it (\{.*?\}) -->")

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

_log = logging.getLogger(__name__)


async def mark_ready(github: GitHub, pull: int) -> None:
    """Mark draft pull request `pull` ready for review."""
    found = (await github.query(_PULL_ID, number=pull))["repository"]
    await github.mutate(_TO_READY, id=found["pullRequest"]["id"])


def land_it_comment(pull: int) -> str:
    """The Land it comment: approval of pull request `pull`, in words and in its marker."""
    marker = json.dumps({"pull": pull})
    said = f"Land it: #{pull} is approved to land, from Wayfarer."
    return f"{said}\n\n<!-- wayfarer:land-it {marker} -->\n"


def landed_by(timeline: Sequence[Event], pull: int, viewer: str) -> bool:
    """Whether `viewer` said Land it for pull request `pull` on a ticket's `timeline`.
    Anyone may copy a marker, so only the person whose token Wayfarer holds is believed."""
    for e in timeline:
        if e.kind != "IssueComment" or e.actor != viewer or e.body is None:
            continue
        found = _LAND_IT.search(e.body)
        if found is None:
            continue
        try:
            said = json.loads(found.group(1))
        except ValueError:
            continue
        if isinstance(said, dict) and said.get("pull") == pull:
            return True
    return False


class Joining:
    """A person's commands into the merge queue, and the stale hold a hand-readied draft
    leaves. Each acts only on a ticket as the page last read it, in the state it is for."""

    def __init__(self, github: GitHub, stream: Stream, settings: Settings) -> None:
        self._github = github
        self._stream = stream
        self._settings = settings
        # A label GitHub would not take off is tried again only once its ticket reads
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
            # Ready first: a hold with a ready pull request is a stale one, and cleared.
            if pull.draft:
                await mark_ready(self._github, pull.number)
            await self._github.write("DELETE", f"/issues/{ticket}/labels/{HELD}", {})
        except GitHubError:
            _log.warning("Ticket #%s could not be let land.", ticket, exc_info=True)

    async def land_it(self, ticket: int) -> None:
        """Approve a clean, green pull request waiting in review, so it joins the queue."""
        read = self._stream.get(f"ticket:{ticket}")
        if self._settings.auto_merge or not isinstance(read, Ticket):
            return
        pull = read.pull_request
        if read.state is not TicketState.IN_REVIEW or pull is None or pull.draft or pull.merged:
            return
        if pull.approved or pull.checks not in (None, Checks.PASSING):
            return
        try:
            body = {"body": land_it_comment(pull.number)}
            await self._github.write("POST", f"/issues/{ticket}/comments", body)
        except GitHubError:
            _log.warning("Ticket #%s could not be approved to land.", ticket, exc_info=True)

    async def clear_stale(self, tickets: Iterable[Ticket]) -> None:
        """Take the hold off every Held ticket whose pull request a person marked ready."""
        for ticket in tickets:
            pull = ticket.pull_request
            if ticket.state is not TicketState.HELD or pull is None or pull.draft or pull.merged:
                continue
            if self._refused.get(ticket.number) == ticket:
                continue
            try:
                await self._github.write("DELETE", f"/issues/{ticket.number}/labels/{HELD}", {})
            except GitHubError:
                _log.warning(
                    "Ticket #%s's stale hold was not cleared.", ticket.number, exc_info=True
                )
                self._refused[ticket.number] = ticket
            else:
                self._refused.pop(ticket.number, None)
