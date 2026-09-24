"""Restart, against the host's real Docker: the containers a crash left behind (#43).

Each container is made, never started, from an empty image of the test's own, and
carries Waystation's run-id label exactly as a session's sandbox does.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from conftest import Launcher, Stream, post, quick
from github_stand_in import LOGIN, GitHub
from wayfarer.github import Repo
from wayfarer.read_model import HELD
from wayfarer.store import Purpose, Store

pytestmark = [pytest.mark.git, pytest.mark.docker]


def _docker(*args: str, input: bytes | None = None) -> str:
    return subprocess.run(
        ["docker", *args], input=input, check=True, capture_output=True
    ).stdout.decode()


@pytest.fixture
def left_running() -> Iterator[dict[str, str]]:
    """Two sandbox containers, by run id: one of a session this clone's store has, and
    one no store here has heard of. Removed afterwards, whatever the test did."""
    image = f"wayfarer-test-empty:{uuid4().hex[:12]}"
    # An empty tar is an image with no files, which is all a container never started needs.
    _docker("import", "-", image, input=b"\0" * 1024)
    runs = {"orphan": f"run-{uuid4().hex[:12]}", "unknown": f"run-{uuid4().hex[:12]}"}
    containers = [
        _docker("create", "--label", f"waystation.run-id={run}", image, "/none").strip()
        for run in runs.values()
    ]
    yield runs
    subprocess.run(["docker", "rm", "--force", *containers], capture_output=True)
    subprocess.run(["docker", "image", "rm", image], capture_output=True)


def _containers(run_id: str) -> list[str]:
    labelled = f"label=waystation.run-id={run_id}"
    return _docker("ps", "--all", "--quiet", "--filter", labelled).split()


def test_reaping_an_orphan_removes_its_container_and_leaves_the_unknown_one_alone(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, left_running: dict[str, str]
) -> None:
    _, (ticket,) = github.effort("Widgets", tickets=1)
    ticket.assignees.append(LOGIN)
    orphan, unknown = left_running["orphan"], left_running["unknown"]
    with closing(Store.for_repo(tmp_path / "data", Repo("octo", "widgets"))) as store:
        events = store.event_file(orphan)
        events.touch()
        store.session_started(orphan, ticket.number, Purpose.BUILD, datetime.now(UTC), events)
    url = wayfarer.start(env=quick(tmp_path)).url()

    with Stream(url, patience=30) as page:
        page.item(f"orphan:{orphan}")
        page.item(f"container:{unknown}")
        assert post(f"{url}api/sessions/{orphan}/reap").status_code == 202
        page.until(lambda items: f"orphan:{orphan}" not in items)

    assert _containers(orphan) == []
    assert len(_containers(unknown)) == 1
    assert HELD in ticket.labels
