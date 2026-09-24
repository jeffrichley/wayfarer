"""The cascade: arming an effort is the only way a session ever starts.

Each test serves Wayfarer in this process, against the GitHub stand-in, with its
sessions really running a scripted agent (`cascading.py`). Everything else is HTTP.

Every session is held until its test lets its ticket go, so a test decides when
each one ends, and every start is written down where the test can count it.
"""

from __future__ import annotations

import shlex
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest
from waystation.agents import AgentCommand, AgentEvent
from waystation.testing import ScriptedAgent

import cascading
from cascading import Gate, eventually, git, origin_clone
from conftest import Stream, post
from github_stand_in import LOGIN, GitHub, Issue

pytestmark = pytest.mark.git

_DONE = {"status": "done", "summary": "Built it.", "open_findings": [], "assumptions": []}


@pytest.fixture
def clone(tmp_path: Path, github: GitHub) -> Path:
    return origin_clone(tmp_path, github)


@dataclass(frozen=True)
class _Held:
    """The scripted agent, writing its ticket down as it starts, leaving some work
    uncommitted, and then holding until the test lets that ticket go."""

    released: Path
    started: Path

    def preflight(self) -> None:
        return None

    def command(self, prompt: str, outcome_schema: dict[str, Any]) -> AgentCommand:
        ticket = prompt.rsplit(" ", 1)[-1]
        played = ScriptedAgent(outcome=_DONE).command(prompt, outcome_schema)
        let_go = shlex.quote(str(self.released / ticket))
        held = [
            f"printf 'work on {ticket}\\n' > work-{ticket}.txt",
            f"printf '%s\\n' {ticket} >> {shlex.quote(str(self.started))}",
            f"while [ ! -e {let_go} ]; do sleep 0.05; done",
        ]
        assert played.script is not None
        return replace(played, script="\n".join([*held, played.script]))

    def parse(self, line: str) -> Sequence[AgentEvent]:
        return ScriptedAgent().parse(line)


@dataclass
class Wayfarer:
    """One Wayfarer serving in this process, and the sessions it has started."""

    url: str
    released: Path
    started_log: Path
    gate: Gate

    def started(self) -> list[int]:
        """Every ticket a session was started on, in the order they started."""
        if not self.started_log.exists():
            return []
        return [int(line) for line in self.started_log.read_text().split()]

    def let_go(self, ticket: Issue) -> None:
        """Let the session on `ticket` finish."""
        (self.released / str(ticket.number)).touch()

    def arm(self, effort: Issue) -> None:
        assert post(f"{self.url}api/efforts/{effort.number}/arm").status_code == 202


Serve = Callable[..., Wayfarer]


@pytest.fixture
def wayfarer(clone: Path, tmp_path: Path, github: GitHub) -> Iterator[Serve]:
    """Serves Wayfarer on `clone`; the same data directory each time, as a restart has."""
    released = tmp_path / "released"
    released.mkdir()
    started = tmp_path / "started.txt"
    serving: list[Any] = []

    def serve(cap: int = 3) -> Wayfarer:
        for running in serving:
            running.__exit__(None, None, None)
        serving.clear()
        gate = Gate()
        agent = _Held(released, started)
        context = cascading.serving(
            clone, tmp_path / "data", github, lambda _: agent, gate, cap=cap
        )
        url = context.__enter__()
        serving.append(context)
        return Wayfarer(url, released, started, gate)

    yield serve
    # Anything still held is let go, so shutting down waits on nothing.
    for ticket in range(1, 100):
        (released / str(ticket)).touch()
    for running in serving:
        running.__exit__(None, None, None)


def _page(url: str) -> Stream:
    # The poll keeps a page busy, so a wait is bounded in all, not only per read.
    return Stream(url, patience=20.0)


def _cascade(effort: Issue) -> str:
    return f"cascade:{effort.number}"


def _ticket(ticket: Issue) -> str:
    return f"ticket:{ticket.number}"


