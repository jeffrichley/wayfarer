"""Wayfarer served in this process with its sessions really running, for the tests of
the cascade and of what a session's end leaves behind.

Waystation's token-free `ScriptedAgent` and its `NoSandbox` stand in for Claude Code
in Docker, so a session really runs and nothing spends anything. That is the one
substitution the console script cannot make, because Wayfarer has no unsandboxed
mode, not even behind a flag (ADR-0005). Everything else is HTTP. The clone's origin
is the stand-in's git remote, where each effort's and ticket's branches are pushed.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from waystation import NoSandbox

from conftest import served
from github_stand_in import TOKEN, GitHub
from wayfarer.app import create_app
from wayfarer.github import GitHub as Client
from wayfarer.github import Repo
from wayfarer.models import EnvironmentFailure, GateCheck, GateStatus
from wayfarer.sessions import AgentFor, Sessions
from wayfarer.settings import Settings
from wayfarer.store import Store
from wayfarer.stream import Store as Items

__all__ = ["Gate", "eventually", "git", "origin_clone", "serving"]


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def origin_clone(tmp_path: Path, github: GitHub) -> Path:
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


def eventually(holds: Callable[[], bool], timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while not holds():
        assert time.monotonic() < deadline, "it never happened"
        time.sleep(0.05)


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


@contextmanager
def serving(
    clone: Path, data: Path, github: GitHub, agent: AgentFor, gate: Gate, **settings: Any
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
    )
    with served(app, items) as url:
        yield url
