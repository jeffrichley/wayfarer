"""Every shape that crosses to the browser, defined once.

FastAPI publishes these as OpenAPI, and `web/src/api.gen.ts` is generated from
that schema (`pnpm gen:types`), so the browser's types never drift from these
(ADR-0004).

Everything the browser holds is an `Item`: a shape with a `kind` and an `id`
unique across every kind. It reaches the browser only as a `WireEvent` on the
page's one stream, which the browser applies by id without folding anything.
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
    "EffortUnreadable",
    "EnvironmentFailure",
    "GateCheck",
    "GateStatus",
    "Health",
    "ImageStatus",
    "ProbeCheck",
    "PullRequest",
    "Removal",
    "Snapshot",
    "Ticket",
    "TicketState",
    "Upsert",
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

    kind: Literal["ticket"]
    id: str
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

    kind: Literal["effort"]
    id: str
    number: int
    title: str
    tickets: list[str] = Field(description="The ids of its tickets, each an item of its own.")


class EffortUnreadable(BaseModel):
    """An effort Wayfarer was asked to read and could not. It stands in the effort's place."""

    kind: Literal["effort_unreadable"]
    id: str
    number: int
    reason: str = Field(description="Why, in words for the person.")


class ImageStatus(BaseModel):
    """The image this repo's sessions run in: Wayfarer's base plus the repo's layer (ADR-0005)."""

    kind: Literal["image"]
    id: Literal["image"]
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
    """One line of the last build's output, as Docker printed it."""

    kind: Literal["build_output"]
    id: str
    number: int = Field(description="Where the line falls in the output, counting from 0.")
    line: str


class BuildFinished(BaseModel):
    """How the last build ended."""

    kind: Literal["build_finished"]
    id: Literal["build_finished"]
    tag: str
    ready: bool = Field(description="Built and passed its probe, so sessions may use it.")
    error: str | None = Field(description="Why the build itself failed; null when it built.")
    checks: list[ProbeCheck] = Field(description="The probe's checks; empty when it never built.")


class GateCheck(BaseModel):
    """One of the start gate's six checks, and what it found."""

    name: str = Field(description="What must hold, in plain words.")
    passed: bool
    detail: str = Field(
        description="What was found, in plain words, saying how to fix it when it failed. "
        "Names a credential's variable, never its value."
    )


class EnvironmentFailure(BaseModel):
    """The one Needs you item a failed start gate raises, however many starts it refused."""

    kind: Literal["environment"]
    id: str = Field(description="Stays the same while the gate keeps failing, so it is one item.")
    reason: str = Field(description="Which checks failed and why, in plain words.")
    failed: list[GateCheck]


class GateStatus(BaseModel):
    """The start gate as it stands now: all six checks, run afresh."""

    kind: Literal["gate"]
    id: Literal["gate"]
    checks: list[GateCheck]
    passed: bool = Field(description="Every check passed, so a session may start.")
    raised: EnvironmentFailure | None = Field(
        description="The item the gate raised when it last refused a start; null when it has "
        "not refused one, or has admitted one since."
    )


Item = Annotated[
    ImageStatus | BuildOutput | BuildFinished | Effort | EffortUnreadable | Ticket | GateStatus,
    Field(discriminator="kind"),
]
"""Anything the browser holds, keyed by its `id`."""


class Snapshot(BaseModel):
    """Everything there is, replacing whatever the browser held."""

    kind: Literal["snapshot"]
    items: list[Item]


class Upsert(BaseModel):
    """One item, new or replacing the one with its id."""

    kind: Literal["upsert"]
    item: Item


class Removal(BaseModel):
    """The item with this id is gone."""

    kind: Literal["removal"]
    id: str


WireEvent = Annotated[Snapshot | Upsert | Removal, Field(discriminator="kind")]
"""Every event on the page's stream (ADR-0004)."""
