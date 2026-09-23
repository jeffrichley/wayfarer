"""A repo's session image: what it would be, and refusing a repo with no layer of its own."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from conftest import Launcher, commit_layer, get, post

pytestmark = pytest.mark.git


def test_a_repo_with_no_layer_of_its_own_is_refused_and_told_what_to_add(
    wayfarer: Launcher,
) -> None:
    url = wayfarer.start().url()

    status = get(f"{url}api/image").json()
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

    status = get(f"{url}api/image").json()

    assert status["refusal"] is None
    assert status["tag"].startswith("wayfarer-session:")
    assert status["building"] is False


def test_changing_the_layer_changes_the_tag(wayfarer: Launcher, clone: Path) -> None:
    commit_layer(clone, "FROM wayfarer-base\n")
    url = wayfarer.start().url()
    before = get(f"{url}api/image").json()["tag"]

    commit_layer(clone, "FROM wayfarer-base\nRUN echo toolchain\n")
    edited = get(f"{url}api/image").json()["tag"]
    (clone / ".wayfarer" / "requirements.txt").write_text("pytest\n")
    added = get(f"{url}api/image").json()["tag"]

    assert len({before, edited, added}) == 3


def test_an_image_nobody_has_built_is_not_ready(wayfarer: Launcher, clone: Path) -> None:
    commit_layer(clone, f"FROM wayfarer-base\nRUN echo {uuid4()}\n")
    url = wayfarer.start().url()

    assert get(f"{url}api/image").json()["ready"] is False


def test_there_is_no_build_output_until_someone_asks_for_a_build(
    wayfarer: Launcher, clone: Path
) -> None:
    commit_layer(clone, "FROM wayfarer-base\n")
    url = wayfarer.start().url()

    assert get(f"{url}api/image/build").status_code == 404
