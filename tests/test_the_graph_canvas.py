"""The graph canvas, as a person sees it in the browser (#54).

Wayfarer runs in a clone against the GitHub stand-in, and Chromium opens an
effort's graph as the person's browser does. What the server derives is
`test_the_ticket_graph.py`'s; these hold where the canvas puts it and what
selecting does.
"""

from __future__ import annotations

from collections.abc import Iterator
from itertools import pairwise
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Locator, Page, expect

from conftest import EFFORT_BRANCH, Launcher, land, quick
from github_stand_in import GitHub, Issue
from specimens import VIEWPORT

pytestmark = [pytest.mark.git, pytest.mark.browser]

# The canvas never draws smaller than this, and scrolls instead (#23).
_SCALE_FLOOR = 0.7
_CARD_WIDTH = 184


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    opened = browser.new_page(viewport=VIEWPORT)
    yield opened
    opened.close()


def _open(wayfarer: Launcher, tmp_path: Path, page: Page, effort: Issue) -> None:
    """Wayfarer started and the effort's graph open, laid out."""
    url = wayfarer.start(env=quick(tmp_path)).url()
    page.goto(f"{url}efforts/{effort.number}")
    page.wait_for_selector("[data-piece=graph-canvas][data-laid-out=true]")


def _card(page: Page, ticket: Issue) -> Locator:
    return page.locator(f"[data-piece=ticket-card-{ticket.number}]")


def _left(where: Locator) -> float:
    box = where.bounding_box()
    assert box is not None
    return box["x"]


def _dimmed(where: Locator) -> bool:
    """Whether it is drawn faded, once it has finished fading, whatever does the fading."""
    opacity: float = where.evaluate(
        """async e => {
            await Promise.all(document.getAnimations().map(a => a.finished));
            let seen = 1;
            for (let n = e; n instanceof Element; n = n.parentElement) {
                seen *= Number(getComputedStyle(n).opacity);
            }
            return seen;
        }"""
    )
    # A wire from landed work rests a touch faded; a dimmed thing is far fainter.
    return opacity < 0.5


def _wire(page: Page, blocker: Issue | None, blocked: Issue) -> Locator:
    start = "start" if blocker is None else blocker.number
    return page.locator(f"[data-wire='{start}-{blocked.number}']")


