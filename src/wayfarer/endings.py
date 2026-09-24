"""How a session's end reaches GitHub: its work pushed, and its pull request or its reason.

Whether a session that did not finish failed by its own attempt or by the
environment is decided by its failure's type, never its stage (#20). The
attempt failed if the agent actually ran: it exited, reported nothing or a
report that did not fit, ran past a time cap, left a merge commit in its
series, or was stopped. Anything else is the environment's, which the cascade
answers (`cascade.py`); this module answers the rest.

Every session's commits are kept on Waystation's preservation branch, since a
session lands nowhere, and are pushed from there as the ticket's branch
(`ticket/<n>-<slug>`) into its effort branch (`effort/<n>-<slug>`), which is made
at the trunk the first time a session needs it (#27). A finished session's pull
request opens through the gate (`pull_requests.py`). A failed attempt with
commits opens a draft whose body says in plain words what happened, then the
last summary, then the end of the output; with none, a comment on the ticket
says the same. Either way the ticket is Held. A retry that continues goes on
with the pull request its ticket already has.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from pathlib import Path

from waystation import (
    AgentExited,
    OutcomeInvalid,
    OutcomeMissing,
    Refused,
    RunFailed,
    TimedOut,
)
from waystation.integration import GitRepo

from wayfarer.events import OutcomeSaid, SessionEvent, Text, ToolResult
from wayfarer.github import GitHub
from wayfarer.merge_queue import HELD_MARKER
from wayfarer.models import Effort, Ticket
from wayfarer.outcome import Outcome
from wayfarer.pull_requests import PullRequestGate
from wayfarer.read_model import HELD
from wayfarer.settings import Settings
from wayfarer.store import Fault

__all__ = [
    "STOPPED",
    "Endings",
    "effort_branch",
    "fault",
    "ticket_branch",
    "what_happened",
    "work_branch",
]

STOPPED = "You stopped it."
"""What happened to a session a person stopped."""

# The bounds only a running agent can reach; every other is a stage's.
_AGENT_BOUNDS = {"agent_silence", "agent_wall", "completion_grace"}

# Where an effort branch is fetched to, out of sight of the person's own branches.
_FETCHED = "refs/wayfarer/effort"


def fault(result: RunFailed) -> Fault:
    """Whose failure a failed session was, by the failure's type (#20)."""
    match result.failure:
        case AgentExited() | OutcomeMissing() | OutcomeInvalid():
            return Fault.ATTEMPT
        case TimedOut(bound=bound) if bound in _AGENT_BOUNDS:
            return Fault.ATTEMPT
        case Refused(reason="nonlinear_series"):
            return Fault.ATTEMPT
        case _:
            return Fault.ENVIRONMENT


def what_happened(result: RunFailed) -> str:
    """What happened to a failed session, in plain words, as one or two sentences."""
    match result.failure:
        case TimedOut(bound="agent_wall", limit=limit):
            return f"It ran out of time after {_duration(limit)}."
        case TimedOut(bound="agent_silence", limit=limit):
            return f"It printed nothing for {_duration(limit)}, so it was stopped."
        case TimedOut(bound="completion_grace"):
            return "It reported, then never exited, so it was stopped."
        case TimedOut(bound=bound, limit=limit):
            return f"Its {bound} stage ran past its {_duration(limit)} cap."
        case AgentExited(exit_code=code):
            return f"The agent exited with code {code} before it reported."
        case OutcomeMissing():
            return "The agent stopped without reporting."
        case OutcomeInvalid():
            return "The agent's report did not fit the agreed shape."
        case Refused(reason="nonlinear_series"):
            return "Its commits include a merge commit, so they are not a series that can land."
        case Refused(detail=detail):
            return f"It was refused: {detail}"
        case failure:
            return f"It could not run: {failure!r}"


def effort_branch(effort: Effort) -> str:
    """The branch an effort's tickets land on (#27)."""
    return f"effort/{effort.number}-{_slug(effort.title)}"


def ticket_branch(ticket: Ticket) -> str:
    """The branch a ticket's commits are pushed to, unless its pull request has one."""
    return f"ticket/{ticket.number}-{_slug(ticket.title)}"


def work_branch(ticket: Ticket) -> str:
    """Where a ticket's work goes now: its open pull request's branch, or its own."""
    pull = ticket.pull_request
    return pull.branch if pull is not None and not pull.merged else ticket_branch(ticket)


