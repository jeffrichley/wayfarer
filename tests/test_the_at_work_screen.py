"""At work, as a person watches it in the browser (#56).

Wayfarer is served in this process with its sessions really running recorded Claude
Code output (`claude_stream.Playing`), and Chromium opens `/at-work` as the person's
browser does. What the server derives is `test_at_work.py`'s; these hold what the
screen draws from it, and that it never takes focus from where the person put it.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from claude_stream import Playing, edits, runs_tests, says
from playwright.sync_api import Browser, Page, expect
from test_at_work import ASKING, CRITERIA, WHICH

from cascading import playing
from conftest import post
from github_stand_in import GitHub, Issue
from specimens import VIEWPORT
from wayfarer.asking import ASKED

pytestmark = [pytest.mark.git, pytest.mark.browser]


@pytest.fixture
def agent(tmp_path: Path) -> Playing:
    released = tmp_path / "released"
    released.mkdir()
    return Playing(released)


@pytest.fixture
def url(tmp_path: Path, github: GitHub, agent: Playing) -> Iterator[str]:
    with playing(tmp_path, github, agent) as served:
        yield served


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    opened = browser.new_page(viewport=VIEWPORT)
    yield opened
    opened.close()


def _watch(url: str, page: Page, effort: Issue, *tickets: Issue) -> None:
    """The effort's cascade armed, and At work open on its sessions."""
    assert post(f"{url}api/efforts/{effort.number}/arm").status_code == 202
    page.goto(f"{url}at-work")
    for ticket in tickets:
        page.wait_for_selector(f"[data-piece=lane-{ticket.number}]")


def _focused(page: Page) -> str | None:
    piece: str | None = page.evaluate("document.activeElement?.dataset?.piece ?? null")
    return piece


def test_each_lane_shows_its_latest_beat_and_updates_in_place_without_taking_focus(
    url: str, agent: Playing, github: GitHub, page: Page
) -> None:
    effort, (fold, measure) = github.effort("Widgets", tickets=2)
    agent.first[fold.number] = [says("Reading the fold.")]
    agent.then[fold.number] = [says("Folding works.")]
    agent.first[measure.number] = [says("Measuring the widget.")]
    _watch(url, page, effort, fold, measure)
    lane = page.locator(f"[data-piece=lane-{fold.number}]")
    other = page.locator(f"[data-piece=lane-{measure.number}]")
    expect(lane).to_contain_text("Reading the fold.")
    expect(lane).to_contain_text(f"ticket/{fold.number}-ticket-1")
    expect(other).to_contain_text("Measuring the widget.")
    expect(page.get_by_text("At work · 2 sessions")).to_be_visible()

    other.focus()
    agent.let_go(fold.number)

    expect(lane).to_contain_text("Folding works.")
    # The lane that changed is the same element, and focus stayed where it was put.
    assert _focused(page) == f"lane-{measure.number}"
    page.keyboard.press("Enter")
    expect(other).to_have_attribute("aria-pressed", "true")


def test_selecting_a_lane_swaps_the_story_and_leaves_focus_on_the_lane(
    url: str, agent: Playing, github: GitHub, page: Page
) -> None:
    effort, (fold, measure) = github.effort("Widgets", tickets=2)
    agent.first[fold.number] = [says("Reading the fold.")]
    agent.first[measure.number] = [says("Measuring the widget.")]
    _watch(url, page, effort, fold, measure)
    story = page.locator("[data-piece=session-story]")
    # The first lane is selected until the person chooses.
    expect(story.get_by_role("heading", level=1)).to_have_text(fold.title)
    expect(story).to_contain_text("Reading the fold.")

    page.locator(f"[data-piece=lane-{measure.number}]").click()

    expect(story.get_by_role("heading", level=1)).to_have_text(measure.title)
    expect(story).to_contain_text("Measuring the widget.")
    expect(story).not_to_contain_text("Reading the fold.")
    assert _focused(page) == f"lane-{measure.number}"
    assert page.url.endswith(f"/at-work#{measure.number}")
    # The address names the lane, so opening it again selects it.
    page.reload()
    expect(story.get_by_role("heading", level=1)).to_have_text(measure.title)


def test_the_rail_shows_the_criteria_as_written_a_mark_per_test_run_and_what_changed(
    url: str, agent: Playing, github: GitHub, page: Page
) -> None:
    effort, (ticket,) = github.effort("Widgets", tickets=1)
    ticket.body = CRITERIA
    agent.first[ticket.number] = [
        *runs_tests("t1", exit=1, failed=1, failing=["test_fold"]),
        *edits("e1", "/workspace/src/fold.py"),
        *runs_tests("t2", exit=0, passed=3),
        *runs_tests("t3", exit=1, failed=1, failing=["test_twice"]),
    ]
    _watch(url, page, effort, ticket)
    rail = page.locator("[data-piece=session-evidence]")

    marks = rail.locator("[data-piece=rhythm] .tr")
    expect(marks).to_have_count(3)
    assert [m.get_attribute("aria-label") for m in marks.all()] == [
        "Failing",
        "Passing",
        "Failing",
    ]
    expect(rail.locator("[data-piece=criteria] li")).to_have_text(
        ["Credits are checked", "A missing one fails"]
    )
    expect(rail.locator("[data-piece=changes]")).to_contain_text("src/fold.py")
    # Removed lines are counted with a minus sign, as the prototype sets them.
    expect(rail.locator("[data-piece=changes]")).to_contain_text("+1 \u22121")


def test_an_asked_ticket_shows_its_question_under_the_story_and_answering_resumes_it(
    url: str, agent: Playing, github: GitHub, page: Page
) -> None:
    effort, (ticket,) = github.effort("Exports", tickets=1)
    agent.first[ticket.number] = [says("Checking the credits.")]
    agent.asking[ticket.number] = ASKING
    agent.then[ticket.number] = [says("Warning on no credits, as you said.")]
    _watch(url, page, effort, ticket)
    lane = page.locator(f"[data-piece=lane-{ticket.number}]")
    expect(lane).to_contain_text(f"Asked you: {WHICH}")
    story = page.locator("[data-piece=session-story]")
    expect(story).to_contain_text("Checking the credits.")
    card = story.locator(f"[data-piece=question-{ticket.number}]")
    expect(card).to_contain_text(WHICH)

    card.get_by_role("radio", name="Warn").click()
    card.locator(f"[data-piece=send-answer-{ticket.number}]").click()

    expect(story).to_contain_text("Warning on no credits, as you said.")
    expect(lane).to_contain_text("Warning on no credits, as you said.")
    expect(card).to_have_count(0)
    assert ASKED not in github.labels(ticket.number)
    assert any("Warn" in comment for comment in ticket.comments if "wayfarer:answer" in comment)
