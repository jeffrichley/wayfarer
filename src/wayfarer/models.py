"""Every shape that crosses to the browser, defined once.

FastAPI publishes these as OpenAPI, and `web/src/api.gen.ts` is generated from
that schema (`pnpm gen:types`), so the browser's types never drift from these
(ADR-0004).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

__all__ = ["Checks", "Effort", "Health", "PullRequest", "Ticket", "TicketState"]


class Health(BaseModel):
    """That the process is up, and which Wayfarer it is."""

    version: str


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
    draft: bool
    merged: bool
    checks: Checks | None
    """None when the PR has no checks at all, which counts as green."""
    approved: bool


class Ticket(BaseModel):
    """One ticket in an effort, as GitHub has it now."""

    number: int
    title: str
    state: TicketState
    labels: list[str]
    assignees: list[str]
    blocked_by: list[int]
    """Every ticket blocking this one, open or closed, from GitHub's issue dependencies."""
    open_blockers: int
    pull_request: PullRequest | None


class Effort(BaseModel):
    """An effort's whole ticket graph: its spec issue, and every ticket under it."""

    number: int
    title: str
    tickets: list[Ticket]
