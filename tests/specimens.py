"""The gallery's snapshot check: each specimen, lifted out of its page and drawn.

The app's `/gallery` and the prototype's `prototype_gallery.html` name the same
specimens with `data-specimen`. Both render in the same browser and each pair is
compared pixel for pixel, so there are no stored images to drift between machines.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageChops
from playwright.sync_api import Locator, Page, ViewportSize

REFERENCE = Path(__file__).with_name("prototype_gallery.html")
THEMES = ["light", "dark"]
# The size every screen is checked at first (docs/design/visual-language.md).
VIEWPORT: ViewportSize = {"width": 1440, "height": 900}


def specimen(page: Page, name: str) -> Locator:
    """The specimen the page names `name`."""
    return page.locator(f'[data-specimen="{name}"]')


def choose(gallery: Page, theme: str) -> None:
    """Pick a theme as a person does, with the gallery's own buttons."""
    # Exactly: each theme toggle in the shell's specimens is named for a chart too.
    gallery.get_by_role(
        "button", name={"light": "The chart", "dark": "The night chart"}[theme], exact=True
    ).click()


def set_theme(page: Page, theme: str) -> None:
    page.evaluate(
        """theme => theme === "dark"
            ? document.documentElement.setAttribute("data-theme", "dark")
            : document.documentElement.removeAttribute("data-theme")""",
        theme,
    )


# Where a specimen sits on its page is the page's business, and a box that starts
# half a pixel down draws its edges differently. So each is lifted to the
# viewport's corner, still inheriting from where it sits, with the rest of its
# page hidden so a box a fraction of a pixel wide shows bare page at its edge. It
# keeps the width its place gave it, so a widget laid out wrong in its column
# still disagrees.
_LIFT = """element => {
    const before = element.style.cssText;
    const width = element.getBoundingClientRect().width;
    document.body.style.visibility = "hidden";
    element.style.cssText += `;position:fixed;left:0;top:0;margin:0;width:${width}px;`
        + "box-sizing:border-box;visibility:visible";
    return before;
}"""
_SET_DOWN = """(element, before) => {
    element.style.cssText = before;
    document.body.style.visibility = "";
}"""


def _away(page: Page) -> None:
    # The pointer rests where specimens are lifted to, and would hover them.
    page.mouse.move(VIEWPORT["width"] - 1, VIEWPORT["height"] - 1)


def specimens(
    page: Page, which: Callable[[str], bool] = lambda _: True, *, hover: bool = False
) -> dict[str, Image.Image]:
    """Each specimen on the page `which` picks, by name, as it is drawn now, or
    with the pointer over it. The spinning ring is caught at its first frame, so
    a screenshot is the same every time."""
    shots: dict[str, Image.Image] = {}
    for element in page.locator("[data-specimen]").all():
        name = element.get_attribute("data-specimen")
        assert name is not None
        if not which(name):
            continue
        _away(page)
        before = element.evaluate(_LIFT)
        if hover:
            element.hover()
        png = element.screenshot(animations="disabled")
        element.evaluate(_SET_DOWN, before)
        shots[name] = Image.open(io.BytesIO(png)).convert("RGB")
    _away(page)
    return shots


def disagreements(
    gallery: Page,
    reference: Page,
    which: Callable[[str], bool] = lambda _: True,
    *,
    hover: bool = False,
) -> list[str]:
    """Every specimen the gallery draws differently from the prototype, and every
    one drawn on only one side, which the check could not compare."""
    drawn = specimens(gallery, which, hover=hover)
    expected_names = set()
    found = []
    for name, expected in specimens(reference, which, hover=hover).items():
        expected_names.add(name)
        actual = drawn.get(name)
        if actual is None:
            found.append(f"{name}: not in the gallery")
        elif actual.size != expected.size:
            found.append(f"{name}: {actual.size} in the gallery, {expected.size} in the prototype")
        elif ImageChops.difference(actual, expected).getbbox() is not None:
            found.append(f"{name}: drawn differently")
    found += [f"{name}: not in the prototype" for name in sorted(drawn.keys() - expected_names)]
    return found
