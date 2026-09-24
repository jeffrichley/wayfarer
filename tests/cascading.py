"""Wayfarer served in this process, cascading for real with nothing spent.

It runs against the GitHub stand-in, with Waystation's token-free `ScriptedAgent`
and its `NoSandbox` in place of Claude Code in Docker, so a session really runs
and nothing spends anything. That is the one substitution the console script
cannot make, because Wayfarer has no unsandboxed mode, not even behind a flag
(ADR-0005). Everything else is HTTP. The clone's origin is the stand-in's git
remote, where each effort's and ticket's branches are pushed.

`serving` serves a Wayfarer whose every session is held until its test lets its
ticket go, so a test decides when each one ends, and every start is written down
where the test can count it; `served_with` serves one with whatever agent and
settings a test gives.
"""

from __future__ import annotations

import shlex
import subprocess
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from waystation import NoSandbox
from waystation.agents import AgentCommand, AgentEvent
from waystation.testing import ScriptedAgent

from conftest import Stream, post, served
from github_stand_in import TOKEN, GitHub, Issue
from wayfarer.app import create_app
from wayfarer.github import GitHub as Client
from wayfarer.github import Repo
from wayfarer.models import EnvironmentFailure, GateCheck, GateStatus
from wayfarer.sessions import AgentFor, Sessions
from wayfarer.settings import Settings
from wayfarer.store import Store
from wayfarer.stream import Store as Items

_DONE = {"status": "done", "summary": "Built it.", "open_findings": [], "assumptions": []}


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def host_clone(tmp_path: Path, github: GitHub) -> Path:
    """A clone with one commit and an identity, as a session's host repo, whose origin is
    the stand-in's git remote."""
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--quiet", "--bare", "--initial-branch=main", str(remote))
    repo = tmp_path / "clone"
    git(tmp_path, "clone", "--quiet", str(remote), str(repo))
    git(repo, "config", "user.name", "Ada")
    git(repo, "config", "user.email", "ada@example.com")
    (repo / "README.md").write_text("widgets\n")
    git(repo, "add", "README.md")
    git(repo, "commit", "--quiet", "-m", "first")
    git(repo, "push", "--quiet", "origin", "HEAD:main")
    github.git = remote
    return repo


@dataclass(frozen=True)
class _Held:
    """The scripted agent, saying so and writing its ticket down as it starts, as a real
    one narrates at once, leaving some work uncommitted, and then holding until the
    test lets that ticket go."""

    released: Path
    started: Path

    def preflight(self) -> None:
        return None

    def command(self, prompt: str, outcome_schema: dict[str, Any]) -> AgentCommand:
        ticket = prompt.rsplit(" ", 1)[-1]
        played = ScriptedAgent(outcome=_DONE).command(prompt, outcome_schema)
        let_go = shlex.quote(str(self.released / ticket))
        held = [
            f"printf 'Reading ticket {ticket}.\\n'",
            f"printf 'work on {ticket}\\n' > work-{ticket}.txt",
            f"printf '%s\\n' {ticket} >> {shlex.quote(str(self.started))}",
            f"while [ ! -e {let_go} ]; do sleep 0.05; done",
        ]
        assert played.script is not None
        return replace(played, script="\n".join([*held, played.script]))

    def parse(self, line: str) -> Sequence[AgentEvent]:
        return ScriptedAgent().parse(line)


class Gate:
    """The start gate, admitting every start unless a test says otherwise. The real
    one checks Docker and the image, which a session outside Docker never needs."""

    def __init__(self) -> None:
        self.refusing = False
        self._check = GateCheck(name="Docker is running", passed=True, detail="It answered.")

    async def admit(self) -> EnvironmentFailure | None:
        if not self.refusing:
            return None
        return EnvironmentFailure(
            kind="environment",
            id="environment",
            reason="No session will start until Docker is running.",
            failed=[self._check.model_copy(update={"passed": False})],
        )

    async def status(self) -> GateStatus:
        raised = await self.admit()
        return GateStatus(
            kind="gate", id="gate", checks=[self._check], passed=raised is None, raised=raised
        )


