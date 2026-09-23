"""Recorded Claude Code sessions, played back without spending anything.

`Replayed` hands Waystation's token-free `ScriptedAgent` lines written the way
Claude Code's stream-json prints them, and reads them back with Claude Code's own
parser, so a session's events are the real ones for free. The builders below
write those lines.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from waystation import ClaudeCode
from waystation.agents import AgentCommand, AgentEvent
from waystation.testing import ScriptedAgent

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
