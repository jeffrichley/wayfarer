"""The merge queue: a Landing ticket is re-tested on its effort branch's head, and
exactly the tree that was tested lands.

No image is needed to join the queue, but one is needed to land from it: the
re-test runs the repo's suite through `wf-test` in the session image (ADR-0005).
So, as with a session (`test_one_session.py`), the seam here is the queue
itself, driven the way the read model drives it after each read. It checks in
Waystation's `NoSandbox`, where `wf-test` is a stand-in that writes down the
tree it was run on, fails when that tree holds a file named `red`, and takes its
time over one holding `slow`. A conflict's resolver session is Waystation's
scripted agent, run in `NoSandbox` like any session under test.

GitHub is the stand-in, and the repo's git remote is a real bare repo it reads
branches from, so a push that lands a pull request's commits marks it merged,
as GitHub does.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from collections.abc import Awaitable, Iterator
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

import pytest
from claude_stream import DONE
from waystation import AgentProvider, NoSandbox, PreflightError, RunResult, RunSpec, SandboxBackend
from waystation.testing import ScriptedAgent, ScriptedCommit

from github_stand_in import TOKEN, GitHub, Issue
from github_stand_in import PullRequest as Pull
from wayfarer import stream
from wayfarer.github import GitHub as Client
from wayfarer.github import Repo
from wayfarer.merge_queue import HELD_MARKER, LANDED_MARKER, MergeQueue
from wayfarer.models import Ticket, TicketState
from wayfarer.outcome import Outcome
from wayfarer.read_model import HELD, read_effort
from wayfarer.sessions import Sessions
from wayfarer.settings import Settings
from wayfarer.store import Purpose, Store

pytestmark = pytest.mark.git

_EFFORT_BRANCH = "effort/1-widgets"

_WF_TEST = """\
#!/bin/sh
git rev-parse 'HEAD^{tree}' >> "$TESTED"
if test -e slow; then sleep 30; fi
if test -e red; then echo "red is in the tree" >&2; exit 1; fi
"""


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return done.stdout.strip()


@dataclass
class Repos:
    """The repo on GitHub, its git remote, the person's clone, and what `wf-test` saw."""

    github: GitHub
    remote: Path
    clone: Path
    tested: Path
    sandbox: SandboxBackend

    def branch(self, ticket: Issue, *files: str) -> str:
        """A ticket branch cut from the effort branch as it stands, adding `files`."""
        branch = f"ticket/{ticket.number}-work"
        _git(self.clone, "fetch", "--quiet", "origin")
        _git(self.clone, "checkout", "--quiet", "-B", branch, f"origin/{_EFFORT_BRANCH}")
        for name in files:
            (self.clone / name).write_text(f"{name}\n")
            _git(self.clone, "add", name)
            _git(self.clone, "commit", "--quiet", "-m", f"Add {name}")
        _git(self.clone, "push", "--quiet", "origin", branch)
        _git(self.clone, "checkout", "--quiet", "main")
        return _git(self.clone, "rev-parse", branch)

    def pull(self, ticket: Issue, *files: str, **fields: object) -> Pull:
        """The ready pull request a finished session leaves: its branch, into the effort's."""
        head = self.branch(ticket, *files)
        return self.github.pull_request(
            ticket,
            head=f"ticket/{ticket.number}-work",
            base=_EFFORT_BRANCH,
            head_commit=head,
            **fields,
        )

    def conflicting_pull(self, ticket: Issue) -> Pull:
        """A ready pull request writing `same.py` differently from what `pull(t, "same.py")`
        writes, cut from the effort branch as it stands."""
        branch = f"ticket/{ticket.number}-work"
        _git(self.clone, "checkout", "--quiet", "-B", branch, f"origin/{_EFFORT_BRANCH}")
        (self.clone / "same.py").write_text("different\n")
        _git(self.clone, "add", "same.py")
        _git(self.clone, "commit", "--quiet", "-m", "Add same.py differently")
        _git(self.clone, "push", "--quiet", "origin", branch)
        _git(self.clone, "checkout", "--quiet", "main")
        head = _git(self.clone, "rev-parse", branch)
        return self.github.pull_request(ticket, head=branch, base=_EFFORT_BRANCH, head_commit=head)

    def push_to_effort(self, name: str, content: str | None) -> None:
        """A commit pushed straight to the effort branch, as a person might: writing
        `name` with `content`, or removing it when that is None."""
        _git(self.clone, "fetch", "--quiet", "origin")
        _git(self.clone, "checkout", "--quiet", "-B", "by-hand", f"origin/{_EFFORT_BRANCH}")
        if content is None:
            _git(self.clone, "rm", "--quiet", name)
        else:
            (self.clone / name).write_text(content)
            _git(self.clone, "add", name)
        _git(self.clone, "commit", "--quiet", "-m", f"By hand: {name}")
        _git(self.clone, "push", "--quiet", "origin", f"HEAD:{_EFFORT_BRANCH}")
        _git(self.clone, "checkout", "--quiet", "main")

    def effort_tip(self) -> str:
        return _git(self.remote, "rev-parse", _EFFORT_BRANCH)

    def files_at(self, commit: str) -> set[str]:
        return set(_git(self.remote, "ls-tree", "--name-only", commit).split())

    def trees_tested(self) -> list[str]:
        return self.tested.read_text().split() if self.tested.exists() else []