def test_arming_is_offered_with_how_many_tickets_are_takeable_and_the_cap(
    wayfarer: Serve, github: GitHub
) -> None:
    effort, tickets = github.effort("Widgets", tickets=5)
    github.block(tickets[4], by=tickets[0])
    app = wayfarer(cap=3)

    with _page(app.url) as seen:
        post(f"{app.url}api/efforts/{effort.number}/read")
        cascade = seen.item(_cascade(effort))

    assert cascade["armed"] is False
    assert cascade["takeable"] == 4
    assert cascade["cap"] == 3
    assert cascade["offer"] == "4 tickets are takeable now, up to 3 at a time"
    assert app.started() == []


def test_the_offer_says_so_when_one_ticket_or_none_is_takeable(
    wayfarer: Serve, github: GitHub
) -> None:
    one, _ = github.effort("One", tickets=1)
    none, (taken,) = github.effort("None", tickets=1)
    taken.assignees.append("grace")
    app = wayfarer(cap=2)

    with _page(app.url) as seen:
        post(f"{app.url}api/efforts/{one.number}/read")
        post(f"{app.url}api/efforts/{none.number}/read")
        offers = [seen.item(_cascade(e))["offer"] for e in (one, none)]

    assert offers == [
        "1 ticket is takeable now, up to 2 at a time",
        "No tickets are takeable now, up to 2 at a time",
    ]


def test_an_armed_cascade_starts_every_takeable_ticket_up_to_the_cap(
    wayfarer: Serve, github: GitHub
) -> None:
    effort, tickets = github.effort("Widgets", tickets=4)
    app = wayfarer(cap=3)

    with _page(app.url) as seen:
        app.arm(effort)
        cascade = seen.item(_cascade(effort), armed=True, running=3)
        eventually(lambda: len(app.started()) == 3)
        for ticket in tickets[:3]:
            seen.item(_ticket(ticket), state="building")

        app.let_go(tickets[0])
        eventually(lambda: len(app.started()) == 4)

    assert cascade["paused"] is False
    # The first three start together, so they may write themselves down in any order.
    assert sorted(app.started()[:3]) == [t.number for t in tickets[:3]]
    assert app.started()[3] == tickets[3].number


def test_the_cap_is_shared_by_every_armed_cascade_on_the_repo(
    wayfarer: Serve, github: GitHub
) -> None:
    first, _ = github.effort("First", tickets=2)
    second, _ = github.effort("Second", tickets=2)
    app = wayfarer(cap=3)

    with _page(app.url) as seen:
        app.arm(first)
        seen.item(_cascade(first), running=2)
        app.arm(second)
        seen.item(_cascade(second), armed=True, running=1)
        eventually(lambda: len(app.started()) == 3)
        # The fourth waits for a slot, whichever effort it is in.
        left = seen.item(_cascade(second))

    assert left["takeable"] == 1
    assert len(app.started()) == 3


def test_a_ticket_is_claimed_on_github_before_its_session_starts(
    wayfarer: Serve, github: GitHub
) -> None:
    effort, (ticket,) = github.effort("Widgets", tickets=1)
    app = wayfarer()

    with _page(app.url) as seen:
        app.arm(effort)
        eventually(lambda: app.started() == [ticket.number])
        claimed = seen.item(_ticket(ticket), state="building")

    assert claimed["assignees"] == [LOGIN]
    assert ticket.assignees == [LOGIN]


def test_a_ticket_whose_claim_github_refuses_is_never_started(
    wayfarer: Serve, github: GitHub
) -> None:
    effort, (ticket,) = github.effort("Widgets", tickets=1)
    github.forbid(f"/issues/{ticket.number}/assignees")
    app = wayfarer()

    with _page(app.url) as seen:
        app.arm(effort)
        # It cannot write to GitHub, which is no fault of the ticket's, so it pauses
        # rather than try again on every read.
        cascade = seen.item(_cascade(effort), armed=True, paused=True)

    assert cascade["running"] == 0
    assert f"claim #{ticket.number}" in cascade["reason"]
    assert ticket.assignees == []
    assert app.started() == []


