"""The review desk: what needs the person, worked through in an order that holds still (#57).

Driven as the browser does: GitHub is changed underneath a running Wayfarer, and
the desk is read off the page's stream. How the screen draws it is
`test_the_desk_screen.py`'s; these hold what the server says.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from conftest import EFFORT_BRANCH, Launcher, Stream, land, post, quick
from github_stand_in import GitHub, Issue
from wayfarer.read_model import ASKED, HELD

pytestmark = pytest.mark.git


def read(url: str, page: Stream, *efforts: Issue) -> None:
    """Every effort read, as the screens that show them ask, and home derived from them."""
    for effort in efforts:
        assert post(f"{url}api/efforts/{effort.number}/read").status_code == 202
    page.until(lambda items: all(f"line:{e.number}" in items for e in efforts))


def _desk(items: dict[str, dict[str, Any]]) -> list[str]:
    """The desk's queue as it stands: each entry's ticket, and whether it is new or resolved."""
    entries = items.get("desk", {"entries": []})["entries"]
    return [
        entry["need"]["ticket"]["title"]
        + (" (new)" if entry["new"] else "")
        + (f" ({entry['resolved']})" if entry["resolved"] else "")
        for entry in entries
    ]


def _live(items: dict[str, dict[str, Any]]) -> list[str]:
    """Needs you's live order, as home shows it."""
    return [need["ticket"]["title"] for need in items.get("needs_you", {"items": []})["items"]]


def _arrive(url: str) -> None:
    assert post(f"{url}api/desk/arrived").status_code == 202