@pytest.fixture
def repos(tmp_path: Path, github: GitHub) -> Iterator[Repos]:
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "--quiet", "--bare", "--initial-branch=main", str(remote))
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "--quiet", str(remote), str(clone))
    _git(clone, "config", "user.name", "Ada")
    _git(clone, "config", "user.email", "ada@example.com")
    (clone / "README.md").write_text("widgets\n")
    _git(clone, "add", "README.md")
    _git(clone, "commit", "--quiet", "-m", "first")
    _git(clone, "push", "--quiet", "origin", "HEAD:main", f"HEAD:{_EFFORT_BRANCH}")
    github.git = remote

    bin = tmp_path / "bin"
    bin.mkdir()
    (bin / "wf-test").write_text(_WF_TEST)
    (bin / "wf-test").chmod(0o755)
    tested = tmp_path / "tested.txt"
    sandbox = NoSandbox(
        env={"PATH": f"{bin}{os.pathsep}{os.environ['PATH']}", "TESTED": str(tested)}
    )
    yield Repos(github, remote, clone, tested, sandbox)


@pytest.fixture
def record(tmp_path: Path) -> Iterator[Store]:
    """Wayfarer's store, where a resolver session is recorded as it starts."""
    with closing(Store.open(tmp_path / "data")) as opened:
        yield opened


def _client(github: GitHub) -> Client:
    return Client(
        Repo(github.owner, github.name), Settings(github_api=github.api, github_token=TOKEN)
    )


class Driven:
    """The queue as the read model drives it: after every read, handed what it read."""

    def __init__(
        self,
        repos: Repos,
        spec: Issue,
        *,
        environment: bool = True,
        sandbox: SandboxBackend | None = None,
        settings: Settings | None = None,
        resolver: AgentProvider | None = None,
        record: Store | None = None,
        resolver_sandbox: SandboxBackend | None = None,
    ) -> None:
        """`environment` False is a machine with nowhere to run the re-test. `resolver` is
        the agent a conflict's resolver session runs, recorded in `record`."""
        self._spec = spec
        self._client = _client(repos.github)
        chosen = (sandbox or repos.sandbox) if environment else None
        self.stream = stream.Store(backlog=1000)
        sessions = None
        if resolver is not None:
            assert record is not None
            sessions = Sessions(
                repos.clone,
                record,
                Repo(repos.github.owner, repos.github.name),
                agent=resolver,
                sandbox=resolver_sandbox or NoSandbox(),
                settings=Settings(),
                stream=self.stream,
            )
        self.submitted: list[RunSpec[Outcome]] = []
        self.paused: list[int] = []
        """Each effort whose cascade the queue paused, once a pause."""
        self.queue = MergeQueue(
            repos.clone,
            self._client,
            settings or Settings(),
            sandbox=lambda: chosen,
            stream=self.stream,
            resolvers=lambda: sessions,
            submit=self._submit,
            pause=lambda effort, why: self.paused.append(effort),
        )

    def _submit(self, spec: RunSpec[Outcome]) -> Awaitable[RunResult[Outcome]]:
        """Where the queue runs a session: the cap's seam, so each is seen going through."""
        self.submitted.append(spec)
        return spec.perform()

    def raised(self) -> list[str]:
        """The reason of every environment item on the page."""
        return [item.reason for item in self.stream.items() if item.kind == "environment"]

    async def read(self) -> dict[int, Ticket]:
        effort, tickets = await read_effort(
            self._client, self._spec.number, per_page=50, auto_merge=True
        )
        return {t.number: t for t in await self.queue.line(effort, tickets)}

    async def until(self, done: str, *tickets: Issue) -> dict[int, Ticket]:
        """Read until every one of `tickets` is in state `done`, as the poll would."""
        deadline = time.monotonic() + 30
        while True:
            read = await self.read()
            if all(read[t.number].state == done for t in tickets):
                return read
            assert time.monotonic() < deadline, {n: t.state for n, t in read.items()}
            await asyncio.sleep(0.05)

    async def settled(self) -> None:
        """Until the queue has nothing in hand, and no resolver session under way."""
        deadline = time.monotonic() + 30
        while self.queue.working or self.queue.resolving:
            assert time.monotonic() < deadline, "the queue never settled"
            await asyncio.sleep(0.05)


