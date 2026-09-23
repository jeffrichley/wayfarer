"""A session's normalised events: what its file holds, one JSON object per line.

These are never beats. Beats are derived from them (`beats.py`) and never stored,
so a change to how beats are told re-tells every session already recorded.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter
from waystation.agents import AgentToolKind

__all__ = [
    "AgentEnded",
    "OutcomeSaid",
    "SessionEnded",
    "SessionEvent",
    "SessionStarted",
    "Text",
    "ToolResult",
    "ToolUse",
    "Usage",
    "read_events",
]


class Event(BaseModel):
    """A normalised event, never a beat: beats are derived from these and never stored."""

    seq: int = Field(description="Its place in the session's file, counting from 0.")
    at: datetime = Field(description="When Wayfarer received it.")


class SessionStarted(Event):
    """The session began, handed `prompt`."""

    kind: Literal["session_start"] = "session_start"
    ticket: int
    prompt: str


class Text(Event):
    """Something the agent said."""

    kind: Literal["text"] = "text"
    text: str


class ToolUse(Event):
    """A tool the agent called. `id` pairs it with its `tool_result`."""

    kind: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    tool: AgentToolKind = Field(description="What the tool does, whichever agent it is.")
    input: dict[str, Any]


class ToolResult(Event):
    """What a tool the agent called returned."""

    kind: Literal["tool_result"] = "tool_result"
    id: str
    is_error: bool
    text: str


class OutcomeSaid(Event):
    """The Outcome the agent reported, as it said it, before it was validated."""

    kind: Literal["outcome"] = "outcome"
    raw: Any


class Usage(Event):
    """What the agent reported spending so far."""

    kind: Literal["usage"] = "usage"
    input_tokens: int
    output_tokens: int
    turns: int | None


class AgentEnded(Event):
    """The agent stopped: `exit_code` is -1 when it was stopped rather than exited."""

    kind: Literal["agent_end"] = "agent_end"
    exit_code: int
    hanging: bool
    cancelled: bool


class SessionEnded(Event):
    """The session ended, and how: `succeeded`, `conflicted` or `failed`.

    A cancelled session has no end: Waystation reports nothing for it.
    """

    kind: Literal["session_end"] = "session_end"
    result: Literal["succeeded", "conflicted", "failed"]
    stage: str | None = Field(description="Where a failed session failed; null otherwise.")
    failure: str | None = Field(description="How a failed session failed; null otherwise.")


SessionEvent = Annotated[
    SessionStarted | Text | ToolUse | ToolResult | OutcomeSaid | Usage | AgentEnded | SessionEnded,
    Field(discriminator="kind"),
]

_EVENT: TypeAdapter[SessionEvent] = TypeAdapter(SessionEvent)


def read_events(path: Path) -> list[SessionEvent]:
    """Every event in a session's file, in the order it was written."""
    return [_EVENT.validate_json(line) for line in path.read_text().splitlines()]
