"""The start gate, and the environment failure it raises.

The merge queue raises the same `EnvironmentFailure` for a red effort branch,
with the one check that failed.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

__all__ = [
    "EnvironmentFailure",
    "GateCheck",
    "GateStatus",
]


class GateCheck(BaseModel):
    """One of the start gate's six checks, and what it found."""

    name: str = Field(description="What must hold, in plain words.")
    passed: bool
    detail: str = Field(
        description="What was found, in plain words, saying how to fix it when it failed. "
        "Names a credential's variable, never its value."
    )


class EnvironmentFailure(BaseModel):
    """The one Needs you item a failure of the environment raises: a start gate that keeps
    refusing, however many starts it refused, or an effort branch whose tests are red,
    however many candidates it failed."""

    kind: Literal["environment"]
    id: str = Field(description="Stays the same while the failure lasts, so it is one item.")
    reason: str = Field(description="What failed and why, in plain words.")
    failed: list[GateCheck]


class GateStatus(BaseModel):
    """The start gate as it stands now: all six checks, run afresh."""

    kind: Literal["gate"]
    id: Literal["gate"]
    checks: list[GateCheck]
    passed: bool = Field(description="Every check passed, so a session may start.")
    raised: EnvironmentFailure | None = Field(
        description="The item the gate raised when it last refused a start; null when it has "
        "not refused one, or has admitted one since."
    )