def test_a_candidate_already_on_the_head_is_tested_and_lands_as_it_is(repos: Repos) -> None:
    spec, (ticket,) = repos.github.effort("Widgets", tickets=1)
    pull = repos.pull(ticket, "widget.py")
    head = pull.head_commit

    async def land() -> None:
        driven = Driven(repos, spec)
        await driven.until("landed", ticket)
        await driven.settled()

    asyncio.run(land())

    assert repos.effort_tip() == head
    assert repos.trees_tested() == [_git(repos.remote, "rev-parse", f"{head}^{{tree}}")]
    assert pull.state == "MERGED"
    assert ticket.state == "CLOSED"
    assert ticket.state_reason == "COMPLETED"
    assert ticket.comments == [f"Landed on `{_EFFORT_BRANCH}` at {head}.\n\n{LANDED_MARKER}"]


def test_a_candidate_behind_the_head_is_re_applied_onto_it_and_exactly_the_tested_tree_lands(
    repos: Repos,
) -> None:
    spec, (first, second) = repos.github.effort("Widgets", tickets=2)
    # Both cut from the same head, so whichever lands second is behind it.
    repos.pull(first, "one.py")
    behind = repos.pull(second, "two.py")
    cut_at = behind.head_commit

    async def land() -> None:
        driven = Driven(repos, spec)
        await driven.until("landed", first, second)
        await driven.settled()

    asyncio.run(land())

    tip = repos.effort_tip()
    assert tip != cut_at
    assert repos.trees_tested()[-1] == _git(repos.remote, "rev-parse", f"{tip}^{{tree}}")
    assert repos.files_at(tip) == {"README.md", "one.py", "two.py"}
    # Pushed to the ticket branch too, which is how GitHub knows its PR merged.
    assert _git(repos.remote, "rev-parse", behind.head) == tip
    assert behind.state == "MERGED"
    assert second.comments == [f"Landed on `{_EFFORT_BRANCH}` at {tip}.\n\n{LANDED_MARKER}"]


def test_candidates_are_taken_in_the_order_their_pull_requests_became_ready_one_at_a_time(
    repos: Repos,
) -> None:
    spec, tickets = repos.github.effort("Widgets", tickets=3)
    pulls = [repos.pull(t, f"file{t.number}.py", draft=True) for t in tickets]
    # Made ready last to first, so arrival order is not the order they opened in.
    for pull in reversed(pulls):
        repos.github.ready(pull)

    async def land() -> None:
        driven = Driven(repos, spec)
        await driven.until("landed", *tickets)
        await driven.settled()

    asyncio.run(land())

    landed = _git(repos.remote, "log", "--format=%s", "--first-parent", _EFFORT_BRANCH)
    assert landed.splitlines() == [f"Add file{t.number}.py" for t in tickets] + ["first"]
    # One at a time: each was tested on a head that already held every earlier one.
    tested = [
        set(_git(repos.remote, "ls-tree", "--name-only", tree).split())
        for tree in repos.trees_tested()
    ]
    assert tested == [
        {"README.md", "file4.py"},
        {"README.md", "file4.py", "file3.py"},
        {"README.md", "file4.py", "file3.py", "file2.py"},
    ]


