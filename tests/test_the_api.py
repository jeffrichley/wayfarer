"""The JSON API lives under `/api`; every other path is the page."""

from __future__ import annotations

from importlib.metadata import version

from conftest import Launcher, get


def test_health_names_the_running_version(wayfarer: Launcher) -> None:
    url = wayfarer.start().url()

    health = get(f"{url}api/health")

    assert health.status_code == 200
    assert health.json() == {"version": version("wayfarer")}


def test_an_unknown_api_path_is_not_found_rather_than_the_page(wayfarer: Launcher) -> None:
    url = wayfarer.start().url()

    assert get(f"{url}api/no-such-thing").status_code == 404


def test_any_other_path_is_the_page_so_the_app_can_route_itself(wayfarer: Launcher) -> None:
    url = wayfarer.start().url()

    page = get(f"{url}efforts/27/graph")

    assert page.status_code == 200
    assert '<div id="root">' in page.text
