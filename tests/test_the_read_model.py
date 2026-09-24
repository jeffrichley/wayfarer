"""The read model: an effort's whole ticket graph, read from GitHub on every ask.

An effort is a spec issue, and its tickets are that issue's sub-issues. Each read
is one GraphQL query of the stand-in; nothing is kept between reads. A read is
asked for by a command, and what it found arrives over the page's stream.
"""

from __future__ import annotations

import socket
import subprocess
from pathlib import Path
from typing import Any

import pytest

from conftest import Launcher, Stream, post
from github_stand_in import GitHub
from wayfarer.read_model import ASKED, HELD

pytestmark = pytest.mark.git


def _read(url: str, effort: int) -> dict[str, Any]:
    """The first read of `effort`, with its tickets in place of their ids."""
    with Stream(url) as page:
        post(f"{url}api/efforts/{effort}/read")
        read = page.item(f"effort:{effort}")
        return read | {"tickets": [page.items[id] for id in read["tickets"]]}


def _unreadable(url: str, effort: int) -> str:
    """Why a read of `effort` failed, as the page is told."""
    with Stream(url) as page:
        post(f"{url}api/efforts/{effort}/read")
        reason: str = page.item(f"effort:{effort}", kind="effort_unreadable")["reason"]
        return reason


def _tickets(effort: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {ticket["number"]: ticket for ticket in effort["tickets"]}


def test_one_read_returns_every_ticket_with_its_labels_assignees_blockers_and_pr(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (first, second, third) = github.effort("Widgets that fold", tickets=3)
    first.labels.append("ready-for-agent")
    second.assignees.append("octocat")
    github.block(second, by=first)
    github.block(third, by=first)
    github.block(third, by=second)
    pull = github.pull_request(second, draft=True, checks="PENDING")
    url = wayfarer.start().url()

    effort = _read(url, spec.number)

    assert effort["number"] == spec.number
    assert effort["title"] == "Widgets that fold"
    tickets = _tickets(effort)
    assert list(tickets) == [first.number, second.number, third.number]
    assert tickets[first.number]["labels"] == ["ready-for-agent"]
    assert tickets[second.number]["assignees"] == ["octocat"]
    assert tickets[third.number]["blocked_by"] == [first.number, second.number]
    assert tickets[third.number]["open_blockers"] == 2
    assert tickets[second.number]["pull_request"] == {
        "number": pull.number,
        "branch": f"ticket/{second.number}-work",
        "base": "main",
        "head_commit": pull.head_commit,
        "draft": True,
        "merged": False,
        "merge_commit": None,
        "checks": "pending",
        "approved": False,
        "opened": pull.created_at,
    }
    assert tickets[first.number]["pull_request"] is None
    assert len(github.queries) == 1


def _states(url: str, effort: int) -> dict[int, str]:
    return {n: t["state"] for n, t in _tickets(_read(url, effort)).items()}


def test_each_ticket_takes_the_state_its_github_facts_give_it(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, tickets = github.effort("Every state", tickets=10)
    (merged, completed, not_planned, asked, held, ready, draft, failing, taken, blocked) = tickets
    github.pull_request(merged, state="MERGED")
    github.close(completed)
    github.close(not_planned, reason="NOT_PLANNED")
    asked.labels.append(ASKED)
    held.labels.append(HELD)
    github.pull_request(ready, checks="SUCCESS")
    github.pull_request(draft, draft=True)
    github.pull_request(failing, checks="FAILURE")
    taken.assignees.append("octocat")
    github.block(blocked, by=taken)
    url = wayfarer.start().url()

    assert _states(url, spec.number) == {
        merged.number: "landed",
        completed.number: "landed",
        not_planned.number: "closed",
        asked.number: "asked",
        held.number: "held",
        ready.number: "landing",
        draft.number: "in_review",
        failing.number: "in_review",
        taken.number: "blocked",
        blocked.number: "blocked",
    }


def test_an_open_unblocked_unclaimed_ticket_is_takeable(wayfarer: Launcher, github: GitHub) -> None:
    spec, (free, freed) = github.effort("The frontier", tickets=2)
    blocker = github.issue("Done elsewhere")
    github.block(freed, by=blocker)
    github.close(blocker, reason="NOT_PLANNED")
    url = wayfarer.start().url()

    assert _states(url, spec.number) == {free.number: "takeable", freed.number: "takeable"}


def test_a_ticket_matching_two_rules_takes_the_higher_one(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, tickets = github.effort("Overlaps", tickets=5)
    landed_but_labelled, asked_and_held, held_and_ready, ready_and_claimed, pending = tickets
    landed_but_labelled.labels.append(HELD)
    github.pull_request(landed_but_labelled, state="MERGED")
    asked_and_held.labels += [HELD, ASKED]
    held_and_ready.labels.append(HELD)
    github.pull_request(held_and_ready)
    ready_and_claimed.assignees.append("wayfarer")
    github.pull_request(ready_and_claimed)
    github.pull_request(pending, checks="PENDING")
    url = wayfarer.start().url()

    assert _states(url, spec.number) == {
        landed_but_labelled.number: "landed",
        asked_and_held.number: "asked",
        held_and_ready.number: "held",
        ready_and_claimed.number: "landing",
        pending.number: "in_review",
    }


def test_blocking_comes_from_issue_dependencies_not_body_text(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (first, second) = github.effort("Dependencies", tickets=2)
    second.title = f"Blocked by #{first.number}, says the text, but GitHub says otherwise"
    url = wayfarer.start().url()

    ticket = _tickets(_read(url, spec.number))[second.number]

    assert ticket["blocked_by"] == []
    assert ticket["state"] == "takeable"


def test_a_pr_from_another_tickets_branch_is_not_this_tickets_pr(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (mentioned, author) = github.effort("Mentions", tickets=2)
    github.pull_request(author, mentions=[author.number, mentioned.number])
    abandoned = github.pull_request(mentioned, state="CLOSED")
    url = wayfarer.start().url()

    tickets = _tickets(_read(url, spec.number))

    assert tickets[mentioned.number]["pull_request"] is None
    assert tickets[mentioned.number]["state"] == "takeable"
    assert abandoned.number != tickets[author.number]["pull_request"]["number"]


def test_a_ticket_with_a_merged_pr_and_a_newer_open_one_has_landed(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (ticket,) = github.effort("Two PRs", tickets=1)
    merged = github.pull_request(ticket, state="MERGED")
    github.pull_request(ticket, head=f"ticket/{ticket.number}-again")
    url = wayfarer.start().url()

    read = _tickets(_read(url, spec.number))[ticket.number]

    assert read["state"] == "landed"
    assert read["pull_request"]["number"] == merged.number


def test_a_thirty_ticket_effort_is_one_query_within_its_point_budget(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, _ = github.effort("Thirty tickets", tickets=30)
    url = wayfarer.start().url()

    effort = _read(url, spec.number)

    assert len(effort["tickets"]) == 30
    assert len(github.queries) == 1
    assert github.points[0] <= 3


def test_an_effort_too_big_for_one_page_still_reads_every_ticket(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, tickets = github.effort("A big effort", tickets=120)
    url = wayfarer.start().url()

    effort = _read(url, spec.number)

    assert [t["number"] for t in effort["tickets"]] == [t.number for t in tickets]


def test_nothing_is_kept_between_reads_so_a_change_on_github_shows_at_once(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (ticket,) = github.effort("Fresh", tickets=1)
    url = wayfarer.start().url()
    assert _states(url, spec.number) == {ticket.number: "takeable"}

    ticket.labels.append(HELD)

    with Stream(url) as page:
        post(f"{url}api/efforts/{spec.number}/read")
        page.item(f"ticket:{ticket.number}", state="held")
    assert len(github.queries) == 2


def test_a_stale_github_is_believed_until_it_catches_up(wayfarer: Launcher, github: GitHub) -> None:
    spec, (ticket,) = github.effort("Stale", tickets=1)
    url = wayfarer.start().url()

    with github.stale():
        github.close(ticket)
        assert _states(url, spec.number) == {ticket.number: "takeable"}

    with Stream(url) as page:
        post(f"{url}api/efforts/{spec.number}/read")
        page.item(f"ticket:{ticket.number}", state="landed")


def test_an_issue_that_does_not_exist_is_not_found(wayfarer: Launcher) -> None:
    url = wayfarer.start().url()

    assert "no issue #404" in _unreadable(url, 404)


def test_without_a_github_token_a_read_says_so(wayfarer: Launcher) -> None:
    url = wayfarer.start(env={"GH_TOKEN": None, "GITHUB_TOKEN": None}).url()

    assert "GH_TOKEN" in _unreadable(url, 1)


def test_a_token_github_refuses_is_reported_rather_than_read_as_empty(
    wayfarer: Launcher,
) -> None:
    url = wayfarer.start(env={"GH_TOKEN": "revoked"}).url()

    assert "Bad credentials" in _unreadable(url, 1)


def test_a_clone_with_no_github_remote_cannot_read_an_effort(
    wayfarer: Launcher, clone: Path
) -> None:
    subprocess.run(["git", "remote", "remove", "origin"], cwd=clone, check=True)
    url = wayfarer.start().url()

    assert "no GitHub remote" in _unreadable(url, 1)


def test_a_github_that_cannot_be_reached_is_reported(wayfarer: Launcher) -> None:
    with socket.socket() as closed:
        closed.bind(("127.0.0.1", 0))
        nowhere = f"http://127.0.0.1:{closed.getsockname()[1]}"
    url = wayfarer.start(env={"WAYFARER_GITHUB_API": nowhere}).url()

    assert "could not be reached" in _unreadable(url, 1)


def test_a_clone_of_a_repo_github_does_not_have_says_so(wayfarer: Launcher, clone: Path) -> None:
    subprocess.run(
        ["git", "remote", "set-url", "origin", "git@github.com:octo/gone.git"],
        cwd=clone,
        check=True,
    )
    url = wayfarer.start().url()

    assert "octo/gone was not found" in _unreadable(url, 1)
