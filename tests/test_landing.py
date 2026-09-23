"""A clean, green, ready pull request joins the merge queue, and reads as Landing.

Driven as a person does: Wayfarer runs in a clone, a page asks for an effort, and
GitHub is changed underneath it as a person or the cascade would change it. What
the page is told is read off its stream.

The clone has no session image, so nothing here can be re-tested and nothing
leaves the line: that is the queue's own business (`test_the_merge_queue.py`).
Joining, the line, and closing what merged by hand need no image, and are held
here at the HTTP surface.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from conftest import Launcher, Stream, post
from github_stand_in import TOKEN, GitHub, Issue
from wayfarer.github import GitHub as Client
from wayfarer.github import Repo
from wayfarer.merge_queue import LANDED_MARKER
from wayfarer.outcome import Outcome
from wayfarer.pull_requests import PullRequestGate
from wayfarer.read_model import HELD
from wayfarer.settings import Settings

pytestmark = pytest.mark.git

_EFFORT_BRANCH = "effort/1-widgets"

# Fast enough that a change on GitHub is seen within a test's patience.
_QUICK = {"WAYFARER_POLL_ACTIVE": "0.2"}


def _ticket(page: Stream, ticket: Issue, **fields: Any) -> dict[str, Any]:
    return page.item(f"ticket:{ticket.number}", **fields)


def _read(url: str, page: Stream, spec: Issue) -> dict[str, Any]:
    """Ask for the effort, and wait for the page to hold it."""
    post(f"{url}api/efforts/{spec.number}/read")
    return page.item(f"effort:{spec.number}")


def test_a_ready_pull_request_with_no_checks_joins_the_queue_at_the_front(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (ticket,) = github.effort("Widgets", tickets=1)
    github.pull_request(ticket, base=_EFFORT_BRANCH)
    url = wayfarer.start().url()

    with Stream(url) as page:
        post(f"{url}api/efforts/{spec.number}/read")
        landing = _ticket(page, ticket, state="landing")

    assert landing["place_in_line"] == 1
    assert landing["open"] is True


def test_a_queued_ticket_holds_its_dependents_until_it_has_really_landed(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (first, second) = github.effort("Widgets", tickets=2)
    github.block(second, by=first)
    pull = github.pull_request(first, base=_EFFORT_BRANCH)
    url = wayfarer.start(env=_QUICK).url()

    with Stream(url) as page:
        _read(url, page, spec)
        assert page.items[f"ticket:{first.number}"]["state"] == "landing"
        # Landing is not Landed: the blocker is still open.
        assert page.items[f"ticket:{second.number}"]["state"] == "blocked"

        github.merged(pull)
        _ticket(page, first, state="landed", open=False)
        _ticket(page, second, state="takeable")


def test_the_line_is_in_the_order_pull_requests_became_ready_and_a_restart_finds_it_again(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, tickets = github.effort("Widgets", tickets=3)
    pulls = [github.pull_request(t, base=_EFFORT_BRANCH, draft=True) for t in tickets]
    for index in (2, 0, 1):
        github.ready(pulls[index])

    lines = []
    for _ in range(2):
        running = wayfarer.start()
        url = running.url()
        with Stream(url) as page:
            _read(url, page, spec)
            lines.append([page.items[f"ticket:{t.number}"]["place_in_line"] for t in tickets])
        assert running.interrupt() == 0

    assert lines == [[2, 3, 1], [2, 3, 1]]


def test_a_pending_check_waits_and_joins_once_it_passes(wayfarer: Launcher, github: GitHub) -> None:
    spec, (ticket,) = github.effort("Widgets", tickets=1)
    pull = github.pull_request(ticket, base=_EFFORT_BRANCH, checks="PENDING")
    url = wayfarer.start(env=_QUICK).url()

    with Stream(url) as page:
        _read(url, page, spec)
        waiting = page.items[f"ticket:{ticket.number}"]
        assert (waiting["state"], waiting["place_in_line"]) == ("in_review", None)

        pull.checks = "SUCCESS"
        _ticket(page, ticket, state="landing", place_in_line=1)


def test_a_failing_check_never_joins(wayfarer: Launcher, github: GitHub) -> None:
    spec, (ticket,) = github.effort("Widgets", tickets=1)
    github.pull_request(ticket, base=_EFFORT_BRANCH, checks="FAILURE")
    url = wayfarer.start().url()

    with Stream(url) as page:
        _read(url, page, spec)
        failing = page.items[f"ticket:{ticket.number}"]

    assert (failing["state"], failing["place_in_line"]) == ("in_review", None)


def _open_held(github: GitHub, ticket: Issue) -> None:
    """The draft the gate opens for a session that left a blocking finding."""
    client = Client(
        Repo(github.owner, github.name), Settings(github_api=github.api, github_token=TOKEN)
    )
    outcome = Outcome.model_validate(
        {
            "status": "done",
            "summary": "Added the widget.",
            "open_findings": [
                {"axis": "spec", "kind": "blocking", "what": "No limit.", "cites": "A limit"}
            ],
            "assumptions": [],
        }
    )
    asyncio.run(
        PullRequestGate(client).open(
            ticket=ticket.number,
            title=ticket.title,
            branch=f"ticket/{ticket.number}-widget",
            effort_branch=_EFFORT_BRANCH,
            outcome=outcome,
        )
    )


def test_a_draft_stays_held_across_a_restart_and_joins_once_a_person_lets_it(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (ticket,) = github.effort("Widgets", tickets=1)
    _open_held(github, ticket)

    for _ in range(2):
        running = wayfarer.start(env=_QUICK)
        url = running.url()
        with Stream(url) as page:
            _read(url, page, spec)
            held = page.items[f"ticket:{ticket.number}"]
            assert (held["state"], held["place_in_line"]) == ("held", None)
        assert running.interrupt() == 0

    # Let it land: ready, and the label cleared. GitHub is all the gate reads.
    url = wayfarer.start(env=_QUICK).url()
    with Stream(url) as page:
        _read(url, page, spec)
        [pull] = github.pulls()
        github.ready(pull)
        ticket.labels.remove(HELD)
        _ticket(page, ticket, state="landing", place_in_line=1)


def test_a_pull_request_merged_by_hand_has_its_ticket_closed_on_the_next_read(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (ticket,) = github.effort("Widgets", tickets=1)
    pull = github.pull_request(ticket, base=_EFFORT_BRANCH, draft=True)
    github.merged(pull)
    url = wayfarer.start().url()

    with Stream(url) as page:
        post(f"{url}api/efforts/{spec.number}/read")
        _ticket(page, ticket, state="landed", open=False)

    assert ticket.comments == [
        f"Landed on `{_EFFORT_BRANCH}` at {pull.merge_commit}.\n\n{LANDED_MARKER}"
    ]


def test_a_ticket_pull_request_into_the_trunk_never_joins_the_queue(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (ticket,) = github.effort("Widgets", tickets=1)
    # The trunk meets an effort once, through a person's review, never a ticket's.
    pull = github.pull_request(ticket, base="main")
    url = wayfarer.start().url()

    with Stream(url) as page:
        effort = _read(url, page, spec)
        read = page.items[f"ticket:{ticket.number}"]

    assert effort["trunk"] == "main"
    assert read["place_in_line"] is None
    assert pull.state == "OPEN"