def test_a_ticket_a_person_takes_as_wayfarer_claims_it_is_left_to_them(
    wayfarer: Serve, github: GitHub
) -> None:
    effort, (ticket,) = github.effort("Widgets", tickets=1)
    github.meanwhile(lambda: ticket.assignees.append("grace"))
    app = wayfarer()

    with _page(app.url) as seen:
        app.arm(effort)
        # The read after the claim shows both, and Wayfarer lets go of its own.
        seen.item(_ticket(ticket), assignees=["grace"])
        cascade = seen.item(_cascade(effort), waiting=True)

    assert cascade["takeable"] == 0
    assert app.started() == []


def test_a_claim_made_just_before_a_pause_is_let_go_not_stranded(
    wayfarer: Serve, github: GitHub
) -> None:
    effort, (ticket,) = github.effort("Widgets", tickets=1)
    app = wayfarer()
    # The person pauses while the claim is on its way, before any read shows it.
    github.meanwhile(lambda: post(f"{app.url}api/efforts/{effort.number}/pause"))

    with _page(app.url) as seen:
        app.arm(effort)
        seen.item(_cascade(effort), paused=True)
        # The read that shows the claim finds the cascade paused, so it lets go.
        seen.item(_ticket(ticket), assignees=[], state="takeable")
        assert app.started() == []

        post(f"{app.url}api/efforts/{effort.number}/resume")
        eventually(lambda: app.started() == [ticket.number])


def test_a_ticket_a_person_has_taken_is_left_alone(wayfarer: Serve, github: GitHub) -> None:
    effort, (mine, theirs) = github.effort("Widgets", tickets=2)
    # Taken by hand: by the person Wayfarer writes as, and by someone else.
    mine.assignees.append(LOGIN)
    theirs.assignees.append("grace")
    app = wayfarer()

    with _page(app.url) as seen:
        app.arm(effort)
        cascade = seen.item(_cascade(effort), armed=True)

    assert cascade["waiting"] is True
    assert app.started() == []


def test_no_ticket_is_ever_started_automatically_more_than_once(
    wayfarer: Serve, github: GitHub
) -> None:
    effort, (ticket,) = github.effort("Widgets", tickets=1)
    app = wayfarer()

    with _page(app.url) as seen:
        app.arm(effort)
        eventually(lambda: app.started() == [ticket.number])
        app.let_go(ticket)
        seen.item(_cascade(effort), running=0)
        # Someone lets it go on GitHub, so it is takeable again.
        ticket.assignees.clear()
        seen.item(_ticket(ticket), state="takeable")
        seen.item(_cascade(effort), waiting=True, takeable=0)
        # Nor does pausing and resuming, or arming again.
        post(f"{app.url}api/efforts/{effort.number}/pause")
        seen.item(_cascade(effort), paused=True)
        post(f"{app.url}api/efforts/{effort.number}/resume")
        seen.item(_cascade(effort), paused=False, waiting=True)
        app.arm(effort)
        post(f"{app.url}api/efforts/{effort.number}/read")
        seen.item(_cascade(effort), waiting=True)

    # Nor does a restarted Wayfarer, armed afresh.
    again = wayfarer()
    with _page(again.url) as seen:
        again.arm(effort)
        seen.item(_cascade(effort), armed=True, waiting=True)

    assert app.started() == [ticket.number]


def test_a_restarted_wayfarer_brings_an_armed_cascade_back_paused(
    wayfarer: Serve, github: GitHub
) -> None:
    effort, (_, second) = github.effort("Widgets", tickets=2)
    app = wayfarer(cap=1)
    with _page(app.url) as seen:
        app.arm(effort)
        seen.item(_cascade(effort), armed=True, running=1)

    # Stopped mid-session, as Ctrl-C stops it.
    again = wayfarer(cap=1)
    with _page(again.url) as seen:
        post(f"{again.url}api/efforts/{effort.number}/read")
        cascade = seen.item(_cascade(effort), armed=True)

    assert cascade["paused"] is True
    assert second.number not in again.started()


