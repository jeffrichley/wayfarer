"""Every shape that crosses to the browser, defined once.

FastAPI publishes these as OpenAPI, and `web/src/api.gen.ts` is generated from
that schema (`pnpm gen:types`), so the browser's types never drift from these
(ADR-0004).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

__all__ = ["BuildFinished", "BuildOutput", "Health", "ImageStatus", "ProbeCheck"]


class Health(BaseModel):
    """That the process is up, and which Wayfarer it is."""

    version: str


class ImageStatus(BaseModel):
    """The image this repo's sessions run in: Wayfarer's base plus the repo's layer (ADR-0005)."""

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
    """One line of a build's output, as Docker printed it."""

    kind: Literal["output"]
    line: str


class BuildFinished(BaseModel):
    """How a build ended. The last event of its stream."""

    kind: Literal["finished"]
    tag: str
    ready: bool = Field(description="Built and passed its probe, so sessions may use it.")
    error: str | None = Field(description="Why the build itself failed; null when it built.")
    checks: list[ProbeCheck] = Field(description="The probe's checks; empty when it never built.")


BuildEvent = Annotated[BuildOutput | BuildFinished, Field(discriminator="kind")]
