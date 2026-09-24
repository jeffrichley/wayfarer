"""A session that asks ends, and an answer resumes the same conversation (#42).

Each test serves Wayfarer with its sessions really running a scripted agent
(`cascading.py`), each in a home of its own, as each container starts empty. The
agent plays Claude Code's part: a session that asks writes its question where the
image's hook does and ends without reporting, as a deferred call ends one; a
resume finds the conversation it carries on and the answer carried in beside it.
What the image's own hook does with them is the probe's to prove
(`test_building_the_session_image.py`).
"""

from __future__ import annotations

import json
import re
import shlex
import threading
from collections.abc import Iterator, Sequence
from contextlib import closing
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from waystation.agents import AgentCommand, AgentEvent
from waystation.testing import ScriptedAgent, ScriptedCommit

import cascading
from cascading import Gate, eventually, origin_clone
from conftest import Stream, post
from github_stand_in import LOGIN, GitHub, Issue
from wayfarer.asking import ASKED, RESUMED
from wayfarer.github import Repo
from wayfarer.store import Purpose, Store

pytestmark = pytest.mark.git

_DONE = {"status": "done", "summary": "Built it.", "open_findings": [], "assumptions": []}
_WHICH = "Should a book with no credits fail the export or warn?"
_ASKED = {
    "questions": [
        {
            "question": _WHICH,
            "header": "Credits",
            "options": [
                {"label": "Fail", "description": "The export stops."},
                {"label": "Warn", "description": "The export carries on."},
            ],
            "multiSelect": False,
        }
    ]
}


@dataclass
class _Session:
    """What one session was handed, and what it found under its home."""

    ticket: int
    args: list[str]
    prompt: str
    seen: Path

    def found(self, what: str) -> str | None:
        path = self.seen.with_name(f"{self.seen.name}.{what}")
        return path.read_text() if path.exists() else None


@dataclass
class _Claude:
    """Plays Claude Code's part. A ticket in `asking` asks in its first session; every
    other session reports done. A session on a ticket in `waiting` waits until the
    test lets it go."""

    scratch: Path
    asking: set[int] = field(default_factory=set)
    waiting: set[int] = field(default_factory=set)
    sessions: list[_Session] = field(default_factory=list)
    _tickets: dict[str, int] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def agent(self, args: Sequence[str]) -> _Played:
        return _Played(self, list(args))

    def of(self, ticket: Issue) -> list[_Session]:
        return [s for s in self.sessions if s.ticket == ticket.number]

    def let_go(self, ticket: Issue) -> None:
        (self.scratch / f"go-{ticket.number}").touch()

    def handed(self, args: list[str], prompt: str) -> tuple[_Session, bool]:
        """The session this command starts, and whether it asks."""
        conversation = args[-1]
        with self._lock:
            found = re.search(r"implement (\d+)", prompt)
            ticket = int(found[1]) if found else self._tickets[conversation]
            self._tickets[conversation] = ticket
            first = not self.of(Issue(ticket, ""))
            seen = self.scratch / f"seen-{len(self.sessions)}"
            session = _Session(ticket, args, prompt, seen)
            self.sessions.append(session)
        return session, first and ticket in self.asking


@dataclass(frozen=True)
class _Played:
    claude: _Claude
    args: list[str]

    def preflight(self) -> None:
        return None

    def command(self, prompt: str, outcome_schema: dict[str, Any]) -> AgentCommand:
        session, asks = self.claude.handed(self.args, prompt)
        conversation = shlex.quote(self.args[-1])
        seen = shlex.quote(str(session.seen))
        go = shlex.quote(str(self.claude.scratch / f"go-{session.ticket}"))
        script = [
            # What Claude Code would find: the conversation it resumes, and the answer.
            f'cat "$HOME"/.claude/projects/*/{conversation}.jsonl > {seen}.transcript 2>/dev/null',
            f'cat "$HOME/.wayfarer/answer.json" > {seen}.answer 2>/dev/null',
            # The conversation, one turn longer, where Claude Code keeps it.
            f'set -- "$HOME"/.claude/projects/*/{conversation}.jsonl',
            'if [ ! -f "$1" ]; then mkdir -p "$HOME/.claude/projects/-workspace"',
            f'set -- "$HOME/.claude/projects/-workspace/{conversation}.jsonl"; fi',
            "printf 'a turn\\n' >> \"$1\"",
        ]
        if session.ticket in self.claude.waiting:
            script.append(f"while [ ! -e {go} ]; do sleep 0.05; done")
        if asks:
            # As the image's hook writes it, and then the call defers: nothing is reported.
            asked = shlex.quote(json.dumps(_ASKED))
            script += [
                'mkdir -p "$HOME/.wayfarer"',
                f'printf %s {asked} > "$HOME/.wayfarer/question.json"',
            ]
            return replace(
                ScriptedAgent().command(prompt, outcome_schema), script="\n".join(script)
            )
        work = ScriptedCommit(
            message="Warn on no credits", files={f"work-{session.ticket}.py": "#\n"}
        )
        played = ScriptedAgent(outcome=_DONE, commits=[work]).command(prompt, outcome_schema)
        assert played.script is not None
        return replace(played, script="\n".join([*script, played.script]))

    def parse(self, line: str) -> Sequence[AgentEvent]:
        return ScriptedAgent().parse(line)


