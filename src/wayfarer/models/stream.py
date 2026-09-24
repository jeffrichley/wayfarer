"""The page's one stream, and the items it carries (ADR-0004).

Everything the browser holds is an `Item`: a shape with a `kind` and an `id`
unique across every kind. It reaches the browser only as a `WireEvent` on the
page's one stream, which the browser applies by id without folding anything.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from wayfarer.models.cascade import Cascade, ShipEffort
from wayfarer.models.chronicle import ChronicleLine
from wayfarer.models.desk import Desk
from wayfarer.models.gate import EnvironmentFailure, GateStatus
from wayfarer.models.graph import TicketGraph
from wayfarer.models.home import Home, LineRow, NeedsYou
from wayfarer.models.image import BuildFinished, BuildOutput, ImageStatus
from wayfarer.models.read_model import Effort, EffortUnreadable, Ticket
from wayfarer.models.restart import Orphan, UnknownContainer
from wayfarer.models.sessions import Beat

__all__ = [
    "Item",
    "Removal",
    "Snapshot",
    "Upsert",
    "WireEvent",
]


Item = Annotated[
    ImageStatus
    | BuildOutput
    | BuildFinished
    | Effort
    | EffortUnreadable
    | Ticket
    | GateStatus
    | EnvironmentFailure
    | Cascade
    | ShipEffort
    | Orphan
    | UnknownContainer
    | Beat
    | ChronicleLine
    | Home
    | LineRow
    | NeedsYou
    | Desk
    | TicketGraph,
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
