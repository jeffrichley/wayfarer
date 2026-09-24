"""Drive Wayfarer the way a person does: run the console script inside a clone.

`BROWSER` is the standard `webbrowser` override; pointing it at a recorder is how
a test sees the browser being opened without opening one.

Every Wayfarer a test starts talks to the GitHub stand-in (`github_stand_in.py`),
never to GitHub: its API address and token are set in the environment it is
launched from, as a person's would be.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from playwright.sync_api import Browser, Page, sync_playwright
from playwright.sync_api import Error as PlaywrightError

from github_stand_in import TOKEN, GitHub, Issue
from specimens import GALLERY_CLOCK, VIEWPORT, reference_page
from wayfarer.merge_queue import LANDED_MARKER
from wayfarer.stream import Store

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

    def __init__(self, cwd: Path, scratch: Path, github: GitHub, *, docker: bool) -> None:
        """`docker` lets it reach the host's Docker, which only the docker tier does."""
        self.cwd = cwd
        self._scratch = scratch
        self._github = github
        self._docker = docker
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
            # Its store and sessions' files, kept out of the person's own.
            "WAYFARER_DATA_DIR": str(self._scratch / "data"),
        }
        if not self._docker:
            # The host's Docker is shared by every test and any Wayfarer the person
            # runs, and a restarted Wayfarer shows every sandbox container it finds
            # there, so outside the docker tier it finds no Docker at all.
            environment["DOCKER_HOST"] = f"unix://{self._scratch / 'no-docker.sock'}"
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


