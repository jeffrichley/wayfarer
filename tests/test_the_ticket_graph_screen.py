"""The ticket graph screen, as a person reads it in the browser (#55).

Wayfarer runs in a clone against the GitHub stand-in, and Chromium opens an
effort's graph. The canvas itself is `test_the_graph_canvas.py`'s; these hold the
screen around it: the head and its tally, the panel for whatever is selected, and
arming the cascade.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Locator, Page, expect

from conftest import TICKET_BODY, Launcher, land, quick
from github_stand_in import GitHub, Issue
from specimens import VIEWPORT
from wayfarer.read_model import ASKED

pytestmark = [pytest.mark.git, pytest.mark.browser]


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


def _panel(page: Page) -> Locator:
    return page.locator("[data-piece=ticket-detail]")


def _named(*titles: str, tickets: list[Issue]) -> list[Issue]:
    for ticket, title in zip(tickets, titles, strict=True):
        ticket.title = title
    return tickets


def test_the_head_names_the_effort_and_tallies_where_every_ticket_stands(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, tickets = github.effort("Pre-delivery compliance checks", tickets=4)
    meter, flag, scale, room = tickets
    github.block(scale, by=flag)
    github.label(room, ASKED)
    land(github, meter)

    _open(wayfarer, tmp_path, page, spec)

    expect(page.get_by_role("heading", level=1)).to_have_text("Pre-delivery compliance checks")
    expect(page.locator("[data-piece=graph-kicker]")).to_have_text(
        f"/to-tickets · 4 tickets from spec #{spec.number}"
    )
    tally = page.get_by_role("list", name="Ticket states")
    expect(tally.get_by_role("listitem")).to_have_text(
        ["1 landed", "1 asked", "1 takeable", "1 blocked"]
    )


def test_the_tally_moves_as_github_does(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (meter, flag) = github.effort("Widgets", tickets=2)
    github.block(flag, by=meter)
    _open(wayfarer, tmp_path, page, spec)
    tally = page.get_by_role("list", name="Ticket states").get_by_role("listitem")
    expect(tally).to_have_text(["1 takeable", "1 blocked"])

    land(github, meter)

    expect(tally).to_have_text(["1 landed", "1 takeable"])


def test_selecting_a_ticket_fills_the_panel_with_what_to_build_and_what_it_waits_on_and_frees(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, tickets = github.effort("Widgets", tickets=3)
    meter, flag, scale = _named("Meter", "Flag noise", "Scale", tickets=tickets)
    flag.body = TICKET_BODY
    github.block(flag, by=meter)
    github.block(scale, by=flag)
    _open(wayfarer, tmp_path, page, spec)

    _card(page, flag).click()

    panel = _panel(page)
    expect(panel.get_by_role("heading", level=2)).to_have_text("Flag noise")
    expect(panel.locator("[data-piece=what-to-build]")).to_have_text(
        "Measure every chapter's noise floor, and flag the loud ones."
    )
    expect(panel.get_by_role("list", name="Blocked by").get_by_role("button")).to_have_text(
        ["Meter"]
    )
    expect(panel.get_by_role("list", name="Unblocks").get_by_role("button")).to_have_text(["Scale"])


def test_following_a_blocker_moves_the_selection_and_focus_to_its_card(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, tickets = github.effort("Widgets", tickets=2)
    meter, flag = _named("Meter", "Flag", tickets=tickets)
    github.block(flag, by=meter)
    _open(wayfarer, tmp_path, page, spec)
    _card(page, flag).click()

    _panel(page).get_by_role("list", name="Blocked by").get_by_role("button", name="Meter").click()

    expect(_card(page, meter)).to_have_attribute("aria-pressed", "true")
    expect(_card(page, meter)).to_be_focused()
    expect(_panel(page).get_by_role("heading", level=2)).to_have_text("Meter")


def test_following_a_landed_blocker_moves_to_the_start_line_it_folded_into(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, tickets = github.effort("Widgets", tickets=2)
    meter, flag = _named("Meter", "Flag", tickets=tickets)
    github.block(flag, by=meter)
    land(github, meter)
    _open(wayfarer, tmp_path, page, spec)
    _card(page, flag).click()

    _panel(page).get_by_role("list", name="Blocked by").get_by_role("button", name="Meter").click()

    rail = page.locator("[data-piece=start-line]")
    expect(rail).to_have_attribute("aria-pressed", "true")
    expect(rail).to_be_focused()


def test_acceptance_criteria_are_shown_as_written_and_nothing_claims_progress(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (ticket,) = github.effort("Widgets", tickets=1)
    ticket.body = TICKET_BODY
    _open(wayfarer, tmp_path, page, spec)

    _card(page, ticket).click()

    criteria = _panel(page).get_by_role("list", name="Acceptance criteria")
    expect(criteria.get_by_role("listitem")).to_have_text(
        [
            "Measure the noise floor of every chapter",
            "Chapters above -60 dB fail the check",
            "Failures explain the value, the limit, and the timestamp",
        ]
    )
    # The first box is ticked on GitHub, and still nothing is counted or marked.
    expect(_panel(page)).not_to_contain_text(" of 3")
    expect(criteria.get_by_role("checkbox")).to_have_count(0)
    expect(criteria.get_by_role("img")).to_have_count(0)


def test_arming_the_cascade_is_the_only_primary_action_and_confirms_in_one_line(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (ticket,) = github.effort("Widgets", tickets=1)
    # Taken by a person's hand, so arming has nothing to start.
    ticket.assignees.append("grace")
    _open(wayfarer, tmp_path, page, spec)
    _card(page, ticket).click()
    expect(page.locator(".btn-primary")).to_have_count(1)

    page.get_by_role("button", name="Arm the cascade").click()

    confirm = page.locator("[data-piece=arm-confirm]")
    expect(confirm).to_contain_text("No tickets are takeable now, up to 3 at a time")
    # In place of the button, and never a dialog over the screen.
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(page.get_by_role("alertdialog")).to_have_count(0)
    expect(page.locator(".btn-primary")).to_have_count(1)

    confirm.get_by_role("button", name="Arm").click()

    expect(page.locator("[data-piece=cascade]")).to_contain_text("Armed")
    expect(page.get_by_role("button", name="Arm the cascade")).to_have_count(0)


def test_backing_out_of_arming_arms_nothing(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (ticket,) = github.effort("Widgets", tickets=1)
    ticket.assignees.append("grace")
    _open(wayfarer, tmp_path, page, spec)

    page.get_by_role("button", name="Arm the cascade").click()
    page.locator("[data-piece=arm-confirm]").get_by_role("button", name="Not yet").click()

    expect(page.get_by_role("button", name="Arm the cascade")).to_be_focused()
    expect(page.locator("[data-piece=cascade]")).not_to_contain_text("Armed")


def test_selecting_the_start_line_lists_what_has_landed_in_the_order_it_depended_on(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, tickets = github.effort("Widgets", tickets=3)
    scale, meter, _ = _named("Scale", "Meter", "Flag", tickets=tickets)
    github.block(scale, by=meter)
    land(github, scale)
    land(github, meter)
    _open(wayfarer, tmp_path, page, spec)

    page.locator("[data-piece=start-line]").click()

    panel = _panel(page)
    expect(panel.get_by_role("heading", level=2)).to_have_text("2 tickets landed")
    expect(panel.get_by_role("list", name="Landed").get_by_role("listitem")).to_have_text(
        [f"Meter#{meter.number}", f"Scale#{scale.number}"]
    )


def test_a_ticket_opens_selected_from_its_link(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, tickets = github.effort("Widgets", tickets=2)
    _, flag = _named("Meter", "Flag", tickets=tickets)
    url = wayfarer.start(env=quick(tmp_path)).url()

    page.goto(f"{url}efforts/{spec.number}#{flag.number}")

    expect(_card(page, flag)).to_have_attribute("aria-pressed", "true")
    expect(_panel(page).get_by_role("heading", level=2)).to_have_text("Flag")