@dataclass
class _Wayfarer:
    url: str
    claude: _Claude
    data: Path

    def arm(self, effort: Issue) -> None:
        assert post(f"{self.url}api/efforts/{effort.number}/arm").status_code == 202

    def pause(self, effort: Issue) -> None:
        assert post(f"{self.url}api/efforts/{effort.number}/pause").status_code == 202

    def resume(self, effort: Issue) -> None:
        assert post(f"{self.url}api/efforts/{effort.number}/resume").status_code == 202

    def answer(self, ticket: Issue, answers: dict[str, str]) -> None:
        answered = httpx.post(
            f"{self.url}api/tickets/{ticket.number}/answer", json={"answers": answers}, timeout=5.0
        )
        assert answered.status_code == 202

    def purposes(self, ticket: Issue) -> list[Purpose]:
        with closing(Store.for_repo(self.data, Repo("octo", "widgets"))) as store:
            return [row.purpose for row in store.sessions() if row.ticket == ticket.number]


@pytest.fixture
def serve(tmp_path: Path, github: GitHub) -> Iterator[Any]:
    clone = origin_clone(tmp_path, github)
    serving: list[Any] = []
    claude = _Claude(tmp_path)

    def start(**settings: Any) -> _Wayfarer:
        context = cascading.serving(
            clone, tmp_path / "data", github, claude.agent, Gate(), **settings
        )
        serving.append(context)
        return _Wayfarer(context.__enter__(), claude, tmp_path / "data")

    yield start
    for ticket in range(1, 100):
        claude.let_go(Issue(ticket, ""))
    for running in serving:
        running.__exit__(None, None, None)


def _asked(github: GitHub, ticket: Issue) -> bool:
    return ASKED in github.labels(ticket.number)


def test_a_session_that_asks_ends_frees_its_slot_and_leaves_its_question_on_the_ticket(
    serve: Any, github: GitHub
) -> None:
    effort, (asking, next_) = github.effort("Exports", tickets=2)
    app = serve(cap=1)
    app.claude.asking.add(asking.number)

    app.arm(effort)
    eventually(lambda: _asked(github, asking))
    # Its slot freed at once: the next ticket started, and nothing waited on the answer.
    eventually(lambda: bool(app.claude.of(next_)))

    [question] = [c for c in asking.comments if "wayfarer:question" in c]
    assert _WHICH in question
    assert "**Warn**: The export carries on." in question
    # Still claimed, and never held: asking is not a failure.
    assert asking.assignees == [LOGIN]
    assert "wayfarer:held" not in github.labels(asking.number)
    assert [p for p in github.pulls() if asking.number in p.mentions] == []


def test_answering_from_wayfarer_resumes_the_same_conversation_with_the_answer_carried_in(
    serve: Any, github: GitHub
) -> None:
    effort, (ticket,) = github.effort("Exports", tickets=1)
    app = serve()
    app.claude.asking.add(ticket.number)
    app.arm(effort)
    eventually(lambda: _asked(github, ticket))

    with Stream(app.url, patience=20.0) as page:
        page.item(f"ticket:{ticket.number}", state="asked")
        app.answer(ticket, {_WHICH: "Warn"})
        eventually(lambda: len(app.claude.of(ticket)) == 2)

    asked, resumed = app.claude.of(ticket)
    conversation = asked.args[-1]
    assert asked.args[-2] == "--session-id"
    assert resumed.args[-2:] == ["--resume", conversation]
    assert resumed.prompt == RESUMED
    eventually(lambda: resumed.found("answer") is not None)
    assert json.loads(resumed.found("answer") or "") == {_WHICH: "Warn"}
    assert resumed.found("transcript") == "a turn\n"
    # Resumed, it finished, and its work went the way any finished session's does.
    eventually(lambda: any(ticket.number in p.mentions for p in github.pulls()))


