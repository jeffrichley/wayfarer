"""An effort's ticket graph, as the server derives it for the canvas (#54).

Driven as the browser does: GitHub is changed underneath a running Wayfarer, the
effort is read, and its graph is read off the page's stream. How the canvas draws
it is `test_the_graph_canvas.py`'s; these hold what the server says.
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from conftest import EFFORT_BRANCH, Launcher, Stream, land, post, quick
from github_stand_in import GitHub, Issue
from wayfarer.read_model import ASKED

pytestmark = pytest.mark.git


def graph(wayfarer: Launcher, tmp_path: Path, effort: Issue, **fields: Any) -> dict[str, Any]:
    """The effort's graph, once it has been read and has every one of `fields`."""
    url = wayfarer.start(env=quick(tmp_path)).url()
    with Stream(url, patience=30, derived=True) as page:
        assert post(f"{url}api/efforts/{effort.number}/read").status_code == 202
        page.until(lambda items: f"effort:{effort.number}" in items)
        return page.item(f"graph:{effort.number}", **fields)


def _cards(drawn: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {card["ticket"]["title"]: card for card in drawn["cards"]}


def _wires(drawn: dict[str, Any], tickets: list[Issue]) -> set[tuple[str, str, str]]:
    """Each wire as (from, to, kind), naming tickets by title and the start line as such."""
    title = {ticket.number: ticket.title for ticket in tickets}
    return {
        (
            "start line" if wire["blocker"] is None else title[wire["blocker"]],
            title[wire["blocked"]],
            wire["kind"],
        )
        for wire in drawn["wires"]
    }


def _named(*titles: str, tickets: list[Issue]) -> list[Issue]:
    for ticket, title in zip(tickets, titles, strict=True):
        ticket.title = title
    return tickets


def test_columns_count_steps_from_now_over_work_that_has_not_landed(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, tickets = github.effort("Widgets", tickets=4)
    meter, flag, scale, gate = _named("Meter", "Flag", "Scale", "Gate", tickets=tickets)
    github.block(flag, by=meter)
    github.block(scale, by=flag)
    github.block(gate, by=scale)
    land(github, meter)

    cards = _cards(graph(wayfarer, tmp_path, spec))

    # Meter landed, so Flag is on the frontier: the column beside the start line.
    assert {title: card["step"] for title, card in cards.items()} == {
        "Flag": 0,
        "Scale": 1,
        "Gate": 2,
    }


def test_landed_tickets_fold_into_the_start_line_and_a_ticket_in_the_queue_keeps_its_card(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, tickets = github.effort("Widgets", tickets=3)
    meter, flag, scale = _named("Meter", "Flag", "Scale", tickets=tickets)
    github.block(flag, by=meter)
    github.block(scale, by=flag)
    land(github, meter)
    github.pull_request(flag, base=EFFORT_BRANCH)

    drawn = graph(wayfarer, tmp_path, spec)

    assert [ticket["title"] for ticket in drawn["landed"]] == ["Meter"]
    cards = _cards(drawn)
    assert list(cards) == ["Flag", "Scale"]
    # Landing is not landed: the ticket in the queue could yet come back.
    assert cards["Flag"]["state"] == "landing"
    assert cards["Scale"]["step"] == 1


def test_before_anything_lands_the_start_line_holds_nothing(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, _ = github.effort("Widgets", tickets=2)

    drawn = graph(wayfarer, tmp_path, spec)

    assert drawn["landed"] == []
    assert [card["step"] for card in drawn["cards"]] == [0, 0]


def test_landed_work_is_listed_in_the_order_it_depends_on(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, tickets = github.effort("Widgets", tickets=3)
    scale, flag, meter = _named("Scale", "Flag", "Meter", tickets=tickets)
    github.block(scale, by=flag)
    github.block(flag, by=meter)
    for ticket in tickets:
        land(github, ticket)

    drawn = graph(wayfarer, tmp_path, spec)

    assert [ticket["title"] for ticket in drawn["landed"]] == ["Meter", "Flag", "Scale"]
    assert drawn["cards"] == []


def test_wires_are_solid_where_the_blocker_landed_and_dashed_where_it_has_not(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, tickets = github.effort("Widgets", tickets=5)
    meter, peaks, flag, scale, _ = _named(
        "Meter", "Peaks", "Flag", "Scale", "Room", tickets=tickets
    )
    github.block(flag, by=meter)
    github.block(flag, by=peaks)
    github.block(scale, by=flag)
    land(github, meter)
    land(github, peaks)

    drawn = graph(wayfarer, tmp_path, spec)

    # Two landed blockers leave the start line on one wire; a ticket with nothing
    # to wait on hangs off it on a start-line wire.
    assert _wires(drawn, tickets) == {
        ("start line", "Flag", "met"),
        ("Flag", "Scale", "open"),
        ("start line", "Room", "start"),
    }


def test_an_implied_edge_is_not_drawn_and_its_ticket_says_which_it_was(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, tickets = github.effort("Widgets", tickets=3)
    noise, room, export = _named("Noise", "Room", "Export", tickets=tickets)
    github.block(room, by=noise)
    github.block(export, by=room)
    github.block(export, by=noise)

    drawn = graph(wayfarer, tmp_path, spec)

    assert _wires(drawn, tickets) == {
        ("start line", "Noise", "start"),
        ("Noise", "Room", "open"),
        ("Room", "Export", "open"),
    }
    implied = _cards(drawn)["Export"]["implied"]
    assert implied == [
        {
            "blocker": {"number": noise.number, "title": "Noise"},
            "via": {"number": room.number, "title": "Room"},
        }
    ]
    # Still a blocker, so the foot counts it.
    assert [t["title"] for t in _cards(drawn)["Export"]["waiting_on"]] == ["Noise", "Room"]


def test_an_edge_implied_through_landed_work_folds_away_with_it(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, tickets = github.effort("Widgets", tickets=3)
    noise, room, export = _named("Noise", "Room", "Export", tickets=tickets)
    github.block(room, by=noise)
    github.block(export, by=room)
    github.block(export, by=noise)
    land(github, noise)
    land(github, room)

    drawn = graph(wayfarer, tmp_path, spec)

    assert _wires(drawn, tickets) == {("start line", "Export", "met")}
    assert [edge["via"]["title"] for edge in _cards(drawn)["Export"]["implied"]] == ["Room"]


def test_cards_near_the_frontier_are_full_and_further_out_name_only(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, tickets = github.effort("Widgets", tickets=4)
    for blocker, blocked in pairwise(tickets):
        github.block(blocked, by=blocker)

    drawn = graph(wayfarer, tmp_path, spec)

    assert [card["size"] for card in drawn["cards"]] == ["full", "full", "name-only", "name-only"]


def test_a_ticket_waiting_on_you_keeps_a_full_card_however_far_out(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, tickets = github.effort("Widgets", tickets=3)
    for blocker, blocked in pairwise(tickets):
        github.block(blocked, by=blocker)
    github.label(tickets[2], ASKED)

    drawn = graph(wayfarer, tmp_path, spec)

    assert drawn["cards"][2]["step"] == 2
    assert drawn["cards"][2]["size"] == "full"


def test_a_ticket_knows_everything_it_waits_on_and_everything_it_frees(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, tickets = github.effort("Widgets", tickets=5)
    meter, flag, scale, gate, other = tickets
    github.block(flag, by=meter)
    github.block(scale, by=flag)
    github.block(gate, by=scale)
    github.block(gate, by=other)

    cards = {card["ticket"]["number"]: card for card in graph(wayfarer, tmp_path, spec)["cards"]}

    assert sorted(cards[flag.number]["upstream"]) == [meter.number]
    assert sorted(cards[flag.number]["downstream"]) == [scale.number, gate.number]
    assert sorted(cards[gate.number]["upstream"]) == sorted(
        [meter.number, flag.number, scale.number, other.number]
    )
    assert cards[gate.number]["downstream"] == []


def test_a_ticket_closed_without_landing_leaves_the_graph_and_frees_what_it_blocked(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, tickets = github.effort("Widgets", tickets=2)
    dropped, flag = _named("Dropped", "Flag", tickets=tickets)
    github.block(flag, by=dropped)
    github.close(dropped, reason="NOT_PLANNED")

    drawn = graph(wayfarer, tmp_path, spec)

    assert drawn["landed"] == []
    assert list(_cards(drawn)) == ["Flag"]
    assert _cards(drawn)["Flag"]["step"] == 0
    assert _wires(drawn, tickets) == {("start line", "Flag", "start")}


def test_a_blocked_ticket_says_what_it_is_waiting_on(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, tickets = github.effort("Widgets", tickets=3)
    meter, flag, scale = _named("Meter", "Flag", "Scale", tickets=tickets)
    github.block(scale, by=meter)
    github.block(scale, by=flag)
    land(github, meter)

    cards = _cards(graph(wayfarer, tmp_path, spec))

    assert [t["title"] for t in cards["Scale"]["waiting_on"]] == ["Flag"]
    assert cards["Scale"]["since"] is None
    assert cards["Scale"]["at_cap"] is False
