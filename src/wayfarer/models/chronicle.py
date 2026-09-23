"""The chronicle: one line for each thing that moved a ticket (#22)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

__all__ = [
    "Answered",
    "Armed",
    "Asked",
    "ChronicleLine",
    "Closed",
    "Held",
    "Landed",
    "Mention",
    "Published",
    "ReadyToShip",
    "Retried",
    "Shipped",
    "Someone",
    "Taken",
    "Wayfarer",
    "You",
]


class Someone(BaseModel):
    """Anyone but you, whom a line names by their login (#22)."""

    login: str


# Who moved a ticket is read from the kind of event, not the timeline's actor,
# since Wayfarer writes with the person's own token (#22). "wayfarer" reads
# passively, "you" reads "You", and anyone else is named.
Wayfarer = Literal["wayfarer"]
You = Literal["you"]


class Mention(BaseModel):
    """A ticket or an effort as a line names it: by its title, its number riding after."""

    number: int
    title: str


class Taken(BaseModel):
    """A ticket was taken: by a session the cascade started, or by a person's hand."""

    kind: Literal["taken"]
    ticket: Mention
    by: Wayfarer | You | Someone = Field(
        description="Wayfarer when a session the cascade started took it; a person otherwise."
    )


class Asked(BaseModel):
    """A ticket's session ended to ask a person something."""

    kind: Literal["asked"]
    ticket: Mention
    gist: str | None = Field(
        description="The question's gist, quoted as the session wrote it: one sentence, "
        "since a line is at most two (#22). Null until asking by ending gives it (#42)."
    )


class Answered(BaseModel):
    """A person answered a ticket's question, and its session resumed."""

    kind: Literal["answered"]
    ticket: Mention
    by: You | Someone


class Held(BaseModel):
    """A ticket was kept back until a person decides."""

    kind: Literal["held"]
    ticket: Mention
    reason: str | None = Field(
        description="The plain-words Held reason, quoted: one sentence, since a line is at "
        "most two (#22). Null until the chronicle reads it (#41)."
    )


class Retried(BaseModel):
    """You retried a Held ticket (#20). Only Wayfarer starts a session, so only you retry."""

    kind: Literal["retried"]
    ticket: Mention
    over: bool | None = Field(
        description="Started over on the effort branch's head, rather than continuing "
        "where its session stopped. Null until the chronicle reads which (#41)."
    )


class Landed(BaseModel):
    """A ticket landed on its effort branch, with what that directly caused (#22)."""

    kind: Literal["landed"]
    ticket: Mention
    by: Wayfarer | You | Someone = Field(
        description="Wayfarer for a landing through the merge queue; a person for a merge "
        "by hand on GitHub, which lands untested and the line says so (#21)."
    )
    freed: list[Mention] = Field(description="The tickets its landing made takeable.")
    started: list[Mention] = Field(description="Those of them the cascade started a session on.")


class Closed(BaseModel):
    """A person closed a ticket without landing it."""

    kind: Literal["closed"]
    ticket: Mention
    by: You | Someone


class Armed(BaseModel):
    """You armed the effort's cascade, with the sessions it started straight away. The
    cascade is Wayfarer's, so only you arm it (#14)."""

    kind: Literal["armed"]
    started: list[Mention]


class Published(BaseModel):
    """`/to-tickets` published the effort's tickets, with what that directly caused."""

    kind: Literal["published"]
    tickets: int = Field(description="How many tickets it published.")
    freed: list[Mention] = Field(description="Those of them takeable from the start.")
    started: list[Mention] = Field(description="Those the cascade started a session on.")


class ReadyToShip(BaseModel):
    """The effort's last ticket landed, so the effort can ship."""

    kind: Literal["ready_to_ship"]


class Shipped(BaseModel):
    """The effort's branch landed on the trunk."""

    kind: Literal["shipped"]


class ChronicleLine(BaseModel):
    """One line of the chronicle: one thing that moved a ticket, with what it directly
    caused, derived from GitHub and never stored (#22). The browser writes its
    sentence from one template per kind of movement, so a rebuilt chronicle reads
    the same and no line can misname a ticket."""

    kind: Literal["chronicle_line"]
    id: str
    at: datetime
    effort: Mention = Field(description="The effort it moved, named on the right of the line.")
    moved: Annotated[
        Taken
        | Asked
        | Answered
        | Held
        | Retried
        | Landed
        | Closed
        | Armed
        | Published
        | ReadyToShip
        | Shipped,
        Field(discriminator="kind"),
    ]
