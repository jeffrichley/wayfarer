"""Recorded Claude Code sessions, played back without spending anything.

`Replayed` hands Waystation's token-free `ScriptedAgent` lines written the way
Claude Code's stream-json prints them, and reads them back with Claude Code's own
parser, so a session's events are the real ones for free. `Playing` plays each
ticket's own lines, for a Wayfarer whose cascade starts several. The builders
below write those lines.
"""

from __future__ import annotations

import json
import re
import shlex
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from waystation import ClaudeCode
from waystation.agents import AgentCommand, AgentEvent
from waystation.testing import ScriptedAgent

from wayfarer.asking import QUESTION

DONE = {"status": "done", "summary": "Added the widget.", "open_findings": [], "assumptions": []}


@dataclass(frozen=True)
class Replayed:
    """An agent that prints `lines` as Claude Code would have, then keeps running
    until it is stopped when it `lingers`."""

    lines: Sequence[str]
    lingers: bool = False

    def preflight(self) -> None:
        return None

    def command(self, prompt: str, outcome_schema: dict[str, Any]) -> AgentCommand:
        return ScriptedAgent(lines=self.lines, linger=self.lingers).command(prompt, outcome_schema)

    def parse(self, line: str) -> Sequence[AgentEvent]:
        return ClaudeCode().parse(line)


@dataclass
class Playing:
    """Each ticket's session plays `first`, waits until the test lets its ticket go,
    plays `then`, and keeps running until it is stopped.

    A ticket in `asking` asks instead: its first session plays `first`, writes the
    question down where the image's hook does, and ends without reporting, as a
    deferred call ends one (#42). The session that carries on plays `then`.

    A ticket in `recorded` streams that recorded session's file instead, a line
    every `pace` seconds as a busy session narrates, and keeps running once through.
    """

    released: Path
    first: dict[int, list[str]] = field(default_factory=dict)
    then: dict[int, list[str]] = field(default_factory=dict)
    asking: dict[int, dict[str, Any]] = field(default_factory=dict)
    recorded: dict[int, Path] = field(default_factory=dict)
    pace: float = 0.05
    _asked: set[int] = field(default_factory=set)

    def let_go(self, ticket: int) -> None:
        (self.released / str(ticket)).touch()

    def preflight(self) -> None:
        return None

    def command(self, prompt: str, outcome_schema: dict[str, Any]) -> AgentCommand:
        found = re.search(r"implement (\d+)", prompt)
        # A resume is told only to carry on; the one ticket that asked is its ticket.
        ticket = int(found[1]) if found else next(iter(self._asked))
        if ticket in self.recorded:
            played = shlex.quote(str(self.recorded[ticket]))
            paced = f"printf '%s\\n' \"$line\"; sleep {self.pace}"
            script = [f"while IFS= read -r line; do {paced}; done < {played}", *_LINGER]
        elif ticket in self._asked:
            script = [*_printed([init(), *self.then.get(ticket, [])]), *_LINGER]
        elif ticket in self.asking:
            self._asked.add(ticket)
            asked = shlex.quote(json.dumps(self.asking[ticket]))
            script = [
                *_printed([init(), *self.first.get(ticket, [])]),
                f'mkdir -p "$HOME/{Path(QUESTION).parent}"',
                f'printf %s {asked} > "$HOME/{QUESTION}"',
            ]
        else:
            let_go = shlex.quote(str(self.released / str(ticket)))
            script = [
                *_printed([init(), *self.first.get(ticket, [])]),
                f"while [ ! -e {let_go} ]; do sleep 0.05; done",
                *_printed(self.then.get(ticket, [])),
                *_LINGER,
            ]
        return replace(ScriptedAgent().command(prompt, outcome_schema), script="\n".join(script))

    def parse(self, line: str) -> Sequence[AgentEvent]:
        return ClaudeCode().parse(line)


# Running until it is stopped, as `ScriptedAgent(linger=True)` does: a child in the
# background, and the shell waiting on it as its process group's leader.
_LINGER = ["( sleep 999 ) &", "wait"]


def _printed(lines: Sequence[str]) -> list[str]:
    return [f"printf '%s\\n' {shlex.quote(line)}" for line in lines]


def _message(kind: str, *content: dict[str, Any]) -> str:
    return json.dumps({"type": kind, "message": {"content": list(content)}})


def init() -> str:
    return json.dumps({"type": "system", "subtype": "init"})


def says(text: str) -> str:
    """The agent narrating."""
    return _message("assistant", {"type": "text", "text": text})


def calls(id: str, name: str, **given: Any) -> str:
    """The agent calling tool `name` with `given`."""
    return _message("assistant", {"type": "tool_use", "id": id, "name": name, "input": given})


def returns(id: str, text: str, *, is_error: bool = False) -> str:
    """What call `id` returned."""
    return _message(
        "user", {"type": "tool_result", "tool_use_id": id, "content": text, "is_error": is_error}
    )


def reads(id: str, path: str) -> list[str]:
    """A `Read` of `path`, answered."""
    return [calls(id, "Read", file_path=path), returns(id, "…")]


def edits(id: str, path: str) -> list[str]:
    """An `Edit` of `path`, answered."""
    return [
        calls(id, "Edit", file_path=path, old_string="a", new_string="b"),
        returns(id, "edited"),
    ]


def sentinel(exit: int, passed: int | None, failed: int | None, failing: list[str]) -> str:
    """The one line `wf-test` prints last, in the format Wayfarer owns."""
    report = {"exit": exit, "passed": passed, "failed": failed, "failing": failing}
    return "::wf-test " + json.dumps(report)


def runs_tests(
    id: str,
    *,
    exit: int,
    passed: int | None = None,
    failed: int | None = None,
    failing: Sequence[str] = (),
    output: str = "",
) -> list[str]:
    """A test run through `wf-test`, answered as Claude Code answers a shell call."""
    printed = "\n".join([*([output] if output else []), sentinel(exit, passed, failed, [*failing])])
    if exit:
        printed = f"Exit code {exit}\n{printed}"
    return [
        calls(id, "Bash", command="wf-test", description="Run the tests"),
        returns(id, printed, is_error=bool(exit)),
    ]


def busy(path: Path, cycles: int = 200) -> Path:
    """A recorded session written to `path`: an Orient, then `cycles` of reading,
    editing and testing, each saying what it did, as a long session narrates."""
    lines = [init(), says("Reading the ticket.")]
    for n in range(cycles):
        lines += [
            says(f"Cycle {n}: the next criterion."),
            *reads(f"r{n}", f"/workspace/src/part_{n}.py"),
            *edits(f"e{n}", f"/workspace/src/part_{n}.py"),
            *runs_tests(f"t{n}", exit=n % 2, passed=n, failed=n % 2),
        ]
    path.write_text("".join(f"{line}\n" for line in lines))
    return path


def reports(outcome: dict[str, Any]) -> str:
    """The session's last line: its Outcome."""
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "structured_output": outcome,
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "num_turns": 3,
        }
    )
