"""Running the app: one command inside a clone serves a page and opens the browser."""

from __future__ import annotations

import socket
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

from conftest import Launcher, get

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


def test_it_serves_on_the_port_its_setting_names(wayfarer: Launcher) -> None:
    port = _free_port()

    url = wayfarer.start(env={"WAYFARER_PORT": str(port)}).url()

    assert urlsplit(url).port == port
    assert get(url).status_code == 200


def test_when_its_port_is_taken_it_serves_on_another(wayfarer: Launcher) -> None:
    # A port the OS gave this test alone, so no other suite can be holding it.
    with socket.socket() as squatter:
        squatter.bind(("127.0.0.1", 0))
        squatter.listen()
        taken = squatter.getsockname()[1]

        url = wayfarer.start(env={"WAYFARER_PORT": str(taken)}).url()

        assert urlsplit(url).port != taken
        assert get(url).status_code == 200


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
    return port


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
