"""Home, the line: what changed since the person last looked, where every effort is on
the line, what needs them in live order, and what is running (docs/screens/the-line.md).

Each is derived from the other items on the stream and never stored, but the last
visit it counts from (#58).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from wayfarer.models.cascade import ShipEffort
from wayfarer.models.chronicle import Mention
from wayfarer.models.gate import EnvironmentFailure
from wayfarer.models.read_model import TicketState
from wayfarer.models.restart import Orphan, UnknownContainer

__all__ = [
    "Home",
    "LineRow",
    "LineStations",
    "Need",
    "NeedHeld",
    "NeedQuestion",
    "NeedReview",
    "NeedsYou",
    "Station",
    "Working",
]

Station = Literal["wayfinder", "spec", "tickets", "build", "review", "landed"]
"""The six stations of the skill line, in order."""


class Working(BaseModel):
    """A session running now, named by its ticket."""

    ticket: Mention
    effort: Mention


class Home(BaseModel):
    """The masthead and At work: the story since the person last looked."""

    kind: Literal["home"]
    id: Literal["home"]
    repo: str | None = Field(description="`owner/name`; null when the clone has no GitHub.")
    headline: str = Field(
        description="One sentence under 14 words, leading with the top Needs you item, "
        "then the landings since the last visit."
    )
    standfirst: list[str] = Field(description="One sentence per active effort, from its counts.")
    moving: int = Field(description="How many efforts have tickets still to land.")
    since: datetime | None = Field(
        description="When the person last left home, which the headline counts from; null "
        "before their first visit ends."
    )
    working: list[Working] = Field(description="Every session running, in ticket order.")


class LineStations(BaseModel):
    """The tickets at each station an effort's tickets can reach, one state per ticket
    in the effort's order. The map and the spec are behind every effort in this slice,
    which joins it at `/to-tickets`."""

    tickets: list[TicketState] = Field(description="Sliced and not yet started.")
    build: list[TicketState] = Field(description="Building, or stopped there on a person.")
    review: list[TicketState] = Field(description="With a pull request, landing or not.")
    landed: list[TicketState]


class LineRow(BaseModel):
    """One effort on the line: its tickets at the stations they have reached."""

    kind: Literal["line_row"]
    id: str
    effort: Mention
    reached: Station = Field(
        description="The furthest station any of its tickets has reached: its course is "
        "solid up to it and dashed beyond."
    )
    done: bool = Field(
        description="Every ticket landed or closed, so its course rests in ink rather than "
        "the accent."
    )
    total: int = Field(description="Its tickets, but those closed without landing.")
    stations: LineStations


class NeedQuestion(BaseModel):
    """A ticket whose session ended to ask the person something."""

    kind: Literal["question"]
    ticket: Mention
    effort: Mention
    holds_up: int = Field(description="Its ticket plus every open ticket downstream of it.")
    starts: int = Field(description="The tickets that become takeable the moment its ticket lands.")
    since: datetime | None = Field(
        description="When it started waiting, where the chronicle says; ties go to the "
        "longest waiting."
    )
    gist: str | None = Field(description="The question's gist; null until asking gives it.")


class NeedHeld(BaseModel):
    """A ticket kept back until the person decides."""

    kind: Literal["held"]
    ticket: Mention
    effort: Mention
    holds_up: int = Field(description="Its ticket plus every open ticket downstream of it.")
    starts: int = Field(description="The tickets that become takeable the moment its ticket lands.")
    since: datetime | None = Field(
        description="When it started waiting, where the chronicle says; ties go to the "
        "longest waiting."
    )
    reason: str | None = Field(description="The plain-words reason; null until it is read.")


class NeedReview(BaseModel):
    """A clean, green pull request waiting on the person's approval, auto-merge being off."""

    kind: Literal["review"]
    ticket: Mention
    effort: Mention
    holds_up: int = Field(description="Its ticket plus every open ticket downstream of it.")
    starts: int = Field(description="The tickets that become takeable the moment its ticket lands.")
    since: datetime | None = Field(
        description="When it started waiting, where the chronicle says; ties go to the "
        "longest waiting."
    )


Need = Annotated[
    EnvironmentFailure
    | NeedQuestion
    | NeedHeld
    | NeedReview
    | ShipEffort
    | Orphan
    | UnknownContainer,
    Field(discriminator="kind"),
]
"""Anything waiting on a person."""


class NeedsYou(BaseModel):
    """Everything waiting on a person, across every effort, in live order (#24): an
    environment failure pinned first, then what holds up the most, then what holds up
    nothing: shipping an effort, then what a Wayfarer before this one left. Home shows
    it as it stands; the desk freezes its own copy."""

    kind: Literal["needs_you"]
    id: Literal["needs_you"]
    items: list[Need]
