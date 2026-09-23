"""The page's one stream: a snapshot on connect, then upserts and removals by id.

Commands go the other way, as posts that say nothing about their result; the
effect comes back over the stream like any other change (ADR-0004).
"""

from __future__ import annotations

import pytest

from conftest import Launcher, Stream, post
from github_stand_in import GitHub
from wayfarer.read_model import HELD

pytestmark = pytest.mark.git


def test_a_fresh_page_gets_a_snapshot_then_live_upserts_by_id(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (first, second) = github.effort("Widgets that fold", tickets=2)
    url = wayfarer.start().url()

    with Stream(url) as page:
        assert page.next() == {"kind": "snapshot", "items": []}
        post(f"{url}api/efforts/{spec.number}/read")
        effort = page.item(f"effort:{spec.number}")

        assert effort["title"] == "Widgets that fold"
        assert [page.items[id]["number"] for id in effort["tickets"]] == [
            first.number,
            second.number,
        ]
        assert {event["kind"] for event in page.received[1:]} == {"upsert"}


def test_a_page_opened_later_gets_what_is_already_known_in_its_snapshot(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (ticket,) = github.effort("Known", tickets=1)
    url = wayfarer.start().url()
    with Stream(url) as first:
        post(f"{url}api/efforts/{spec.number}/read")
        first.item(f"effort:{spec.number}")

    with Stream(url) as later:
        snapshot = later.next()

    assert snapshot["kind"] == "snapshot"
    assert {item["id"] for item in snapshot["items"]} == {
        f"effort:{spec.number}",
        f"ticket:{ticket.number}",
    }


def test_a_command_is_accepted_and_says_nothing_of_its_result(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, _ = github.effort("Quiet", tickets=1)
    url = wayfarer.start().url()

    with Stream(url) as page:
        accepted = post(f"{url}api/efforts/{spec.number}/read")
        missing = post(f"{url}api/efforts/404/read")

        assert (accepted.status_code, accepted.content) == (202, b"")
        assert (missing.status_code, missing.content) == (202, b"")
        assert page.item(f"effort:{spec.number}")["kind"] == "effort"
        assert "no issue #404" in page.item("effort:404")["reason"]


def test_a_change_to_one_ticket_sends_that_ticket_alone(wayfarer: Launcher, github: GitHub) -> None:
    spec, (changed, _) = github.effort("Small news", tickets=2)
    other, _ = github.effort("Elsewhere", tickets=0)
    url = wayfarer.start().url()
    with Stream(url) as page:
        post(f"{url}api/efforts/{spec.number}/read")
        page.item(f"effort:{spec.number}")

        changed.labels.append(HELD)
        before = len(page.received)
        post(f"{url}api/efforts/{spec.number}/read")
        page.item(f"ticket:{changed.number}", state="held")
        # A later read's arrival marks that nothing more came of the first.
        post(f"{url}api/efforts/{other.number}/read")
        page.until(lambda items: f"effort:{other.number}" in items)
        news = page.received[before:]

    assert [event["item"]["id"] for event in news] == [
        f"ticket:{changed.number}",
        f"effort:{other.number}",
    ]


def test_a_ticket_that_leaves_an_effort_is_removed(wayfarer: Launcher, github: GitHub) -> None:
    spec, (staying, leaving) = github.effort("Shrinking", tickets=2)
    url = wayfarer.start().url()
    with Stream(url) as page:
        post(f"{url}api/efforts/{spec.number}/read")
        page.item(f"effort:{spec.number}")

        leaving.parent = None
        post(f"{url}api/efforts/{spec.number}/read")
        page.until(lambda items: f"ticket:{leaving.number}" not in items)

        assert page.received[-1] == {"kind": "removal", "id": f"ticket:{leaving.number}"}
        assert page.items[f"effort:{spec.number}"]["tickets"] == [f"ticket:{staying.number}"]


def test_an_effort_that_cannot_be_read_takes_its_tickets_with_it(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (ticket,) = github.effort("Vanishing", tickets=1)
    url = wayfarer.start().url()
    with Stream(url) as page:
        post(f"{url}api/efforts/{spec.number}/read")
        page.item(f"ticket:{ticket.number}")

        github.delete(spec)
        post(f"{url}api/efforts/{spec.number}/read")
        page.item(f"effort:{spec.number}", kind="effort_unreadable")
        page.until(lambda items: f"ticket:{ticket.number}" not in items)


def test_a_dropped_connection_resumes_from_the_last_event_seen_with_no_gap_and_no_repeat(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (first, second) = github.effort("Interrupted", tickets=2)
    url = wayfarer.start().url()
    with Stream(url) as watcher:
        page = Stream(url)
        post(f"{url}api/efforts/{spec.number}/read")
        page.item(f"effort:{spec.number}")
        watcher.item(f"effort:{spec.number}")
        page.close()
        dropped_at = page.last_event_id

        # What happens while the page is away, watched from a second page.
        first.labels.append(HELD)
        second.parent = None
        post(f"{url}api/efforts/{spec.number}/read")
        watcher.until(lambda items: f"ticket:{second.number}" not in items)
        missed = watcher.received[watcher.ids.index(dropped_at) + 1 :]

        with Stream(url, last_event_id=dropped_at) as resumed:
            resumed.items = page.items
            caught_up = [resumed.next() for _ in missed]

            assert caught_up == missed
            assert resumed.items == watcher.items
            # Anything after is new, not the missed events again.
            second.parent = spec.number
            post(f"{url}api/efforts/{spec.number}/read")
            news = resumed.until(lambda items: len(items[f"effort:{spec.number}"]["tickets"]) == 2)

    assert [event["kind"] for event in missed] == ["upsert", "upsert", "removal"]
    assert [event["item"]["id"] for event in news] == [
        f"ticket:{second.number}",
        f"effort:{spec.number}",
    ]


def test_a_reconnect_the_server_cannot_resume_gets_a_fresh_snapshot(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (ticket,) = github.effort("Restarted", tickets=1)
    url = wayfarer.start().url()
    with Stream(url) as page:
        post(f"{url}api/efforts/{spec.number}/read")
        page.item(f"ticket:{ticket.number}")

    # An id from a Wayfarer that has since restarted, and one that was never an id.
    for last_event_id in ("an-earlier-wayfarer-12", "nonsense"):
        with Stream(url, last_event_id=last_event_id) as reconnected:
            snapshot = reconnected.next()

        assert snapshot["kind"] == "snapshot"
        assert f"ticket:{ticket.number}" in {item["id"] for item in snapshot["items"]}


def test_two_pages_open_at_once_both_see_every_change(wayfarer: Launcher, github: GitHub) -> None:
    spec, (ticket,) = github.effort("Shared", tickets=1)
    url = wayfarer.start().url()

    with Stream(url) as left, Stream(url) as right:
        post(f"{url}api/efforts/{spec.number}/read")
        left.item(f"effort:{spec.number}")
        right.item(f"effort:{spec.number}")
        ticket.labels.append(HELD)
        post(f"{url}api/efforts/{spec.number}/read")
        left.item(f"ticket:{ticket.number}", state="held")
        right.item(f"ticket:{ticket.number}", state="held")

        assert left.items == right.items
        assert left.received == right.received


def test_a_page_left_open_does_not_keep_ctrl_c_from_stopping_wayfarer(
    wayfarer: Launcher,
) -> None:
    instance = wayfarer.start()
    with Stream(instance.url()) as page:
        page.next()

        assert instance.interrupt() == 0
