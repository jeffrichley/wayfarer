"""The shared layer every screen is assembled from, as the gallery shows it (#70).

The snapshot check in `test_the_gallery.py` holds how each piece looks at rest.
These hold what a picture at rest cannot: how a button answers the pointer, that
each region of the page scrolls on its own, and what each piece says to a person
who cannot see it.
"""

from __future__ import annotations

import pytest
from PIL import ImageChops
from playwright.sync_api import Page

from specimens import THEMES, choose, disagreements, set_theme, specimen, specimens

pytestmark = [pytest.mark.git, pytest.mark.browser]

CRITERIA = [
    "Measure the noise floor of every chapter",
    "Chapters above \N{MINUS SIGN}60 dB fail the check",
    "Failures explain the value, the limit, and the timestamp",
    "The clean fixture passes",
]


def _enabled_button(name: str) -> bool:
    return name.startswith("button-") and not name.endswith("-disabled")


def _disabled_button(name: str) -> bool:
    return name.startswith("button-") and name.endswith("-disabled")


@pytest.mark.parametrize("theme", THEMES)
def test_every_button_answers_the_pointer_as_the_prototype_does(
    gallery: Page, reference: Page, theme: str
) -> None:
    choose(gallery, theme)
    set_theme(reference, theme)

    assert disagreements(gallery, reference, _enabled_button, hover=True) == []


def test_a_disabled_button_does_not_answer_the_pointer(gallery: Page) -> None:
    at_rest = specimens(gallery, _disabled_button)
    hovered = specimens(gallery, _disabled_button, hover=True)

    assert sorted(at_rest) == sorted(
        [
            f"button-{variant}{size}-disabled"
            for variant in ["primary", "secondary", "ghost"]
            for size in ["", "-small", "-arrow"]
        ]
        + ["button-link-disabled"]
    )
    moved = [
        name
        for name, shot in at_rest.items()
        if ImageChops.difference(shot, hovered[name]).getbbox() is not None
    ]
    assert moved == []


@pytest.mark.parametrize("theme", THEMES)
def test_a_disabled_button_is_drawn_apart_from_its_enabled_twin(gallery: Page, theme: str) -> None:
    choose(gallery, theme)
    buttons = specimens(gallery, lambda name: name.startswith("button-"))

    alike = [
        name
        for name, shot in buttons.items()
        if name.endswith("-disabled")
        and ImageChops.difference(shot, buttons[name.removesuffix("-disabled")]).getbbox() is None
    ]
    assert alike == []


def test_a_disabled_button_is_unavailable_and_still_reachable(gallery: Page) -> None:
    for name in specimens(gallery, _disabled_button):
        control = specimen(gallery, name).get_by_role("button")
        assert control.is_disabled(), f"{name} is not disabled"
        assert control.evaluate("e => getComputedStyle(e).cursor") == "default", name
        control.focus()
        assert control.evaluate("e => e === document.activeElement"), f"{name} cannot be focused"


def test_a_disabled_link_is_not_a_link(gallery: Page) -> None:
    link = specimen(gallery, "button-link").get_by_role("link", name="Open the desk")
    assert link.get_attribute("href") == "#desk"

    disabled = specimen(gallery, "button-link-disabled")
    assert disabled.get_by_role("link").count() == 0
    disabled.get_by_role("button", name="Open the desk").click(force=True)
    assert gallery.url.endswith("/gallery")


@pytest.mark.parametrize("frame", ["frame", "frame-no-route", "split-left", "split-right"])
def test_each_region_of_the_page_scrolls_on_its_own(gallery: Page, frame: str) -> None:
    regions = specimen(gallery, frame).locator(".pane")
    assert regions.count() == (1 if frame.startswith("frame") else 2)

    for index in range(regions.count()):
        region = regions.nth(index)
        region.scroll_into_view_if_needed()
        region.hover()
        page_at = gallery.evaluate("scrollY")
        gallery.mouse.wheel(0, 120)
        region.page.wait_for_function("e => e.scrollTop > 0", arg=region.element_handle())

        others = [regions.nth(i) for i in range(regions.count()) if i != index]
        assert [other.evaluate("e => e.scrollTop") for other in others] == [0] * len(others)
        assert gallery.evaluate("scrollY") == page_at, f"{frame} scrolled the page"
        region.evaluate("e => { e.scrollTop = 0; }")


def test_a_name_and_its_id_look_the_same_wherever_they_ride(gallery: Page) -> None:
    carriers = ["type-name", "name-plain", "name-row", "name-line", "name-head"]
    looks = {
        name: specimen(gallery, name)
        .locator(".id")
        .evaluate(
            """id => {
                const own = getComputedStyle(id), name = getComputedStyle(id.parentElement);
                return [own.fontFamily === name.fontFamily ? "same face" : "its own face",
                        (parseFloat(own.fontSize) / parseFloat(name.fontSize)).toFixed(2),
                        own.color, own.marginLeft, own.whiteSpace];
            }"""
        )
        for name in carriers
    }

    assert set(map(tuple, looks.values())) == {
        tuple(looks["type-name"]),
    }
    assert looks["type-name"][0] == "its own face"
    assert looks["type-name"][1] == "0.80"
    assert [specimen(gallery, name).locator(".id").inner_text() for name in carriers] == [
        "#127"
    ] * len(carriers)


def test_a_sequence_of_test_runs_reads_in_order(gallery: Page) -> None:
    runs = specimen(gallery, "runs").get_by_role("list", name="5 test runs")
    marks = runs.get_by_role("img")

    assert [marks.nth(i).get_attribute("aria-label") for i in range(marks.count())] == [
        "Failing",
        "Passing",
        "Failing",
        "Failing",
        "Passing",
    ]
    # Read left to right, in the order they ran.
    lefts = marks.evaluate_all("marks => marks.map(m => m.getBoundingClientRect().x)")
    assert lefts == sorted(set(lefts))


def test_the_thread_shows_landed_current_and_pending_steps(gallery: Page) -> None:
    steps = specimen(gallery, "thread").get_by_role("listitem")

    assert [
        steps.nth(i).get_by_role("img").get_attribute("aria-label") for i in range(steps.count())
    ] == ["Landed", "Landed", "Landed", "Building", "Not reached yet", "Not reached yet"]
    # The line runs solid through what has happened and dashed into what has not.
    assert [
        steps.nth(i).evaluate("e => getComputedStyle(e, '::before').borderLeftStyle")
        for i in range(steps.count() - 1)
    ] == ["solid", "solid", "solid", "dashed", "dashed"]


def test_the_criteria_read_as_written_and_nothing_more(gallery: Page) -> None:
    criteria = specimen(gallery, "criteria")

    assert criteria.get_by_role("listitem").all_inner_texts() == CRITERIA
    assert criteria.inner_text().split("\n") == CRITERIA
    assert criteria.get_by_role("checkbox").count() == 0
    assert criteria.get_by_role("img").count() == 0
    assert criteria.locator("input, button, a").count() == 0
