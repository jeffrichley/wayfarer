"""The image sessions run in, and how its last build went (ADR-0005)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

__all__ = [
    "BuildFinished",
    "BuildOutput",
    "ImageStatus",
    "ProbeCheck",
]


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
