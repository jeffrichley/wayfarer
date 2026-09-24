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
from wayfarer.joining import land_it_comment
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


def test_a_landing_ticket_holds_its_dependents_until_it_has_really_landed(
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

    url = wayfarer.start(env=_QUICK).url()
    with Stream(url) as page:
        _read(url, page, spec)
        assert post(f"{url}api/tickets/{ticket.number}/let-it-land").status_code == 202
        _ticket(page, ticket, state="landing", place_in_line=1)

    [pull] = github.pulls()
    assert pull.draft is False
    assert HELD not in github.labels(ticket.number)


def test_a_draft_marked_ready_by_hand_on_github_has_its_stale_hold_cleared(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (ticket,) = github.effort("Widgets", tickets=1)
    _open_held(github, ticket)
    url = wayfarer.start(env=_QUICK).url()

    with Stream(url) as page:
        _read(url, page, spec)
        _ticket(page, ticket, state="held")
        [pull] = github.pulls()
        # Ready, and nothing else: the label is Wayfarer's to clear (#21).
        github.ready(pull)
        _ticket(page, ticket, state="landing", place_in_line=1)

    assert HELD not in github.labels(ticket.number)


def test_a_stale_hold_github_will_not_clear_is_not_asked_about_again_until_it_changes(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (ticket,) = github.effort("Widgets", tickets=1)
    _open_held(github, ticket)
    [pull] = github.pulls()
    github.ready(pull)
    github.forbid(f"/labels/{HELD}")
    url = wayfarer.start(env=_QUICK).url()

    with Stream(url) as page:
        for _ in range(3):
            _read(url, page, spec)
        assert page.items[f"ticket:{ticket.number}"]["state"] == "held"
        refused = [r.status for r in github.requests if r.method == "DELETE"]

        github.unforbid(f"/labels/{HELD}")
        github.label(ticket, "needs-thought")
        _ticket(page, ticket, state="landing")

    assert refused == [403]


_MANUAL = _QUICK | {"WAYFARER_AUTO_MERGE": "0"}


def test_with_auto_merge_off_land_it_puts_a_clean_green_pull_request_the_person_opened_in_line(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (ticket,) = github.effort("Widgets", tickets=1)
    # Opened by the person whose token Wayfarer holds, so GitHub refuses them an approval.
    pull = github.pull_request(ticket, base=_EFFORT_BRANCH, checks="SUCCESS")
    url = wayfarer.start(env=_MANUAL).url()

    with Stream(url) as page:
        _read(url, page, spec)
        _ticket(page, ticket, state="in_review", place_in_line=None)
        assert post(f"{url}api/tickets/{ticket.number}/land-it").status_code == 202
        _ticket(page, ticket, state="landing", place_in_line=1)

    assert pull.review is None
    assert not [r for r in github.requests if r.status >= 400]


def test_with_auto_merge_off_an_approving_review_on_github_puts_it_in_line(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (ticket,) = github.effort("Widgets", tickets=1)
    pull = github.pull_request(ticket, base=_EFFORT_BRANCH, author="grace")
    url = wayfarer.start(env=_MANUAL).url()

    with Stream(url) as page:
        _read(url, page, spec)
        _ticket(page, ticket, state="in_review")
        pull.review = "APPROVED"
        _ticket(page, ticket, state="landing", place_in_line=1)


def test_land_it_counts_only_when_the_person_whose_token_wayfarer_holds_said_it(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (ticket,) = github.effort("Widgets", tickets=1)
    pull = github.pull_request(ticket, base=_EFFORT_BRANCH)
    # Wayfarer's words, copied onto the ticket by someone else.
    github.comment(ticket, land_it_comment(pull.number), by="mallory")
    # And the person's own, naming another pull request, or mangled.
    github.comment(ticket, land_it_comment(pull.number + 1))
    github.comment(ticket, "<!-- wayfarer:land-it {mangled} -->")
    github.comment(ticket, "<!-- wayfarer:land-it [3] -->")
    url = wayfarer.start(env=_MANUAL).url()

    with Stream(url) as page:
        _read(url, page, spec)
        assert page.items[f"ticket:{ticket.number}"]["state"] == "in_review"


def test_neither_command_acts_on_a_ticket_in_any_other_state(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, tickets = github.effort("Widgets", tickets=5)
    takeable, draft, failing, held, landing = tickets
    github.pull_request(draft, base=_EFFORT_BRANCH, draft=True)
    github.pull_request(failing, base=_EFFORT_BRANCH, checks="FAILURE")
    github.pull_request(landing, base=_EFFORT_BRANCH, review="APPROVED")
    _open_held(github, held)
    url = wayfarer.start(env=_MANUAL).url()

    with Stream(url) as page:
        _read(url, page, spec)
        _ticket(page, landing, state="landing")
        _ticket(page, held, state="held")
        before = [(p.number, p.draft, p.review) for p in github.pulls()]
        for ticket in (takeable, draft, failing, landing, Issue(999, "Unread")):
            assert post(f"{url}api/tickets/{ticket.number}/let-it-land").status_code == 202
        for ticket in (takeable, draft, failing, held, landing, Issue(999, "Unread")):
            assert post(f"{url}api/tickets/{ticket.number}/land-it").status_code == 202
        # A read after them all, so each has had its turn by the time it shows.
        _read(url, page, spec)

    assert [(p.number, p.draft, p.review) for p in github.pulls()] == before
    assert [t.comments for t in tickets] == [[]] * 5
    assert HELD in github.labels(held.number)