def test_pausing_submits_nothing_new_while_running_sessions_finish(
    wayfarer: Serve, github: GitHub
) -> None:
    effort, (first, second) = github.effort("Widgets", tickets=2)
    app = wayfarer(cap=1)

    with _page(app.url) as seen:
        app.arm(effort)
        eventually(lambda: app.started() == [first.number])
        post(f"{app.url}api/efforts/{effort.number}/pause")
        seen.item(_cascade(effort), paused=True)

        # The running session is not stopped: it finishes, and frees its slot.
        app.let_go(first)
        seen.item(_cascade(effort), paused=True, running=0)
        assert app.started() == [first.number]

        post(f"{app.url}api/efforts/{effort.number}/resume")
        eventually(lambda: app.started() == [first.number, second.number])


def test_stopping_a_ticket_keeps_its_work_and_holds_it(
    wayfarer: Serve, github: GitHub, clone: Path
) -> None:
    effort, (ticket,) = github.effort("Widgets", tickets=1)
    app = wayfarer()

    with _page(app.url) as seen:
        app.arm(effort)
        eventually(lambda: app.started() == [ticket.number])
        post(f"{app.url}api/tickets/{ticket.number}/stop")
        held = seen.item(_ticket(ticket), state="held")
        seen.item(_cascade(effort), running=0)

    assert held["assignees"] == [LOGIN]
    [kept] = git(clone, "branch", "--list", "waystation/*", "--format=%(refname:short)").split()
    assert git(clone, "show", f"{kept}:work-{ticket.number}.txt") == f"work on {ticket.number}\n"
    assert app.started() == [ticket.number]


def test_a_landing_starts_what_it_frees(wayfarer: Serve, github: GitHub) -> None:
    effort, (first, second) = github.effort("Widgets", tickets=2)
    github.block(second, by=first)
    app = wayfarer()

    with _page(app.url) as seen:
        app.arm(effort)
        eventually(lambda: app.started() == [first.number])
        app.let_go(first)
        seen.item(_cascade(effort), running=0, waiting=True)

        # It lands, and its dependent is taken without anyone asking.
        github.close(first)
        eventually(lambda: app.started() == [first.number, second.number])
        seen.item(_cascade(effort), running=1, waiting=False)


def test_nothing_takeable_leaves_the_cascade_armed_and_waiting(
    wayfarer: Serve, github: GitHub
) -> None:
    effort, (ticket,) = github.effort("Widgets", tickets=1)
    elsewhere = github.issue("Something else")
    github.block(ticket, by=elsewhere)
    app = wayfarer()

    with _page(app.url) as seen:
        app.arm(effort)
        cascade = seen.item(_cascade(effort), armed=True)
        assert cascade["waiting"] is True

        # Its blocker closes, and the cascade, still armed, takes it.
        github.close(elsewhere)
        eventually(lambda: app.started() == [ticket.number])


def test_when_every_ticket_is_closed_the_cascade_disarms_and_raises_shipping(
    wayfarer: Serve, github: GitHub
) -> None:
    effort, (landed, dropped) = github.effort("Widgets", tickets=2)
    github.close(dropped, reason="NOT_PLANNED")
    app = wayfarer()

    with _page(app.url) as seen:
        app.arm(effort)
        eventually(lambda: app.started() == [landed.number])
        app.let_go(landed)
        github.close(landed)
        cascade = seen.item(_cascade(effort), armed=False)
        ship = seen.item(f"ship:{effort.number}")

    assert cascade["waiting"] is False
    assert ship == {
        "kind": "ship",
        "id": f"ship:{effort.number}",
        "effort": effort.number,
        "title": "Widgets",
    }


def test_a_refused_start_gate_pauses_the_cascade_and_raises_one_item(
    wayfarer: Serve, github: GitHub
) -> None:
    effort, _ = github.effort("Widgets", tickets=2)
    app = wayfarer()
    app.gate.refusing = True

    with _page(app.url) as seen:
        app.arm(effort)
        cascade = seen.item(_cascade(effort), armed=True, paused=True)
        gate = seen.item("gate", passed=False)

    assert gate["raised"]["reason"] == "No session will start until Docker is running."
    assert cascade["reason"] == "The start gate refused a start."
    assert cascade["running"] == 0
    assert app.started() == []