def test_answering_by_hand_on_github_resumes_it_too(serve: Any, github: GitHub) -> None:
    effort, (ticket,) = github.effort("Exports", tickets=1)
    app = serve()
    app.claude.asking.add(ticket.number)
    app.arm(effort)
    eventually(lambda: _asked(github, ticket))

    github.comment(ticket, "Warn, and say so in the summary.", by="octocat")
    github.unlabel(ticket, ASKED, by="octocat")
    eventually(lambda: len(app.claude.of(ticket)) == 2)

    resumed = app.claude.of(ticket)[1]
    eventually(lambda: resumed.found("answer") is not None)
    assert json.loads(resumed.found("answer") or "") == {_WHICH: "Warn, and say so in the summary."}


def test_a_resume_is_a_continuation_and_never_the_tickets_automatic_start(
    serve: Any, github: GitHub
) -> None:
    effort, (ticket,) = github.effort("Exports", tickets=1)
    app = serve()
    app.claude.asking.add(ticket.number)
    app.arm(effort)
    eventually(lambda: _asked(github, ticket))

    app.answer(ticket, {_WHICH: "Warn"})
    eventually(lambda: len(app.claude.of(ticket)) == 2)

    eventually(lambda: app.purposes(ticket) == [Purpose.BUILD, Purpose.RESUME])


def test_a_resume_waits_for_a_free_slot_under_the_cap(serve: Any, github: GitHub) -> None:
    effort, (asking, busy) = github.effort("Exports", tickets=2)
    app = serve(cap=1)
    app.claude.asking.add(asking.number)
    app.claude.waiting.add(busy.number)
    app.arm(effort)
    eventually(lambda: _asked(github, asking))
    eventually(lambda: bool(app.claude.of(busy)))

    app.answer(asking, {_WHICH: "Warn"})
    eventually(lambda: not _asked(github, asking))
    with pytest.raises(AssertionError):
        eventually(lambda: len(app.claude.of(asking)) == 2, timeout=1.0)

    app.claude.let_go(busy)
    eventually(lambda: len(app.claude.of(asking)) == 2)


def test_a_resume_waits_while_the_cascade_is_paused(serve: Any, github: GitHub) -> None:
    effort, (ticket,) = github.effort("Exports", tickets=1)
    app = serve()
    app.claude.asking.add(ticket.number)
    app.arm(effort)
    eventually(lambda: _asked(github, ticket))

    app.pause(effort)
    app.answer(ticket, {_WHICH: "Warn"})
    eventually(lambda: not _asked(github, ticket))
    with pytest.raises(AssertionError):
        eventually(lambda: len(app.claude.of(ticket)) == 2, timeout=1.0)

    app.resume(effort)
    eventually(lambda: len(app.claude.of(ticket)) == 2)


def test_an_asked_ticket_let_go_of_by_hand_is_never_started_cold(
    serve: Any, github: GitHub
) -> None:
    effort, (ticket,) = github.effort("Exports", tickets=1)
    app = serve()
    app.claude.asking.add(ticket.number)
    app.arm(effort)
    eventually(lambda: _asked(github, ticket))

    for login in list(ticket.assignees):
        github.unassign(ticket, login, by="octocat")

    with Stream(app.url, patience=20.0) as page:
        read = page.item(f"ticket:{ticket.number}", assignees=[])
    assert read["state"] == "asked"
    with pytest.raises(AssertionError):
        eventually(lambda: len(app.claude.of(ticket)) == 2, timeout=1.0)


def test_a_resume_whose_conversation_was_lost_starts_cold_told_the_question_and_answer(
    serve: Any, github: GitHub, tmp_path: Path
) -> None:
    effort, (ticket,) = github.effort("Exports", tickets=1)
    app = serve()
    app.claude.asking.add(ticket.number)
    app.arm(effort)
    eventually(lambda: _asked(github, ticket))

    for transcript in (tmp_path / "data").rglob("transcript.jsonl"):
        transcript.unlink()
    app.answer(ticket, {_WHICH: "Warn"})
    eventually(lambda: len(app.claude.of(ticket)) == 2)

    cold = app.claude.of(ticket)[1]
    assert cold.args[-2] == "--session-id"
    assert cold.prompt.startswith(f"/mattpocock-skills:implement {ticket.number}")
    assert f"You asked: {_WHICH}\nThe answer: Warn" in cold.prompt