@contextmanager
def served(app: FastAPI, stream: Store) -> Iterator[str]:
    """Serve `app`, built in this process, until the block ends; its URL.

    Only for what the console script cannot be given: a session that runs outside
    Docker, which Wayfarer itself never offers (ADR-0005).
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    url = f"http://127.0.0.1:{sock.getsockname()[1]}/"
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
    loops: list[asyncio.AbstractEventLoop] = []

    def serve() -> None:
        # As `asyncio.run` does, down to cancelling what is left; its loop is held
        # here, so stopping can reach into it from this thread.
        with asyncio.Runner() as runner:
            loops.append(runner.get_loop())
            runner.run(server.serve(sockets=[sock]))

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not (server.started and loops):
        assert thread.is_alive() and time.monotonic() < deadline, "wayfarer never started"
        time.sleep(0.01)
    try:
        yield url
    finally:
        # As the console script stops: every page's stream ends, then the server.
        # The stream belongs to the server's loop, so it is closed there.
        [loop] = loops
        loop.call_soon_threadsafe(stream.close)
        server.should_exit = True
        thread.join(timeout=30)
        assert not thread.is_alive(), f"wayfarer never stopped, awaiting:\n{_awaiting(loop)}"


def _awaiting(loop: asyncio.AbstractEventLoop) -> str:
    """What each task on `loop` is waiting on, innermost last: why a stop hangs."""
    lines = []
    for task in asyncio.all_tasks(loop):
        lines.append(repr(task))
        awaited: Any = task.get_coro()
        while awaited is not None:
            frame = getattr(awaited, "cr_frame", None) or getattr(awaited, "ag_frame", None)
            where = f"{frame.f_code.co_filename}:{frame.f_lineno}" if frame else ""
            lines.append(f"    {type(awaited).__name__} {where}")
            awaited = getattr(awaited, "cr_await", None) or getattr(awaited, "ag_await", None)
    return "\n".join(lines)


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
def host_repo(tmp_path: Path) -> Path:
    """A clone with one commit and an identity, as a session's host repo."""
    repo = tmp_path / "host"
    repo.mkdir()
    _git(repo, "init", "--quiet", "--initial-branch=main")
    _git(repo, "config", "user.name", "Ada")
    _git(repo, "config", "user.email", "ada@example.com")
    (repo / "README.md").write_text("widgets\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "--quiet", "-m", "first")
    return repo


@pytest.fixture
def github() -> Iterator[GitHub]:
    """The repo the clone was cloned from, on the GitHub stand-in."""
    stand_in = GitHub("octo", "widgets")
    stand_in.start()
    yield stand_in
    stand_in.stop()


@pytest.fixture
def wayfarer(
    clone: Path, tmp_path: Path, github: GitHub, request: pytest.FixtureRequest
) -> Iterator[Launcher]:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    docker = request.node.get_closest_marker("docker") is not None
    launcher = Launcher(clone, scratch, github, docker=docker)
    yield launcher
    launcher.close()


# Per module, not per session: Playwright's sync API holds an event loop open on
# this thread while it runs, and `asyncio.run` in a later module refuses to start
# inside it.
@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    """Chromium, as the person's browser; the browser tier skips, saying why, without it."""
    with sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch()
        except PlaywrightError as error:
            pytest.skip(f"no Chromium for Playwright; `just browser` installs it ({error.message})")
        yield chromium
        chromium.close()


@pytest.fixture
def gallery(wayfarer: Launcher, browser: Browser) -> Iterator[Page]:
    """The app's /gallery: every primitive in every state on one page."""
    page = browser.new_page(viewport=VIEWPORT)
    page.clock.set_fixed_time(GALLERY_CLOCK)
    page.goto(wayfarer.start().url().rstrip("/") + "/gallery")
    page.wait_for_selector("[data-specimen]")
    yield page
    page.close()


@pytest.fixture
def reference(browser: Browser, tmp_path: Path) -> Iterator[Page]:
    """The same specimens as the frozen prototype draws them."""
    page = browser.new_page(viewport=VIEWPORT)
    page.goto(reference_page(tmp_path).as_uri())
    yield page
    page.close()


def commit_layer(clone: Path, dockerfile: str) -> None:
    """Give the repo its own layer of the session image."""
    layer = clone / ".wayfarer"
    layer.mkdir(exist_ok=True)
    (layer / "Dockerfile").write_text(dockerfile)


@pytest.fixture
def built_tags() -> Iterator[list[str]]:
    """Tags a test built, removed afterwards so runs do not pile images up."""
    tags: list[str] = []
    yield tags
    for built in tags:
        subprocess.run(["docker", "image", "rm", built], capture_output=True)


def get(url: str) -> httpx.Response:
    return httpx.get(url, timeout=5.0)


def post(url: str, json: Any = None) -> httpx.Response:
    return httpx.post(url, json=json, timeout=5.0)


Items = dict[str, dict[str, Any]]

# The kinds of item derived from the rest: home (`wayfarer.home`), the desk
# (`wayfarer.desk`), each effort's ticket graph (`wayfarer.graph`) and At work's
# lanes (`wayfarer.at_work`).
_DERIVED = {"desk", "home", "lane", "line_row", "needs_you", "ticket_graph"}


class Stream:
    """One page's stream, applied as the browser applies it: replaced by id, never merged.

    `timeout` is per read; a stream carrying an image build needs a generous one,
    because a build pauses while Docker downloads. `patience`, when given, bounds
    each wait in all, for a stream busy enough that no single read ever times out.

    Home's items, the ticket graphs and the lanes are derived from every other item
    and change along with them, so only a test about them, passing `derived`, sees
    them: every other test reads the stream as if they were not on it, their ids
    included.
    """

    def __init__(
        self,
        url: str,
        last_event_id: str | None = None,
        timeout: float = 20.0,
        patience: float | None = None,
        derived: bool = False,
    ) -> None:
        headers = {} if last_event_id is None else {"Last-Event-ID": last_event_id}
        self._opened = httpx.stream("GET", f"{url}api/events", headers=headers, timeout=timeout)
        response = self._opened.__enter__()
        response.raise_for_status()
        self._lines = response.iter_lines()
        self.items: Items = {}
        self.received: list[dict[str, Any]] = []
        self.ids: list[str] = []
        self._patience = patience
        self._derived = derived
        self._derived_ids: set[str] = set()

    def __enter__(self) -> Stream:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        """Drop the connection, as a closed tab or a lost network does."""
        self._opened.__exit__(None, None, None)

    @property
    def last_event_id(self) -> str:
        return self.ids[-1]

    def next(self, deadline: float | None = None) -> dict[str, Any]:
        """The next event, once it is applied; failing past `deadline` (monotonic).

        The deadline is checked on every line, keep-alive pings included, since a
        quiet stream pings often enough that no read ever times out.
        """
        event: dict[str, Any] | None = None
        id: str | None = None
        for line in self._lines:
            if deadline is not None and time.monotonic() > deadline:
                pytest.fail(f"the page never showed it; it holds {self.items}")
            if line.startswith("data:"):
                event = json.loads(line.removeprefix("data:"))
            elif line.startswith("id:"):
                id = line.removeprefix("id:").strip()
            elif not line and event is not None:
                if not self._derived and self._leave_out(event):
                    event = id = None
                    continue
                break
        else:
            pytest.fail("the stream ended")
        if id is not None:
            self.ids.append(id)
        if event["kind"] == "snapshot":
            self.items = {item["id"]: item for item in event["items"]}
        elif event["kind"] == "upsert":
            self.items[event["item"]["id"]] = event["item"]
        else:
            del self.items[event["id"]]
        self.received.append(event)
        return event

    def _leave_out(self, event: dict[str, Any]) -> bool:
        """Whether `event` is only a derived item's, leaving what a snapshot holds besides."""
        if event["kind"] == "snapshot":
            mine = [item for item in event["items"] if item["kind"] in _DERIVED]
            self._derived_ids |= {item["id"] for item in mine}
            event["items"] = [item for item in event["items"] if item["kind"] not in _DERIVED]
            return False
        if event["kind"] == "upsert" and event["item"]["kind"] in _DERIVED:
            self._derived_ids.add(event["item"]["id"])
            return True
        return event["kind"] == "removal" and event["id"] in self._derived_ids

    def until(self, arrived: Callable[[Items], bool]) -> list[dict[str, Any]]:
        """Read until `arrived` holds of what the page holds; the events that took."""
        start = len(self.received)
        deadline = None if self._patience is None else time.monotonic() + self._patience
        while not arrived(self.items):
            self.next(deadline)
        return self.received[start:]

    def item(self, id: str, **fields: Any) -> dict[str, Any]:
        """The item with `id`, once it has arrived with every one of `fields`."""
        self.until(lambda items: _has(items.get(id), fields))
        return self.items[id]


def _has(item: dict[str, Any] | None, fields: dict[str, Any]) -> bool:
    return item is not None and all(item.get(k) == v for k, v in fields.items())


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Run the docker tier on one worker, one test after another; and skip it, saying
    why, where no daemon answers (GitHub's macOS runners).

    The suite runs in parallel (`-n auto`, pyproject.toml), but every image build
    starts `FROM wayfarer-base`, and two layers alike share a tag, so builds side by
    side would race to build the base, and one's cleanup could remove another's tag.
    """
    needing = [item for item in items if "docker" in item.keywords]
    for item in needing:
        item.add_marker(pytest.mark.xdist_group("docker"))
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


# Per read of the stream: a build pauses while Docker downloads.
BUILD_TIMEOUT = 900.0


@dataclass
class Built:
    """What the page was told of one build, once the image says it is over."""

    output: list[str]
    finished: dict[str, Any]
    image: dict[str, Any]


def build_layer(url: str, clone: Path, dockerfile: str) -> Built:
    """Commit `dockerfile` as the layer, click Build, and watch the stream to its end."""
    commit_layer(clone, dockerfile)
    with Stream(url, timeout=BUILD_TIMEOUT) as page:
        assert post(f"{url}api/image/build").status_code == 202
        # Started, which clears any earlier build's output and ending from the page.
        page.item("image", building=True)
        finished = page.item("build_finished")
        image = page.item("image", building=False)
        return Built(build_output(page.items), finished, image)


def build_output(items: Items) -> list[str]:
    """The last build's output, in the order Docker printed it."""
    lines = [item for item in items.values() if item["kind"] == "build_output"]
    return [item["line"] for item in sorted(lines, key=lambda item: item["number"])]


# The effort branch a ticket's pull request targets, in tests that need no git.
EFFORT_BRANCH = "effort/1-widgets"


def quick(tmp_path: Path) -> dict[str, str]:
    """A Wayfarer's environment that reads a change on GitHub again within a test's patience."""
    return {"WAYFARER_DATA_DIR": str(tmp_path / "data"), "WAYFARER_POLL_ACTIVE": "0.2"}


def land(github: GitHub, ticket: Issue) -> None:
    """Closed with the marked comment, as Wayfarer closes a ticket that landed: back to
    back, so GitHub stamps both to the same second."""
    at = github.now
    github.comment(ticket, f"Landed on `{EFFORT_BRANCH}` at {'a' * 40}.\n\n{LANDED_MARKER}")
    github.now = at
    github.close(ticket)
