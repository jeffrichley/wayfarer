"""The start gate: what must hold before any session starts (ADR-0005).

Six checks, each of which would otherwise fail a session halfway through and
waste the run: the Docker daemon is up; the image for the current layer exists;
that image passed its probe; an agent credential is set; the clone has a git
identity; the read-only GitHub token a session reads its ticket with is set. Git
identity is here because Waystation's preflight does not check it, and would
refuse mid-run at clone instead, once per session running.

The cascade asks `admit` when it is armed and before each session starts, and
pauses when refused. However many starts are refused, the gate raises one item
for the person, and it touches nothing already running.

Credentials are read from the environment Wayfarer was started from, at the
moment of each check. They are never stored, never asked for, and only their
variables' names are ever reported.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import uuid4

from wayfarer.image import REFUSAL, Images
from wayfarer.models import EnvironmentFailure, GateCheck, GateStatus
from wayfarer.settings import Settings

__all__ = [
    "API_KEY",
    "OAUTH_TOKEN",
    "SESSION_GH_TOKEN",
    "StartGate",
]

# The two kinds of credential Claude Code accepts. The API key wins when both
# are set, as it does for the CLI itself.
API_KEY = "ANTHROPIC_API_KEY"
OAUTH_TOKEN = "CLAUDE_CODE_OAUTH_TOKEN"

# The fine-grained token (issues read, contents read) a session's `gh` reads its
# ticket with. Its own name, so it is never mistaken for the person's GH_TOKEN,
# which Wayfarer writes to GitHub with.
SESSION_GH_TOKEN = "WAYFARER_SESSION_GH_TOKEN"


class StartGate:
    """The six checks for one clone, and the one item they raise when they fail."""

    def __init__(self, repo: Path, images: Images, settings: Settings) -> None:
        self._repo = repo
        self._images = images
        self._settings = settings
        self.raised: EnvironmentFailure | None = None

    async def check(self) -> list[GateCheck]:
        """All six checks, run afresh, in order. A failure never skips a later check."""
        docker = await _daemon_answers(self._settings.docker_timeout)
        built, probed = await self._image(docker.passed)
        return [docker, built, probed, _credential(), await self._identity(), _session_token()]

    async def status(self) -> GateStatus:
        """The six checks, run now. Looking raises nothing; only a refused start does."""
        checks = await self.check()
        return GateStatus(
            checks=checks, passed=all(check.passed for check in checks), raised=self.raised
        )

    async def admit(self) -> EnvironmentFailure | None:
        """Whether a session may start now: None when it may, or the one item raised."""
        failed = [check for check in await self.check() if not check.passed]
        if not failed:
            self.raised = None
            return None
        # One item however many starts it refused: a refusal while one is raised
        # updates that item rather than adding another.
        self.raised = EnvironmentFailure(
            kind="environment",
            id=self.raised.id if self.raised else uuid4().hex,
            reason=_reason(failed),
            failed=failed,
        )
        return self.raised

    async def _image(self, docker_up: bool) -> tuple[GateCheck, GateCheck]:
        built, probed = "the session image is built", "the session image passed its probe"
        current = self._images.current()
        if current is None:
            nothing = "There is no image to probe, because none can be built for this repo."
            return (
                GateCheck(name=built, passed=False, detail=REFUSAL),
                GateCheck(name=probed, passed=False, detail=nothing),
            )
        if not docker_up:
            unseen = f"Docker is not running, so {current} cannot be looked for."
            return (
                GateCheck(name=built, passed=False, detail=unseen),
                GateCheck(name=probed, passed=False, detail=unseen),
            )
        if (await self._images.status()).ready:
            # A tag is only ever given to an image that passed (ADR-0005, and see
            # wayfarer.image), so its existing is the proof.
            return (
                GateCheck(name=built, passed=True, detail=f"{current} exists."),
                GateCheck(
                    name=probed,
                    passed=True,
                    detail=f"{current} is only tagged once it has passed its probe.",
                ),
            )
        return (
            GateCheck(
                name=built,
                passed=False,
                detail=f"No image is tagged {current}, which is the tag the current layer "
                "builds. Build the session image to make one.",
            ),
            GateCheck(name=probed, passed=False, detail=self._unprobed(current)),
        )

    def _unprobed(self, tag: str) -> str:
        build = self._images.last_build
        outcome = build.outcome if build is not None and build.tag == tag else None
        if outcome is not None and outcome.error is None:
            failing = ", ".join(check.name for check in outcome.checks if not check.passed)
            return f"{tag} was built but failed its probe: {failing}."
        # Nothing is stored about a failed probe, so after a restart this cannot
        # tell a failed image from an unbuilt one; it says only what is certain.
        return f"No image tagged {tag} has passed its probe. Build the session image to probe it."

    async def _identity(self) -> GateCheck:
        name = await _git_config(self._repo, "user.name")
        email = await _git_config(self._repo, "user.email")
        if name and email:
            return GateCheck(
                name="the clone has a git identity",
                passed=True,
                detail=f"Commits will be made as {name} <{email}>.",
            )
        missing = [key for key, value in (("user.name", name), ("user.email", email)) if not value]
        commands = " and ".join(f"git config {key}" for key in missing)
        return GateCheck(
            name="the clone has a git identity",
            passed=False,
            detail=f"Git has no {' or '.join(missing)} for this clone, and a session's commits "
            f"need both. Set them with {commands} in the clone.",
        )


async def _daemon_answers(timeout: float) -> GateCheck:
    name = "Docker is running"
    try:
        process = await asyncio.create_subprocess_exec(
            "docker",
            "info",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as error:
        return GateCheck(name=name, passed=False, detail=f"Docker could not be run: {error}.")
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        return GateCheck(
            name=name,
            passed=False,
            detail=f"The Docker daemon did not answer within {timeout:g} seconds.",
        )
    if process.returncode != 0:
        said = stderr.decode(errors="replace").strip().splitlines()
        return GateCheck(
            name=name,
            passed=False,
            detail="The Docker daemon did not answer"
            + (f": {said[-1]}" if said else ".")
            + " Start Docker; the gate checks again before every start.",
        )
    return GateCheck(name=name, passed=True, detail="The Docker daemon answered.")


def _credential() -> GateCheck:
    name = "an agent credential is set"
    present = [variable for variable in (API_KEY, OAUTH_TOKEN) if os.environ.get(variable)]
    if not present:
        return GateCheck(
            name=name,
            passed=False,
            detail=f"Neither {API_KEY} nor {OAUTH_TOKEN} is set in the environment Wayfarer "
            "was started from. Set one there and start Wayfarer again; it never asks for one "
            "and never stores one.",
        )
    detail = f"{present[0]} is set, and sessions will use it."
    if len(present) > 1:
        detail += f" It wins over {present[1]}, which is also set."
    return GateCheck(name=name, passed=True, detail=detail)


def _session_token() -> GateCheck:
    name = "a read-only GitHub token is set"
    if os.environ.get(SESSION_GH_TOKEN):
        return GateCheck(
            name=name, passed=True, detail=f"{SESSION_GH_TOKEN} is set for sessions to read with."
        )
    return GateCheck(
        name=name,
        passed=False,
        detail=f"{SESSION_GH_TOKEN} is not set in the environment Wayfarer was started from. "
        "A session reads its own ticket with it, so it should be a fine-grained token that can "
        "only read this repo's issues and contents. Set it there and start Wayfarer again.",
    )


async def _git_config(repo: Path, key: str) -> str:
    process = await asyncio.create_subprocess_exec(
        "git",
        "config",
        "--get",
        key,
        cwd=repo,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await process.communicate()
    return stdout.decode(errors="replace").strip()


def _reason(failed: list[GateCheck]) -> str:
    names = " and ".join(check.name for check in failed)
    details = " ".join(check.detail for check in failed)
    return f"No session will start until {names}. {details}"
