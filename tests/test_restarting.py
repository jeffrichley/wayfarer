"""Restart: a Wayfarer back after a crash or a quit makes the same next move as one
that never stopped (#43, ADR-0002).

Each test serves Wayfarer in this process, sessions and all, with nothing spent
(`cascading.py`), and serving it again is the restart. A crash is what it leaves
in the store: a session started and never ended, which no clean stop leaves.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from cascading import Containers, Serve, eventually, host_clone, page, serving
from cascading import cascade_id as _cascade
from cascading import ticket_id as _ticket
from conftest import post
from github_stand_in import LOGIN, GitHub, Issue
from wayfarer.github import Repo
from wayfarer.outcome import Outcome
from wayfarer.read_model import ASKED, HELD
from wayfarer.store import Purpose, Store

pytestmark = pytest.mark.git


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    return host_clone(tmp_path)


@pytest.fixture
def wayfarer(clone: Path, tmp_path: Path, github: GitHub) -> Iterator[Serve]:
    with serving(clone, tmp_path, github) as serve:
        yield serve


def _record(tmp_path: Path) -> closing[Store]:
    """The store the Wayfarer before this one kept for the clone's repo."""
    return closing(Store.for_repo(tmp_path / "data", Repo("octo", "widgets")))


def _crashed(tmp_path: Path, run_id: str, ticket: Issue, *, armed: Issue | None = None) -> None:
    """Leave what a Wayfarer that died mid-session leaves: its ticket claimed on GitHub,
    and a session in its store that never ended."""
    ticket.assignees.append(LOGIN)
    with _record(tmp_path) as store:
        events = store.event_file(run_id)
        events.touch()
        store.session_started(run_id, ticket.number, Purpose.BUILD, datetime.now(UTC), events)
        if armed is not None:
            store.arm(armed.number)


def _needs(items: dict[str, dict[str, Any]]) -> list[str]:
    return [need["kind"] for need in items.get("needs_you", {"items": []})["items"]]


@pytest.mark.parametrize("restarted", [False, True], ids=["never stopped", "restarted"])
def test_a_restarted_wayfarer_makes_the_same_next_move_as_one_that_never_stopped(
    wayfarer: Serve, github: GitHub, restarted: bool
) -> None:
    effort, (first, taken, second, third) = github.effort("Widgets", tickets=4)
    taken.assignees.append("grace")
    github.block(third, by=first)
    app = wayfarer(cap=1)
    with page(app.url) as seen:
        app.arm(effort)
        eventually(lambda: app.started() == [first.number])
        post(f"{app.url}api/efforts/{effort.number}/pause")
        app.let_go(first)
        seen.item(_cascade(effort), paused=True, running=0)
    github.close(first)

    if restarted:
        app = wayfarer(cap=1)
    with page(app.url) as seen:
        seen.item(_cascade(effort), armed=True, paused=True)
        post(f"{app.url}api/efforts/{effort.number}/resume")
        # Not the ticket already started once, nor the one a person took.
        eventually(lambda: app.started() == [first.number, second.number])
        app.let_go(second)
        eventually(lambda: app.started() == [first.number, second.number, third.number])


def test_an_armed_cascade_comes_back_paused_without_anyone_reading_its_effort(
    wayfarer: Serve, github: GitHub
) -> None:
    effort, tickets = github.effort("Widgets", tickets=2)
    app = wayfarer(cap=1)
    with page(app.url) as seen:
        app.arm(effort)
        eventually(lambda: len(app.started()) == 1)

    again = wayfarer(cap=1)
    with page(again.url) as seen:
        cascade = seen.item(_cascade(effort), armed=True, paused=True)
        for ticket in tickets:
            seen.item(_ticket(ticket))

    assert cascade["takeable"] == 1
    assert len(again.started()) == 1


def test_a_session_that_never_finished_is_raised_by_its_ticket_and_offered_a_reap(
    wayfarer: Serve, github: GitHub, tmp_path: Path
) -> None:
    effort, (left, _) = github.effort("Widgets", tickets=2)
    left.title = "Flag loudness"
    _crashed(tmp_path, "run-left", left)
    containers = Containers(left={"run-left"})
    app = wayfarer(containers=containers)

    with page(app.url, home=True) as seen:
        orphan = seen.item("orphan:run-left")
        # GitHub names its effort, which is read though no cascade on it was armed.
        seen.item(_ticket(left), state="blocked")
        seen.until(lambda items: _needs(items) == ["orphan"])

        assert post(f"{app.url}api/sessions/run-left/reap").status_code == 202
        seen.until(lambda items: "orphan:run-left" not in items)
        # It waits on a person, as a stopped session's ticket does.
        seen.item(_ticket(left), state="held")
        seen.until(lambda items: _needs(items) == ["held"])

    assert orphan["ticket"] == left.number
    assert orphan["title"] == "Flag loudness"
    assert orphan["effort"] == {"number": effort.number, "title": "Widgets"}
    assert containers.reaped == ["run-left"]
    assert HELD in left.labels
    with _record(tmp_path) as store:
        [row] = store.sessions()
    assert row.ended is not None
    assert app.started() == []


