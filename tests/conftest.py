"""Drive Wayfarer the way a person does: run the console script inside a clone.

`BROWSER` is the standard `webbrowser` override; pointing it at a recorder is how
a test sees the browser being opened without opening one.

Every Wayfarer a test starts talks to the GitHub stand-in (`github_stand_in.py`),
never to GitHub: its API address and token are set in the environment it is
launched from, as a person's would be.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Generator, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
from playwright.sync_api import Browser, sync_playwright
from playwright.sync_api import Error as PlaywrightError

from github_stand_in import TOKEN, GitHub

# The names a GitHub token may be set under; a person's real one never reaches a test.
_GITHUB_TOKENS = ("GH_TOKEN", "GITHUB_TOKEN")

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

    def __init__(self, cwd: Path, scratch: Path, github: GitHub) -> None:
        self.cwd = cwd
        self._scratch = scratch
        self._github = github
        self._recorder = scratch / "recorder.py"
        self._recorder.write_text(_RECORDER)
        self._instances: list[Instance] = []

    def start(self, *args: str, env: Mapping[str, str | None] | None = None) -> Instance:
        """Run `wayfarer`; `env` overrides the environment, and `None` unsets a name."""
        opened = self._scratch / f"opened-{len(self._instances)}.txt"
        environment = {
            name: value for name, value in os.environ.items() if name not in _GITHUB_TOKENS
        }
        environment |= {
            "BROWSER": f"{sys.executable} {self._recorder} {opened} %s",
            "PYTHONUNBUFFERED": "1",
            "WAYFARER_GITHUB_API": self._github.api,
            # Whatever port the OS has free, so no test contends with another
            # suite on the machine for the default one.
            "WAYFARER_PORT": "0",
            "GH_TOKEN": TOKEN,
        }
        for name, value in (env or {}).items():
            if value is None:
                environment.pop(name, None)
            else:
                environment[name] = value
        process = subprocess.Popen(
            [_console_script(), *args],
            cwd=self.cwd,
            env=environment,
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
def github() -> Iterator[GitHub]:
    """The repo the clone was cloned from, on the GitHub stand-in."""
    stand_in = GitHub("octo", "widgets")
    stand_in.start()
    yield stand_in
    stand_in.stop()


@pytest.fixture
def wayfarer(clone: Path, tmp_path: Path, github: GitHub) -> Iterator[Launcher]:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    launcher = Launcher(clone, scratch, github)
    yield launcher
    launcher.close()


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    """Chromium, as the person's browser; the browser tier skips, saying why, without it."""
    with sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch()
        except PlaywrightError as error:
            pytest.skip(f"no Chromium for Playwright; `just browser` installs it ({error.message})")
        yield chromium
        chromium.close()


def commit_layer(clone: Path, dockerfile: str) -> None:
    """Give the repo its own layer of the session image."""
    layer = clone / ".wayfarer"
    layer.mkdir(exist_ok=True)
    (layer / "Dockerfile").write_text(dockerfile)


def build_layer(url: str, clone: Path, dockerfile: str) -> tuple[list[str], dict[str, Any]]:
    """Commit `dockerfile` as the layer, click Build, and read the stream to its end."""
    commit_layer(clone, dockerfile)

    assert post(f"{url}api/image/build").status_code == 202
    output: list[str] = []
    for kind, event in events(f"{url}api/image/build"):
        if kind == "output":
            output.append(event["line"])
        else:
            return output, event
    pytest.fail("the build stream ended without saying how the build finished")


@pytest.fixture
def built_tags() -> Iterator[list[str]]:
    """Tags a test built, removed afterwards so runs do not pile images up."""
    tags: list[str] = []
    yield tags
    for built in tags:
        subprocess.run(["docker", "image", "rm", built], capture_output=True)


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


def stream(url: str, timeout: float = 10.0) -> Generator[Any]:
    """Each server-sent event's payload at `url`, read while the stream stays open.

    Close the iterator to hang up, as a page does when it goes away.
    """
    with httpx.stream("GET", url, timeout=timeout) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line.startswith("data:"):
                yield json.loads(line.removeprefix("data:"))


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
