"""The session image, and the probe that proves it (ADR-0005).

A session runs in an image of two parts: `wayfarer-base`, built from the recipe
in `wayfarer/base/`, and the repo's own layer, a Dockerfile committed at
`.wayfarer/Dockerfile` that starts `FROM wayfarer-base` and adds the repo's
toolchain. The layer's build context is `.wayfarer/` alone, so the tag can hash
all of it without hashing the whole checkout.

The tag hashes the base recipe, the pins and the layer, so a stale image is a
missing tag rather than silent drift. And **a tag exists only once its image has
passed the probe**: the build leaves an untagged image, the probe runs against
its id, and only a pass names it. So the tag existing is the proof, it survives a
restart with nothing stored, and an image that failed has no name a session could
ask for.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import tempfile
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from functools import partial
from importlib.resources import files
from pathlib import Path
from typing import Any
from uuid import uuid4

from wayfarer.models import BuildEvent, BuildFinished, BuildOutput, ImageStatus, ProbeCheck

__all__ = ["BASE", "LAYER", "REFUSAL", "Build", "Images", "NoLayer", "Recipe", "tag"]

LAYER = ".wayfarer/Dockerfile"

REFUSAL = (
    "This repo has no layer of its own, so Wayfarer will not build it an image. "
    f"Commit a Dockerfile at {LAYER} that starts FROM wayfarer-base and installs the "
    "toolchain the repo's tests need. Sessions never fall back to the bare base, or "
    "every red test would look like the agent's fault."
)

# How long the probe's one container may take. It runs four quick commands, so
# this only bounds an image whose entrypoint or shell hangs.
PROBE_TIMEOUT_SECONDS = 120.0

_PLUGIN = "mattpocock-skills@mattpocock"

# Printed between the probe's answers, so one container answers all four.
_MARK = "@@wayfarer-probe@@"
_PROBE_SCRIPT = f"""\
claude --version 2>&1
echo {_MARK}
claude plugin list --json 2>&1
echo {_MARK}
command -v wf-test
echo {_MARK}
id -u
stat -c %u /workspace 2>&1
"""


@dataclass(frozen=True)
class Recipe:
    """Everything Wayfarer puts into the base. Pins move by deliberate edit, never "latest"."""

    files: Path
    cli_version: str
    skills_version: str
    skills_commit: str


BASE = Recipe(
    files=Path(str(files("wayfarer") / "base")),
    cli_version="2.1.280",
    # mattpocock/skills v1.2.3. The version is what the probe reads back from the
    # installed plugin; the commit is what the base checks out.
    skills_version="1.2.3",
    skills_commit="6acc160e4e0cd062dbbbd7a1b26ae92855edf07e",
)


class NoLayer(Exception):
    """The repo has committed no layer of its own."""

    def __init__(self) -> None:
        super().__init__(REFUSAL)


def tag(layer: Path, recipe: Recipe) -> str:
    """The tag an image built from `recipe` and the layer directory `layer` has."""
    digest = hashlib.sha256(_base_digest(recipe).encode())
    _feed_tree(digest, layer)
    return f"wayfarer-session:{digest.hexdigest()[:16]}"


def _base_tag(recipe: Recipe) -> str:
    return f"wayfarer-base:{_base_digest(recipe)[:16]}"


def _base_digest(recipe: Recipe) -> str:
    digest = hashlib.sha256()
    for pin in (recipe.cli_version, recipe.skills_version, recipe.skills_commit):
        _feed(digest, pin.encode())
    _feed_tree(digest, recipe.files)
    return digest.hexdigest()


def _feed_tree(digest: Any, root: Path) -> None:
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        _feed(digest, path.relative_to(root).as_posix().encode())
        _feed(digest, path.read_bytes())


def _feed(digest: Any, part: bytes) -> None:
    # Length-prefixed, so no two different sequences of parts hash the same.
    digest.update(len(part).to_bytes(8, "big"))
    digest.update(part)


class Build:
    """One build of one tag: its output so far, and how it finished."""

    def __init__(self, tag: str) -> None:
        self.tag = tag
        self._events: list[BuildOutput | BuildFinished] = []
        self._changed = asyncio.Condition()

    @property
    def finished(self) -> bool:
        return self.outcome is not None

    @property
    def outcome(self) -> BuildFinished | None:
        """How it finished; None while it is still running."""
        last = self._events[-1] if self._events else None
        return last if isinstance(last, BuildFinished) else None

    async def output(self, line: str) -> None:
        await self._emit(BuildOutput(kind="output", line=line))

    async def finish(self, finished: BuildFinished) -> None:
        await self._emit(finished)

    async def events(self) -> AsyncIterator[BuildEvent]:
        """Everything so far, then each event as it happens, ending with how it finished."""
        seen = 0
        while True:
            async with self._changed:
                await self._changed.wait_for(partial(self._beyond, seen))
                fresh = self._events[seen:]
            seen += len(fresh)
            for event in fresh:
                yield event
                if isinstance(event, BuildFinished):
                    return

    def _beyond(self, seen: int) -> bool:
        return len(self._events) > seen

    async def _emit(self, event: BuildOutput | BuildFinished) -> None:
        async with self._changed:
            self._events.append(event)
            self._changed.notify_all()


class Images:
    """One repo's session image: what it would be, and the build a person last asked for."""

    def __init__(self, repo: Path, recipe: Recipe = BASE) -> None:
        self._layer = (repo / LAYER).parent
        self._recipe = recipe
        self.last_build: Build | None = None
        self._running: asyncio.Task[None] | None = None

    @property
    def building(self) -> bool:
        return self.last_build is not None and not self.last_build.finished

    def current(self) -> str | None:
        """The tag an image of the current inputs has, without asking Docker; None if refused."""
        return tag(self._layer, self._recipe) if _has_layer(self._layer) else None

    async def status(self) -> ImageStatus:
        current = self.current()
        if current is None:
            return ImageStatus(
                layer=LAYER, refusal=REFUSAL, tag=None, ready=False, building=self.building
            )
        return ImageStatus(
            layer=LAYER,
            refusal=None,
            tag=current,
            ready=await _exists(current),
            building=self.building,
        )

    def build(self) -> None:
        """Start a build of the current inputs, unless one is already running.

        Builds happen only when a person asks: nothing else calls this.
        """
        if not _has_layer(self._layer):
            raise NoLayer
        if self.building:
            return
        # Hashed and built from one copy taken now, so editing the layer while it
        # builds cannot tag an image under a hash of other inputs.
        snapshot = Path(tempfile.mkdtemp(prefix="wayfarer-layer-"))
        shutil.copytree(self._layer, snapshot, dirs_exist_ok=True)
        build = Build(tag(snapshot, self._recipe))
        self.last_build = build
        self._running = asyncio.create_task(self._build(build, snapshot))

    async def _build(self, build: Build, layer: Path) -> None:
        try:
            finished = await _build_and_probe(build, layer, self._recipe)
        except OSError as error:
            finished = _failed(build, f"Docker could not be run: {error}")
        finally:
            shutil.rmtree(layer, ignore_errors=True)
        await build.finish(finished)


