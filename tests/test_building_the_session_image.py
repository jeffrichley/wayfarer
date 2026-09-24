"""Building a repo's session image on click, and the probe that proves it.

These build for real: the first one in a fresh Docker pays for the base (the CLI
download and the plugin clone), and every later one reuses Docker's cache.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from conftest import (
    BUILD_TIMEOUT,
    Launcher,
    Stream,
    build_layer,
    build_output,
    commit_layer,
    post,
)

pytestmark = pytest.mark.docker


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
    built = build_layer(url, clone, f"FROM wayfarer-base\nRUN echo {marker} | rev\n")
    finished = built.finished
    built_tags.append(finished["tag"])

    assert any(line.endswith(marker[::-1]) for line in built.output)
    assert finished["ready"] is True, built.output
    assert set(_checks(finished).values()) == {True}
    assert built.image == {
        "kind": "image",
        "id": "image",
        "layer": ".wayfarer/Dockerfile",
        "refusal": None,
        "tag": finished["tag"],
        "ready": True,
        "building": False,
    }
    assert _exists(finished["tag"])


def test_a_new_tag_is_probed_for_the_cli_the_plugin_the_wrapper_a_non_root_owner_and_asking(
    wayfarer: Launcher, clone: Path, built_tags: list[str]
) -> None:
    url = wayfarer.start().url()

    finished = build_layer(url, clone, "FROM wayfarer-base\nRUN echo probe-me\n").finished
    built_tags.append(finished["tag"])

    assert set(_checks(finished)) == {
        "Claude Code at its pin",
        "mattpocock-skills at its pin",
        "wf-test runs and reports",
        "a non-root user owns the workspace",
        "a session can ask by ending",
    }


@pytest.mark.parametrize(
    ("layer", "failing"),
    [
        ("USER root\n", "a non-root user owns the workspace"),
        ("RUN rm -rf /home/agent/.claude/plugins\n", "mattpocock-skills at its pin"),
        ("USER root\nRUN rm /usr/local/bin/wf-test\nUSER agent\n", "wf-test runs and reports"),
        ("RUN rm /home/agent/.local/bin/claude\n", "Claude Code at its pin"),
        ("RUN echo '{}' > /home/agent/.claude/settings.json\n", "a session can ask by ending"),
        (
            "USER root\nRUN rm /usr/local/bin/wf-ask-tool\nUSER agent\n",
            "a session can ask by ending",
        ),
    ],
)
def test_an_image_that_fails_its_probe_is_never_tagged_for_a_session(
    wayfarer: Launcher, clone: Path, built_tags: list[str], layer: str, failing: str
) -> None:
    url = wayfarer.start().url()

    built = build_layer(url, clone, f"FROM wayfarer-base\n{layer}")
    finished = built.finished
    built_tags.append(finished["tag"])

    assert finished["ready"] is False
    assert _checks(finished)[failing] is False
    assert not _exists(finished["tag"])
    assert built.image["ready"] is False


def test_a_layer_that_does_not_build_says_so_and_leaves_no_tag(
    wayfarer: Launcher, clone: Path
) -> None:
    url = wayfarer.start().url()

    built = build_layer(url, clone, "FROM wayfarer-base\nRUN exit 3\n")
    finished = built.finished

    assert finished["ready"] is False
    assert finished["error"] is not None
    assert finished["checks"] == []
    assert not _exists(finished["tag"])
    assert built.output


def test_a_second_click_while_building_joins_the_build_rather_than_starting_another(
    wayfarer: Launcher, clone: Path, built_tags: list[str]
) -> None:
    url = wayfarer.start().url()
    # Unique, so Docker's cache cannot make it quick enough to finish between clicks.
    commit_layer(clone, f"FROM wayfarer-base\nRUN sleep 3 && echo {uuid4()}\n")

    with Stream(url, timeout=BUILD_TIMEOUT) as page:
        assert post(f"{url}api/image/build").status_code == 202
        page.item("image", building=True)
        assert post(f"{url}api/image/build").status_code == 202
        built_tags.append(page.item("build_finished")["tag"])
        page.item("image", building=False)

    # A second build would have replaced the first one's output with its own.
    assert not [event for event in page.received if event["kind"] == "removal"]
    assert sum("RUN sleep 3" in line for line in build_output(page.items)) == 1


def test_a_new_click_replaces_the_last_builds_output_with_its_own(
    wayfarer: Launcher, clone: Path, built_tags: list[str]
) -> None:
    url = wayfarer.start().url()
    # Far longer than the second, so a line of it left behind would show.
    before = uuid4().hex
    first = build_layer(
        url, clone, f"FROM wayfarer-base\nRUN for i in $(seq 200); do echo {before}; done\n"
    )
    built_tags.append(first.finished["tag"])

    after = uuid4().hex
    second = build_layer(url, clone, f"FROM wayfarer-base\nRUN echo {after}\n")
    built_tags.append(second.finished["tag"])

    assert any(before in line for line in first.output)
    assert any(after in line for line in second.output)
    assert not any(before in line for line in second.output)


def test_editing_the_layer_mid_build_does_not_change_what_the_build_is_tagged(
    wayfarer: Launcher, clone: Path, built_tags: list[str]
) -> None:
    url = wayfarer.start().url()
    marker = uuid4().hex
    commit_layer(clone, f"FROM wayfarer-base\nRUN sleep 3 && echo {marker} > /tmp/built\n")

    with Stream(url, timeout=BUILD_TIMEOUT) as page:
        post(f"{url}api/image/read")
        clicked = page.item("image")["tag"]
        assert post(f"{url}api/image/build").status_code == 202
        commit_layer(clone, "FROM wayfarer-base\nRUN echo edited > /tmp/built\n")
        finished = page.item("build_finished")
    built_tags.append(finished["tag"])

    assert finished["tag"] == clicked
    inside = subprocess.run(
        ["docker", "run", "--rm", clicked, "cat", "/tmp/built"], capture_output=True, text=True
    )
    assert inside.stdout.strip() == marker
