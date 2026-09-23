"""A repo's session image: what it would be, and refusing a repo with no layer of its own."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from conftest import Launcher, Stream, commit_layer, post

pytestmark = pytest.mark.git


def _image(url: str) -> dict[str, Any]:
    """What a newly opened page is told of the image, once it asks for a read."""
    with Stream(url) as page:
        post(f"{url}api/image/read")
        return page.item("image")


def test_a_repo_with_no_layer_of_its_own_is_refused_and_told_what_to_add(
    wayfarer: Launcher,
) -> None:
    url = wayfarer.start().url()

    status = _image(url)
    build = post(f"{url}api/image/build")

    assert status["tag"] is None
    assert status["ready"] is False
    assert ".wayfarer/Dockerfile" in status["refusal"]
    assert "FROM wayfarer-base" in status["refusal"]
    assert build.status_code == 409
    assert build.json()["detail"] == status["refusal"]


def test_a_repo_with_a_layer_is_not_refused_and_has_a_tag_waiting_to_be_built(
    wayfarer: Launcher, clone: Path
) -> None:
    commit_layer(clone, "FROM wayfarer-base\n")
    url = wayfarer.start().url()

    status = _image(url)

    assert status["refusal"] is None
    assert status["tag"].startswith("wayfarer-session:")
    assert status["building"] is False


def test_changing_the_layer_changes_the_tag(wayfarer: Launcher, clone: Path) -> None:
    commit_layer(clone, "FROM wayfarer-base\n")
    url = wayfarer.start().url()
    with Stream(url) as page:
        post(f"{url}api/image/read")
        tags = [page.item("image")["tag"]]

        commit_layer(clone, "FROM wayfarer-base\nRUN echo toolchain\n")
        post(f"{url}api/image/read")
        page.until(lambda items: items["image"]["tag"] not in tags)
        tags.append(page.items["image"]["tag"])
        (clone / ".wayfarer" / "requirements.txt").write_text("pytest\n")
        post(f"{url}api/image/read")
        page.until(lambda items: items["image"]["tag"] not in tags)


def test_an_image_nobody_has_built_is_not_ready(wayfarer: Launcher, clone: Path) -> None:
    commit_layer(clone, f"FROM wayfarer-base\nRUN echo {uuid4()}\n")
    url = wayfarer.start().url()

    assert _image(url)["ready"] is False


def test_there_is_no_build_output_until_someone_asks_for_a_build(
    wayfarer: Launcher, clone: Path
) -> None:
    commit_layer(clone, "FROM wayfarer-base\n")
    url = wayfarer.start().url()

    with Stream(url) as page:
        post(f"{url}api/image/read")
        page.item("image")

        assert set(page.items) == {"image"}
