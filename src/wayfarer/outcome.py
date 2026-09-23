"""The Outcome: the structured report a session hands back when it ends.

The prompt is only the bare slash command, so these field descriptions are the
one place the session is told what each field means and when a finding blocks.
They reach it as the JSON schema Claude Code validates its output against, so
they are load-bearing, and so are the enums: without them a real run invented
its own field names and filed smells as open findings. For the same reason no
field is allowed that is not named here.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["Assumption", "Axis", "Finding", "FindingKind", "Outcome"]


class Axis(StrEnum):
    """Which half of the review found it."""

    SPEC = "spec"
    """The code does not do what the ticket or its parent spec asked."""
    STANDARDS = "standards"
    """The code breaks a standard the repo documents."""


class FindingKind(StrEnum):
    """Whether a finding holds the ticket back from landing."""

    BLOCKING = "blocking"
    """Any spec finding, and any breach of a documented repo standard."""
    JUDGEMENT = "judgement"
    """A judgement call, including every code smell. It never blocks."""


class Finding(BaseModel):
    """One review finding the session left unfixed."""

    model_config = ConfigDict(extra="forbid")

    axis: Axis = Field(
        description="`spec` when the code does not do what the ticket or its parent spec "
        "asked; `standards` when it breaks a standard the repo documents."
    )
    kind: FindingKind = Field(
        description="`blocking` for every spec finding and every breach of a documented repo "
        "standard; `judgement` for a judgement call, including every code smell. Only "
        "`blocking` holds the ticket back from landing."
    )
    what: str = Field(description="What is wrong, in one sentence.")
    cites: str = Field(
        description="The spec line or the documented standard it breaks, quoted word for word."
    )
    file: str | None = Field(default=None, description="The file it is in, when it is in one.")
    line: int | None = Field(default=None, description="The line it is on, when it is on one.")

    @property
    def blocks(self) -> bool:
        """Any spec finding, whatever the session called it, and any breach of a
        documented standard; never a judgement call on the standards axis."""
        return self.axis is Axis.SPEC or self.kind is FindingKind.BLOCKING


class Assumption(BaseModel):
    """A decision the session made for itself rather than stopping to ask."""

    model_config = ConfigDict(extra="forbid")

    what: str = Field(description="What was assumed, in one sentence.")
    why: str = Field(description="Why, and what the ticket, spec and code left open.")


class Outcome(BaseModel):
    """What the session did, reported once as it ends."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["done", "not_done"] = Field(
        description="`done` when the ticket's acceptance criteria are met and the work is "
        "committed; `not_done` otherwise."
    )
    summary: str = Field(
        description="What was built and how it was tested, for a person reviewing the pull "
        "request; it becomes the pull request's body."
    )
    open_findings: list[Finding] = Field(
        description="Only the review findings left unfixed; a finding that was fixed is not "
        "listed. Empty when none are left."
    )
    assumptions: list[Assumption] = Field(
        description="Every decision made without asking because the ticket, spec and code "
        "did not settle it, including the seam chosen when none was agreed. An assumption "
        "never holds the ticket back. Empty when none were made."
    )
