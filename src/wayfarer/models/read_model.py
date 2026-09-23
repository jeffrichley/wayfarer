"""An effort and its tickets, as GitHub has them now."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

__all__ = [
    "Checks",
    "Effort",
    "EffortUnreadable",
    "PullRequest",
    "Ticket",
    "TicketState",
]


class TicketState(StrEnum):
    """Where a ticket stands, derived from GitHub on every read and never stored.

    When a ticket matches more than one, it takes the first in this order.
    """

    LANDED = "landed"
    """Its PR merged, or it was closed as completed."""
    CLOSED = "closed"
    """Closed without landing: not planned, or a duplicate."""
    ASKED = "asked"
    """Labelled `wayfarer:asked`: its session ended to ask a person something."""
    HELD = "held"
    """Labelled `wayfarer:held`: kept back until a person decides."""
    LANDING = "landing"
    """Its PR is ready, its checks green or absent, and approved if auto-merge is off."""
    IN_REVIEW = "in_review"
    """It has an open PR that is not landing."""
    BUILDING = "building"
    """A session is running on it."""
    TAKEABLE = "takeable"
    """Open, every blocker closed, and nobody on it: on the frontier."""
    BLOCKED = "blocked"
    """Anything else: a blocker is still open, or someone has taken it by hand."""


class Checks(StrEnum):
    """A pull request's checks, rolled up. A PR with no checks has none of these."""

    PASSING = "passing"
    PENDING = "pending"
    FAILING = "failing"


class PullRequest(BaseModel):
    """The pull request carrying a ticket's work, from the ticket's own branch."""

    number: int
    branch: str
    """Its head: the ticket branch, `ticket/<n>-…`."""
    base: str
    """Where it merges: the effort branch."""
    head_commit: str
    """The commit at its head, which moves when work is pushed to it."""
    draft: bool
    merged: bool
    merge_commit: str | None
    """The commit its merge made on its base; None until it merges."""
    checks: Checks | None
    """None when the PR has no checks at all, which counts as green."""
    approved: bool


class Ticket(BaseModel):
    """One ticket in an effort, as GitHub has it now."""

    kind: Literal["ticket"]
    id: str
    number: int
    title: str
    state: TicketState
    open: bool
    """Whether its issue is open. A landed ticket stays open until Wayfarer closes it."""
    labels: list[str]
    assignees: list[str]
    blocked_by: list[int]
    """Every ticket blocking this one, open or closed, from GitHub's issue dependencies."""
    open_blockers: int
    pull_request: PullRequest | None
    place_in_line: int | None = Field(
        description="Its place in its effort branch's merge queue while it is Landing, 1 at "
        "the front; null when it is not in the queue. Read from GitHub, so a restart finds "
        "the same line."
    )


class Effort(BaseModel):
    """An effort's whole ticket graph: its spec issue, and every ticket under it."""

    kind: Literal["effort"]
    id: str
    number: int
    title: str
    trunk: str = Field(
        description="The repo's default branch, which the effort meets once, when it ships."
    )
    tickets: list[str] = Field(description="The ids of its tickets, each an item of its own.")


class EffortUnreadable(BaseModel):
    """An effort Wayfarer was asked to read and could not. It stands in the effort's place."""

    kind: Literal["effort_unreadable"]
    id: str
    number: int
    reason: str = Field(description="Why, in words for the person.")
