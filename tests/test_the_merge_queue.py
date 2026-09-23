"""The merge queue: a Landing ticket is re-tested on its effort branch's head, and
exactly the tree that was tested lands.

No image is needed to join the queue, but one is needed to land from it: the
re-test runs the repo's suite through `wf-test` in the session image (ADR-0005).
So, as with a session (`test_one_session.py`), the seam here is the queue
itself, driven the way the read model drives it after each read. It checks in
Waystation's `NoSandbox`, where `wf-test` is a stand-in that writes down the
tree it was run on, fails when that tree holds a file named `red`, and takes its
time over one holding `slow`.

GitHub is the stand-in, and the repo's git remote is a real bare repo it reads
branches from, so a push that lands a pull request's commits marks it merged,
as GitHub does.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from waystation import NoSandbox, PreflightError, SandboxBackend

from github_stand_in import TOKEN, GitHub, Issue
from github_stand_in import PullRequest as Pull
from wayfarer.github import GitHub as Client
from wayfarer.github import Repo
from wayfarer.merge_queue import LANDED_MARKER, MergeQueue
from wayfarer.models import Ticket, TicketState
from wayfarer.read_model import read_effort
from wayfarer.settings import Settings

pytestmark = pytest.mark.git

_EFFORT_BRANCH = "effort/1-widgets"

_WF_TEST = """\
#!/bin/sh
git rev-parse 'HEAD^{tree}' >> "$TESTED"
if test -e slow; then sleep 30; fi
test ! -e red
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
    ) -> None:
        """`environment` False is a machine with nowhere to run the re-test."""
        self._spec = spec
        self._client = _client(repos.github)
        chosen = (sandbox or repos.sandbox) if environment else None
        self.queue = MergeQueue(
            repos.clone, self._client, settings or Settings(), sandbox=lambda: chosen
        )

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
        """Until the queue has nothing in hand."""
        deadline = time.monotonic() + 30
        while self.queue.working:
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


def test_a_candidate_that_fails_its_re_test_never_lands_and_the_line_moves_on(
    repos: Repos,
) -> None:
    spec, (broken, fine) = repos.github.effort("Widgets", tickets=2)
    repos.pull(broken, "red")
    repos.pull(fine, "fine.py")

    async def land() -> dict[int, Ticket]:
        driven = Driven(repos, spec)
        await driven.until("landed", fine)
        await driven.settled()
        for _ in range(3):
            await driven.read()
        await driven.settled()
        return await driven.read()

    read = asyncio.run(land())

    assert repos.files_at(repos.effort_tip()) == {"README.md", "fine.py"}
    assert read[broken.number].state == TicketState.LANDING
    assert broken.comments == []
    # Tested once: nothing re-runs a failed re-test by itself.
    assert len(repos.trees_tested()) == 2


def test_a_candidate_that_conflicts_with_the_head_never_lands(repos: Repos) -> None:
    spec, (first, second) = repos.github.effort("Widgets", tickets=2)
    repos.pull(first, "same.py")
    # The same file, written differently on the second branch.
    branch = f"ticket/{second.number}-work"
    _git(repos.clone, "checkout", "--quiet", "-B", branch, f"origin/{_EFFORT_BRANCH}")
    (repos.clone / "same.py").write_text("different\n")
    _git(repos.clone, "add", "same.py")
    _git(repos.clone, "commit", "--quiet", "-m", "Add same.py differently")
    _git(repos.clone, "push", "--quiet", "origin", branch)
    _git(repos.clone, "checkout", "--quiet", "main")
    repos.github.pull_request(
        second, head=branch, base=_EFFORT_BRANCH, head_commit=_git(repos.clone, "rev-parse", branch)
    )

    async def land() -> dict[int, Ticket]:
        driven = Driven(repos, spec)
        await driven.until("landed", first)
        await driven.settled()
        await driven.read()
        await driven.settled()
        return await driven.read()

    read = asyncio.run(land())

    assert read[second.number].state == TicketState.LANDING
    assert len(repos.trees_tested()) == 1


def test_a_re_test_that_outruns_its_wall_cap_counts_as_failed(repos: Repos) -> None:
    spec, (slow, fine) = repos.github.effort("Widgets", tickets=2)
    repos.pull(slow, "slow")
    repos.pull(fine, "fine.py")

    async def land() -> dict[int, Ticket]:
        driven = Driven(repos, spec, settings=Settings(landing_check_wall=0.5))
        read = await driven.until("landed", fine)
        await driven.settled()
        return read

    read = asyncio.run(land())

    assert read[slow.number].state == TicketState.LANDING
    assert repos.files_at(repos.effort_tip()) == {"README.md", "fine.py"}


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
