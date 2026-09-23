"""The merge queue: how a Landing ticket's work reaches its effort branch.

A ticket joins by one rule, read entirely from GitHub: it is Landing
(`read_model.derive_state`). Each effort branch has one line, in the order its
candidates' pull requests became ready, which GitHub's timeline records. So the
queue keeps nothing, and a restart rebuilds the same line (ADR-0002). A Landing
ticket is still open, so its dependents stay blocked until it has really landed.

Each line is worked from the front, one candidate at a time. The candidate is
re-applied onto the effort branch's current head, the repo's full suite runs
over exactly that commit through `wf-test` in a sandbox (ADR-0005), and that
commit is what lands: one atomic push moves the ticket branch to it, which is
how GitHub learns the pull request merged, and fast-forwards the effort branch
onto it. Wayfarer then closes the ticket itself, because GitHub closes an issue
for a merge into the default branch only. The close comment carries a hidden
marker, so a close without one is a person's.

This stands in for Waystation's merge queue (waystation#138), built from its
public landing steps, and is deleted when that ships.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path

from waystation import PreflightError, SandboxBackend, StageError, prepare_workspace
from waystation.integration import Conflict, GitRepo

from wayfarer.github import GitHub, GitHubError
from wayfarer.models import Effort, PullRequest, Ticket, TicketState
from wayfarer.settings import Settings

__all__ = ["LANDED_MARKER", "MergeQueue"]

_log = logging.getLogger(__name__)

LANDED_MARKER = "<!-- wayfarer:landed -->"
"""Carried by the comment Wayfarer closes a landed ticket with."""

# Asked only when something is Landing, one alias per pull request: nested in the
# effort's own read, this connection would cost a point per ticket (ADR-0003).
_READY = """
query Ready($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {%s
  }
}
"""
_PULL = """
    pr%(number)d: pullRequest(number: %(number)d) {
      createdAt
      timelineItems(itemTypes: [READY_FOR_REVIEW_EVENT], last: 1) {
        nodes { ... on ReadyForReviewEvent { createdAt } }
      }
    }"""

# The repo's whole suite, through the image's own test wrapper (ADR-0005).
_CHECK = ("wf-test",)

# Where a line's branches are fetched to: out of sight of the person's own
# branches, and holding what is being tested while it is.
_FETCHED = "refs/wayfarer/queue"


class MergeQueue:
    """One line per effort branch, each worked one candidate at a time.

    `sandbox` is where a re-test runs, asked afresh for each candidate; None when
    there is nowhere to run one, and then the line waits with nothing lost.
    """

    def __init__(
        self,
        clone: Path,
        github: GitHub,
        settings: Settings,
        sandbox: Callable[[], SandboxBackend | None],
    ) -> None:
        self._clone = clone
        self._github = github
        self._settings = settings
        self._sandbox = sandbox
        self.working: dict[str, asyncio.Task[None]] = {}
        """The work each effort branch's line has in hand, by the branch."""
        # The ticket each line is landing: a read may see its pull request merged
        # before the line has closed it, and it is the line's to close.
        self._in_hand: set[int] = set()
        # A candidate that did not land is kept as its pull request read then,
        # and taken again only once that reads differently: a push, a check.
        # What else a failed re-test or a conflict does is the unhappy path's (#40).
        self._set_aside: dict[int, PullRequest] = {}
        # A close GitHub refused is tried again only once its ticket reads
        # differently, since retrying on every read would ask without end.
        self._refused: dict[int, Ticket] = {}

    async def line(self, effort: Effort, tickets: list[Ticket]) -> list[Ticket]:
        """`tickets`, each Landing one given its place in line. Called after each read:
        it closes every ticket whose pull request merged, and starts the front of each
        line that has nothing in hand."""
        await self._close_merged(effort, tickets)
        joined = [
            ticket
            for ticket in tickets
            if ticket.state is TicketState.LANDING
            and ticket.pull_request is not None
            # The trunk meets an effort once, through a person's review of the
            # effort branch, so a ticket's PR into it never lands by itself.
            and ticket.pull_request.base != effort.trunk
        ]
        try:
            ready = await self._ready(joined)
        except GitHubError:
            _log.warning("The merge queue could not be read; it waits.", exc_info=True)
            return tickets
        lines: defaultdict[str, list[Ticket]] = defaultdict(list)
        for ticket in sorted(joined, key=lambda t: ready[t.number]):
            assert ticket.pull_request is not None
            lines[ticket.pull_request.base].append(ticket)
        places: dict[int, int] = {}
        for branch, waiting in lines.items():
            places |= {ticket.number: place for place, ticket in enumerate(waiting, 1)}
            if branch not in self.working:
                self._start(branch, waiting)
        return [t.model_copy(update={"place_in_line": places.get(t.number)}) for t in tickets]

    async def stop(self) -> None:
        """Abandon every candidate in hand. Nothing is lost: each is still in line on GitHub."""
        for task in list(self.working.values()):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _ready(self, joined: list[Ticket]) -> dict[int, tuple[datetime, int]]:
        """When each ticket's pull request last became ready, from GitHub's timeline; its
        number breaks a tie."""
        if not joined:
            return {}
        pulls = {t.number: t.pull_request.number for t in joined if t.pull_request}
        aliases = "".join(_PULL % {"number": number} for number in sorted(set(pulls.values())))
        repository = await self._github.query(_READY % aliases)
        order: dict[int, tuple[datetime, int]] = {}
        for ticket, number in pulls.items():
            pull = repository[f"pr{number}"]
            events = pull["timelineItems"]["nodes"]
            # A pull request that opened ready has no event: it was ready when opened.
            at = events[-1]["createdAt"] if events else pull["createdAt"]
            order[ticket] = (datetime.fromisoformat(at), number)
        return order

    def _start(self, branch: str, waiting: list[Ticket]) -> None:
        task = asyncio.create_task(self._work(waiting))
        self.working[branch] = task
        task.add_done_callback(lambda _: self.working.pop(branch, None))

    async def _work(self, waiting: list[Ticket]) -> None:
        """Land the first candidate that will, in order. One that lands ends the turn: its
        writes set off a read, and that read starts the next."""
        for ticket in waiting:
            pull = ticket.pull_request
            assert pull is not None
            if self._set_aside.get(ticket.number) == pull:
                continue
            self._set_aside.pop(ticket.number, None)
            self._in_hand.add(ticket.number)
            try:
                if await self._take(ticket, pull):
                    return
            finally:
                self._in_hand.discard(ticket.number)

    async def _take(self, ticket: Ticket, pull: PullRequest) -> bool:
        """Try to land one candidate: whether the line's turn is over, landed or waiting."""
        backend = self._sandbox()
        if backend is None:
            return True
        try:
            await backend.preflight()
        except PreflightError:
            # Nowhere to re-test: the candidate keeps its place, and the line waits.
            _log.warning("The merge queue has nowhere to re-test.", exc_info=True)
            return True
        try:
            landed = await self._land(pull, backend)
        except (StageError, OSError):
            _log.warning("Ticket #%s could not be re-tested.", ticket.number, exc_info=True)
            landed = None
        if landed is None:
            self._set_aside[ticket.number] = pull
            return False
        # The push is not GitHub's API, so nothing else says to read again.
        self._github.freshness.poke()
        try:
            await self._close(ticket.number, pull.base, landed)
        except GitHubError:
            # The next read finds its pull request merged and closes it then.
            _log.warning("Ticket #%s landed but is not closed.", ticket.number, exc_info=True)
        return True

    async def _land(self, pull: PullRequest, backend: SandboxBackend) -> str | None:
        """Re-apply, re-test and land `pull`: the commit that landed, or None if it did not."""
        git = await GitRepo.open(self._clone)
        head = await self._fetch(git, pull.base)
        theirs = await self._fetch(git, pull.branch)
        candidate = await _reapply(git, onto=head, series=theirs)
        if isinstance(candidate, Conflict) or not await self._passes(backend, candidate):
            return None
        # Atomic, so the pull request is marked merged exactly when the effort
        # branch takes it. The effort branch is not forced: if it moved since the
        # fetch, the push is refused and nothing lands.
        pushed = await git.run(
            "push",
            "--atomic",
            "--quiet",
            f"--force-with-lease=refs/heads/{pull.branch}:{theirs}",
            "origin",
            f"{candidate}:refs/heads/{pull.branch}",
            f"{candidate}:refs/heads/{pull.base}",
        )
        if pushed.exit_code != 0:
            _log.warning("Pushing #%s's landing was refused: %s", pull.number, pushed.stderr)
            return None
        return candidate

    async def _fetch(self, git: GitRepo, branch: str) -> str:
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

    async def _passes(self, backend: SandboxBackend, candidate: str) -> bool:
        """The repo's suite, run in a sandbox over exactly `candidate`, passed in time."""
        workspace = await prepare_workspace(self._clone, base=candidate)
        try:
            async with backend.start(workspace, env={}) as sandbox:
                async with asyncio.timeout(self._settings.landing_check_wall):
                    ran = await sandbox.exec(_CHECK, capture=False)
        except TimeoutError:
            return False
        finally:
            await workspace.remove()
        return ran.exit_code == 0

    async def _close_merged(self, effort: Effort, tickets: Iterable[Ticket]) -> None:
        """Close each open ticket whose pull request merged: by hand, or by a Wayfarer that
        stopped before it closed it."""
        for ticket in tickets:
            pull = ticket.pull_request
            if (
                pull is None
                or pull.base == effort.trunk
                or not (pull.merged and ticket.open and pull.merge_commit is not None)
            ):
                continue
            if ticket.number in self._in_hand or self._refused.get(ticket.number) == ticket:
                continue
            self._refused.pop(ticket.number, None)
            try:
                await self._close(ticket.number, pull.base, pull.merge_commit)
            except GitHubError:
                self._refused[ticket.number] = ticket
                _log.warning("Ticket #%s was not closed.", ticket.number, exc_info=True)

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


async def _reapply(git: GitRepo, *, onto: str, series: str) -> str | Conflict:
    """The commits `series` has that `onto` lacks, replayed one by one onto `onto`, as
    Waystation's own apply does: the new tip, or the conflict that stopped it. A series
    already on `onto` is its own tip. Nothing but objects is written."""
    base = await git.git("merge-base", onto, series)
    if base == onto:
        return series
    tip, parent = onto, base
    for commit in (await git.git("rev-list", "--reverse", f"{base}..{series}")).split():
        tree = await git.merge_tree(base=parent, ours=tip, theirs=commit)
        if isinstance(tree, Conflict):
            return tree
        tip = await git.commit_tree(tree, tip, like=commit)
        parent = commit
    return tip