def test_each_landing_ticket_has_its_place_in_line_and_a_fresh_queue_finds_the_same_line(
    repos: Repos,
) -> None:
    spec, (first, second, third) = repos.github.effort("Widgets", tickets=3)
    repos.pull(second, "b.py")
    repos.pull(first, "a.py")
    repos.pull(third, "c.py", draft=True)

    async def places() -> dict[int, int | None]:
        # Nowhere to run the re-test, so nothing leaves the line.
        driven = Driven(repos, spec, environment=False)
        read = await driven.read()
        return {n: t.place_in_line for n, t in read.items()}

    before = asyncio.run(places())
    # A restart: a new queue, with nothing kept from the last.
    after = asyncio.run(places())

    assert before == after == {first.number: 2, second.number: 1, third.number: None}


def test_a_candidate_that_fails_its_re_test_is_held_with_its_pull_request_back_to_draft(
    repos: Repos,
) -> None:
    spec, (fine, broken) = repos.github.effort("Widgets", tickets=2)
    repos.pull(fine, "fine.py")
    pull = repos.pull(broken, "red")

    async def land() -> dict[int, Ticket]:
        driven = Driven(repos, spec)
        await driven.until("held", broken)
        await driven.settled()
        for _ in range(3):
            await driven.read()
            await driven.settled()
        return await driven.read()

    read = asyncio.run(land())

    tip = repos.effort_tip()
    assert repos.files_at(tip) == {"README.md", "fine.py"}
    assert read[fine.number].state == TicketState.LANDED
    assert read[broken.number].state == TicketState.HELD
    assert pull.draft is True
    assert repos.github.labels(broken.number) == [HELD]
    [why] = broken.comments
    # What it was tested against: the head, and what had landed on it since it was cut.
    assert f"re-applied onto `{_EFFORT_BRANCH}` at {tip}" in why
    assert "Add fine.py" in why
    assert "red is in the tree" in why
    assert why.endswith(HELD_MARKER)
    # The fine one, the broken one, then the bare head once; nothing re-runs it by itself.
    assert len(repos.trees_tested()) == 3


def test_a_held_candidate_merged_by_hand_on_github_is_accepted_as_landed(repos: Repos) -> None:
    spec, (broken,) = repos.github.effort("Widgets", tickets=1)
    pull = repos.pull(broken, "red")

    async def land() -> dict[int, Ticket]:
        driven = Driven(repos, spec)
        await driven.until("held", broken)
        await driven.settled()
        repos.github.merged(pull)
        await driven.until("landed", broken)
        # The read that saw it merged closed it, so the next finds it closed.
        return await driven.read()

    read = asyncio.run(land())

    assert read[broken.number].open is False
    assert broken.state_reason == "COMPLETED"
    assert broken.comments[-1] == (
        f"Landed on `{_EFFORT_BRANCH}` at {pull.merge_commit}.\n\n{LANDED_MARKER}"
    )


def test_a_re_test_that_outruns_its_wall_cap_is_held_like_a_failed_one(repos: Repos) -> None:
    spec, (slow, fine) = repos.github.effort("Widgets", tickets=2)
    repos.pull(slow, "slow")
    repos.pull(fine, "fine.py")

    async def land() -> dict[int, Ticket]:
        # Far below the slow check's 30 s, and far above the fine one's, even on a
        # machine loaded by the suite running in parallel.
        driven = Driven(repos, spec, settings=Settings(landing_check_wall=5.0))
        read = await driven.until("landed", fine)
        await driven.settled()
        return read

    read = asyncio.run(land())

    assert read[slow.number].state == TicketState.HELD
    [why] = slow.comments
    assert "`wf-test` ran past its 5 s cap and was stopped." in why
    assert repos.files_at(repos.effort_tip()) == {"README.md", "fine.py"}


