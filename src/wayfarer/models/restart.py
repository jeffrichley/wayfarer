"""What a Wayfarer before this one left behind, found as this one starts.

Both are Needs you items, pinned below everything that holds up a ticket (#24).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from wayfarer.models.chronicle import Mention

__all__ = [
    "Orphan",
    "UnknownContainer",
]


class Orphan(BaseModel):
    """A session the store has as started and never finished: the Wayfarer running it
    stopped before it did. Offered a reap, which removes whatever container it left and
    holds its ticket; its work is not recovered (ADR-0002)."""

    kind: Literal["orphan"]
    id: str = Field(description="`orphan:<run id>`.")
    run_id: str
    ticket: int
    title: str | None = Field(
        description="Its ticket's title; null when GitHub could not be read as Wayfarer started."
    )
    effort: Mention | None = Field(
        description="The effort its ticket is in; null when GitHub has it in none, or could "
        "not be read."
    )
    started: datetime


class UnknownContainer(BaseModel):
    """A container Waystation labelled with a run id the store has never heard of. The
    label carries no repo, so it may be another repo's Wayfarer's: it is shown, and
    never reaped automatically."""

    kind: Literal["unknown_container"]
    id: str = Field(description="`container:<run id>`.")
    run_id: str
