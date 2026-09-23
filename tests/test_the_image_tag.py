"""The tag hashes everything that goes into an image, so a stale image is a missing tag."""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from wayfarer.image import BASE, Recipe, tag

pytestmark = pytest.mark.unit


@pytest.fixture
def layer(tmp_path: Path) -> Path:
    layer = tmp_path / "layer"
    layer.mkdir()
    (layer / "Dockerfile").write_text("FROM wayfarer-base\n")
    return layer


def test_the_same_inputs_give_the_same_tag(layer: Path) -> None:
    assert tag(layer, BASE) == tag(layer, BASE)


@pytest.mark.parametrize(
    "moved",
    [
        replace(BASE, cli_version="moved"),
        replace(BASE, skills_version="moved"),
        replace(BASE, skills_commit="moved"),
    ],
    ids=["cli", "skills version", "skills commit"],
)
def test_moving_any_pin_changes_the_tag(layer: Path, moved: Recipe) -> None:
    assert tag(layer, moved) != tag(layer, BASE)


def test_editing_the_base_recipe_changes_the_tag(layer: Path, tmp_path: Path) -> None:
    recipe = tmp_path / "base"
    shutil.copytree(BASE.files, recipe)
    before = tag(layer, replace(BASE, files=recipe))

    with (recipe / "wf-test").open("a") as wf_test:
        wf_test.write("# edited\n")

    assert tag(layer, replace(BASE, files=recipe)) != before


def test_moving_a_file_within_the_layer_changes_the_tag(layer: Path) -> None:
    (layer / "a.txt").write_text("same content")
    before = tag(layer, BASE)

    (layer / "a.txt").rename(layer / "b.txt")

    assert tag(layer, BASE) != before
