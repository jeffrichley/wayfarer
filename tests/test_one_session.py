"""One session against one ticket, end to end, with the engine's own scripted agent.

A run really runs — a real workspace, real git, real Outcome validation, real
hooks — with Waystation's token-free `ScriptedAgent` in place of a paid model
and its `NoSandbox` in place of Docker, so nothing here spends anything.

Arming a cascade is the only way a session starts (`test_the_cascade.py`); here
the seam is the session's own interface, the Waystation run spec the cascade
submits, so what one session records is checked without a cascade around it.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest
from claude_stream import DONE, Replayed, calls, init, reads, reports, returns, says
from waystation import AgentProvider, NoSandbox, OutcomeInvalid, RunFailed, RunSucceeded
from waystation.testing import ScriptedAgent

from wayfarer import stream
from wayfarer.github import Repo
from wayfarer.outcome import Assumption, Axis, Finding, FindingKind
from wayfarer.sessions import Sessions, read_events
from wayfarer.settings import Settings
from wayfarer.store import Purpose, SessionRow, Store

pytestmark = pytest.mark.git


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    with closing(Store.open(tmp_path / "data")) as opened:
        yield opened


def _sessions(host_repo: Path, store: Store, agent: AgentProvider) -> Sessions:
    return Sessions(
        host_repo,
        store,
        Repo("octo", "widgets"),
        agent=lambda _: agent,
        sandbox=NoSandbox(),
        settings=Settings(),
        stream=stream.Store(backlog=1000),
    )


def _recorded(ticket: int) -> list[str]:
    """A short session on `ticket` as Claude Code's stream-json prints it."""
    return [
        init(),
        says(f"Reading ticket {ticket}."),
        *reads("t1", "README.md"),
        calls("t2", "Bash", command="wf-test"),
        returns("t2", "1 failed", is_error=True),
        reports(DONE),
    ]


def test_a_session_is_given_the_bare_slash_command_and_nothing_else(
    host_repo: Path, store: Store
) -> None:
    sessions = _sessions(host_repo, store, ScriptedAgent(outcome=DONE))

    spec = sessions.spec(7)
    result = asyncio.run(spec.perform())

    assert spec.prompt == "/mattpocock-skills:implement 7"
    [row] = store.sessions()
    started = read_events(row.event_file)[0]
    assert started.kind == "session_start"
    assert started.prompt == "/mattpocock-skills:implement 7"
    assert isinstance(result, RunSucceeded)


def test_the_report_comes_back_in_the_agreed_shape_and_is_written_down(
    host_repo: Path, store: Store
) -> None:
    reported = {
        "status": "not_done",
        "summary": "Added the widget; the spec's limit is not enforced yet.",
        "open_findings": [
            {
                "axis": "spec",
                "kind": "blocking",
                "what": "Widgets past the limit are accepted.",
                "cites": "A widget past the limit is refused",
                "file": "src/widgets.py",
                "line": 12,
            },
            {
                "axis": "standards",
                "kind": "judgement",
                "what": "The helper is long.",
                "cites": "Keep functions short",
            },
        ],
        "assumptions": [{"what": "Tested at the HTTP surface.", "why": "No seam was agreed."}],
    }
    sessions = _sessions(host_repo, store, ScriptedAgent(outcome=reported))

    result = asyncio.run(sessions.spec(7).perform())

    assert isinstance(result, RunSucceeded)
    assert result.outcome.status == "not_done"
    assert result.outcome.open_findings == [
        Finding(
            axis=Axis.SPEC,
            kind=FindingKind.BLOCKING,
            what="Widgets past the limit are accepted.",
            cites="A widget past the limit is refused",
            file="src/widgets.py",
            line=12,
        ),
        Finding(
            axis=Axis.STANDARDS,
            kind=FindingKind.JUDGEMENT,
            what="The helper is long.",
            cites="Keep functions short",
        ),
    ]
    assert result.outcome.assumptions == [
        Assumption(what="Tested at the HTTP surface.", why="No seam was agreed.")
    ]
    [row] = store.sessions()
    assert row.ended is not None
    assert row.outcome == result.outcome


def test_a_report_with_fields_of_its_own_invention_is_refused(
    host_repo: Path, store: Store
) -> None:
    invented = {
        **DONE,
        "open_findings": [{"severity": "low", "note": "The name is odd."}],
    }
    sessions = _sessions(host_repo, store, ScriptedAgent(outcome=invented))

    result = asyncio.run(sessions.spec(7).perform())

    assert isinstance(result, RunFailed)
    assert isinstance(result.failure, OutcomeInvalid)
    [row] = store.sessions()
    assert row.ended is not None
    assert row.outcome is None


def test_a_session_is_recorded_the_moment_it_starts_not_when_it_ends(
    host_repo: Path, store: Store
) -> None:
    # Scripted to take far longer than the test waits, so it is still running.
    sessions = _sessions(host_repo, store, ScriptedAgent(outcome=DONE, delay=60))

    async def while_it_runs() -> list[SessionRow]:
        running = asyncio.create_task(sessions.spec(7).perform())
        try:
            async with asyncio.timeout(20):
                while not (rows := store.sessions()):
                    await asyncio.sleep(0.05)
            assert not running.done()
            return rows
        finally:
            running.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await running

    [row] = asyncio.run(while_it_runs())

    assert row.ticket == 7
    assert row.purpose == Purpose.BUILD
    assert row.ended is None
    assert row.outcome is None


def test_every_event_is_written_to_the_sessions_own_file_with_nobody_watching(
    host_repo: Path, store: Store
) -> None:
    for ticket in (7, 8):
        sessions = _sessions(host_repo, store, Replayed(_recorded(ticket)))
        assert isinstance(asyncio.run(sessions.spec(ticket).perform()), RunSucceeded)

    seven, eight = store.sessions()
    assert seven.event_file != eight.event_file
    events = read_events(seven.event_file)
    assert [event.kind for event in events] == [
        "session_start",
        "text",
        "tool_use",
        "tool_result",
        "tool_use",
        "tool_result",
        "outcome",
        "usage",
        "agent_end",
        "session_end",
    ]
    assert [event.seq for event in events] == list(range(len(events)))
    assert [event.at for event in events] == sorted(event.at for event in events)
    _, said, read, answered, ran, failed, outcome, *_ = events
    assert said.model_dump(include={"text"}) == {"text": "Reading ticket 7."}
    assert read.model_dump(include={"id", "name", "tool", "input"}) == {
        "id": "t1",
        "name": "Read",
        "tool": "read",
        "input": {"file_path": "README.md"},
    }
    assert answered.model_dump(include={"id", "is_error", "text"}) == {
        "id": "t1",
        "is_error": False,
        "text": "…",
    }
    assert ran.model_dump(include={"tool"}) == {"tool": "shell"}
    assert failed.model_dump(include={"is_error"}) == {"is_error": True}
    assert outcome.model_dump(include={"raw"}) == {"raw": DONE}
    assert "Reading ticket 8." in eight.event_file.read_text()
    assert "Reading ticket 7." not in eight.event_file.read_text()
