"""A session's conversation outlives its sandbox, so a later session can carry it on.

As a session's agent ends, its transcript is carried out of the sandbox and kept
beside its event file; a resume carries it back in, with any other files it is
handed, and runs the agent on the same conversation. With the transcript lost, it
starts cold (#20, #19).

The seam is the session's own interface, as in `test_one_session.py`: Waystation's
`ScriptedAgent` in `NoSandbox`, whose home is a directory of the test's, stands in
for Claude Code in Docker. It writes a transcript where Claude Code would, and
writes down what it was given.
"""

from __future__ import annotations

import asyncio
import json
import shlex
import shutil
from collections.abc import Iterator, Sequence
from contextlib import closing
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest
from claude_stream import DONE
from waystation import NoSandbox, RunSucceeded
from waystation.agents import AgentCommand, AgentEvent
from waystation.testing import ScriptedAgent

from wayfarer import stream
from wayfarer.github import Repo
from wayfarer.sessions import TRANSCRIPT, Sessions
from wayfarer.settings import Settings
from wayfarer.store import Purpose, Store

pytestmark = pytest.mark.git


@dataclass(frozen=True)
class _Claude:
    """The scripted agent, playing Claude Code's part in a conversation: it writes the
    transcript for the conversation its arguments name, and writes down, in `seen`,
    its arguments, its prompt and what it found under its home."""

    args: Sequence[str]
    seen: Path

    def preflight(self) -> None:
        return None

    def command(self, prompt: str, outcome_schema: dict[str, Any]) -> AgentCommand:
        played = ScriptedAgent(outcome=DONE).command(prompt, outcome_schema)
        conversation = shlex.quote(self.args[1])
        noted = shlex.quote(str(self.seen))
        script = [
            # Whatever Claude Code would find: a resumed transcript, a carried file.
            f'cat "$HOME"/.claude/projects/*/{conversation}.jsonl > {noted}.transcript 2>/dev/null',
            f'cat "$HOME/.wayfarer/answer.json" > {noted}.answer 2>/dev/null',
            f"printf '%s\\n' {' '.join(shlex.quote(a) for a in self.args)} > {noted}.args",
            f"printf '%s' {shlex.quote(prompt)} > {noted}.prompt",
            # Then the conversation, one line longer, where Claude Code keeps it.
            f'set -- "$HOME"/.claude/projects/*/{conversation}.jsonl',
            'if [ ! -f "$1" ]; then mkdir -p "$HOME/.claude/projects/-work"',
            f'set -- "$HOME/.claude/projects/-work/{conversation}.jsonl"; fi',
            "printf 'a turn\\n' >> \"$1\"",
            'mkdir -p "$HOME/.wayfarer"',
            'printf \'{"asked": true}\' > "$HOME/.wayfarer/question.json"',
        ]
        assert played.script is not None
        return replace(played, script="\n".join([*script, played.script]))

    def parse(self, line: str) -> Sequence[AgentEvent]:
        return ScriptedAgent().parse(line)


@dataclass
class _Played:
    sessions: Sessions
    seen: Path
    store: Store
    home: Path

    def saw(self, what: str) -> str | None:
        found = self.seen.with_name(f"{self.seen.name}.{what}")
        return found.read_text() if found.exists() else None


@pytest.fixture
def played(host_repo: Path, tmp_path: Path) -> Iterator[_Played]:
    home = tmp_path / "home"
    home.mkdir()
    seen = tmp_path / "seen"
    with closing(Store.open(tmp_path / "data")) as store:
        sessions = Sessions(
            host_repo,
            store,
            Repo("octo", "widgets"),
            agent=lambda args: _Claude(args, seen),
            sandbox=NoSandbox(env={"HOME": str(home), "PATH": "/usr/bin:/bin"}),
            settings=Settings(),
            stream=stream.Store(backlog=1000),
            carry_out=[".wayfarer/question.json"],
        )
        yield _Played(sessions, seen, store, home)


def _run(played: _Played, spec: Any) -> str:
    # Every session's container starts empty, whatever the last one left in its home.
    shutil.rmtree(played.home)
    played.home.mkdir()
    result = asyncio.run(spec.perform())
    assert isinstance(result, RunSucceeded)
    return result.run_id


def test_a_session_names_its_conversation_and_carries_its_transcript_out(
    played: _Played,
) -> None:
    run_id = _run(played, played.sessions.spec(7))

    [row] = played.store.sessions()
    assert row.conversation is not None
    assert played.saw("args") == f"--session-id\n{row.conversation}\n"
    assert played.sessions.carried(run_id, TRANSCRIPT) == b"a turn\n"
    assert json.loads(played.sessions.carried(run_id, ".wayfarer/question.json") or b"") == {
        "asked": True
    }


def test_a_resume_carries_the_transcript_and_its_files_in_and_goes_on_with_the_conversation(
    played: _Played,
) -> None:
    first = _run(played, played.sessions.spec(7))

    again = _run(
        played,
        played.sessions.resume(
            7,
            first,
            base="HEAD",
            prompt="Carry on.",
            cold="Start again.",
            purpose=Purpose.CONTINUE,
            files_in={".wayfarer/answer.json": b'{"answer": "blue"}'},
        ),
    )

    first_row, second_row = played.store.sessions()
    assert second_row.purpose is Purpose.CONTINUE
    assert second_row.conversation == first_row.conversation
    assert played.saw("args") == f"--resume\n{first_row.conversation}\n"
    assert played.saw("prompt") == "Carry on."
    assert played.saw("transcript") == "a turn\n"
    assert played.saw("answer") == '{"answer": "blue"}'
    assert played.sessions.carried(again, TRANSCRIPT) == b"a turn\na turn\n"


def test_a_resume_whose_transcript_is_lost_starts_cold_on_a_fresh_conversation(
    played: _Played,
) -> None:
    first = _run(played, played.sessions.spec(7))
    (played.store.carried(first) / TRANSCRIPT).unlink()

    _run(
        played,
        played.sessions.resume(
            7, first, base="HEAD", prompt="Carry on.", cold="Start again.", purpose=Purpose.CONTINUE
        ),
    )

    first_row, second_row = played.store.sessions()
    assert second_row.conversation != first_row.conversation
    assert played.saw("args") == f"--session-id\n{second_row.conversation}\n"
    assert played.saw("prompt") == "/mattpocock-skills:implement 7\n\nStart again."