def _has_layer(layer: Path) -> bool:
    return (layer / "Dockerfile").is_file()


async def _build_and_probe(build: Build, layer: Path, recipe: Recipe) -> BuildFinished:
    base = _base_tag(recipe)
    # No timeout on a build: it streams every line to the person who asked for
    # it, and how long a toolchain takes to install is the repo's business.
    built = await _stream(
        build,
        "build",
        "--progress=plain",
        "--tag",
        base,
        "--build-arg",
        f"CLAUDE_CODE_VERSION={recipe.cli_version}",
        "--build-arg",
        f"SKILLS_COMMIT={recipe.skills_commit}",
        str(recipe.files),
    )
    if built != 0:
        return _failed(build, "Wayfarer's base did not build; the output above says why.")

    with tempfile.TemporaryDirectory() as scratch:
        iidfile = Path(scratch) / "iid"
        built = await _stream(
            build,
            "build",
            "--progress=plain",
            # The layer says `FROM wayfarer-base`; this points that name at the
            # base these pins built, rather than at whatever was built last.
            "--build-context",
            f"wayfarer-base=docker-image://{base}",
            "--iidfile",
            str(iidfile),
            str(layer),
        )
        if built != 0:
            return _failed(
                build, f"The repo's layer ({LAYER}) did not build; the output above says why."
            )
        image = iidfile.read_text().strip()

    checks = await _probe(image, recipe)
    ready = all(check.passed for check in checks)
    if ready:
        await _docker("tag", image, build.tag)
    return BuildFinished(kind="finished", tag=build.tag, ready=ready, error=None, checks=checks)


