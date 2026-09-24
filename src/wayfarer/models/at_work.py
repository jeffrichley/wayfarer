"""At work: a lane for every session running or stopped to ask, and what each has
changed (docs/screens/live-build.md).

A lane is derived from the other items on the stream whenever they change, and
never stored; a session's changes are folded from its events as its beats are.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from wayfarer.models.asking import Asking
from wayfarer.models.chronicle import Mention
from wayfarer.models.read_model import TicketState

__all__ = [
    "Changes",
    "FileChange",
    "Lane",
    "TestMark",
]


class FileChange(BaseModel):
    """One file a session changed, and by how many lines."""

    path: str = Field(description="Relative to the session's workspace.")
    added: int
    removed: int


class Changes(BaseModel):
    """What one session has changed so far, as its own edits say: not a diff, so a file
    it wrote whole without having written it before counts every line as added."""

    kind: Literal["changes"]
    id: str = Field(description="`changes:<session>`.")
    session: str = Field(description="The session's run id.")
    files: list[FileChange] = Field(description="In the order each was first changed.")


class TestMark(BaseModel):
    """One test run, as its mark in a session's rhythm."""

    # Not a test class, though its name says so.
    __test__ = False

    passed: bool = Field(description="Green by its exit status; red otherwise.")
    at: datetime


class Lane(BaseModel):
    """One ticket with a session on it now, or whose session stopped to ask the person."""

    kind: Literal["lane"]
    id: str = Field(description="`lane:<ticket>`.")
    ticket: Mention
    effort: Mention
    state: TicketState = Field(description="Building, or Asked.")
    branch: str = Field(description="Where its work goes: its pull request's, or its own.")
    session: str | None = Field(
        description="The run id of its latest session, whose beats are its story and whose "
        "changes are `changes:<session>`; null until one is recorded."
    )
    started: datetime | None = Field(description="When its latest session started.")
    latest: str | None = Field(
        description="What its latest session last did, in one sentence; for an Asked ticket, "
        "what it asked. Null before its first beat."
    )
    criteria: list[str] = Field(description="Its acceptance criteria, as its ticket words them.")
    rhythm: list[TestMark] = Field(description="Its latest session's test runs, in order.")
    question: Asking | None = Field(description="What it asked, while it waits on an answer.")