def test_the_frontier_is_the_first_column_of_cards_beside_the_start_line(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (meter, flag, scale, room, gate) = github.effort("Widgets", tickets=5)
    github.block(flag, by=meter)
    github.block(scale, by=flag)
    github.block(gate, by=scale)
    github.block(gate, by=room)
    land(github, meter)
    _open(wayfarer, tmp_path, page, spec)

    rail = _left(page.locator("[data-piece=start-line]"))
    frontier = {_left(_card(page, flag)), _left(_card(page, room))}

    # Meter landed, so Flag stands on the frontier beside Room, which waits on
    # nothing: Room can start now, however far on the only ticket it feeds sits.
    assert len(frontier) == 1
    (column,) = frontier
    assert rail < column < _left(_card(page, scale))
    expect(_card(page, meter)).to_have_count(0)


def test_landed_work_folds_into_the_start_line_and_a_ticket_in_the_queue_keeps_its_card(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (meter, peaks, flag) = github.effort("Widgets", tickets=3)
    land(github, meter)
    land(github, peaks)
    github.pull_request(flag, base=EFFORT_BRANCH)
    _open(wayfarer, tmp_path, page, spec)

    rail = page.locator("[data-piece=start-line]")
    expect(rail).to_contain_text("2 tickets landed")
    expect(_card(page, flag)).to_contain_text("Landing")


def test_before_anything_lands_the_start_line_says_the_course_starts_here(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, _ = github.effort("Widgets", tickets=2)
    _open(wayfarer, tmp_path, page, spec)

    rail = page.locator("[data-piece=start-line]")
    expect(rail).to_contain_text("Nothing landed yet")
    expect(rail).to_contain_text("The course starts here")
    # The rail runs the full height of the graph, inside its padding.
    drawn, graph = rail.bounding_box(), page.locator("[data-piece=graph-stage]").bounding_box()
    assert drawn is not None and graph is not None
    assert drawn["y"] - graph["y"] <= 12
    assert graph["y"] + graph["height"] - (drawn["y"] + drawn["height"]) <= 12


def test_a_ticket_whose_pull_request_is_not_landing_keeps_a_card_in_review(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (flag,) = github.effort("Widgets", tickets=1)
    github.pull_request(flag, base=EFFORT_BRANCH, draft=True)
    _open(wayfarer, tmp_path, page, spec)

    expect(_card(page, flag)).to_have_accessible_name("Ticket 1, In review")
    expect(_card(page, flag)).to_contain_text("Its pull request is open")


def test_wires_are_solid_where_the_blocker_landed_and_dashed_where_it_has_not(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (meter, flag, scale) = github.effort("Widgets", tickets=3)
    github.block(flag, by=meter)
    github.block(scale, by=flag)
    land(github, meter)
    _open(wayfarer, tmp_path, page, spec)

    dashes = "e => getComputedStyle(e).strokeDasharray"
    assert _wire(page, None, flag).evaluate(dashes) == "none"
    assert _wire(page, flag, scale).evaluate(dashes) != "none"


def test_a_wire_leaves_the_start_line_level_with_the_ticket_it_feeds(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, tickets = github.effort("Widgets", tickets=3)
    _open(wayfarer, tmp_path, page, spec)

    rail = page.locator("[data-piece=start-line]").bounding_box()
    assert rail is not None
    for ticket in tickets:
        wire = _wire(page, None, ticket).bounding_box()
        card = _card(page, ticket).bounding_box()
        assert wire is not None and card is not None
        # One straight run from the rail's edge to the card's middle.
        assert wire["height"] < 4
        assert abs(wire["x"] - (rail["x"] + rail["width"])) < 2
        assert abs(wire["y"] + wire["height"] / 2 - (card["y"] + card["height"] / 2)) < 2


def test_an_implied_edge_is_not_drawn(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (noise, room, export) = github.effort("Widgets", tickets=3)
    github.block(room, by=noise)
    github.block(export, by=room)
    github.block(export, by=noise)
    _open(wayfarer, tmp_path, page, spec)

    expect(_wire(page, room, export)).to_have_count(1)
    expect(_wire(page, noise, export)).to_have_count(0)


def test_selecting_a_ticket_lights_what_it_waits_on_and_what_it_frees_and_dims_the_rest(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (meter, flag, scale, room) = github.effort("Widgets", tickets=4)
    github.block(flag, by=meter)
    github.block(scale, by=flag)
    _open(wayfarer, tmp_path, page, spec)

    _card(page, flag).click()

    expect(_card(page, flag)).to_have_attribute("aria-pressed", "true")
    assert [_dimmed(_card(page, t)) for t in (meter, flag, scale, room)] == [
        False,
        False,
        False,
        True,
    ]
    assert not _dimmed(page.locator("[data-piece=start-line]"))
    assert _dimmed(_wire(page, None, room))
    assert not _dimmed(_wire(page, meter, flag))
    assert not _dimmed(_wire(page, None, meter))


def test_the_trace_follows_only_the_selected_tickets_thread(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (meter, flag, scale) = github.effort("Widgets", tickets=3)
    github.block(scale, by=meter)
    github.block(scale, by=flag)
    land(github, flag)
    _open(wayfarer, tmp_path, page, spec)

    _card(page, meter).click()

    # Scale is freed by Meter, but its wire from the course is another thread.
    assert not _dimmed(_card(page, scale))
    assert not _dimmed(_wire(page, meter, scale))
    assert not _dimmed(_wire(page, None, meter))
    assert _dimmed(_wire(page, None, scale))


def test_escape_clears_the_selection_and_focus_stays_where_it_was(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (meter, flag) = github.effort("Widgets", tickets=2)
    _open(wayfarer, tmp_path, page, spec)
    _card(page, flag).click()
    expect(_card(page, flag)).to_have_attribute("aria-pressed", "true")

    page.keyboard.press("Escape")

    expect(_card(page, flag)).to_have_attribute("aria-pressed", "false")
    assert not _dimmed(_card(page, meter))
    assert _card(page, flag).evaluate("e => document.activeElement === e")


def test_clicking_empty_canvas_clears_the_selection(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (meter, flag) = github.effort("Widgets", tickets=2)
    _open(wayfarer, tmp_path, page, spec)
    _card(page, flag).click()

    stage = page.locator("[data-piece=graph-canvas]").bounding_box()
    assert stage is not None
    page.mouse.click(stage["x"] + stage["width"] - 4, stage["y"] + stage["height"] - 4)

    expect(_card(page, flag)).to_have_attribute("aria-pressed", "false")
    assert not _dimmed(_card(page, meter))


def test_the_start_line_can_be_selected(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (meter, _) = github.effort("Widgets", tickets=2)
    land(github, meter)
    _open(wayfarer, tmp_path, page, spec)
    rail = page.locator("[data-piece=start-line]")

    rail.click()

    expect(rail).to_have_attribute("aria-pressed", "true")
    expect(rail).to_have_accessible_name("1 ticket landed")


def test_past_the_scale_floor_the_canvas_scrolls_rather_than_shrinking_text(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, tickets = github.effort("Widgets", tickets=12)
    for blocker, blocked in pairwise(tickets):
        github.block(blocked, by=blocker)
    _open(wayfarer, tmp_path, page, spec)

    canvas = page.locator("[data-piece=graph-canvas]")
    scrolls: bool = canvas.evaluate("e => e.scrollWidth > e.clientWidth")
    assert scrolls
    card = _card(page, tickets[0]).bounding_box()
    assert card is not None
    assert card["width"] >= _CARD_WIDTH * _SCALE_FLOOR - 0.5


def test_a_graph_that_fits_is_drawn_at_full_size(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (first, second) = github.effort("Widgets", tickets=2)
    github.block(second, by=first)
    _open(wayfarer, tmp_path, page, spec)

    card = _card(page, first).bounding_box()
    assert card is not None
    assert card["width"] == _CARD_WIDTH


def test_the_graph_moves_as_github_does(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (meter, flag) = github.effort("Widgets", tickets=2)
    github.block(flag, by=meter)
    _open(wayfarer, tmp_path, page, spec)
    before = _left(_card(page, flag))

    land(github, meter)

    expect(_card(page, meter)).to_have_count(0)
    expect(page.locator("[data-piece=start-line]")).to_contain_text("1 ticket landed")
    # Flag steps onto the frontier, a column to the left.
    page.wait_for_function(
        "([n, x]) => document.querySelector(`[data-piece=ticket-card-${n}]`)"
        ".getBoundingClientRect().x < x",
        arg=[flag.number, before],
    )
