"""An effort's ticket graph as the canvas draws it (docs/screens/ticket-graph.md).

Derived from the effort's tickets whenever the stream changes and never stored,
since the browser never folds or derives (ADR-0004): the start line that landed
work folds into, a card for every ticket still to land, and the wires between
them. Where each card sits is the browser's, which gives the graph to elkjs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from wayfarer.models.chronicle import Mention
from wayfarer.models.home import Station
from wayfarer.models.read_model import TicketState

__all__ = [
    "Blocker",
    "GraphCard",
    "Neighbour",
    "Reached",
    "Tally",
    "ThreadStep",
    "TicketGraph",
    "Wire",
]


class Neighbour(BaseModel):
    """A ticket one step away on the graph, landed or still to land, as the panel lists it."""

    ticket: Mention
    state: TicketState


class Blocker(Neighbour):
    """A ticket that blocks another directly."""

    via: Mention | None = Field(
        description="The drawn blocker that itself waits on this one, when the edge is "
        "implied and so not drawn; null when it is drawn."
    )


Reached = Literal["done", "here", "ahead"]
"""Where a ticket's thread stands at a station: behind it, at it, or not reached yet."""


class ThreadStep(BaseModel):
    """One station of a ticket's thread, from its map to landing (CONTEXT.md)."""

    station: Station
    name: str = Field(description="What it made there, or that it has not yet.")
    number: int | None = Field(description="The issue it made there; null when it is none.")
    reached: Reached = Field(description="Done and behind it, where it is now, or not reached yet.")
    state: TicketState | None = Field(
        description="The ticket's state, at the station it is at; null at every other."
    )


class Tally(BaseModel):
    """How many of an effort's tickets stand in one state."""

    state: TicketState
    count: int


class GraphCard(BaseModel):
    """A ticket that has not landed, as its card on the graph."""

    ticket: Mention
    state: TicketState = Field(description="Never landed, which folds, or closed, which is off.")
    step: int = Field(
        description="How many tickets that have not landed stand between it and a session: "
        "0 on the frontier, the column beside the start line."
    )
    size: Literal["full", "name-only"] = Field(
        description="Full when it is on the frontier or one step out; name-only further out."
    )
    waiting_on: list[Mention] = Field(
        description="Its blockers that have not landed or closed, in ticket order."
    )
    since: datetime | None = Field(
        description="When the session building it started; null when it is not building."
    )
    at_cap: bool = Field(
        description="Takeable under an armed cascade whose slots are full: it starts when a "
        "slot frees."
    )
    blocked_by: list[Blocker] = Field(
        description="Every ticket blocking it, landed or still to land, in ticket order; "
        "one closed without landing blocks nothing."
    )
    unblocks: list[Neighbour] = Field(
        description="Every ticket still to land that it blocks, in ticket order."
    )
    taken_by: list[str] = Field(
        description="Who took it by hand, when that and no blocker is what keeps it from "
        "the frontier; empty otherwise."
    )
    thread: list[ThreadStep] = Field(description="Its thread, a step per station.")
    upstream: list[int] = Field(
        description="Every ticket still on the graph it waits on, however far back."
    )
    downstream: list[int] = Field(description="Every ticket it frees, however far on.")


class Wire(BaseModel):
    """A drawn edge, from blocker to blocked."""

    blocker: int | None = Field(description="The blocker's number; null for the start line.")
    blocked: int
    kind: Literal["met", "open", "start"] = Field(
        description="`met` where the blocker landed, so it leaves the start line; `open` "
        "where it has not; `start` from the start line to a ticket with nothing to wait on."
    )


class TicketGraph(BaseModel):
    """One effort's ticket graph: the size of the work left, not the work done."""

    kind: Literal["ticket_graph"]
    id: str = Field(description="`graph:<effort>`.")
    effort: int
    tally: list[Tally] = Field(
        description="How many tickets stand in each state, in the order states rank; a "
        "state no ticket is in is left out, and so is closed, which is off the graph."
    )
    landed: list[Mention] = Field(
        description="Every landed ticket, folded into the start line, in dependency order."
    )
    cards: list[GraphCard] = Field(description="Every ticket still to land, in ticket order.")
    wires: list[Wire] = Field(
        description="Every edge drawn: implied edges are not, and edges between landed "
        "tickets are folded away with them."
    )
