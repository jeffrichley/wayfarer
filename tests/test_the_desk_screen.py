"""The review desk, as a person works through it in the browser (#57).

Wayfarer runs in a clone against the GitHub stand-in, and Chromium opens it as
the person's browser does. What the server derives is `test_the_desk.py`'s;
these hold what the screen draws from it, and what its actions send.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Locator, Page, expect

from conftest import EFFORT_BRANCH, Launcher, post, quick
from github_stand_in import GitHub, Issue
from specimens import VIEWPORT
from wayfarer.asking import question_comment
from wayfarer.models import Choice, Question
from wayfarer.read_model import ASKED, HELD

pytestmark = [pytest.mark.git, pytest.mark.browser]

_CREDITS = Question(
    question="Should a book with no credits fail the export or warn?",
    header="Credits",
    options=[
        Choice(label="Fail", description="The export stops, naming the book."),
        Choice(label="Warn", description="The export carries on, and says so."),
    ],
    multi_select=False,
)


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    opened = browser.new_page(viewport=VIEWPORT)
    yield opened
    opened.close()


def _ask(github: GitHub, ticket: Issue) -> None:
    """Leave `ticket` as a session that asked leaves it: claimed, the question, the label."""
    github.assign(ticket, "wayfarer")
    github.comment(ticket, question_comment("run-1", [_CREDITS]))
    github.label(ticket, ASKED)


def _open(
    wayfarer: Launcher, tmp_path: Path, page: Page, effort: Issue, *, auto_merge: bool = True
) -> str:
    """Wayfarer started, the effort read as a screen that shows it asks, and the desk open."""
    env = quick(tmp_path) | ({} if auto_merge else {"WAYFARER_AUTO_MERGE": "0"})
    url = wayfarer.start(env=env).url()
    assert post(f"{url}api/efforts/{effort.number}/read").status_code == 202
    page.goto(f"{url}desk")
    return url


def _queue(page: Page) -> Locator:
    return page.locator("[data-piece=needs-you-queue] button")


def _surface(page: Page) -> Locator:
    return page.locator("[data-piece=desk-item]")


def test_the_queue_holds_its_order_new_items_join_at_the_bottom_and_it_reranks_on_return(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (flag, meter, scale) = github.effort("Widgets", tickets=3)
    flag.title, meter.title = "Flag loudness", "Meter peaks"
    github.label(flag, ASKED)
    github.block(scale, by=meter)
    url = _open(wayfarer, tmp_path, page, spec)
    queue = _queue(page)
    expect(queue).to_have_count(1)

    # Meter peaks holds up more, and still joins at the bottom, marked new.
    github.label(meter, ASKED)
    expect(queue).to_have_count(2)
    expect(queue.nth(0)).to_contain_text("Flag loudness")
    expect(queue.nth(1)).to_contain_text("New · Question · Widgets")
    expect(queue.nth(1)).to_contain_text("Meter peaks")

    # A reload is the same visit, so the order holds.
    page.reload()
    expect(queue.nth(1)).to_contain_text("New · Question")

    # Coming back re-ranks it.
    page.goto(url)
    page.goto(f"{url}desk")
    expect(queue.nth(0)).to_contain_text("Meter peaks")
    expect(queue.nth(1)).to_contain_text("Flag loudness")
    expect(page.get_by_text("New · ")).to_have_count(0)


def test_a_resolved_item_stays_in_place_dimmed_saying_what_happened(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (flag, meter) = github.effort("Widgets", tickets=2)
    flag.title, meter.title = "Flag loudness", "Meter peaks"
    github.label(flag, ASKED)
    github.label(meter, ASKED)
    _open(wayfarer, tmp_path, page, spec)
    queue = _queue(page)
    expect(queue).to_have_count(2)

    github.unlabel(flag, ASKED)

    expect(queue.nth(0)).to_contain_text("Answered")
    expect(queue.nth(0).get_by_role("img", name="Resolved")).to_be_visible()
    expect(queue.nth(1)).to_contain_text("Meter peaks")
    # Home counts only what still needs the person.
    expect(page.locator("[data-piece=needs-you]")).to_contain_text("1")


def test_selecting_an_item_repaints_the_queue_in_place_and_keeps_focus(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (flag, meter) = github.effort("Widgets", tickets=2)
    flag.title, meter.title = "Flag loudness", "Meter peaks"
    github.label(flag, ASKED)
    github.label(meter, ASKED)
    _open(wayfarer, tmp_path, page, spec)
    queue = _queue(page)
    expect(queue.nth(0)).to_have_attribute("aria-pressed", "true")
    second = queue.nth(1).element_handle()

    queue.nth(1).click()

    expect(queue.nth(1)).to_have_attribute("aria-pressed", "true")
    expect(queue.nth(0)).to_have_attribute("aria-pressed", "false")
    expect(queue.nth(1)).to_be_focused()
    # The very button clicked, not a new one drawn in its place.
    assert page.evaluate("b => b.isConnected && b === document.activeElement", second)
    expect(_surface(page).locator("h2")).to_contain_text("Meter peaks")
    assert page.url.endswith(f"/desk#ticket:{meter.number}")


def test_each_kind_of_item_has_its_own_surface_with_exactly_one_primary_action(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (flag, meter, scale) = github.effort("Widgets", tickets=3)
    flag.title, meter.title, scale.title = "Flag loudness", "Meter peaks", "Scale bars"
    _ask(github, flag)
    github.label(meter, HELD)
    github.pull_request(scale, base=EFFORT_BRANCH)
    url = _open(wayfarer, tmp_path, page, spec, auto_merge=False)
    # Arming finds no session image in this clone, so the environment pauses it.
    post(f"{url}api/efforts/{spec.number}/arm")
    queue = _queue(page)
    page.goto(f"{url}desk")
    expect(queue).to_have_count(4)

    surfaces = {}
    for i in range(4):
        queue.nth(i).click()
        expect(_surface(page).locator(".btn-primary")).to_have_count(1)
        head = _surface(page).locator("header")
        surfaces[head.get_attribute("data-piece")] = (
            _surface(page).locator(".btn-primary").inner_text()
        )

    assert surfaces == {
        "environment-header": "Resume the cascades",
        "question-header": "Send answer and resume",
        "held-header": "Continue",
        "pr-header": "Review it on GitHub",
    }


def test_a_review_says_what_landing_it_frees_before_its_button(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (flag, meter, scale) = github.effort("Widgets", tickets=3)
    flag.title, meter.title = "Flag loudness", "Meter peaks"
    github.pull_request(flag, base=EFFORT_BRANCH)
    github.block(meter, by=flag)
    github.block(scale, by=meter)
    _open(wayfarer, tmp_path, page, spec, auto_merge=False)

    lands = _surface(page).locator("[data-piece=lands]")
    expect(lands).to_have_text(
        "Landing it lands Flag loudness. Meter peaks#3 starts the moment it does."
    )
    expect(_surface(page).locator("[data-piece=pr-header]")).to_contain_text("Holds up 3 tickets")
    button = _surface(page).locator(".btn-primary")
    # The sentence comes first, as the page is read.
    assert lands.evaluate(
        "(lands, button) => !!(lands.compareDocumentPosition(button) & 4)", button.element_handle()
    )


def test_answering_on_the_desk_posts_the_answer_and_the_item_resolves_in_place(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (flag, meter) = github.effort("Widgets", tickets=2)
    flag.title, meter.title = "Flag loudness", "Meter peaks"
    _ask(github, flag)
    github.label(meter, ASKED)
    _open(wayfarer, tmp_path, page, spec)
    queue = _queue(page)
    expect(queue.nth(0)).to_contain_text("Flag loudness")

    _surface(page).get_by_role("radio", name="Fail").click()
    _surface(page).get_by_role("button", name="Send answer and resume").click()

    expect(queue.nth(0)).to_contain_text("Answered")
    expect(queue.nth(1)).to_contain_text("Meter peaks")
    assert ASKED not in github.labels(flag.number)
