"""The beat list: a session's story as it reads on screen (#49).

The snapshot check in `test_the_gallery.py` holds how the list looks at rest.
These hold what a picture at rest cannot: what each mark says to a person who
cannot see it, the test output behind its control, a call's counter running, and
the pane following new beats only for a reader already at the bottom.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from playwright.sync_api import Locator, Page

from specimens import GALLERY_CLOCK

pytestmark = [pytest.mark.git, pytest.mark.browser]


def _specimen(page: Page, name: str) -> Locator:
    return page.locator(f'[data-specimen="{name}"]')


def _rows(beats: Locator) -> list[str]:
    """Each row of the list as a person reads it: a chapter's label, or a beat's
    time, what its mark says, and its sentence."""
    rows: list[str] = beats.locator("ol > li").evaluate_all(
        """rows => rows.map(row => {
            const mark = row.querySelector('[role="img"]');
            const words = row.innerText.replace(/\\s+/g, " ").trim();
            return mark ? `${mark.getAttribute("aria-label")} · ${words}` : words;
        })"""
    )
    return rows


def test_every_kind_of_beat_carries_its_mark_in_its_chapter(gallery: Page) -> None:
    assert _rows(_specimen(gallery, "beats")) == [
        "BEFORE ANY TEST Orient",
        "Read · 09:05 Read ISSUE.md, CONTEXT.md and beats.py",
        "Remark · 09:08 The analysis pass already runs astats, so the noise floor can join it.",
        "RED → GREEN Cycle 1",
        "Failing test · 09:11 1 failing: measures the noise floor Show test output",
        "Passing test · 09:15 12 passing",
        "Refactor · 09:17 Refactored limits.py; still 12 passing",
        "RED → GREEN Cycle 2",
        "Failing test · 09:19 1 failing: flags the hiss fixture Show test output",
        "Passing test · 09:24 13 passing",
        "Outcome · 09:26 Every criterion passes, and the full suite with them.",
    ]


def test_a_red_beats_output_stays_folded_until_asked_for(gallery: Page) -> None:
    red = _specimen(gallery, "beats").get_by_role("listitem").filter(has_text="measures the noise")
    toggle = red.get_by_role("button", name="Show test output")
    output = red.locator("pre")

    assert toggle.get_attribute("aria-expanded") == "false"
    assert output.is_hidden()

    toggle.click()
    assert red.get_by_role("button", name="Hide test output").get_attribute("aria-expanded") == (
        "true"
    )
    assert output.is_visible()
    assert "expected a noise floor, got None" in output.inner_text()

    red.get_by_role("button", name="Hide test output").click()
    assert output.is_hidden()


def test_a_call_with_no_result_yet_counts_the_seconds_it_has_taken(gallery: Page) -> None:
    working = _specimen(gallery, "beats-working").locator(
        "li", has=gallery.get_by_role("img", name="Working")
    )
    counter = working.locator(".num")

    assert working.inner_text().startswith("Running the full suite")
    assert counter.inner_text() == "12s"

    gallery.clock.set_fixed_time(GALLERY_CLOCK + timedelta(seconds=65))
    gallery.wait_for_function("n => n.innerText === '1m 17s'", arg=counter.element_handle())


# At the bottom, give or take the part of a pixel a scroll position rounds away.
_AT_THE_BOTTOM = "p => p.scrollHeight - p.scrollTop - p.clientHeight <= 1"


def _pane(page: Page) -> Locator:
    return _specimen(page, "beats-working").locator(".pane")


def _add_a_pane_more_than_fits(page: Page) -> None:
    """Beats until a reader at the top is well away from the bottom."""
    pane = _pane(page)
    while pane.evaluate("p => p.scrollHeight <= 2 * p.clientHeight"):
        page.get_by_role("button", name="Add a beat").click()


def test_the_pane_follows_new_beats_while_the_reader_is_at_the_bottom(gallery: Page) -> None:
    _add_a_pane_more_than_fits(gallery)
    gallery.get_by_role("button", name="Add a beat").click()

    gallery.wait_for_function(_AT_THE_BOTTOM, arg=_pane(gallery).element_handle())


def test_a_reader_who_scrolled_up_is_never_pulled_back_down(gallery: Page) -> None:
    _add_a_pane_more_than_fits(gallery)
    pane = _pane(gallery)
    gallery.wait_for_function(_AT_THE_BOTTOM, arg=pane.element_handle())
    pane.hover()
    gallery.mouse.wheel(0, -2000)
    gallery.wait_for_function("p => p.scrollTop === 0", arg=pane.element_handle())
    beats = pane.get_by_role("listitem").count()

    gallery.get_by_role("button", name="Add a beat").click()
    gallery.wait_for_function(
        "([p, n]) => p.querySelectorAll('li').length > n", arg=[pane.element_handle(), beats]
    )

    # A scroll the arrival started ends, or a second passes with none: which
    # arrives first is where the pane settled.
    settled = pane.evaluate(
        """p => new Promise(done => {
            p.addEventListener("scrollend", () => done(p.scrollTop), { once: true });
            setTimeout(() => done(p.scrollTop), 1000);
        })"""
    )
    assert settled == 0


def test_only_a_beat_that_arrives_rises_into_place(gallery: Page) -> None:
    pane = _pane(gallery)
    rising = "li => li.getAnimations().length > 0"
    assert pane.locator("li").evaluate_all(f"rows => rows.filter({rising}).length") == 0

    gallery.get_by_role("button", name="Add a beat").click()

    arrived = pane.get_by_role("listitem").filter(has_text="A later beat, number 1.")
    assert arrived.evaluate(rising)
