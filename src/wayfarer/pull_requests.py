"""The pull request gate: how a finished session's work reaches the effort branch.

When a session ends, Wayfarer opens its pull request against the effort branch
and decides, from the Outcome and exactly once, whether it opens ready or as a
draft. A draft holds its ticket. From then on only GitHub is read: the gate never
looks at the Outcome again, so a restarted Wayfarer reaches the same answer
(ADR-0002).

A ticket whose pull request is ready, green and unheld reads as Landing, and
lands: its pull request merges into the effort branch and Wayfarer closes the
ticket itself, because GitHub closes an issue for a merge into the default branch
only. The close comment carries a hidden marker, so a close without one is a
person's.

The merge is a stand-in for the merge queue (#39), which re-tests a candidate on
the effort branch's head before it lands, and replaces `land`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from wayfarer.github import GitHub, GitHubError
from wayfarer.models import Effort, Ticket, TicketState
from wayfarer.outcome import Axis, Finding, Outcome
from wayfarer.read_model import HELD

__all__ = ["LANDED_MARKER", "PullRequestGate", "body", "opens_ready"]

_log = logging.getLogger(__name__)

LANDED_MARKER = "<!-- wayfarer:landed -->"
"""Carried by the comment Wayfarer closes a landed ticket with."""

# GitHub's default, and the one that keeps the ticket's own commits as they were
# tested; the merge queue (#39) lands by fast-forward instead.
_MERGE_METHOD = "merge"


def opens_ready(outcome: Outcome) -> bool:
    """Finished with nothing blocking. Everything else, every `not_done` too, is a draft."""
    return outcome.status == "done" and not any(f.blocks for f in outcome.open_findings)


def body(ticket: int, outcome: Outcome) -> str:
    """The pull request's body: the summary, the findings by axis with what they cite,
    then the assumptions under "Assumed". A section with nothing in it is left out."""
    parts = [f"For #{ticket}.", outcome.summary.strip()]
    if outcome.open_findings:
        parts.append("## Findings")
        for axis, heading in ((Axis.SPEC, "Spec"), (Axis.STANDARDS, "Standards")):
            found = [f for f in outcome.open_findings if f.axis is axis]
            if found:
                parts += [f"### {heading}", "\n".join(_finding(f) for f in found)]
    if outcome.assumptions:
        parts += [
            "## Assumed",
            "\n".join(f"- **{a.what}** {a.why}" for a in outcome.assumptions),
        ]
    return "\n\n".join(parts) + "\n"


def _finding(finding: Finding) -> str:
    kind = "Blocking" if finding.blocks else "Judgement call"
    where = ""
    if finding.file is not None:
        at = finding.file if finding.line is None else f"{finding.file}:{finding.line}"
        where = f" (`{at}`)"
    return f"- **{kind}:** {finding.what}{where}\n  > {finding.cites}"


class PullRequestGate:
    """Opens each finished session's pull request, and lands each one that is Landing."""

    def __init__(self, github: GitHub) -> None:
        self._github = github
        # A refused write is re-read in case it landed (ADR-0003), so retrying on
        # every read would ask again without end. Each ticket GitHub refused is
        # kept as it read then, and tried again only once it reads differently: a
        # push, a check, a label.
        self._refused: dict[int, Ticket] = {}

    async def open(
        self, *, ticket: int, title: str, branch: str, effort_branch: str, outcome: Outcome
    ) -> int:
        """Open the pull request from `branch` into `effort_branch`, ready or as a draft,
        holding the ticket when it is a draft. Returns its number."""
        ready = opens_ready(outcome)
        opened = await self._github.write(
            "POST",
            "/pulls",
            {
                "title": title,
                "head": branch,
                "base": effort_branch,
                "body": body(ticket, outcome),
                "draft": not ready,
            },
        )
        if not ready:
            await self._github.write("POST", f"/issues/{ticket}/labels", {"labels": [HELD]})
        number: int = opened["number"]
        return number

    async def land(self, effort: Effort, tickets: Iterable[Ticket]) -> None:
        """Merge every Landing ticket's pull request, and close every ticket whose pull
        request has merged. Called after each read; a refusal waits for the next."""
        for ticket in tickets:
            pull = ticket.pull_request
            # The trunk meets an effort once, through a person's review of the
            # effort branch, so a ticket's PR into it never lands by itself.
            if pull is None or pull.base == effort.trunk:
                continue
            if self._refused.get(ticket.number) == ticket:
                continue
            self._refused.pop(ticket.number, None)
            try:
                if ticket.state is TicketState.LANDING:
                    merged = await self._github.write(
                        "PUT", f"/pulls/{pull.number}/merge", {"merge_method": _MERGE_METHOD}
                    )
                    await self._close(ticket.number, pull.base, merged["sha"])
                # Merged but still open: by hand, or by a Wayfarer that stopped
                # before it closed the ticket.
                elif pull.merged and ticket.open and pull.merge_commit is not None:
                    await self._close(ticket.number, pull.base, pull.merge_commit)
            except GitHubError:
                self._refused[ticket.number] = ticket
                _log.warning("Ticket #%s did not land.", ticket.number, exc_info=True)

    async def _close(self, ticket: int, branch: str, sha: str) -> None:
        # The comment first, so the ticket is never closed without saying why.
        await self._github.write(
            "POST",
            f"/issues/{ticket}/comments",
            {"body": f"Landed on `{branch}` at {sha}.\n\n{LANDED_MARKER}"},
        )
        await self._github.write(
            "PATCH", f"/issues/{ticket}", {"state": "closed", "state_reason": "completed"}
        )
