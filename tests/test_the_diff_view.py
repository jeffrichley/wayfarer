"""Reading a change on the review desk: the diff view, as the gallery shows it (#53).

The snapshot check in `test_the_gallery.py` holds how the diff looks at rest.
These hold what a picture at rest cannot: which file it opens on, that a tab
changes the file, that a sign reads without colour, that a finding sits under
its line, and that a long line wraps inside its column.
"""

from __future__ import annotations

import io
from itertools import combinations

import pytest
from PIL import Image, ImageChops
from playwright.sync_api import Locator, Page

from specimens import THEMES, choose

pytestmark = [pytest.mark.git, pytest.mark.browser]


def _specimen(page: Page, name: str) -> Locator:
    return page.locator(f'[data-specimen="{name}"]')


def _numbers(diff: Locator) -> list[tuple[str, str]]:
    """Each line's old and new numbers, top to bottom, blank where it has none."""
    rows = diff.locator("tr:has(td + td)").all()
    return [
        (row.locator("td").nth(0).inner_text(), row.locator("td").nth(1).inner_text())
        for row in rows
    ]


def test_the_diff_names_each_changed_file_with_its_counts(gallery: Page) -> None:
    tabs = (
        _specimen(gallery, "diff").get_by_role("tablist", name="Changed files").get_by_role("tab")
    )

    assert tabs.all_inner_texts() == [
        "analysis/limits.ts+1",
        "checks/peak.ts+21",
        "checks/peak.test.ts+21",
        "compliance/check-label.ts+2 \N{MINUS SIGN}1",
    ]
    assert tabs.nth(3).get_attribute("title") == "app/compliance/check-label.ts"


def test_the_diff_opens_on_the_file_a_finding_is_about(gallery: Page) -> None:
    diff = _specimen(gallery, "diff")

    assert diff.get_by_role("tab", selected=True).all_inner_texts() == ["checks/peak.test.ts+21"]
    assert diff.get_by_role("tabpanel", name="checks/peak.test.ts+21").is_visible()
    # With no finding it opens on the first file.
    assert _specimen(gallery, "diff-changed").get_by_role(
        "tab", selected=True
    ).all_inner_texts() == ["compliance/check-label.ts+2 \N{MINUS SIGN}1"]


def test_choosing_a_file_shows_its_changes(gallery: Page) -> None:
    diff = _specimen(gallery, "diff")

    diff.get_by_role("tab", name="analysis/limits.ts").click()

    assert diff.get_by_role("tab", selected=True).all_inner_texts() == ["analysis/limits.ts+1"]
    assert _numbers(diff.get_by_role("tabpanel")) == [("3", "3"), ("4", "4"), ("", "5"), ("5", "6")]
    assert diff.locator("tr:has(td[colspan])").count() == 0


def test_each_line_says_whether_it_was_added_or_removed(gallery: Page) -> None:
    signs = _specimen(gallery, "diff-changed").locator("tbody tr td:nth-child(3)")

    assert [cell.get_attribute("aria-label") for cell in signs.all()] == [
        "Removed",
        "Added",
        None,
        None,
        None,
        "Added",
        None,
    ]


@pytest.mark.parametrize("theme", THEMES)
def test_additions_and_removals_read_apart_with_colour_removed(gallery: Page, theme: str) -> None:
    choose(gallery, theme)
    gallery.add_style_tag(content="html { filter: grayscale(1); }")
    rows = _specimen(gallery, "diff-changed").locator("tbody tr")

    # Removed, added, and unchanged, as check-label.ts's first three lines run.
    signs = {
        kind: _shot(rows.nth(i).locator("td").nth(2))
        for i, kind in enumerate(["del", "add", "ctx"])
    }

    alike = [
        (a, b)
        for (a, one), (b, other) in combinations(signs.items(), 2)
        if ImageChops.difference(one, other).getbbox() is None
    ]
    assert alike == []
    # The removed code is struck through, so it reads as gone beside what replaced it.
    code = [rows.nth(i).locator("td").nth(3) for i in range(2)]
    assert [cell.evaluate("e => getComputedStyle(e).textDecorationLine") for cell in code] == [
        "line-through",
        "none",
    ]


def test_a_finding_sits_beneath_the_line_it_concerns(gallery: Page) -> None:
    diff = _specimen(gallery, "diff")
    finding = diff.locator("tr:has(td[colspan])")

    assert finding.count() == 1
    assert [text for text in finding.inner_text().split("\n") if text] == [
        "/code-review \N{MIDDLE DOT} Spec axis",
        "Only checks that at exists. Assert the clipped fixture\N{RIGHT SINGLE QUOTATION MARK}s"
        " known peak time so story 4 is actually proven.",
    ]
    line = finding.locator("xpath=preceding-sibling::tr[1]")
    assert line.locator("td").nth(1).inner_text() == "19"
    assert "toBeDefined" in line.inner_text()
    above, below = line.bounding_box(), finding.bounding_box()
    assert above is not None and below is not None
    assert below["y"] == pytest.approx(above["y"] + above["height"], abs=1)


def test_a_long_line_wraps_without_moving_the_gutter(gallery: Page) -> None:
    diff = _specimen(gallery, "diff-long-line")
    table = diff.locator("table")
    rows = table.locator("tr").all()

    # The diff stays inside its column rather than scrolling it sideways.
    assert table.evaluate("t => t.getBoundingClientRect().width") <= 420
    heights = [row.evaluate("e => e.getBoundingClientRect().height") for row in rows]
    assert max(heights) > 2 * min(heights), "the long line did not wrap"
    # Every column starts where it starts on every other line.
    columns = [
        {tuple(round(v) for v in row.locator("td").nth(c).evaluate(_COLUMN_BOX)) for row in rows}
        for c in range(4)
    ]
    assert [len(column) for column in columns] == [1, 1, 1, 1]
    # The numbers and sign sit level with the first line of the code they number.
    wrapped = rows[heights.index(max(heights))]
    tops = [cell.evaluate(_TEXT_TOP) for cell in wrapped.locator("td").all()]
    assert len({round(top) for top in tops if top is not None}) == 1, tops


_COLUMN_BOX = "e => { const r = e.getBoundingClientRect(); return [r.x, r.width]; }"
# Where a cell's first line of text starts, not where its box does.
_TEXT_TOP = """e => {
    const range = document.createRange();
    range.selectNodeContents(e);
    const rects = [...range.getClientRects()];
    return rects.length ? rects[0].top : null;
}"""


def _shot(cell: Locator) -> Image.Image:
    png = cell.screenshot(animations="disabled")
    return Image.open(io.BytesIO(png)).convert("L")
