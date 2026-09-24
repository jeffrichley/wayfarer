"""A session's story, told as beats."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

__all__ = [
    "Beat",
    "BeatKind",
    "Retry",
    "RetryFrom",
    "TestRun",
]


class BeatKind(StrEnum):
    """What kind of moment a beat is."""

    READ = "read"
    """Consecutive reads and searches, folded into one."""
    REMARK = "remark"
    """The agent's own narration."""
    RED = "red"
    """A test run through `wf-test` that failed, by its exit status."""
    GREEN = "green"
    """A test run through `wf-test` that passed, by its exit status."""
    REFACTOR = "refactor"
    """Edits after a green, confirmed by the next run staying green."""
    OUTCOME = "outcome"
    """The one beat that closes a session: the Outcome it reported, or how it ended without."""
    WORKING = "working"
    """A call with no result yet, which its beat replaces, or which goes when it has none."""


class TestRun(BaseModel):
    """One test run, as `wf-test` reported it on its own line."""

    # Not a test class, though its name says so.
    __test__ = False

    exit: int = Field(description="The tests' real exit status: 0 is green, anything else red.")
    passed: int | None = Field(description="Null when the runner wrote no JUnit report.")
    failed: int | None = Field(description="Null when the runner wrote no JUnit report.")
    failing: list[str] = Field(description="The failing tests' names, when the runner wrote them.")


class Beat(BaseModel):
    """One meaningful moment in a session, derived from its events and never stored.

    Folding the session's events again gives the same beats with the same ids, so a
    replay tells exactly the story that was watched live.
    """

    kind: Literal["beat"]
    id: str = Field(description="`beat:<session>:<seq>`, where `seq` is its first event's.")
    session: str = Field(description="The session's run id.")
    seq: int = Field(description="Its first event's place in the session; beats sort by it.")
    beat: BeatKind
    at: datetime = Field(description="When its first event arrived.")
    chapter: int = Field(description="0 for Orient, before the first red; then cycle 1, 2, ….")
    text: str = Field(description="One sentence.")
    run: TestRun | None = Field(description="The test run a red, green or refactor rests on.")
    output: str | None = Field(description="What a red run printed; null for every other beat.")


class RetryFrom(StrEnum):
    """Where a person's retry of a Held ticket starts (#20)."""

    CONTINUE = "continue"
    """Where its last session stopped: its pull request's head, or its kept commits, with
    the conversation resumed when its transcript survives."""
    START_OVER = "start_over"
    """Afresh from the effort branch's head. Its pull request closes; its commits are kept
    on their preservation branch."""


class Retry(BaseModel):
    """A person's retry of a Held ticket: the person's start, not the cascade's."""

    start: RetryFrom = Field(
        default=RetryFrom.CONTINUE,
        description="`continue` unless said otherwise. Offer `start_over` first for a ticket "
        "held by a red re-test, since continuing would build on the version that broke.",
    )
