"""The gallery: every primitive in every state on one page, drawn as the frozen prototype draws it.

The reference is `prototype_gallery.html`: the prototype's own stylesheet and
markup. Both pages render in the same browser and each specimen is compared
pixel for pixel, so there are no stored images to drift between machines.
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterator
from itertools import combinations
from pathlib import Path

import pytest
from PIL import Image, ImageChops
from playwright.sync_api import Browser, Page

from conftest import Launcher

pytestmark = [pytest.mark.git, pytest.mark.browser]

REFERENCE = Path(__file__).with_name("prototype_gallery.html")
PROTOTYPE_CSS = Path(__file__).parents[1] / "prototype" / "assets" / "wayfarer.css"

GLYPHS = ["done", "review", "building", "ask", "held", "take", "blocked", "pending", "out"]
THEMES = ["light", "dark"]


@pytest.fixture
def gallery(wayfarer: Launcher, browser: Browser) -> Iterator[Page]:
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(wayfarer.start().url().rstrip("/") + "/gallery")
    page.wait_for_selector("[data-specimen]")
    yield page
    page.close()


@pytest.fixture
def reference(browser: Browser) -> Iterator[Page]:
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(REFERENCE.as_uri())
    yield page
    page.close()


def _theme(page: Page, theme: str) -> None:
    page.evaluate(
        """theme => theme === "dark"
            ? document.documentElement.setAttribute("data-theme", "dark")
            : document.documentElement.removeAttribute("data-theme")""",
        theme,
    )


# Where a specimen sits on its page is the page's business, and a box that starts
# half a pixel down draws its edges differently. So each is lifted to the
# viewport's corner, still inheriting from where it sits, with the rest of its
# page hidden so a box a fraction of a pixel wide shows bare page at its edge.
_LIFT = """element => {
    const before = element.style.cssText;
    document.body.style.visibility = "hidden";
    element.style.cssText += ";position:fixed;left:0;top:0;margin:0;visibility:visible";
    return before;
}"""
_SET_DOWN = """(element, before) => {
    element.style.cssText = before;
    document.body.style.visibility = "";
}"""


def _specimens(page: Page) -> dict[str, Image.Image]:
    """Each specimen on the page, by name, as it is drawn now. The spinning ring
    is caught at its first frame, so a screenshot is the same every time."""
    shots: dict[str, Image.Image] = {}
    for element in page.locator("[data-specimen]").all():
        name = element.get_attribute("data-specimen")
        assert name is not None
        before = element.evaluate(_LIFT)
        png = element.screenshot(animations="disabled")
        element.evaluate(_SET_DOWN, before)
        shots[name] = Image.open(io.BytesIO(png)).convert("RGB")
    return shots


def _disagreements(gallery: Page, reference: Page) -> list[str]:
    """Every specimen the gallery draws differently from the prototype."""
    drawn = _specimens(gallery)
    found = []
    for name, expected in _specimens(reference).items():
        actual = drawn.get(name)
        if actual is None:
            found.append(f"{name}: not in the gallery")
        elif actual.size != expected.size:
            found.append(f"{name}: {actual.size} in the gallery, {expected.size} in the prototype")
        elif ImageChops.difference(actual, expected).getbbox() is not None:
            found.append(f"{name}: drawn differently")
    return found


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
    _theme(gallery, theme)
    _theme(reference, theme)

    assert _disagreements(gallery, reference) == []


@pytest.mark.parametrize("theme", THEMES)
def test_every_token_has_the_prototypes_value(gallery: Page, reference: Page, theme: str) -> None:
    _theme(gallery, theme)
    _theme(reference, theme)
    names = _tokens()

    assert _token_values(gallery, names) == _token_values(reference, names)


def test_the_night_chart_is_a_different_chart(gallery: Page) -> None:
    light = _token_values(gallery, ["--bg", "--fg", "--accent"])
    _theme(gallery, "dark")

    night = _token_values(gallery, ["--bg", "--fg", "--accent"])

    assert all(light[name] != night[name] for name in light)


def test_a_visual_change_makes_the_gallery_disagree_with_the_prototype(
    gallery: Page, reference: Page
) -> None:
    gallery.add_style_tag(content=".st-held { border-width: 3px; }")

    assert _disagreements(gallery, reference) == [
        "glyph-held: drawn differently",
        "glyph-held-lg: drawn differently",
    ]


def test_every_state_glyph_sits_beside_its_word(gallery: Page) -> None:
    for glyph in GLYPHS:
        specimen = gallery.locator(f'[data-specimen="glyph-{glyph}"]')
        assert specimen.locator(".st").get_attribute("aria-hidden") == "true"
        assert specimen.inner_text().strip(), f"the {glyph} glyph has no word"

    assert gallery.locator('[data-specimen="glyph-review"]').inner_text() == "Landing"
    assert gallery.locator('[data-specimen="glyph-held"]').inner_text() == "Held"


def test_every_state_glyph_reads_apart_with_colour_removed(gallery: Page) -> None:
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
