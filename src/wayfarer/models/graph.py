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
from wayfarer.models.read_model import TicketState

__all__ = [
    "GraphCard",
    "ImpliedEdge",
    "TicketGraph",
    "Wire",
]


class ImpliedEdge(BaseModel):
    """A blocker the ticket already waits on through another, so it is not drawn."""

    blocker: Mention
    via: Mention = Field(description="The drawn blocker that itself waits on `blocker`.")


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
    implied: list[ImpliedEdge] = Field(description="Its blockers not drawn, and through which.")
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
    landed: list[Mention] = Field(
        description="Every landed ticket, folded into the start line, in dependency order."
    )
    cards: list[GraphCard] = Field(description="Every ticket still to land, in ticket order.")
    wires: list[Wire] = Field(
        description="Every edge drawn: implied edges are not, and edges between landed "
        "tickets are folded away with them."
    )
