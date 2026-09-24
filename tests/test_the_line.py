"""Home, the line: what changed since the person last looked, and where everything is (#58).

Driven as the browser does: GitHub is changed underneath a running Wayfarer, each
effort is read, and home is read off the page's stream. How the screen draws it
is `test_the_line_screen.py`'s; these hold what the server says.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from conftest import EFFORT_BRANCH, Launcher, Stream, land, post, quick
from github_stand_in import GitHub, Issue
from wayfarer.read_model import ASKED

pytestmark = pytest.mark.git

# Two questions, as Needs you lists them.
_FLAG, _METER = "question Flag loudness", "question Meter peaks"


def read(url: str, page: Stream, *efforts: Issue) -> None:
    """Every effort read, as the screens that show them ask, and home derived from them."""
    for effort in efforts:
        assert post(f"{url}api/efforts/{effort.number}/read").status_code == 202
    page.until(lambda items: all(f"line:{e.number}" in items for e in efforts))


def _needs(items: dict[str, dict[str, Any]]) -> list[str]:
    """What needs the person, in order: each item's kind and its ticket's title."""
    needs = items.get("needs_you", {"items": []})["items"]
    return [f"{need['kind']} {need['ticket']['title']}" for need in needs]


def test_the_headline_leads_with_what_needs_you_then_the_landings(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, (flag, meter) = github.effort("Widgets", tickets=2)
    land(github, flag)
    github.label(meter, ASKED)
    url = wayfarer.start(env=quick(tmp_path)).url()

    with Stream(url, patience=30, derived=True) as page:
        read(url, page, spec)
        home = page.item(
            "home",
            headline="An agent has stopped to ask you something, and one ticket landed.",
        )

    assert home["repo"] == "octo/widgets"


def test_the_headline_stays_under_fourteen_words_however_much_happened(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, tickets = github.effort("Widgets", tickets=13)
    for ticket in tickets[:12]:
        land(github, ticket)
    github.label(tickets[12], ASKED)
    url = wayfarer.start(env=quick(tmp_path)).url()

    with Stream(url, patience=30, derived=True) as page:
        read(url, page, spec)
        home = page.item(
            "home", headline="An agent has stopped to ask you something, and 12 tickets landed."
        )

    assert len(home["headline"].split()) < 14


def test_one_standfirst_sentence_per_active_effort_from_its_own_counts(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    widgets, (flag, meter, _) = github.effort("Widgets", tickets=3)
    land(github, flag)
    github.label(meter, ASKED)
    shipped, (done,) = github.effort("Gadgets", tickets=1)
    land(github, done)
    url = wayfarer.start(env=quick(tmp_path)).url()

    with Stream(url, patience=30, derived=True) as page:
        read(url, page, widgets, shipped)
        home = page.item("home", moving=1)

    assert home["standfirst"] == [
        "Nothing is building on Widgets, with one ticket waiting on you and 1 of 3 landed."
    ]


def test_each_effort_rows_course_reaches_the_furthest_station_its_tickets_have(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    widgets, (flag, meter, scale) = github.effort("Widgets", tickets=3)
    land(github, flag)
    github.pull_request(meter, base=EFFORT_BRANCH, draft=True)
    github.block(scale, by=meter)
    sliced, _ = github.effort("Gadgets", tickets=2)
    shipped, (done, dropped) = github.effort("Gizmos", tickets=2)
    land(github, done)
    github.close(dropped, "NOT_PLANNED")
    url = wayfarer.start(env=quick(tmp_path)).url()

    with Stream(url, patience=30, derived=True) as page:
        read(url, page, widgets, sliced, shipped)
        rows = {n: page.items[f"line:{n}"] for n in (widgets.number, sliced.number, shipped.number)}

    assert rows[widgets.number]["reached"] == "landed"
    assert rows[widgets.number]["stations"] == {
        "tickets": ["blocked"],
        "build": [],
        "review": ["in_review"],
        "landed": ["landed"],
    }
    assert rows[sliced.number]["reached"] == "tickets"
    assert not rows[sliced.number]["done"]
    # Finished, its course rests; what was closed without landing left the line.
    assert rows[shipped.number]["done"]
    assert rows[shipped.number]["total"] == 1
    assert rows[shipped.number]["stations"]["landed"] == ["landed"]


def test_needs_you_ranks_what_holds_up_the_most_first_and_reranks_live(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, (flag, meter, scale, ruler) = github.effort("Widgets", tickets=4)
    flag.title, meter.title = "Flag loudness", "Meter peaks"
    github.label(flag, ASKED)
    github.block(scale, by=meter)
    github.block(ruler, by=scale)
    url = wayfarer.start(env=quick(tmp_path)).url()

    with Stream(url, patience=30, derived=True) as page:
        read(url, page, spec)
        page.until(lambda items: _needs(items) == [_FLAG])

        # Meter peaks holds up the two tickets behind it as well: it goes first, live.
        github.label(meter, ASKED)
        page.until(
            lambda items: _needs(items) == ["question Meter peaks", "question Flag loudness"]
        )
        first, second = page.items["needs_you"]["items"]

    # Its own ticket and both downstream, of which only the next starts when it lands.
    assert (first["holds_up"], first["starts"]) == (3, 1)
    assert (second["holds_up"], second["starts"]) == (1, 0)


def test_needs_you_gives_a_tie_to_whatever_has_waited_longest(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, (flag, meter, _) = github.effort("Widgets", tickets=3)
    flag.title, meter.title = "Flag loudness", "Meter peaks"
    github.label(meter, ASKED)
    github.label(flag, ASKED)
    url = wayfarer.start(env=quick(tmp_path)).url()

    with Stream(url, patience=30, derived=True) as page:
        read(url, page, spec)
        page.until(
            lambda items: _needs(items) == ["question Meter peaks", "question Flag loudness"]
        )
        page.item(
            "home",
            standfirst=[
                "Nothing is building on Widgets, with two tickets waiting on you and nothing "
                "landed yet."
            ],
        )


def test_needs_you_is_one_list_across_efforts_where_the_bigger_stall_goes_first(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    widgets, (flag,) = github.effort("Widgets", tickets=1)
    gadgets, (meter, scale, ruler) = github.effort("Gadgets", tickets=3)
    flag.title, meter.title = "Flag loudness", "Meter peaks"
    github.label(flag, ASKED)
    github.label(meter, ASKED)
    github.block(scale, by=meter)
    github.block(ruler, by=scale)
    url = wayfarer.start(env=quick(tmp_path)).url()

    with Stream(url, patience=30, derived=True) as page:
        read(url, page, widgets, gadgets)
        page.until(lambda items: _needs(items) == [_METER, _FLAG])
        needs = page.items["needs_you"]["items"]

    # A three-ticket stall in the later effort sits above a one-ticket question.
    assert [(n["effort"]["title"], n["holds_up"]) for n in needs] == [
        ("Gadgets", 3),
        ("Widgets", 1),
    ]


def test_two_items_stalling_one_ticket_both_count_it_and_nothing_sums_them(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, (flag, meter, ruler) = github.effort("Widgets", tickets=3)
    flag.title, meter.title = "Flag loudness", "Meter peaks"
    github.label(flag, ASKED)
    github.label(meter, ASKED)
    github.block(ruler, by=flag)
    github.block(ruler, by=meter)
    url = wayfarer.start(env=quick(tmp_path)).url()

    with Stream(url, patience=30, derived=True) as page:
        read(url, page, spec)
        page.until(lambda items: len(_needs(items)) == 2)
        needs = page.items["needs_you"]["items"]

    # Each holds up itself and the ruler; neither alone starts it.
    assert [(n["holds_up"], n["starts"]) for n in needs] == [(2, 0), (2, 0)]


def test_a_review_waits_from_when_its_pull_request_opened_and_the_longest_goes_first(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, (flag, meter) = github.effort("Widgets", tickets=2)
    flag.title, meter.title = "Flag loudness", "Meter peaks"
    older = github.pull_request(meter, base=EFFORT_BRANCH)
    github.pull_request(flag, base=EFFORT_BRANCH)
    url = wayfarer.start(env={**quick(tmp_path), "WAYFARER_AUTO_MERGE": "0"}).url()

    with Stream(url, patience=30, derived=True) as page:
        read(url, page, spec)
        page.until(lambda items: _needs(items) == ["review Meter peaks", "review Flag loudness"])
        first = page.items["needs_you"]["items"][0]

    assert datetime.fromisoformat(first["since"]) == datetime.fromisoformat(older.created_at)


def test_an_environment_failure_is_pinned_first_and_shipping_an_effort_last(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    widgets, (flag, meter) = github.effort("Widgets", tickets=2)
    flag.title = "Flag loudness"
    github.label(flag, ASKED)
    github.block(meter, by=flag)
    gadgets, (done,) = github.effort("Gadgets", tickets=1)
    land(github, done)
    url = wayfarer.start(env=quick(tmp_path)).url()

    with Stream(url, patience=30, derived=True) as page:
        # The clone has no session image, so the start gate refuses every start.
        for effort in (widgets, gadgets):
            assert post(f"{url}api/efforts/{effort.number}/arm").status_code == 202
        page.until(
            lambda items: (
                [n["kind"] for n in items.get("needs_you", {"items": []})["items"]]
                == ["environment", "question", "ship"]
            )
        )
        page.item("home", headline="Every cascade is paused, and one ticket landed.")


def test_the_last_visit_ends_on_leaving_so_a_reload_keeps_the_headline(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, (flag, meter) = github.effort("Widgets", tickets=2)
    github.now = datetime.now(UTC) - timedelta(days=1)
    land(github, flag)
    url = wayfarer.start(env=quick(tmp_path)).url()

    with Stream(url, patience=30, derived=True) as page:
        read(url, page, spec)
        post(f"{url}api/home/arrived")
        page.item("home", headline="One ticket landed so far.")

        # Leaving then reloading: the page says it left, and never that it arrived.
        post(f"{url}api/home/left")
        with Stream(url, derived=True) as reloaded:
            assert reloaded.item("home")["headline"] == "One ticket landed so far."

        # Coming back is a new visit, counting from when the last one ended.
        post(f"{url}api/home/arrived")
        page.item("home", headline="Nothing has moved since you last looked.")
        github.now = datetime.now(UTC) + timedelta(hours=1)
        land(github, meter)
        page.item("home", headline="One ticket landed since you last looked.")
