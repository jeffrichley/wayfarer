"""The gallery: every primitive in every state on one page, drawn as the frozen prototype draws it.

The reference is `prototype_gallery.html`: the prototype's own stylesheet and
markup. Both pages render in the same browser and each specimen is compared
pixel for pixel, so there are no stored images to drift between machines.
"""

from __future__ import annotations

import io
import re
from itertools import combinations
from pathlib import Path

import pytest
from PIL import Image, ImageChops
from playwright.sync_api import Page

from specimens import THEMES, choose, disagreements, set_theme

pytestmark = [pytest.mark.git, pytest.mark.browser]

PROTOTYPE_CSS = Path(__file__).parents[1] / "prototype" / "assets" / "wayfarer.css"

GLYPHS = ["done", "review", "building", "ask", "held", "take", "blocked", "pending", "out"]


def _tokens() -> list[str]:
    """Every custom property the prototype's stylesheet declares."""
    return sorted(set(re.findall(r"^\s*(--[\w-]+)\s*:", PROTOTYPE_CSS.read_text(), re.M)))


def _token_values(page: Page, names: list[str]) -> dict[str, str]:
    """What each token resolves to where it is used: the pixel it paints as a
    colour, and the font and length it gives. Two spellings of one value, such as
    `0.18` minified to `.18`, agree."""
    values: dict[str, str] = page.evaluate(
        """names => {
            const probe = document.createElement("div");
            document.body.append(probe);
            const canvas = document.createElement("canvas").getContext("2d");
            const values = Object.fromEntries(names.map(name => {
                probe.style.cssText = `position:absolute; color:var(${name});`
                    + `font-family:var(${name}); width:var(${name})`;
                const used = getComputedStyle(probe);
                canvas.clearRect(0, 0, 1, 1);
                canvas.fillStyle = used.color;
                canvas.fillRect(0, 0, 1, 1);
                const pixel = canvas.getImageData(0, 0, 1, 1).data.join(",");
                return [name, [pixel, used.fontFamily, used.width].join(" | ")];
            }));
            probe.remove();
            return values;
        }""",
        names,
    )
    return values


@pytest.mark.parametrize("theme", THEMES)
def test_the_gallery_draws_every_primitive_as_the_prototype_does(
    gallery: Page, reference: Page, theme: str
) -> None:
    choose(gallery, theme)
    set_theme(reference, theme)

    assert disagreements(gallery, reference) == []


@pytest.mark.parametrize("theme", THEMES)
def test_every_token_has_the_prototypes_value(gallery: Page, reference: Page, theme: str) -> None:
    choose(gallery, theme)
    set_theme(reference, theme)
    names = _tokens()

    assert _token_values(gallery, names) == _token_values(reference, names)


def test_the_night_chart_is_a_different_chart(gallery: Page) -> None:
    light = _token_values(gallery, ["--bg", "--fg", "--accent"])
    choose(gallery, "dark")

    night = _token_values(gallery, ["--bg", "--fg", "--accent"])

    assert all(light[name] != night[name] for name in light)


def test_a_visual_change_makes_the_gallery_disagree_with_the_prototype(
    gallery: Page, reference: Page
) -> None:
    gallery.add_style_tag(content=".st-held { border-width: 3px; }")

    assert disagreements(gallery, reference) == [
        "glyph-held: drawn differently",
        "glyph-held-lg: drawn differently",
        "full-held: drawn differently",
        "name-only-held: drawn differently",
        "line-held: drawn differently",
    ]


def test_a_gallery_specimen_with_nothing_to_compare_against_fails_the_check(
    gallery: Page, reference: Page
) -> None:
    gallery.evaluate(
        """() => document.querySelector("[data-specimen]").parentElement
            .insertAdjacentHTML("beforeend", '<div data-specimen="widget-new">New</div>')"""
    )

    assert disagreements(gallery, reference) == ["widget-new: not in the prototype"]


def test_every_state_glyph_sits_beside_its_word(gallery: Page) -> None:
    for glyph in GLYPHS:
        specimen = gallery.locator(f'[data-specimen="glyph-{glyph}"]')
        assert specimen.locator(".st").get_attribute("aria-hidden") == "true"
        assert specimen.inner_text().strip(), f"the {glyph} glyph has no word"

    assert gallery.locator('[data-specimen="glyph-review"]').inner_text() == "Landing"
    assert gallery.locator('[data-specimen="glyph-held"]').inner_text() == "Held"


@pytest.mark.parametrize("theme", THEMES)
def test_every_state_glyph_reads_apart_with_colour_removed(gallery: Page, theme: str) -> None:
    choose(gallery, theme)
    gallery.add_style_tag(content="html { filter: grayscale(1); }")

    glyphs = [_glyph_shot(gallery, glyph) for glyph in GLYPHS]

    alike = [
        (a, b)
        for (a, one), (b, other) in combinations(zip(GLYPHS, glyphs, strict=True), 2)
        if one.size == other.size and ImageChops.difference(one, other).getbbox() is None
    ]
    assert alike == []


def _glyph_shot(page: Page, glyph: str) -> Image.Image:
    png = page.locator(f'[data-specimen="glyph-{glyph}"] .st').screenshot(animations="disabled")
    return Image.open(io.BytesIO(png)).convert("L")
