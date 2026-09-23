"""Every shape that crosses to the browser, defined once.

FastAPI publishes these as OpenAPI, and `web/src/api.gen.ts` is generated from
that schema (`pnpm gen:types`), so the browser's types never drift from these
(ADR-0004).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

__all__ = [
    "BuildFinished",
    "BuildOutput",
    "Checks",
    "Effort",
    "Health",
    "ImageStatus",
    "ProbeCheck",
    "PullRequest",
    "Ticket",
    "TicketState",
]


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
    branch: str
    """Its head: the ticket branch, `ticket/<n>-…`."""
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


class ImageStatus(BaseModel):
    """The image this repo's sessions run in: Wayfarer's base plus the repo's layer (ADR-0005)."""

    layer: str = Field(description="Where the repo's layer lives, relative to the clone.")
    refusal: str | None = Field(
        description="Why no image can be built for this repo, in words for the person; "
        "null when one can."
    )
    tag: str | None = Field(
        description="The tag an image of the current inputs has; null when refused."
    )
    ready: bool = Field(description="That tag exists, so it was built and passed its probe.")
    building: bool


class ProbeCheck(BaseModel):
    """One thing the probe proved, or failed to prove, about a newly built image."""

    name: str
    passed: bool
    detail: str


class BuildOutput(BaseModel):
    """One line of a build's output, as Docker printed it."""

    kind: Literal["output"]
    line: str


class BuildFinished(BaseModel):
    """How a build ended. The last event of its stream."""

    kind: Literal["finished"]
    tag: str
    ready: bool = Field(description="Built and passed its probe, so sessions may use it.")
    error: str | None = Field(description="Why the build itself failed; null when it built.")
    checks: list[ProbeCheck] = Field(description="The probe's checks; empty when it never built.")


BuildEvent = Annotated[BuildOutput | BuildFinished, Field(discriminator="kind")]
