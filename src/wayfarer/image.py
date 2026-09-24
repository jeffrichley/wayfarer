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
import shlex
import shutil
import tempfile
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any
from uuid import uuid4

from wayfarer.beats import reported_run
from wayfarer.models import BuildFinished, BuildOutput, ImageStatus, ProbeCheck
from wayfarer.stream import Store

__all__ = ["BASE", "LAYER", "REFUSAL", "Build", "Images", "Recipe", "tag"]

LAYER = ".wayfarer/Dockerfile"

REFUSAL = (
    "This repo has no layer of its own, so Wayfarer will not build it an image. "
    f"Commit a Dockerfile at {LAYER} that starts FROM wayfarer-base and installs the "
    "toolchain the repo's tests need. Sessions never fall back to the bare base, or "
    "every red test would look like the agent's fault."
)

# How long the probe's one container may take. It runs five quick commands, so
# this only bounds an image whose entrypoint or shell hangs.
PROBE_TIMEOUT_SECONDS = 120.0

_PLUGIN = "mattpocock-skills@mattpocock"

# Printed between the probe's answers, so one container answers all five.
_MARK = "@@wayfarer-probe@@"

# Asking by ending, end to end but for the model (#42): the hook the settings name
# for `AskUserQuestion` defers a question and writes it down, then answers it once
# an answer is carried in; and the permission prompt tool a session is named
# answers MCP's listing with `ask`. Printed as one JSON object of what held.
_ASK_PROBE = """\
import json, os, pathlib, shutil, subprocess, tempfile
said = {}
settings = json.loads((pathlib.Path.home() / ".claude/settings.json").read_text())
hooks = [
    hook["command"]
    for matcher in settings.get("hooks", {}).get("PreToolUse", [])
    if matcher.get("matcher") == "AskUserQuestion"
    for hook in matcher.get("hooks", [])
]
said["hooked"] = bool(hooks)
home = pathlib.Path(tempfile.mkdtemp())
call = json.dumps({"tool_input": {"questions": [{"question": "Which?", "options": []}]}})
def decide():
    # Through a shell, as Claude Code runs a hook's command.
    run = subprocess.run(hooks[0], shell=True, input=call, capture_output=True, text=True,
                         env={**os.environ, "HOME": str(home)})
    return json.loads(run.stdout or "{}").get("hookSpecificOutput", {})
if hooks:
    deferred = decide()
    kept = home / ".wayfarer" / "question.json"
    said["defers"] = deferred.get("permissionDecision") == "defer" and kept.is_file()
    (home / ".wayfarer" / "answer.json").write_text(json.dumps({"Which?": "That one"}))
    allowed = decide()
    said["answers"] = allowed.get("permissionDecision") == "allow" and allowed.get(
        "updatedInput", {}).get("answers") == {"Which?": "That one"}
tool = shutil.which("wf-ask-tool")
if tool:
    asked = "\\n".join(json.dumps(m) for m in [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ])
    replies = subprocess.run([tool], input=asked, capture_output=True, text=True).stdout
    listed = [json.loads(line) for line in replies.splitlines() if line.strip()]
    said["tool"] = any(
        t.get("name") == "ask" for m in listed for t in m.get("result", {}).get("tools", [])
    )
print(json.dumps(said))
"""
_PROBE_SCRIPT = f"""\
claude --version 2>&1
echo {_MARK}
claude plugin list --json 2>&1
echo {_MARK}
wf-test true 2>&1
echo {_MARK}
id -u
stat -c %u /workspace 2>&1
echo {_MARK}
python3 -c {shlex.quote(_ASK_PROBE)} 2>&1
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
    """One build of one tag, whose output and ending reach the stream as they happen."""

    def __init__(self, tag: str, store: Store) -> None:
        self.tag = tag
        self._store = store
        self._lines = 0
        self.outcome: BuildFinished | None = None
        """How it finished; None while it is still running."""

    @property
    def finished(self) -> bool:
        return self.outcome is not None

    def output(self, line: str) -> None:
        self._store.upsert(
            BuildOutput(
                kind="build_output",
                id=f"build_output:{self._lines}",
                number=self._lines,
                line=line,
            )
        )
        self._lines += 1

    def finish(self, finished: BuildFinished) -> None:
        self._store.upsert(finished)
        self.outcome = finished

    def clear(self) -> None:
        """Take its output and ending off the stream, as a new build replaces it."""
        for number in range(self._lines):
            self._store.remove(f"build_output:{number}")
        self._store.remove("build_finished")


class Images:
    """One repo's session image: what it would be, and the build a person last asked for."""

    def __init__(self, repo: Path, store: Store, recipe: Recipe = BASE) -> None:
        self._layer = (repo / LAYER).parent
        self._store = store
        self._recipe = recipe
        self.last_build: Build | None = None

    @property
    def building(self) -> bool:
        return self.last_build is not None and not self.last_build.finished

    async def read(self) -> None:
        """Read what the image would be now, from the layer on disk and Docker's tags."""
        self._store.upsert(await self.status())

    def current(self) -> str | None:
        """The tag an image of the current inputs has, without asking Docker; None if refused."""
        return tag(self._layer, self._recipe) if _has_layer(self._layer) else None

    async def status(self) -> ImageStatus:
        current = self.current()
        if current is None:
            return ImageStatus(
                kind="image",
                id="image",
                layer=LAYER,
                refusal=REFUSAL,
                tag=None,
                ready=False,
                building=self.building,
            )
        return ImageStatus(
            kind="image",
            id="image",
            layer=LAYER,
            refusal=None,
            tag=current,
            ready=await _exists(current),
            building=self.building,
        )

    def build(self) -> Coroutine[None, None, None]:
        """Take the layer as it is at the click, and return the work of building it.

        Builds happen only when a person asks: nothing else calls this. A click while
        a build runs joins it. A repo with no layer is refused, which the page reads
        in the image's status, so a refused click is only a fresh read of it.
        """
        if not _has_layer(self._layer) or self.building:
            return self.read()
        # Hashed and built from one copy taken now, before the click is answered,
        # so editing the layer while it builds cannot tag an image under a hash of
        # other inputs.
        snapshot = Path(tempfile.mkdtemp(prefix="wayfarer-layer-"))
        shutil.copytree(self._layer, snapshot, dirs_exist_ok=True)
        if self.last_build is not None:
            self.last_build.clear()
        build = Build(tag(snapshot, self._recipe), self._store)
        self.last_build = build
        return self._build(build, snapshot)

    async def _build(self, build: Build, layer: Path) -> None:
        await self.read()
        try:
            finished = await _build_and_probe(build, layer, self._recipe)
        except OSError as error:
            finished = _failed(build, f"Docker could not be run: {error}")
        finally:
            shutil.rmtree(layer, ignore_errors=True)
        build.finish(finished)
        await self.read()


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
    return BuildFinished(
        kind="build_finished",
        id="build_finished",
        tag=build.tag,
        ready=ready,
        error=None,
        checks=checks,
    )


