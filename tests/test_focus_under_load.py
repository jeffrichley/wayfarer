"""Focus stays where the person clicked, on every screen, under load (#59).

Principle 12, proved rather than asserted: each screen gets the one check in
`focus.py` while recorded sessions stream through the real server, so the page is
busy with live updates the whole time, never quiet. One ticket stops to ask, so At
work has an answer to type into; the other two stream a long recorded session each.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from claude_stream import Playing, busy, says
from focus import counting, keeps_focus
from playwright.sync_api import Browser, Page, expect
from test_at_work import ASKING

from cascading import playing
from conftest import post
from github_stand_in import GitHub, Issue
from specimens import VIEWPORT

pytestmark = [pytest.mark.git, pytest.mark.browser]


@dataclass(frozen=True)
class Busy:
    """Wayfarer with an effort's cascade armed: one ticket asking, two streaming."""

    url: str
    effort: Issue
    asking: Issue
    streaming: tuple[Issue, Issue]


@pytest.fixture
def busy_line(tmp_path: Path, github: GitHub) -> Iterator[Busy]:
    effort, (asking, *streaming) = github.effort("Widgets", tickets=3)
    released = tmp_path / "released"
    released.mkdir()
    agent = Playing(
        released,
        first={asking.number: [says("Checking the credits.")]},
        asking={asking.number: ASKING},
        recorded={t.number: busy(tmp_path / f"session-{t.number}.jsonl") for t in streaming},
    )
    with playing(tmp_path, github, agent) as url:
        assert post(f"{url}api/efforts/{effort.number}/arm").status_code == 202
        yield Busy(url, effort, asking, (streaming[0], streaming[1]))


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    opened = counting(browser.new_page(viewport=VIEWPORT))
    yield opened
    opened.close()


def test_on_home_a_switcher_keeps_focus_while_sessions_stream(busy_line: Busy, page: Page) -> None:
    page.goto(busy_line.url)
    switcher = page.locator("[data-piece=repo-switcher]")

    keeps_focus(page, switcher, "Escape")

    # The click opened its menu, and Escape, pressed where focus was left, closed it.
    expect(switcher).to_have_attribute("aria-expanded", "false")
    expect(switcher).to_be_focused()


def test_on_the_ticket_graph_a_card_keeps_focus_while_sessions_stream(
    busy_line: Busy, page: Page
) -> None:
    page.goto(f"{busy_line.url}efforts/{busy_line.effort.number}")
    page.wait_for_selector("[data-piece=graph-canvas][data-laid-out=true]")
    card = page.locator(f"[data-piece=ticket-card-{busy_line.streaming[0].number}]")

    keeps_focus(page, card, "Escape")

    # The click selected it, and Escape cleared the selection and left focus there.
    expect(card).to_have_attribute("aria-pressed", "false")
    expect(card).to_be_focused()


def test_at_work_a_lane_keeps_focus_while_its_own_session_streams_into_it(
    busy_line: Busy, page: Page
) -> None:
    first, second = busy_line.streaming
    page.goto(f"{busy_line.url}at-work")
    lane = page.locator(f"[data-piece=lane-{first.number}]")
    expect(lane).to_be_visible()

    keeps_focus(page, lane, "Tab")

    expect(lane).to_have_attribute("aria-pressed", "true")
    # Tab went on from the lane the person left focus on, to the next one.
    expect(page.locator(f"[data-piece=lane-{second.number}]")).to_be_focused()


def test_at_work_an_answer_can_be_typed_while_the_other_sessions_stream(
    busy_line: Busy, page: Page
) -> None:
    page.goto(f"{busy_line.url}at-work#{busy_line.asking.number}")
    note = page.get_by_label("Anything the agent should know")

    keeps_focus(page, note, "W")
    page.keyboard.type("arn them")

    expect(note).to_have_value("Warn them")


def test_the_check_fails_when_a_live_update_moves_focus(busy_line: Busy, page: Page) -> None:
    page.goto(f"{busy_line.url}at-work")
    lane = page.locator(f"[data-piece=lane-{busy_line.streaming[0].number}]")
    expect(lane).to_be_visible()
    # A screen that, whenever an update redraws it, puts focus somewhere of its own.
    page.evaluate(
        "new MutationObserver(() => document.querySelector('[data-piece=session-story] a').focus())"
        ".observe(document.querySelector('[data-piece=session-lanes]'),"
        " {subtree: true, childList: true, characterData: true})"
    )

    with pytest.raises(AssertionError, match="focus is on a Ticket"):
        keeps_focus(page, lane, "Tab")