def test_a_container_no_session_accounts_for_is_shown_and_never_reaped(
    wayfarer: Serve, github: GitHub, tmp_path: Path
) -> None:
    _, (left,) = github.effort("Widgets", tickets=1)
    _crashed(tmp_path, "run-left", left)
    containers = Containers(left={"run-left", "someone-elses"})
    app = wayfarer(containers=containers)

    with page(app.url, home=True) as seen:
        unknown = seen.item("container:someone-elses")
        seen.until(lambda items: _needs(items) == ["orphan", "unknown_container"])
        # Asked outright, it is still not reaped: it may be another repo's Wayfarer's.
        post(f"{app.url}api/sessions/someone-elses/reap")
        post(f"{app.url}api/sessions/run-left/reap")
        seen.until(lambda items: _needs(items) == ["held", "unknown_container"])

    assert unknown["run_id"] == "someone-elses"
    assert containers.reaped == ["run-left"]
    assert containers.left == {"someone-elses"}


def test_what_the_last_wayfarer_left_is_pinned_below_shipping_an_effort(
    wayfarer: Serve, github: GitHub, tmp_path: Path
) -> None:
    shipped, (done,) = github.effort("Shipped", tickets=1)
    github.close(done)
    _, (left,) = github.effort("Widgets", tickets=1)
    github.label(left, ASKED)
    _crashed(tmp_path, "run-left", left, armed=shipped)
    app = wayfarer(containers=Containers(left={"someone-elses"}))

    with page(app.url, home=True) as seen:
        seen.until(
            lambda items: _needs(items) == ["question", "ship", "orphan", "unknown_container"]
        )


def test_a_restarted_wayfarer_takes_every_tickets_state_from_github_alone(
    wayfarer: Serve, github: GitHub, tmp_path: Path
) -> None:
    effort, (left, built, asked) = github.effort("Widgets", tickets=3)
    _crashed(tmp_path, "run-left", left, armed=effort)
    with _record(tmp_path) as store:
        events = store.event_file("run-built")
        events.touch()
        store.session_started("run-built", built.number, Purpose.BUILD, datetime.now(UTC), events)
        done = Outcome(status="done", summary="Built it.", open_findings=[], assumptions=[])
        store.session_ended("run-built", datetime.now(UTC), done)
    # GitHub moved on without it: what was built never landed, and the other asked.
    github.label(asked, ASKED)
    app = wayfarer(containers=Containers(left={"run-left"}))

    with page(app.url) as seen:
        states = {t.number: seen.item(_ticket(t))["state"] for t in (left, built, asked)}

    # A session the store has as running builds nothing: only a session here does.
    assert states == {left.number: "blocked", built.number: "takeable", asked.number: "asked"}
    assert app.started() == []


def test_a_reap_github_refuses_leaves_the_orphan_offered(
    wayfarer: Serve, github: GitHub, tmp_path: Path
) -> None:
    _, (left,) = github.effort("Widgets", tickets=1)
    _crashed(tmp_path, "run-left", left)
    github.forbid(f"/issues/{left.number}/labels")
    app = wayfarer(containers=Containers(left={"run-left"}))

    with page(app.url) as seen:
        seen.item("orphan:run-left")
        post(f"{app.url}api/sessions/run-left/reap")
        eventually(
            lambda: any(r.method == "POST" and r.path.endswith("/labels") for r in github.requests)
        )
        # Reaping again is safe, so it is still offered.
        seen.item(_ticket(left), state="blocked")
        assert "orphan:run-left" in seen.items

    with _record(tmp_path) as store:
        [row] = store.sessions()
    assert row.ended is None


def test_an_orphan_on_a_ticket_in_no_effort_is_still_raised_by_its_ticket(
    wayfarer: Serve, github: GitHub, tmp_path: Path
) -> None:
    loose = github.issue("Loose end")
    _crashed(tmp_path, "run-loose", loose)
    app = wayfarer()

    with page(app.url) as seen:
        orphan = seen.item("orphan:run-loose")

    assert orphan["ticket"] == loose.number
    assert (orphan["title"], orphan["effort"]) == ("Loose end", None)