class Endings:
    """What each session's end leaves on GitHub, for one clone."""

    def __init__(self, clone: Path, github: GitHub, settings: Settings) -> None:
        self._clone = clone
        self._opened: GitRepo | None = None
        self._github = github
        self._settings = settings
        self._gate = PullRequestGate(github)
        # Sessions start together, and two fetches into one ref would collide.
        self._fetching = asyncio.Lock()

    async def _git(self) -> GitRepo:
        if self._opened is None:
            self._opened = await GitRepo.open(self._clone)
        return self._opened

    async def effort_head(self, effort: Effort) -> str:
        """The effort branch's head, made at the trunk's if the branch is not yet on
        GitHub: where a session on the effort starts."""
        branch = effort_branch(effort)
        async with self._fetching, self._bounded():
            git = await self._git()
            there = await git.git("ls-remote", "--heads", "origin", f"refs/heads/{branch}")
            if not there:
                trunk = await self._fetch(git, effort.trunk)
                await git.git("push", "--quiet", "origin", f"{trunk}:refs/heads/{branch}")
            return await self._fetch(git, branch)

    async def branch_head(self, branch: str) -> str:
        """The head of `branch` on GitHub: where a retry that continues a pull request starts."""
        async with self._fetching, self._bounded():
            return await self._fetch(await self._git(), branch)

    async def kept(self, run_id: str) -> str | None:
        """The preservation branch session `run_id` left, or None when it had no commits."""
        branch = f"waystation/{run_id}"
        found = await (await self._git()).run(
            "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"
        )
        return branch if found.exit_code == 0 else None

    async def ended(
        self,
        ticket: Ticket,
        effort: Effort,
        *,
        preserved: str | None,
        outcome: Outcome | None,
        why: str | None,
        events: Sequence[SessionEvent],
        over: bool,
    ) -> None:
        """Push what a session left and open or update its pull request, or say on its
        ticket why there is none. `outcome` is what a finished session reported; `why`
        says what happened to one that failed, for a draft's body or a comment. `over`
        is a start over, whose commits replace any its ticket branch still holds."""
        pull = (
            ticket.pull_request if ticket.pull_request and not ticket.pull_request.merged else None
        )
        if preserved is None and pull is None:
            said = why or _nothing_committed(outcome)
            await self._comment_held(ticket.number, self._held(said, events))
            return
        branch = work_branch(ticket)
        if preserved is not None:
            await self._push(preserved, branch, over=over)
        if outcome is not None and why is None:
            await self._gate.open(
                ticket=ticket.number,
                title=ticket.title,
                branch=branch,
                effort_branch=effort_branch(effort),
                outcome=outcome,
                pull=pull.number if pull else None,
            )
            return
        said = why or _nothing_committed(outcome)
        await self._gate.hold(
            ticket=ticket.number,
            title=ticket.title,
            branch=branch,
            effort_branch=effort_branch(effort),
            body=f"For #{ticket.number}.\n\n{self._held(said, events)}",
            pull=pull.number if pull else None,
        )

    async def _push(self, preserved: str, branch: str, *, over: bool) -> None:
        """Push `preserved` as the ticket branch. `over` replaces what a start over left
        behind; otherwise it only moves on, and a branch holding other commits refuses
        it, so nothing pushed before is lost."""
        force = ("--force",) if over else ()
        async with self._bounded():
            await (await self._git()).git(
                "push", "--quiet", *force, "origin", f"refs/heads/{preserved}:refs/heads/{branch}"
            )
        # The push is not GitHub's API, so nothing else says to read again.
        self._github.freshness.poke()

    async def hold_saying(self, ticket: int, why: str) -> None:
        """Hold a ticket with nothing to publish, saying `why` on it."""
        await self._comment_held(ticket, f"**Held: {why}**\n")

    async def _comment_held(self, ticket: int, said: str) -> None:
        # The comment first, so the ticket is never held without saying why.
        await self._github.write(
            "POST", f"/issues/{ticket}/comments", {"body": f"{said}\n{HELD_MARKER}"}
        )
        await self._github.write("POST", f"/issues/{ticket}/labels", {"labels": [HELD]})

    def _held(self, why: str, events: Sequence[SessionEvent]) -> str:
        """What happened in plain words, then the last summary, then the end of the output."""
        parts = [f"**Held: {why}**"]
        if (summary := _last_summary(events)) is not None:
            parts += ["## The last summary", summary.strip()]
        if tail := _tail(events, self._settings.held_output_lines):
            parts += ["## The end of the output", f"````text\n{tail}\n````"]
        return "\n\n".join(parts) + "\n"

    def _bounded(self) -> asyncio.Timeout:
        """The same stage cap a session's own steps run under, since only a hang would
        reach it."""
        return asyncio.timeout(self._settings.stage_timeout)

    @staticmethod
    async def _fetch(git: GitRepo, branch: str) -> str:
        ref = f"{_FETCHED}/{branch}"
        await git.git(
            "fetch",
            "--quiet",
            "--no-tags",
            "--no-write-fetch-head",
            "origin",
            f"+refs/heads/{branch}:{ref}",
        )
        return await git.git("rev-parse", "--verify", f"{ref}^{{commit}}")


def _nothing_committed(outcome: Outcome | None) -> str:
    if outcome is not None and outcome.status == "done":
        return "It said it was done, but committed nothing."
    return "It did not finish, and committed nothing."


def _last_summary(events: Sequence[SessionEvent]) -> str | None:
    """The summary of the last report the agent made, valid or not."""
    for event in reversed(events):
        if isinstance(event, OutcomeSaid) and isinstance(event.raw, dict):
            summary = event.raw.get("summary")
            if isinstance(summary, str) and summary.strip():
                return summary
    return None


def _tail(events: Sequence[SessionEvent], lines: int) -> str:
    """The last `lines` lines of what the agent said and its tools returned."""
    said = [e.text for e in events if isinstance(e, Text | ToolResult) and e.text.strip()]
    return "\n".join("\n".join(said).splitlines()[-lines:])


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def _duration(seconds: float) -> str:
    if seconds >= 3600:
        return f"{seconds / 3600:g} h"
    return f"{seconds / 60:g} min" if seconds >= 60 else f"{seconds:g} s"
