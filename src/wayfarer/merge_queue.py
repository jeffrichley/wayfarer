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

A candidate that cannot land is handed to a person, never tried again by itself
(#21). One that fails its re-test is held: its pull request goes back to draft,
the ticket is labelled `wayfarer:held`, and a comment names what it was tested
with and the end of what failed. The effort branch's own head is then checked
once, so a red branch raises one item and stops its line rather than holding
every ticket in it. One that conflicts gets one resolver session, which stays
Landing while it works; a second conflict, or a resolver that fails, holds it.
A branch with a merge commit in it is held with the reason, since landing it
would mean rewriting a person's commits.

This stands in for Waystation's merge queue (waystation#138), built from its
public landing steps, and is deleted when that ships.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from waystation import (
    PreflightError,
    RunFailed,
    RunResult,
    RunSpec,
    RunSucceeded,
    SandboxBackend,
    StageError,
    prepare_workspace,
)
from waystation.integration import Conflict, GitRepo

from wayfarer.github import GitHub, GitHubError
from wayfarer.models import Effort, EnvironmentFailure, GateCheck, PullRequest, Ticket, TicketState
from wayfarer.outcome import Outcome
from wayfarer.read_model import HELD
from wayfarer.sessions import Sessions
from wayfarer.settings import Settings
from wayfarer.stream import Store

__all__ = ["HELD_MARKER", "LANDED_MARKER", "MergeQueue", "Submit"]

_log = logging.getLogger(__name__)

LANDED_MARKER = "<!-- wayfarer:landed -->"
"""Carried by the comment Wayfarer closes a landed ticket with."""

HELD_MARKER = "<!-- wayfarer:held -->"
"""Carried by the comment saying why the merge queue held a ticket."""

type Submit = Callable[[RunSpec[Outcome]], Awaitable[RunResult[Outcome]]]
"""Where a resolver session is run: under the cap every session shares."""

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

# A resolver's view of the ticket branch. A workspace carries only branches and
# tags of the host's (Waystation ADR-0037), so it is one while the resolver runs.
_RESOLVING = "wayfarer/resolving"

_MERGE_COMMIT = """\
**Held: the branch has a merge commit; rebase it onto `{base}`.** The merge queue \
lands a ticket's commits one by one onto the effort branch, and a merge commit \
cannot be replayed without rewriting it, which Wayfarer never does to a person's \
commits."""

_CONFLICTED_AGAIN = """\
**Held: it conflicted with `{base}` again after its resolver session.** Its one \
automatic resolver session has run, so a person decides what happens next."""


class MergeQueue:
    """One line per effort branch, each worked one candidate at a time.

    `sandbox` is where a re-test runs, asked afresh for each candidate; None when
    there is nowhere to run one, and then the line waits with nothing lost.
    `resolvers` runs a conflicted candidate's resolver session, asked afresh the
    same way, through `submit`; `stream` carries the item a red effort branch raises.
    """

    def __init__(
        self,
        clone: Path,
        github: GitHub,
        settings: Settings,
        sandbox: Callable[[], SandboxBackend | None],
        *,
        stream: Store,
        resolvers: Callable[[], Sessions | None] = lambda: None,
        submit: Submit = lambda spec: spec.perform(),
    ) -> None:
        self._clone = clone
        self._github = github
        self._settings = settings
        self._sandbox = sandbox
        self._stream = stream
        self._resolvers = resolvers
        self._submit = submit
        self.working: dict[str, asyncio.Task[None]] = {}
        """The work each effort branch's line has in hand, by the branch."""
        self.resolving: dict[int, asyncio.Task[None]] = {}
        """Each ticket with a resolver session under way. It stays Landing, and in line."""
        # The ticket each line is landing: a read may see its pull request merged
        # before the line has closed it, and it is the line's to close.
        self._in_hand: set[int] = set()
        # A candidate that did not land is kept as its pull request read then,
        # and taken again only once that reads differently: a push, a check. A
        # held one reads differently at once, and is not Landing, so it is not.
        self._set_aside: dict[int, PullRequest] = {}
        # Each effort branch whose head failed the suite on its own, at that head:
        # its line lands nothing until the branch moves.
        self._red: dict[str, str] = {}
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
        for task in [*self.working.values(), *self.resolving.values()]:
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
        # A resolver builds on the head as it stands, so its line lands nothing behind
        # its back: what it makes is re-tested on that same head.
        if any(ticket.number in self.resolving for ticket in waiting):
            return
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
            async with self._bounded():
                await backend.preflight()
        except (PreflightError, TimeoutError):
            # Nowhere to re-test: the candidate keeps its place, and the line waits.
            _log.warning("The merge queue has nowhere to re-test.", exc_info=True)
            return True
        try:
            return await self._land(ticket, pull, backend)
        except (StageError, OSError, TimeoutError):
            _log.warning("Ticket #%s could not be re-tested.", ticket.number, exc_info=True)
            self._set_aside[ticket.number] = pull
            return False

    async def _land(self, ticket: Ticket, pull: PullRequest, backend: SandboxBackend) -> bool:
        """Re-apply, re-test and land `pull`, or say why not: whether the line's turn is over."""
        async with self._bounded():
            git = await GitRepo.open(self._clone)
            head = await self._fetch(git, pull.base)
            theirs = await self._fetch(git, pull.branch)
        if self._red.get(pull.base) == head:
            return True
        self._forget_red(pull.base)
        async with self._bounded():
            merges = await _has_merge_commit(git, onto=head, series=theirs)
            candidate = None if merges else await _reapply(git, onto=head, series=theirs)
        if candidate is None:
            await self._hold(ticket, pull, _MERGE_COMMIT.format(base=pull.base))
            return False
        if isinstance(candidate, Conflict):
            await self._conflicted(ticket, pull, head, theirs)
            return False
        tested = await self._check(backend, candidate)
        if not tested.passed:
            # Checked once, so a red branch raises one item rather than one a ticket.
            bare = await self._check(backend, head)
            if not bare.passed:
                self._raise_red(pull.base, head, bare)
                return True
            await self._hold(
                ticket, pull, await self._why_retest_failed(git, pull, head, theirs, tested)
            )
            return False
        # Atomic, so the pull request is marked merged exactly when the effort
        # branch takes it. The effort branch is not forced: if it moved since the
        # fetch, the push is refused and nothing lands.
        async with self._bounded():
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
            self._set_aside[ticket.number] = pull
            return False
        # The push is not GitHub's API, so nothing else says to read again.
        self._github.freshness.poke()
        try:
            await self._close(ticket.number, pull.base, candidate)
        except GitHubError:
            # The next read finds its pull request merged and closes it then.
            _log.warning("Ticket #%s landed but is not closed.", ticket.number, exc_info=True)
        return True

    def _bounded(self) -> asyncio.Timeout:
        """The cap on every step but the re-test itself, which only a hang would reach:
        a hung step would otherwise hold its line forever. The same stage cap a
        session's own steps run under."""
        return asyncio.timeout(self._settings.stage_timeout)

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

    async def _check(self, backend: SandboxBackend, commit: str) -> _Tested:
        """The repo's suite, run in a sandbox over exactly `commit`, and how it ended."""
        async with self._bounded():
            workspace = await prepare_workspace(self._clone, base=commit)
        try:
            async with backend.start(workspace, env={}) as sandbox:
                async with asyncio.timeout(self._settings.landing_check_wall):
                    # Uncaptured, so the result carries Waystation's bounded tails.
                    ran = await sandbox.exec(_CHECK, capture=False)
        except TimeoutError:
            cap = _duration(self._settings.landing_check_wall)
            return _Tested(False, f"`wf-test` ran past its {cap} cap and was stopped.")
        finally:
            await workspace.remove()
        output = "\n".join(tail for tail in (ran.stdout, ran.stderr) if tail.strip())
        return _Tested(ran.exit_code == 0, output.rstrip())

    async def _why_retest_failed(
        self, git: GitRepo, pull: PullRequest, head: str, theirs: str, tested: _Tested
    ) -> str:
        """Why a candidate that failed its re-test is held: what it was tested with, and
        the end of what failed."""
        cut = await git.git("merge-base", head, theirs)
        landed = await git.git("log", "--format=- %h %s", f"{cut}..{head}")
        since = (
            f"It was tested with what had landed on `{pull.base}` since it was cut:\n\n{landed}"
            if landed
            else f"Nothing had landed on `{pull.base}` since it was cut."
        )
        return (
            f"**Held: its re-test on `{pull.base}` was red.** Its commits were re-applied "
            f"onto `{pull.base}` at {head}, and the suite was red there, though `{pull.base}` "
            f"alone is green. Nothing re-runs it by itself.\n\n{since}\n\n"
            f"The end of what `wf-test` said:\n\n````text\n{tested.output}\n````"
        )

    async def _hold(self, ticket: Ticket, pull: PullRequest, why: str) -> None:
        """Hand `ticket` to a person: say why on it, label it Held, and return its pull
        request to draft. A Held ticket is not Landing, so nothing takes it again by itself."""
        self._set_aside[ticket.number] = pull
        try:
            # The comment first, so the ticket is never held without saying why.
            await self._github.write(
                "POST", f"/issues/{ticket.number}/comments", {"body": f"{why}\n\n{HELD_MARKER}"}
            )
            await self._github.write("POST", f"/issues/{ticket.number}/labels", {"labels": [HELD]})
            found = await self._github.query(_PULL_ID, number=pull.number)
            await self._github.mutate(_TO_DRAFT, id=found["pullRequest"]["id"])
        except GitHubError:
            # Set aside until its pull request reads differently, as any that did not land.
            _log.warning("Ticket #%s could not be held.", ticket.number, exc_info=True)

    async def _conflicted(self, ticket: Ticket, pull: PullRequest, head: str, theirs: str) -> None:
        """A candidate that conflicts gets one resolver session, and is held on its second
        conflict. Its place in line is kept while the resolver works."""
        self._set_aside[ticket.number] = pull
        sessions = self._resolvers()
        if sessions is None:
            # Nowhere to run a resolver: it waits for its pull request to change.
            _log.warning("Ticket #%s conflicts, with nowhere to resolve it.", ticket.number)
            return
        if sessions.resolved(ticket.number):
            await self._hold(ticket, pull, _CONFLICTED_AGAIN.format(base=pull.base))
            return
        task = asyncio.create_task(self._resolve(sessions, ticket, pull, head, theirs))
        self.resolving[ticket.number] = task
        task.add_done_callback(lambda _: self.resolving.pop(ticket.number, None))

    async def _resolve(
        self, sessions: Sessions, ticket: Ticket, pull: PullRequest, head: str, theirs: str
    ) -> None:
        """Run `ticket`'s resolver session onto `head`, and push what it made to the ticket
        branch, which puts it back in line to be re-tested; or hold the ticket."""
        local = f"{_RESOLVING}/{pull.branch}"
        try:
            async with self._bounded():
                git = await GitRepo.open(self._clone)
                await git.git("branch", "--force", local, theirs)
            try:
                result = await self._submit(
                    sessions.resolver(ticket.number, onto=head, branch=local)
                )
            finally:
                async with self._bounded():
                    await git.git("branch", "--delete", "--force", local)
            await self._take_resolution(git, ticket, pull, theirs, result)
        except (PreflightError, StageError, OSError, TimeoutError, GitHubError) as error:
            # The environment's, before the resolver's agent ran: that is not its one
            # resolver session, so the next read tries again, from its place in line,
            # with one item raised however many times it cannot (#21, decision 8).
            _log.warning("Ticket #%s's resolver could not run.", ticket.number, exc_info=True)
            self._set_aside.pop(ticket.number, None)
            self._raise(
                _unresolved_id(pull.base),
                f"A resolver session could not start on `{pull.base}`, so its line waits.",
                check=f"A resolver session can start on `{pull.base}`",
                detail=str(error) or type(error).__name__,
            )
            return
        self._stream.remove(_unresolved_id(pull.base))

    async def _take_resolution(
        self,
        git: GitRepo,
        ticket: Ticket,
        pull: PullRequest,
        theirs: str,
        result: RunResult[Outcome],
    ) -> None:
        if isinstance(result, RunFailed) and result.agent is None:
            raise StageError(result.stage, result.failure)
        if (
            isinstance(result, RunSucceeded)
            and result.outcome.status == "done"
            and result.preserved is not None
        ):
            # Not forced past a person's push: if the ticket branch moved, this is
            # refused, and the pull request, having moved, is taken again anyway.
            async with self._bounded():
                pushed = await git.run(
                    "push",
                    "--quiet",
                    f"--force-with-lease=refs/heads/{pull.branch}:{theirs}",
                    "origin",
                    f"refs/heads/{result.preserved}:refs/heads/{pull.branch}",
                )
            if pushed.exit_code != 0:
                _log.warning("Pushing #%s's resolution was refused: %s", pull.number, pushed.stderr)
            self._github.freshness.poke()
            return
        if isinstance(result, RunFailed):
            said = f"It failed: {result.failure!r}."
        elif isinstance(result, RunSucceeded) and result.outcome.status == "done":
            said = "It changed nothing."
        else:
            said = f"It said: {result.outcome.summary}"
        await self._hold(
            ticket,
            pull,
            f"**Held: its resolver session could not resolve its conflict with "
            f"`{pull.base}`.** {said}",
        )

    def _raise_red(self, branch: str, head: str, bare: _Tested) -> None:
        """The one item a red effort branch raises, however many candidates it failed. The
        candidate keeps its place at the front of a line that lands nothing until the
        branch moves."""
        self._red[branch] = head
        self._raise(
            _red_id(branch),
            f"The effort branch's tests are red: `{branch}` at {head[:7]} is red on its own, "
            "so nothing lands on it until that is fixed.",
            check=f"The tests are green on `{branch}`",
            detail=bare.output or "`wf-test` was red and said nothing.",
        )

    def _raise(self, id: str, reason: str, *, check: str, detail: str) -> None:
        """One Needs you item for a failure of the environment while landing, the same
        shape a failed start gate raises. Raising it again changes nothing."""
        failed = [GateCheck(name=check, passed=False, detail=detail)]
        self._stream.upsert(
            EnvironmentFailure(kind="environment", id=id, reason=reason, failed=failed)
        )

    def _forget_red(self, branch: str) -> None:
        if self._red.pop(branch, None) is not None:
            self._stream.remove(_red_id(branch))

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


@dataclass(frozen=True)
class _Tested:
    """How one run of the suite ended."""

    passed: bool
    output: str
    """The end of what it printed, or why it said nothing."""


_PULL_ID = """
query PullId($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) { pullRequest(number: $number) { id } }
}
"""

# A draft is a Held ticket's pull request, and only GraphQL can make one of a ready one.
_TO_DRAFT = """
mutation ToDraft($id: ID!) {
  convertPullRequestToDraft(input: {pullRequestId: $id}) { pullRequest { isDraft } }
}
"""


def _red_id(branch: str) -> str:
    return f"environment:red:{branch}"


def _unresolved_id(branch: str) -> str:
    return f"environment:resolver:{branch}"


def _duration(seconds: float) -> str:
    return f"{seconds / 60:g} min" if seconds >= 60 else f"{seconds:g} s"


async def _has_merge_commit(git: GitRepo, *, onto: str, series: str) -> bool:
    """Whether `series` carries a merge commit that `onto` does not."""
    base = await git.git("merge-base", onto, series)
    return bool(await git.git("rev-list", "--merges", f"{base}..{series}"))


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
