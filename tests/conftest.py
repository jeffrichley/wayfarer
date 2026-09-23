"""Drive Wayfarer the way a person does: run the console script inside a clone.

`BROWSER` is the standard `webbrowser` override; pointing it at a recorder is how
a test sees the browser being opened without opening one.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest

# The port Wayfarer tries first; the Vite dev server proxies the API to it.
DEFAULT_PORT = 7431

_RECORDER = """\
import pathlib, sys
pathlib.Path(sys.argv[1]).write_text(sys.argv[2])
"""


def _console_script() -> str:
    script = shutil.which("wayfarer", path=str(Path(sys.executable).parent))
    assert script is not None, "the wayfarer console script is not installed in this venv"
    return script


@dataclass
class Instance:
    """One running `wayfarer` process, and what it opened in the browser."""

    process: subprocess.Popen[str]
    opened: Path
    _output: str | None = field(default=None)

    def url(self, timeout: float = 20.0) -> str:
        """The URL it opened in the browser, waiting for it to do so."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.opened.exists() and self.opened.read_text():
                return self.opened.read_text()
            if self.process.poll() is not None:
                pytest.fail(f"wayfarer exited before opening a browser:\n{self.output()}")
            time.sleep(0.05)
        pytest.fail("wayfarer never opened a browser")

    def interrupt(self) -> int:
        """Press Ctrl-C and wait for it to exit."""
        self.process.send_signal(signal.SIGINT)
        return self.process.wait(timeout=15)

    def output(self) -> str:
        if self._output is None:
            if self.process.poll() is None:
                self.process.kill()
            stdout, _ = self.process.communicate(timeout=15)
            self._output = stdout
        return self._output


class Launcher:
    """Starts `wayfarer` processes in one directory, and cleans up after them."""

    def __init__(self, cwd: Path, scratch: Path) -> None:
        self.cwd = cwd
        self._scratch = scratch
        self._recorder = scratch / "recorder.py"
        self._recorder.write_text(_RECORDER)
        self._instances: list[Instance] = []

    def start(self, *args: str) -> Instance:
        opened = self._scratch / f"opened-{len(self._instances)}.txt"
        env = {
            **os.environ,
            "BROWSER": f"{sys.executable} {self._recorder} {opened} %s",
            "PYTHONUNBUFFERED": "1",
        }
        process = subprocess.Popen(
            [_console_script(), *args],
            cwd=self.cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        instance = Instance(process, opened)
        self._instances.append(instance)
        return instance

    def close(self) -> None:
        # Ctrl-C, as a person stops it, so the process exits cleanly and coverage
        # gets to record what it ran; a kill only if that fails.
        for instance in self._instances:
            if instance.process.poll() is None:
                try:
                    instance.interrupt()
                except subprocess.TimeoutExpired:
                    instance.process.kill()
                    instance.process.wait(timeout=15)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    """A local clone of a repo on GitHub, as a person would have one."""
    repo = tmp_path / "clone"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    _git(repo, "remote", "add", "origin", "https://github.com/octo/widgets.git")
    return repo


@pytest.fixture
def wayfarer(clone: Path, tmp_path: Path) -> Iterator[Launcher]:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    launcher = Launcher(clone, scratch)
    yield launcher
    launcher.close()


def commit_layer(clone: Path, dockerfile: str) -> None:
    """Give the repo its own layer of the session image."""
    layer = clone / ".wayfarer"
    layer.mkdir(exist_ok=True)
    (layer / "Dockerfile").write_text(dockerfile)


def get(url: str) -> httpx.Response:
    return httpx.get(url, timeout=5.0)


def post(url: str) -> httpx.Response:
    return httpx.post(url, timeout=5.0)


def events(url: str, timeout: float = 900.0) -> Iterator[tuple[str, Any]]:
    """Each server-sent event at `url` as (kind, payload), until the server ends it.

    The timeout is per read, and generous because a stream may carry a whole
    image build, which pauses while Docker downloads.
    """
    with httpx.stream("GET", url, timeout=timeout) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line.startswith("data:"):
                payload = json.loads(line.removeprefix("data:"))
                yield payload["kind"], payload


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip the docker tier, saying why, where no daemon answers (GitHub's macOS runners)."""
    needing = [item for item in items if "docker" in item.keywords]
    if not needing or _docker_answers():
        return
    for item in needing:
        item.add_marker(pytest.mark.skip(reason="no reachable Docker daemon"))


def _docker_answers() -> bool:
    try:
        # Bounded so a wedged daemon skips the tier rather than hanging collection.
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
