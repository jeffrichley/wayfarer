"""Running the app: one command inside a clone serves a page and opens the browser."""

from __future__ import annotations

import socket
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

from conftest import DEFAULT_PORT, Launcher, get

pytestmark = pytest.mark.git


def test_running_inside_a_clone_serves_a_page_on_localhost_and_opens_a_browser(
    wayfarer: Launcher,
) -> None:
    url = wayfarer.start().url()

    assert urlsplit(url).hostname == "127.0.0.1"
    page = get(url)
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert '<div id="root">' in page.text


def test_ctrl_c_stops_the_process_and_frees_its_port(wayfarer: Launcher) -> None:
    instance = wayfarer.start()
    url = instance.url()

    exit_code = instance.interrupt()

    assert exit_code == 0, instance.output()
    with pytest.raises(httpx.ConnectError):
        get(url)
    assert "Traceback" not in instance.output()


def test_ctrl_c_leaves_nothing_behind_in_the_clone(wayfarer: Launcher, clone: Path) -> None:
    before = _everything_in(clone)
    instance = wayfarer.start()
    instance.url()

    instance.interrupt()

    assert _everything_in(clone) == before


def test_outside_a_clone_it_refuses_and_says_why(wayfarer: Launcher, tmp_path: Path) -> None:
    wayfarer.cwd = tmp_path / "not-a-clone"
    wayfarer.cwd.mkdir()

    instance = wayfarer.start()

    assert instance.process.wait(timeout=15) != 0
    assert "not inside a git clone" in instance.output()


def test_when_the_default_port_is_taken_it_serves_on_another(wayfarer: Launcher) -> None:
    with socket.socket() as squatter:
        squatter.bind(("127.0.0.1", DEFAULT_PORT))
        squatter.listen()

        url = wayfarer.start().url()

        assert urlsplit(url).port != DEFAULT_PORT
        assert get(url).status_code == 200


def _everything_in(directory: Path) -> set[Path]:
    return set(directory.rglob("*"))


def test_a_second_instance_on_the_same_clone_refuses_and_says_why(wayfarer: Launcher) -> None:
    first = wayfarer.start()
    url = first.url()

    second = wayfarer.start()

    assert second.process.wait(timeout=15) != 0
    assert "already running for this clone" in second.output()
    assert url in second.output()
    assert get(url).status_code == 200


def test_a_second_instance_refuses_from_a_subdirectory_of_the_clone_too(
    wayfarer: Launcher, clone: Path
) -> None:
    wayfarer.start().url()
    (clone / "src").mkdir()
    wayfarer.cwd = clone / "src"

    second = wayfarer.start()

    assert second.process.wait(timeout=15) != 0
    assert "already running for this clone" in second.output()


def test_after_ctrl_c_the_clone_is_free_for_a_new_instance(wayfarer: Launcher) -> None:
    first = wayfarer.start()
    first.url()
    first.interrupt()

    second = wayfarer.start()

    assert get(second.url()).status_code == 200
