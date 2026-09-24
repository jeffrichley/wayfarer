"""An effort's cascade, and the item it raises when the effort can ship."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

__all__ = [
    "Cascade",
    "ShipEffort",
]


class Cascade(BaseModel):
    """An effort's cascade, armed or not: once armed, Wayfarer starts a session on every
    takeable ticket, up to the cap, and on whatever each landing frees."""

    kind: Literal["cascade"]
    id: str
    effort: int
    armed: bool
    paused: bool = Field(description="Starting nothing new, while running sessions finish.")
    reason: str | None = Field(
        description="Why it paused itself, in plain words; null when a person paused it, or "
        "it is not paused."
    )
    waiting: bool = Field(
        description="Armed and running, with nothing it may start and nothing under way: "
        "waiting on a person."
    )
    takeable: int = Field(
        description="Takeable tickets it would start, which leaves out any it has started "
        "once already."
    )
    running: int = Field(description="Its tickets claimed or with a session running.")
    cap: int = Field(description="How many sessions may run at once, across every cascade.")
    offer: str = Field(
        description="The confirmation arming asks, naming how many tickets are takeable and "
        "the cap."
    )


class ShipEffort(BaseModel):
    """The Needs you item an effort raises when every ticket in it is closed."""

    kind: Literal["ship"]
    id: str
    effort: int
    title: str
    branch: str = Field(description="The effort branch, which its own pull request goes from.")
    trunk: str = Field(description="The repo's default branch, which it goes into.")