def test_a_red_effort_branch_raises_one_item_and_blames_no_candidate_until_it_is_fixed(
    repos: Repos,
) -> None:
    spec, (first, second) = repos.github.effort("Widgets", tickets=2)
    repos.pull(first, "one.py")
    repos.pull(second, "two.py")
    repos.push_to_effort("red", "broken\n")

    driven = Driven(repos, spec)

    async def wait_then_land() -> tuple[dict[int, Ticket], list[str], list[str]]:
        for _ in range(4):
            await driven.read()
            await driven.settled()
        waiting = await driven.read()
        raised = driven.raised()
        # A person fixes the branch: the line starts again, and both land.
        repos.push_to_effort("red", None)
        await driven.until("landed", first, second)
        await driven.settled()
        return waiting, raised, driven.raised()

    waiting, raised, after = asyncio.run(wait_then_land())

    assert [
        (waiting[t.number].state, waiting[t.number].place_in_line) for t in (first, second)
    ] == [
        (TicketState.LANDING, 1),
        (TicketState.LANDING, 2),
    ]
    [reason] = raised
    assert f"`{_EFFORT_BRANCH}`" in reason
    # Its cascade paused once, however many reads found the branch still red.
    assert driven.paused == [spec.number]
    # Each says only that it landed: neither was blamed for the branch.
    assert [len(first.comments), len(second.comments)] == [1, 1]
    assert LANDED_MARKER in first.comments[0] and LANDED_MARKER in second.comments[0]
    assert repos.github.labels(first.number) == repos.github.labels(second.number) == []
    assert after == []
    assert repos.files_at(repos.effort_tip()) == {"README.md", "one.py", "two.py"}
    # Blocked by the red head: the first candidate and the bare head, once, then two landings.
    assert len(repos.trees_tested()) == 4


_RESOLVES = ScriptedAgent(
    commits=[ScriptedCommit("Resolve same.py", {"same.py": "same.py\ndifferent\n"})],
    outcome=DONE,
)


def test_a_conflict_gets_one_resolver_session_and_stays_landing_until_it_lands(
    repos: Repos, record: Store
) -> None:
    spec, (first, second) = repos.github.effort("Widgets", tickets=2)
    repos.pull(first, "same.py")
    repos.conflicting_pull(second)

    async def land() -> tuple[set[str], Driven]:
        driven = Driven(repos, spec, resolver=_RESOLVES, record=record)
        seen: set[str] = set()
        deadline = time.monotonic() + 30
        while (read := await driven.read())[second.number].state != "landed":
            seen.add(read[second.number].state)
            assert time.monotonic() < deadline, seen
            await asyncio.sleep(0.05)
        await driven.settled()
        return seen, driven

    seen, driven = asyncio.run(land())

    assert seen == {TicketState.LANDING}
    assert [row.purpose for row in record.sessions()] == [Purpose.RESOLVE]
    # Submitted through the queue's one way to run a session, which is the cap's.
    [resolver] = driven.submitted
    assert f"ticket/{second.number}-work" in str(resolver.prompt)
    tip = repos.effort_tip()
    assert _git(repos.remote, "show", f"{tip}:same.py") == "same.py\ndifferent"
    assert second.comments == [f"Landed on `{_EFFORT_BRANCH}` at {tip}.\n\n{LANDED_MARKER}"]


def test_a_second_conflict_after_its_resolver_session_hands_the_ticket_to_a_person(
    repos: Repos, record: Store
) -> None:
    spec, (first, second) = repos.github.effort("Widgets", tickets=2)
    repos.pull(first, "same.py")
    pull = repos.conflicting_pull(second)

    async def land() -> dict[int, Ticket]:
        driven = Driven(repos, spec, resolver=_RESOLVES, record=record)
        branch = f"ticket/{second.number}-work"
        cut = _git(repos.remote, "rev-parse", branch)
        deadline = time.monotonic() + 30
        # Read until the resolver has pushed, which no read lands in the same turn.
        while _git(repos.remote, "rev-parse", branch) == cut:
            assert time.monotonic() < deadline, "the resolver never pushed"
            await driven.read()
            await driven.settled()
        # Resolved, and before it is taken again a person changes the same file.
        repos.push_to_effort("same.py", "by hand\n")
        read = await driven.until("held", second)
        # Held is labelled before its pull request goes back to draft.
        await driven.settled()
        return read

    read = asyncio.run(land())

    assert read[second.number].state == TicketState.HELD
    assert pull.draft is True
    [why] = second.comments
    assert f"conflicted with `{_EFFORT_BRANCH}` again after its resolver session" in why
    assert [row.purpose for row in record.sessions()] == [Purpose.RESOLVE]


