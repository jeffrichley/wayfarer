"""A clean, green, ready pull request lands itself, and Wayfarer closes its ticket.

Driven as a person does: Wayfarer runs in a clone, a page asks for an effort, and
GitHub is changed underneath it as a person or the cascade would change it. What
landed is read off the stand-in and off the page's stream.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from conftest import Launcher, Stream, post
from github_stand_in import TOKEN, GitHub, Issue
from wayfarer.github import GitHub as Client
from wayfarer.github import Repo
from wayfarer.outcome import Outcome
from wayfarer.pull_requests import LANDED_MARKER, PullRequestGate
from wayfarer.read_model import HELD
from wayfarer.settings import Settings

pytestmark = pytest.mark.git

_EFFORT_BRANCH = "effort/1-widgets"

# Fast enough that a change on GitHub is seen within a test's patience.
_QUICK = {"WAYFARER_POLL_ACTIVE": "0.2"}


def _merges(github: GitHub) -> list[str]:
    return [r.path for r in github.requests if r.method == "PUT" and r.path.endswith("/merge")]


def _landed(page: Stream, ticket: Issue) -> dict[str, object]:
    """The ticket as the page holds it once it has landed and been closed."""
    return page.item(f"ticket:{ticket.number}", state="landed", open=False)


def test_a_ready_pull_request_with_no_checks_lands_and_its_ticket_is_closed_with_a_marked_comment(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (ticket,) = github.effort("Widgets", tickets=1)
    pull = github.pull_request(ticket, base=_EFFORT_BRANCH)
    url = wayfarer.start().url()

    with Stream(url) as page:
        post(f"{url}api/efforts/{spec.number}/read")
        landed = _landed(page, ticket)

    [merged] = github.pulls()
    assert merged.state == "MERGED"
    assert landed["pull_request"] == {
        "number": pull.number,
        "branch": pull.head,
        "base": _EFFORT_BRANCH,
        "draft": False,
        "merged": True,
        "head_commit": pull.head_commit,
        "merge_commit": merged.merge_commit,
        "checks": None,
        "approved": False,
    }
    assert ticket.state_reason == "COMPLETED"
    assert ticket.comments == [
        f"Landed on `{_EFFORT_BRANCH}` at {merged.merge_commit}.\n\n{LANDED_MARKER}"
    ]


def test_a_pending_check_waits_and_lands_once_it_passes(wayfarer: Launcher, github: GitHub) -> None:
    spec, (ticket,) = github.effort("Widgets", tickets=1)
    pull = github.pull_request(ticket, base=_EFFORT_BRANCH, checks="PENDING")
    url = wayfarer.start(env=_QUICK).url()

    with Stream(url) as page:
        post(f"{url}api/efforts/{spec.number}/read")
        page.item(f"effort:{spec.number}")
        assert page.items[f"ticket:{ticket.number}"]["state"] == "in_review"
        assert _merges(github) == []

        pull.checks = "SUCCESS"
        _landed(page, ticket)


def test_a_failing_check_never_lands(wayfarer: Launcher, github: GitHub) -> None:
    spec, (ticket,) = github.effort("Widgets", tickets=1)
    github.pull_request(ticket, base=_EFFORT_BRANCH, checks="FAILURE")
    url = wayfarer.start().url()

    with Stream(url) as page:
        post(f"{url}api/efforts/{spec.number}/read")
        page.item(f"effort:{spec.number}")

    assert _merges(github) == []
    assert ticket.state == "OPEN"


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


def test_a_draft_stays_held_across_a_restart_and_lands_once_a_person_lets_it(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (ticket,) = github.effort("Widgets", tickets=1)
    _open_held(github, ticket)

    for _ in range(2):
        running = wayfarer.start(env=_QUICK)
        url = running.url()
        with Stream(url) as page:
            post(f"{url}api/efforts/{spec.number}/read")
            page.item(f"effort:{spec.number}")
            assert page.items[f"ticket:{ticket.number}"]["state"] == "held"
        assert running.interrupt() == 0
    assert _merges(github) == []

    # Let it land: ready, and the label cleared. GitHub is all the gate reads.
    url = wayfarer.start(env=_QUICK).url()
    with Stream(url) as page:
        post(f"{url}api/efforts/{spec.number}/read")
        page.item(f"ticket:{ticket.number}", state="held")
        [pull] = github.pulls()
        pull.draft = False
        ticket.labels.remove(HELD)
        _landed(page, ticket)


def test_a_pull_request_merged_by_hand_has_its_ticket_closed_on_the_next_read(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (ticket,) = github.effort("Widgets", tickets=1)
    pull = github.pull_request(ticket, base=_EFFORT_BRANCH, draft=True)
    github.merged(pull)
    url = wayfarer.start().url()

    with Stream(url) as page:
        post(f"{url}api/efforts/{spec.number}/read")
        _landed(page, ticket)

    assert _merges(github) == []
    assert ticket.comments == [
        f"Landed on `{_EFFORT_BRANCH}` at {pull.merge_commit}.\n\n{LANDED_MARKER}"
    ]


def _reads(github: GitHub, count: int) -> None:
    """Wait until the stand-in has answered `count` reads of an effort. Reads of one
    effort run one at a time, so every earlier read has finished by then."""
    deadline = time.monotonic() + 20
    while len(github.queries) < count:
        assert time.monotonic() < deadline, f"only {len(github.queries)} reads came"
        time.sleep(0.05)


def test_a_merge_github_refuses_is_not_retried_until_the_pull_request_changes(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (ticket,) = github.effort("Widgets", tickets=1)
    pull = github.pull_request(ticket, base=_EFFORT_BRANCH, mergeable=False)
    url = wayfarer.start().url()

    with Stream(url) as page:
        for _ in range(3):
            post(f"{url}api/efforts/{spec.number}/read")
        _reads(github, 3)
        # A refused write is re-read in case it landed (ADR-0003); retrying on that
        # read would ask GitHub again without end.
        assert len(_merges(github)) == 1
        assert ticket.state == "OPEN"
        assert ticket.comments == []

        # The conflict fixed with a new commit, as a person pushes one.
        pull.mergeable = True
        pull.head_commit = "f" * 40
        post(f"{url}api/efforts/{spec.number}/read")
        _landed(page, ticket)