@dataclass
class Containers:
    """The containers a restart finds, in place of Docker's, and every one it reaped.
    A session outside Docker leaves none, so a test says what a crash left."""

    left: set[str] = field(default_factory=set)
    reaped: list[str] = field(default_factory=list)

    async def run_ids(self) -> set[str]:
        return set(self.left)

    async def reap(self, run_id: str) -> None:
        self.reaped.append(run_id)
        self.left.discard(run_id)


@dataclass
class Wayfarer:
    """One Wayfarer serving in this process, and the sessions it has started."""

    url: str
    released: Path
    started_log: Path
    gate: Gate

    def started(self) -> list[int]:
        """Every ticket a session was started on, in the order they started."""
        if not self.started_log.exists():
            return []
        return [int(line) for line in self.started_log.read_text().split()]

    def let_go(self, ticket: Issue) -> None:
        """Let the session on `ticket` finish."""
        (self.released / str(ticket.number)).touch()

    def arm(self, effort: Issue) -> None:
        assert post(f"{self.url}api/efforts/{effort.number}/arm").status_code == 202


Serve = Callable[..., Wayfarer]


@contextmanager
def serving(clone: Path, tmp_path: Path, github: GitHub) -> Iterator[Serve]:
    """Serves Wayfarer on `clone`; the same data directory each time, as a restart has.
    Serving again stops the one before, as Ctrl-C does."""
    released = tmp_path / "released"
    released.mkdir()
    started = tmp_path / "started.txt"
    running: list[Any] = []

    def serve(cap: int = 3, containers: Containers | None = None) -> Wayfarer:
        for context in running:
            context.__exit__(None, None, None)
        running.clear()
        gate = Gate()
        agent = _Held(released, started)
        context = served_with(
            clone,
            tmp_path / "data",
            github,
            lambda _: agent,
            gate,
            containers=containers,
            cap=cap,
        )
        url = context.__enter__()
        running.append(context)
        return Wayfarer(url, released, started, gate)

    try:
        yield serve
    finally:
        # Anything still held is let go, so shutting down waits on nothing.
        for ticket in range(1, 100):
            (released / str(ticket)).touch()
        for context in running:
            context.__exit__(None, None, None)


@contextmanager
def served_with(
    clone: Path,
    data: Path,
    github: GitHub,
    agent: AgentFor,
    gate: Gate,
    containers: Containers | None = None,
    **settings: Any,
) -> Iterator[str]:
    """Wayfarer serving `clone`, its store in `data`, its sessions run by `agent`; its URL.
    `settings` are the ones a test changes; the poll is brisk, so a change made on GitHub
    is seen within a test's patience."""
    chosen = Settings(
        github_api=github.api,
        github_token=TOKEN,
        data_dir=data,
        poll_active=0.1,
        poll_idle=0.1,
        **settings,
    )
    items = Items(chosen.stream_backlog)

    def sessions(store: Store) -> Sessions:
        return Sessions(
            clone,
            store,
            Repo(github.owner, github.name),
            agent=agent,
            sandbox=NoSandbox(),
            settings=chosen,
            stream=items,
        )

    app = create_app(
        clone,
        chosen,
        Client(Repo(github.owner, github.name), chosen),
        items,
        sessions=sessions,
        gate=gate,
        containers=containers or Containers(),
    )
    with served(app, items) as url:
        yield url


def eventually(holds: Callable[[], bool], timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while not holds():
        assert time.monotonic() < deadline, "it never happened"
        time.sleep(0.05)


def page(url: str, derived: bool = False) -> Stream:
    # The poll keeps a page busy, so a wait is bounded in all, not only per read.
    return Stream(url, patience=20.0, derived=derived)


def cascade_id(effort: Issue) -> str:
    return f"cascade:{effort.number}"


def ticket_id(ticket: Issue) -> str:
    return f"ticket:{ticket.number}"
