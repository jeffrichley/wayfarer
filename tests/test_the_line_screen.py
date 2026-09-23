"""Home, the line, as a person sees it in the browser (#58).

Wayfarer runs in a clone against the GitHub stand-in, and Chromium opens it as
the person's browser does. What the server derives is `test_the_line.py`'s;
these hold what the screen draws from it, and when it says the person came and
went.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, expect
from test_the_line import land

from conftest import Launcher, post
from github_stand_in import GitHub
from specimens import VIEWPORT
from wayfarer.read_model import ASKED

pytestmark = [pytest.mark.git, pytest.mark.browser]

_EFFORT_BRANCH = "effort/1-widgets"


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    opened = browser.new_page(viewport=VIEWPORT)
    yield opened
    opened.close()


def _open(wayfarer: Launcher, tmp_path: Path, page: Page, *efforts: int) -> str:
    """Wayfarer started, its efforts read as a screen that shows them asks, and home open."""
    env = {"WAYFARER_DATA_DIR": str(tmp_path / "data"), "WAYFARER_POLL_ACTIVE": "0.2"}
    url = wayfarer.start(env=env).url()
    for effort in efforts:
        assert post(f"{url}api/efforts/{effort}/read").status_code == 202
    page.goto(url)
    for effort in efforts:
        page.wait_for_selector(f"[data-piece=line-{effort}]")
    return url


def _course(page: Page, effort: int) -> list[str]:
    """How the row draws its course through each station: solid, or dashed."""
    tracks = page.locator(f"[data-piece=line-{effort}] [data-piece^=track-]")
    drawn: list[str] = tracks.evaluate_all(
        "cells => cells.map(c => getComputedStyle(c, '::before').borderTopStyle)"
    )
    return drawn


def test_each_effort_row_draws_its_course_solid_to_the_furthest_station_and_dashed_beyond(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    widgets, (flag, meter) = github.effort("Widgets", tickets=2)
    github.pull_request(flag, base=_EFFORT_BRANCH, draft=True)
    github.label(meter, ASKED)
    shipped, (done,) = github.effort("Gadgets", tickets=1)
    land(github, done)
    _open(wayfarer, tmp_path, page, widgets.number, shipped.number)

    assert _course(page, widgets.number) == ["solid"] * 5 + ["dashed"]
    row = page.locator(f"[data-piece=line-{widgets.number}]")
    expect(row.locator("[data-piece=track-build]")).to_have_text("1 asking you")
    expect(row.locator("[data-piece=track-review]")).to_have_text("1 in review")
    # What waits on the person is found first: it is set bold.
    expect(row.locator("[data-piece=track-build] strong")).to_have_text("1 asking you")
    expect(row.get_by_role("link", name="Widgets")).to_be_visible()

    # A finished effort's course is whole, and no longer a place to go.
    assert _course(page, shipped.number) == ["solid"] * 6
    finished = page.locator(f"[data-piece=line-{shipped.number}]")
    expect(finished.get_by_role("link", name="Gadgets")).to_have_count(0)
    expect(finished.locator("[data-piece=track-landed]")).to_have_text("1 of 1 landed")


def test_home_leads_with_the_headline_and_a_standfirst_sentence_per_active_effort(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (flag, meter) = github.effort("Widgets", tickets=2)
    land(github, flag)
    github.label(meter, ASKED)
    _open(wayfarer, tmp_path, page, spec.number)

    expect(page.locator("[data-piece=headline]")).to_have_text(
        "An agent has stopped to ask you something, and one ticket landed."
    )
    expect(page.locator("[data-piece=standfirst]")).to_have_text(
        "Nothing is building on Widgets, with one ticket waiting on you and 1 of 2 landed."
    )
    expect(page.locator("[data-piece=needs-you]")).to_contain_text("1")


def test_needs_you_on_home_takes_the_live_order_as_it_changes(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (flag, meter, scale) = github.effort("Widgets", tickets=3)
    flag.title, meter.title = "Flag loudness", "Meter peaks"
    github.label(flag, ASKED)
    github.block(scale, by=meter)
    _open(wayfarer, tmp_path, page, spec.number)
    rows = page.locator("[data-piece=needs-you-panel] li")
    expect(rows).to_have_count(1)

    # No reload: Meter peaks holds up more, so it takes the top of the list live.
    github.label(meter, ASKED)
    expect(rows).to_have_count(2)
    expect(rows.nth(0)).to_contain_text("Meter peaks")
    expect(rows.nth(0)).to_contain_text("Holds up 2 tickets")
    expect(rows.nth(1)).to_contain_text("Flag loudness")


def test_refreshing_keeps_the_headline_and_coming_back_counts_from_leaving(
    wayfarer: Launcher, github: GitHub, tmp_path: Path, page: Page
) -> None:
    spec, (flag,) = github.effort("Widgets", tickets=1)
    github.now = datetime.now(UTC) - timedelta(days=1)
    land(github, flag)
    url = _open(wayfarer, tmp_path, page, spec.number)
    headline = page.locator("[data-piece=headline]")
    expect(headline).to_have_text("One ticket landed so far.")

    page.reload()
    page.wait_for_selector(f"[data-piece=line-{spec.number}]")
    expect(headline).to_have_text("One ticket landed so far.")

    # Leaving ends the visit; the next one counts from there.
    page.goto(f"{url}gallery")
    page.goto(url)
    expect(headline).to_have_text("Nothing has moved since you last looked.")
