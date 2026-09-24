"""The review desk: Needs you in an order that holds still while the person works
through it (docs/screens/review-desk.md).

Derived from Needs you and never stored but the order it froze, which lives only
as long as the process (#57).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from wayfarer.models.home import Need

__all__ = ["Desk", "DeskEntry"]


class DeskEntry(BaseModel):
    """One item in the desk's queue, where it stood when the person arrived."""

    key: str = Field(
        description="Stays the same while the item lasts, whatever kind it turns: "
        "`ticket:<n>` for an item on a ticket, else the item's own id."
    )
    need: Need = Field(
        description="The item as it stands, said live; once resolved, as it last stood."
    )
    new: bool = Field(description="It arrived after the person did, so it joined at the bottom.")
    resolved: str | None = Field(
        description="What happened to it, in plain words, once it no longer needs the person; "
        "null while it does."
    )


class Desk(BaseModel):
    """Needs you as the desk shows it: in the order it stood when the person arrived, each
    item said live, new ones at the bottom, and resolved ones kept in place. Arriving
    again re-ranks it; before the first arrival it is the live order."""

    kind: Literal["desk"]
    id: Literal["desk"]
    entries: list[DeskEntry]