def test_the_desk_holds_its_order_while_home_reranks_live(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, (flag, meter, scale) = github.effort("Widgets", tickets=3)
    flag.title, meter.title = "Flag loudness", "Meter peaks"
    github.label(flag, ASKED)
    github.label(meter, ASKED)
    url = wayfarer.start(env=quick(tmp_path)).url()

    with Stream(url, patience=30, derived=True) as page:
        read(url, page, spec)
        # Before the person has arrived, the desk is the live order.
        page.until(lambda items: _desk(items) == ["Flag loudness", "Meter peaks"])
        _arrive(url)

        # Meter peaks now holds up the scale as well, so it goes first on home.
        github.block(scale, by=meter)
        # A new edge bumps no issue's update time, so the page asks for a read.
        read(url, page, spec)
        page.until(lambda items: _live(items) == ["Meter peaks", "Flag loudness"])
        # The desk stays as it was, though what each holds up is said live.
        page.until(lambda items: items["desk"]["entries"][1]["need"]["holds_up"] == 2)
        assert _desk(page.items) == ["Flag loudness", "Meter peaks"]


def test_coming_back_to_the_desk_reranks_it(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, (flag, meter, scale) = github.effort("Widgets", tickets=3)
    flag.title, meter.title = "Flag loudness", "Meter peaks"
    github.label(flag, ASKED)
    github.label(meter, ASKED)
    url = wayfarer.start(env=quick(tmp_path)).url()

    with Stream(url, patience=30, derived=True) as page:
        read(url, page, spec)
        page.until(lambda items: _desk(items) == ["Flag loudness", "Meter peaks"])
        _arrive(url)
        github.block(scale, by=meter)
        # A new edge bumps no issue's update time, so the page asks for a read.
        read(url, page, spec)
        page.until(lambda items: _live(items) == ["Meter peaks", "Flag loudness"])

        _arrive(url)
        page.until(lambda items: _desk(items) == ["Meter peaks", "Flag loudness"])


def test_a_new_item_joins_the_bottom_of_the_desk_marked_new(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, (flag, meter, scale) = github.effort("Widgets", tickets=3)
    flag.title, meter.title = "Flag loudness", "Meter peaks"
    github.label(flag, ASKED)
    github.block(scale, by=meter)
    url = wayfarer.start(env=quick(tmp_path)).url()

    with Stream(url, patience=30, derived=True) as page:
        read(url, page, spec)
        page.until(lambda items: _desk(items) == ["Flag loudness"])
        _arrive(url)

        # It holds up more than what is already there, and still goes at the bottom.
        github.label(meter, ASKED)
        page.until(lambda items: _live(items) == ["Meter peaks", "Flag loudness"])
        page.until(lambda items: _desk(items) == ["Flag loudness", "Meter peaks (new)"])

        # Coming back, it is ranked with the rest and no longer new.
        _arrive(url)
        page.until(lambda items: _desk(items) == ["Meter peaks", "Flag loudness"])


def test_a_resolved_item_stays_in_place_saying_what_happened(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, (flag, meter, scale) = github.effort("Widgets", tickets=3)
    flag.title, meter.title, scale.title = "Flag loudness", "Meter peaks", "Scale bars"
    github.label(flag, ASKED)
    github.label(meter, ASKED)
    github.label(scale, ASKED)
    url = wayfarer.start(env=quick(tmp_path)).url()

    with Stream(url, patience=30, derived=True) as page:
        read(url, page, spec)
        page.until(lambda items: len(_desk(items)) == 3)
        _arrive(url)

        # Answered on GitHub, and landed: both gone from home, both kept on the desk.
        github.unlabel(flag, ASKED)
        land(github, meter)
        page.until(lambda items: _live(items) == ["Scale bars"])
        page.until(
            lambda items: (
                _desk(items) == ["Flag loudness (Answered)", "Meter peaks (Landed)", "Scale bars"]
            )
        )

        # Coming back, what was resolved has gone.
        _arrive(url)
        page.until(lambda items: _desk(items) == ["Scale bars"])


def test_a_hold_let_go_and_a_ticket_closed_unlanded_each_say_so(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, (flag, meter) = github.effort("Widgets", tickets=2)
    flag.title, meter.title = "Flag loudness", "Meter peaks"
    github.label(flag, HELD)
    github.label(meter, ASKED)
    url = wayfarer.start(env=quick(tmp_path)).url()

    with Stream(url, patience=30, derived=True) as page:
        read(url, page, spec)
        page.until(lambda items: len(_desk(items)) == 2)
        _arrive(url)

        github.unlabel(flag, HELD)
        github.close(meter, "NOT_PLANNED")
        page.until(
            lambda items: (
                _desk(items) == ["Flag loudness (Released)", "Meter peaks (Closed without landing)"]
            )
        )


def test_a_review_names_the_tickets_that_start_the_moment_it_lands(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, (flag, meter, scale) = github.effort("Widgets", tickets=3)
    flag.title, meter.title = "Flag loudness", "Meter peaks"
    github.pull_request(flag, base=EFFORT_BRANCH)
    github.block(meter, by=flag)
    github.block(scale, by=meter)
    url = wayfarer.start(env={**quick(tmp_path), "WAYFARER_AUTO_MERGE": "0"}).url()

    with Stream(url, patience=30, derived=True) as page:
        read(url, page, spec)
        page.until(lambda items: _live(items) == ["Flag loudness"])
        review = page.items["needs_you"]["items"][0]

    # It holds up all three, and only the next one starts when it lands.
    assert review["holds_up"] == 3
    assert review["starting"] == [{"number": meter.number, "title": "Meter peaks"}]


def test_an_environment_failure_arriving_while_the_person_works_still_goes_first(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, (flag, _) = github.effort("Widgets", tickets=2)
    flag.title = "Flag loudness"
    github.label(flag, ASKED)
    url = wayfarer.start(env=quick(tmp_path)).url()

    with Stream(url, patience=30, derived=True) as page:
        read(url, page, spec)
        page.until(lambda items: _desk(items) == ["Flag loudness"])
        _arrive(url)

        # The clone has no session image, so the start gate refuses the cascade.
        post(f"{url}api/efforts/{spec.number}/arm")
        page.until(lambda items: len(items["desk"]["entries"]) == 2)
        first, second = page.items["desk"]["entries"]

    # It stopped everything, so nothing sits above it, new or not.
    assert (first["need"]["kind"], first["new"]) == ("environment", True)
    assert second["need"]["ticket"]["title"] == "Flag loudness"