def _failed(build: Build, error: str) -> BuildFinished:
    return BuildFinished(
        kind="build_finished",
        id="build_finished",
        tag=build.tag,
        ready=False,
        error=error,
        checks=[],
    )


async def _stream(build: Build, *args: str) -> int:
    """Run `docker args`, passing each line of its output to the build as it comes."""
    process = await asyncio.create_subprocess_exec(
        "docker", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    assert process.stdout is not None
    try:
        async for raw in process.stdout:
            build.output(raw.decode(errors="replace").rstrip("\r\n"))
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
    answers = [*output.split(f"{_MARK}\n"), "", "", "", "", ""][:5]
    judges: list[Callable[[str, Recipe], ProbeCheck]] = [_cli, _plugin, _wf_test, _owner, _asks]
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
    # Read as a session's run is read, so an image whose wf-test is on the path but
    # cannot run, or cannot say so, fails here and not in every session after.
    run = reported_run(answer)
    return ProbeCheck(
        name="wf-test runs and reports",
        passed=run is not None and run.exit == 0,
        detail=f"wf-test true said {answer or 'nothing'!r}",
    )


def _owner(answer: str, recipe: Recipe) -> ProbeCheck:
    user, owner = [*answer.split(), "?", "?"][:2]
    return ProbeCheck(
        name="a non-root user owns the workspace",
        passed=user not in ("0", "?") and user == owner,
        detail=f"sessions run as uid {user}; /workspace is owned by uid {owner}",
    )


# What each part of asking the probe tried, in words for the person when it failed.
_ASKING = {
    "hooked": "the settings name a hook for AskUserQuestion",
    "defers": "the hook defers a question and writes it down",
    "answers": "the hook answers a question once its answer is carried in",
    "tool": "wf-ask-tool lists its ask tool",
}


def _asks(answer: str, recipe: Recipe) -> ProbeCheck:
    # A session that cannot ask guesses instead, and nothing it reports says so.
    try:
        said = json.loads(answer.splitlines()[-1]) if answer else {}
    except ValueError:
        said = {}
    failed = [words for part, words in _ASKING.items() if said.get(part) is not True]
    return ProbeCheck(
        name="a session can ask by ending",
        passed=not failed,
        detail="; ".join(f"not so: {words}" for words in failed)
        or "the hook defers and answers, and the prompt tool answers",
    )