def test_a_resolver_that_cannot_start_raises_one_item_and_costs_the_ticket_nothing(
    repos: Repos, record: Store
) -> None:
    spec, (first, second) = repos.github.effort("Widgets", tickets=2)
    repos.pull(first, "same.py")
    repos.conflicting_pull(second)

    async def wait() -> tuple[dict[int, Ticket], list[str]]:
        driven = Driven(
            repos, spec, resolver=_RESOLVES, record=record, resolver_sandbox=_NoDaemon()
        )
        await driven.until("landed", first)
        for _ in range(3):
            await driven.read()
            await driven.settled()
        return await driven.read(), driven.raised()

    read, raised = asyncio.run(wait())

    assert read[second.number].state == TicketState.LANDING
    [reason] = raised
    assert f"A resolver session could not start on `{_EFFORT_BRANCH}`" in reason
    assert second.comments == []
    # It never ran, so it is not the ticket's one resolver session.
    assert record.sessions() == []


def test_a_resolver_session_that_fails_hands_the_ticket_to_a_person(
    repos: Repos, record: Store
) -> None:
    spec, (first, second) = repos.github.effort("Widgets", tickets=2)
    repos.pull(first, "same.py")
    repos.conflicting_pull(second)
    gave_up = ScriptedAgent(outcome={**DONE, "status": "not_done", "summary": "Both are right."})

    async def land() -> dict[int, Ticket]:
        driven = Driven(repos, spec, resolver=gave_up, record=record)
        read = await driven.until("held", second)
        await driven.settled()
        return read

    read = asyncio.run(land())

    assert read[first.number].state == TicketState.LANDED
    [why] = second.comments
    assert "its resolver session could not resolve its conflict" in why
    assert "Both are right." in why
    assert repos.github.labels(second.number) == [HELD]


def test_a_branch_carrying_a_merge_commit_is_refused_with_a_reason_and_never_rewritten(
    repos: Repos,
) -> None:
    spec, (ticket,) = repos.github.effort("Widgets", tickets=1)
    branch = f"ticket/{ticket.number}-work"
    repos.branch(ticket, "widget.py")
    repos.push_to_effort("other.py", "other\n")
    # GitHub's "Update branch": the effort branch merged into the ticket's.
    _git(repos.clone, "fetch", "--quiet", "origin")
    _git(repos.clone, "checkout", "--quiet", "-B", branch, f"origin/{branch}")
    _git(repos.clone, "merge", "--quiet", "--no-ff", "-m", "Merge", f"origin/{_EFFORT_BRANCH}")
    _git(repos.clone, "push", "--quiet", "origin", branch)
    _git(repos.clone, "checkout", "--quiet", "main")
    merged = _git(repos.clone, "rev-parse", branch)
    pull = repos.github.pull_request(ticket, head=branch, base=_EFFORT_BRANCH, head_commit=merged)

    async def land() -> dict[int, Ticket]:
        driven = Driven(repos, spec)
        read = await driven.until("held", ticket)
        await driven.settled()
        return read

    read = asyncio.run(land())

    assert read[ticket.number].state == TicketState.HELD
    assert pull.draft is True
    [why] = ticket.comments
    assert f"the branch has a merge commit; rebase it onto `{_EFFORT_BRANCH}`" in why
    assert repos.trees_tested() == []
    assert _git(repos.remote, "rev-parse", branch) == merged


class _NoDaemon(NoSandbox):
    """A sandbox backend whose daemon does not answer."""

    async def preflight(self) -> None:
        raise PreflightError("Docker is not running.")


def test_with_nowhere_to_re_test_the_front_candidate_keeps_its_place_and_lands_later(
    repos: Repos,
) -> None:
    spec, (ticket,) = repos.github.effort("Widgets", tickets=1)
    pull = repos.pull(ticket, "widget.py")

    async def wait_then_land() -> dict[int, Ticket]:
        down = Driven(repos, spec, sandbox=_NoDaemon())
        await down.read()
        await down.settled()
        waiting = await down.read()
        await down.settled()
        assert repos.trees_tested() == []
        assert repos.effort_tip() != pull.head_commit
        # Docker is back: the same ticket, still at the front, lands.
        await Driven(repos, spec).until("landed", ticket)
        return waiting

    waiting = asyncio.run(wait_then_land())

    assert (waiting[ticket.number].state, waiting[ticket.number].place_in_line) == (
        TicketState.LANDING,
        1,
    )
    assert repos.effort_tip() == pull.head_commit
