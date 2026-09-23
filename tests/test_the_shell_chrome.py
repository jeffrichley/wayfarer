"""The shell chrome every effort screen sits in: the top bar and the route band (#47).

The snapshot check in `test_the_gallery.py` holds how each looks at rest. These
hold what a picture at rest cannot: where the course runs solid, which stations
go anywhere, how the menus open and close, and what the theme toggle remembers.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Locator, Page, expect

from specimens import choose

pytestmark = [pytest.mark.git, pytest.mark.browser]

EFFORT = "ACX compliance before delivery"


def _specimen(page: Page, name: str) -> Locator:
    return page.locator(f'[data-specimen="{name}"]')


@pytest.mark.parametrize(
    ("route", "course"),
    [
        ("route-building", ["solid"] * 5),
        ("route-sliced", ["solid", "solid", "dashed", "dashed", "dashed"]),
        ("route-charting", ["dashed"] * 5),
    ],
)
def test_the_course_is_solid_to_the_furthest_station_reached_and_dashed_beyond(
    gallery: Page, route: str, course: list[str]
) -> None:
    tracks = _specimen(gallery, route).locator('[data-piece="track"]')

    drawn = tracks.evaluate_all(
        """tracks => tracks.map(t => {
            const drawn = getComputedStyle(t);
            return [drawn.display, drawn.borderTopStyle];
        })"""
    )

    # Five legs between six stations; the end of the line has none.
    assert [style for display, style in drawn if display != "none"] == course
    assert drawn[-1][0] == "none"


def test_a_station_with_no_screen_is_disabled_not_a_dead_link(gallery: Page) -> None:
    route = _specimen(gallery, "route-charting").get_by_role(
        "navigation", name="Where this effort is on the skill line"
    )

    assert route.get_by_role("link").all_inner_texts() == [
        "/wayfinder\nChart the way\n3 decided · 3 patches of fog"
    ]
    for key in ["spec", "tickets", "build", "review"]:
        station = route.locator(f'[data-piece="station-{key}"]')
        assert station.get_attribute("aria-disabled") == "true", key
        assert station.get_attribute("title") == "Opens once the map's way is clear", key
        assert station.get_attribute("href") is None, key


def test_the_current_station_is_the_page_and_the_end_of_the_line_goes_nowhere(
    gallery: Page,
) -> None:
    route = _specimen(gallery, "route-building")

    assert route.locator('[aria-current="page"]').all_inner_texts() == [
        "/tdd\nBuild\n2 building · 1 asking"
    ]
    landed = route.locator('[data-piece="station-landed"]')
    assert landed.get_by_role("link").count() == 0
    assert landed.get_attribute("aria-disabled") is None
    assert landed.inner_text().endswith("2 of 9")


def test_a_solid_glyph_on_the_line_is_drawn_in_ink(gallery: Page) -> None:
    route = _specimen(gallery, "route-building")
    fill = "e => getComputedStyle(e.querySelector('.st')).backgroundColor"

    landed = route.locator('[data-piece="station-wayfinder"]').evaluate(fill)
    asking = route.locator('[data-piece="station-build"]').evaluate(fill)

    assert asking == landed
    assert asking != gallery.evaluate("getComputedStyle(document.body).backgroundColor")


def test_one_menu_opens_at_a_time(gallery: Page) -> None:
    bar = _specimen(gallery, "topbar-effort")
    repo = bar.get_by_role("button", name="galley")
    effort = bar.get_by_role("button", name=EFFORT)

    repo.click()
    expect(repo).to_have_attribute("aria-expanded", "true")
    expect(bar.get_by_role("link", name="madrigal")).to_be_visible()

    effort.click()
    expect(repo).to_have_attribute("aria-expanded", "false")
    expect(bar.get_by_role("link", name="madrigal")).to_have_count(0)
    expect(effort).to_have_attribute("aria-expanded", "true")
    expect(bar.get_by_role("link", name="Per-chapter voice casting")).to_be_visible()

    effort.click()
    expect(effort).to_have_attribute("aria-expanded", "false")
    expect(bar.locator('[data-piece="menu"]')).to_have_count(0)


def test_escape_closes_the_menu_and_returns_focus_to_its_button(gallery: Page) -> None:
    bar = _specimen(gallery, "topbar-effort")
    effort = bar.get_by_role("button", name=EFFORT)
    effort.focus()
    gallery.keyboard.press("Enter")
    gallery.keyboard.press("Tab")
    expect(bar.get_by_role("link").filter(has_text="Building · 2 of 9 landed")).to_be_focused()

    gallery.keyboard.press("Escape")

    expect(effort).to_have_attribute("aria-expanded", "false")
    expect(bar.locator('[data-piece="menu"]')).to_have_count(0)
    expect(effort).to_be_focused()


def test_escape_closes_the_menu_and_leaves_focus_the_person_moved_elsewhere(
    gallery: Page,
) -> None:
    bar = _specimen(gallery, "topbar-effort")
    bar.get_by_role("button", name="galley").click()
    elsewhere = _specimen(gallery, "button-secondary").get_by_role("button")
    elsewhere.focus()

    gallery.keyboard.press("Escape")

    expect(bar.locator('[data-piece="menu"]')).to_have_count(0)
    expect(elsewhere).to_be_focused()


def test_an_outside_click_closes_the_menu_and_returns_focus_to_its_button(gallery: Page) -> None:
    bar = _specimen(gallery, "topbar-effort")
    repo = bar.get_by_role("button", name="galley")
    repo.click()

    gallery.get_by_role("heading", name="Gallery").click()

    expect(repo).to_have_attribute("aria-expanded", "false")
    expect(bar.locator('[data-piece="menu"]')).to_have_count(0)
    expect(repo).to_be_focused()


def test_a_click_that_takes_focus_elsewhere_keeps_it_there(gallery: Page) -> None:
    bar = _specimen(gallery, "topbar-effort")
    bar.get_by_role("button", name="galley").click()
    elsewhere = _specimen(gallery, "button-secondary").get_by_role("button")

    elsewhere.click()

    expect(bar.locator('[data-piece="menu"]')).to_have_count(0)
    expect(elsewhere).to_be_focused()


def test_needs_you_stays_in_place_and_goes_quiet_when_nothing_waits(gallery: Page) -> None:
    waiting = _specimen(gallery, "topbar-effort").get_by_role("link", name="Needs you")
    quiet = _specimen(gallery, "topbar-nothing-waiting").get_by_role("link", name="Needs you")

    assert waiting.text_content() == "Needs you 4"
    assert quiet.text_content() == "Needs you 0"
    assert waiting.evaluate("e => e.getBoundingClientRect().x") == quiet.evaluate(
        "e => e.getBoundingClientRect().x"
    )
    colour = "e => getComputedStyle(e.lastElementChild).backgroundColor"
    assert waiting.evaluate(colour) != quiet.evaluate(colour)


def test_the_agents_working_say_how_many(gallery: Page) -> None:
    def working(specimen: str) -> Locator:
        return _specimen(gallery, specimen).locator('[data-piece="agents-working"]')

    expect(working("topbar-effort")).to_have_text("3 agents working")
    expect(working("topbar-quiet")).to_have_text("No agents working")


def test_the_theme_toggle_switches_the_chart_and_remembers_it(gallery: Page) -> None:
    toggle = _specimen(gallery, "topbar").locator('[data-piece="theme-toggle"]')
    assert toggle.get_attribute("aria-label") == "Switch to the night chart"

    toggle.click()

    page = gallery.locator("html")
    expect(page).to_have_attribute("data-theme", "dark")
    expect(toggle).to_have_attribute("aria-label", "Switch to the light chart")
    assert gallery.evaluate("localStorage.getItem('wayfarer.theme')") == "dark"

    gallery.reload()
    expect(page).to_have_attribute("data-theme", "dark")
    expect(toggle).to_have_attribute("aria-label", "Switch to the light chart")
    toggle.click()
    expect(page).not_to_have_attribute("data-theme", "dark")
    assert gallery.evaluate("localStorage.getItem('wayfarer.theme')") == "light"


def test_every_theme_toggle_shows_the_chart_the_page_is_not_in(gallery: Page) -> None:
    choose(gallery, "dark")

    toggles = gallery.locator('[data-piece="theme-toggle"]')
    expect(toggles).to_have_count(4)
    for i in range(4):
        expect(toggles.nth(i)).to_have_attribute("title", "Light chart")