def _failed(build: Build, error: str) -> BuildFinished:
    return BuildFinished(kind="finished", tag=build.tag, ready=False, error=error, checks=[])


async def _stream(build: Build, *args: str) -> int:
    """Run `docker args`, passing each line of its output to the build as it comes."""
    process = await asyncio.create_subprocess_exec(
        "docker", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    assert process.stdout is not None
    try:
        async for raw in process.stdout:
            await build.output(raw.decode(errors="replace").rstrip("\r\n"))
        return await process.wait()
    finally:
        # Wayfarer stopping mid-build cancels this; the build must not outlive it.
        if process.returncode is None:
            process.kill()
            await process.wait()


async def _docker(*args: str) -> int:
    process = await asyncio.create_subprocess_exec(
        "docker",
        *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    return await process.wait()


async def _exists(image: str) -> bool:
    try:
        return await _docker("image", "inspect", image) == 0
    except OSError:
        return False


async def _probe(image: str, recipe: Recipe) -> list[ProbeCheck]:
    """Run the image once, as a session would, and judge what it says about itself."""
    name = f"wayfarer-probe-{uuid4().hex[:12]}"
    process = await asyncio.create_subprocess_exec(
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        # A session gets nothing from the network it did not bake in, so neither
        # does the probe.
        "--network=none",
        "--entrypoint",
        "sh",
        image,
        "-c",
        _PROBE_SCRIPT,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), PROBE_TIMEOUT_SECONDS)
    except TimeoutError:
        await _docker("rm", "--force", name)
        output = b""
    return _judge(output.decode(errors="replace"), recipe)


def _judge(output: str, recipe: Recipe) -> list[ProbeCheck]:
    answers = [*output.split(f"{_MARK}\n"), "", "", "", ""][:4]
    judges: list[Callable[[str, Recipe], ProbeCheck]] = [_cli, _plugin, _wf_test, _owner]
    return [judge(answer.strip(), recipe) for judge, answer in zip(judges, answers, strict=True)]


def _cli(answer: str, recipe: Recipe) -> ProbeCheck:
    found = answer.split()[0] if answer else ""
    return ProbeCheck(
        name="Claude Code at its pin",
        passed=found == recipe.cli_version,
        detail=f"claude --version said {answer or 'nothing'!r}; the pin is {recipe.cli_version}",
    )


def _plugin(answer: str, recipe: Recipe) -> ProbeCheck:
    try:
        listed = json.loads(answer)
    except ValueError:
        listed = []
    installed = [p for p in listed if isinstance(p, dict) and p.get("id") == _PLUGIN]
    versions = [str(p.get("version")) for p in installed if p.get("enabled")]
    return ProbeCheck(
        name="mattpocock-skills at its pin",
        passed=recipe.skills_version in versions,
        detail=(
            f"{_PLUGIN} is enabled at {', '.join(versions)}"
            if versions
            else f"{_PLUGIN} is not installed and enabled"
        )
        + f"; the pin is {recipe.skills_version}",
    )


def _wf_test(answer: str, recipe: Recipe) -> ProbeCheck:
    return ProbeCheck(
        name="wf-test on the path",
        passed=bool(answer),
        detail=f"found at {answer}" if answer else "wf-test is not on the path",
    )


def _owner(answer: str, recipe: Recipe) -> ProbeCheck:
    user, owner = [*answer.split(), "?", "?"][:2]
    return ProbeCheck(
        name="a non-root user owns the workspace",
        passed=user not in ("0", "?") and user == owner,
        detail=f"sessions run as uid {user}; /workspace is owned by uid {owner}",
    )
