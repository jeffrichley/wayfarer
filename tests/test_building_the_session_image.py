"""Building a repo's session image on click, and the probe that proves it.

These build for real: the first one in a fresh Docker pays for the base (the CLI
download and the plugin clone), and every later one reuses Docker's cache.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from conftest import Launcher, commit_layer, events, get, post

pytestmark = pytest.mark.docker


@pytest.fixture
def built_tags() -> Iterator[list[str]]:
    """Tags a test built, removed afterwards so runs do not pile images up."""
    tags: list[str] = []
    yield tags
    for built in tags:
        subprocess.run(["docker", "image", "rm", built], capture_output=True)


def _build(url: str, clone: Path, dockerfile: str) -> tuple[list[str], dict[str, Any]]:
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


def _checks(finished: dict[str, Any]) -> dict[str, bool]:
    return {check["name"]: check["passed"] for check in finished["checks"]}


def _exists(tag: str) -> bool:
    return subprocess.run(["docker", "image", "inspect", tag], capture_output=True).returncode == 0


def test_a_repo_with_a_layer_gets_an_image_built_on_click_with_output_streamed(
    wayfarer: Launcher, clone: Path, built_tags: list[str]
) -> None:
    url = wayfarer.start().url()

    # Unique, so the step really runs and its own output, not a cache hit, streams.
    marker = uuid4().hex
    output, finished = _build(url, clone, f"FROM wayfarer-base\nRUN echo {marker} | rev\n")
    built_tags.append(finished["tag"])

    assert any(line.endswith(marker[::-1]) for line in output)
    assert finished["ready"] is True, output
    assert set(_checks(finished).values()) == {True}
    assert get(f"{url}api/image").json() == {
        "layer": ".wayfarer/Dockerfile",
        "refusal": None,
        "tag": finished["tag"],
        "ready": True,
        "building": False,
    }
    assert _exists(finished["tag"])


def test_a_new_tag_is_probed_for_the_cli_the_plugin_the_wrapper_and_a_non_root_owner(
    wayfarer: Launcher, clone: Path, built_tags: list[str]
) -> None:
    url = wayfarer.start().url()

    _, finished = _build(url, clone, "FROM wayfarer-base\nRUN echo probe-me\n")
    built_tags.append(finished["tag"])

    assert set(_checks(finished)) == {
        "Claude Code at its pin",
        "mattpocock-skills at its pin",
        "wf-test on the path",
        "a non-root user owns the workspace",
    }


@pytest.mark.parametrize(
    ("layer", "failing"),
    [
        ("USER root\n", "a non-root user owns the workspace"),
        ("RUN rm -rf /home/agent/.claude/plugins\n", "mattpocock-skills at its pin"),
        ("USER root\nRUN rm /usr/local/bin/wf-test\nUSER agent\n", "wf-test on the path"),
        ("RUN rm /home/agent/.local/bin/claude\n", "Claude Code at its pin"),
    ],
)
def test_an_image_that_fails_its_probe_is_never_tagged_for_a_session(
    wayfarer: Launcher, clone: Path, built_tags: list[str], layer: str, failing: str
) -> None:
    url = wayfarer.start().url()

    _, finished = _build(url, clone, f"FROM wayfarer-base\n{layer}")
    built_tags.append(finished["tag"])

    assert finished["ready"] is False
    assert _checks(finished)[failing] is False
    assert not _exists(finished["tag"])
    assert get(f"{url}api/image").json()["ready"] is False


def test_a_layer_that_does_not_build_says_so_and_leaves_no_tag(
    wayfarer: Launcher, clone: Path
) -> None:
    url = wayfarer.start().url()

    output, finished = _build(url, clone, "FROM wayfarer-base\nRUN exit 3\n")

    assert finished["ready"] is False
    assert finished["error"] is not None
    assert finished["checks"] == []
    assert not _exists(finished["tag"])
    assert output


def test_a_second_click_while_building_joins_the_build_rather_than_starting_another(
    wayfarer: Launcher, clone: Path, built_tags: list[str]
) -> None:
    url = wayfarer.start().url()
    # Unique, so Docker's cache cannot make it quick enough to finish between clicks.
    commit_layer(clone, f"FROM wayfarer-base\nRUN sleep 3 && echo {uuid4()}\n")

    assert post(f"{url}api/image/build").status_code == 202
    assert get(f"{url}api/image").json()["building"] is True
    assert post(f"{url}api/image/build").status_code == 202
    streamed = list(events(f"{url}api/image/build"))
    built_tags.append(streamed[-1][1]["tag"])

    assert [kind for kind, _ in streamed].count("finished") == 1
    assert sum("RUN sleep 3" in event.get("line", "") for _, event in streamed) == 1


def test_editing_the_layer_mid_build_does_not_change_what_the_build_is_tagged(
    wayfarer: Launcher, clone: Path, built_tags: list[str]
) -> None:
    url = wayfarer.start().url()
    marker = uuid4().hex
    commit_layer(clone, f"FROM wayfarer-base\nRUN sleep 3 && echo {marker} > /tmp/built\n")
    clicked = get(f"{url}api/image").json()["tag"]

    assert post(f"{url}api/image/build").status_code == 202
    commit_layer(clone, "FROM wayfarer-base\nRUN echo edited > /tmp/built\n")
    *_, (_, finished) = events(f"{url}api/image/build")
    built_tags.append(finished["tag"])

    assert finished["tag"] == clicked
    inside = subprocess.run(
        ["docker", "run", "--rm", clicked, "cat", "/tmp/built"], capture_output=True, text=True
    )
    assert inside.stdout.strip() == marker
