"""A pull request's diff, as the review desk shows it (#109, docs/screens/review-desk.md).

Read from GitHub when a review opens and again when the pull request's head
moves, and never stored (ADR-0003). Its shape is the one the diff view takes
(`web/src/Diff.tsx`).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

__all__ = [
    "DiffFile",
    "DiffLine",
    "LeftOut",
    "Omission",
    "PullDiff",
    "PullDiffUnreadable",
]


class DiffLine(BaseModel):
    """One line of a file's change: an added line has only a new number, a removed one
    only an old number, and a line of context around them has both."""

    old: int | None
    new: int | None
    code: str = Field(description="The line as written, without its sign.")


class DiffFile(BaseModel):
    """One changed file, sent whole."""

    path: str
    lines: list[DiffLine] = Field(description="Every hunk's lines, in order.")


class Omission(StrEnum):
    """Why a changed file's lines were not sent."""

    BOUND = "bound"
    """Sending it would pass the bound on how much of a diff is sent."""
    NO_PATCH = "no_patch"
    """GitHub gives no patch for it: a binary file, or one too large for GitHub to show."""


class LeftOut(BaseModel):
    """A changed file whose lines were not sent, named with its counts."""

    path: str
    added: int
    removed: int
    why: Omission


class PullDiff(BaseModel):
    """A pull request's changed files as its head has them, in GitHub's order."""

    kind: Literal["pull_diff"]
    id: str = Field(description="`diff:<pull request>`.")
    pull: int
    head_commit: str = Field(description="The head the diff was read at.")
    files: list[DiffFile] = Field(
        description="Each file sent, until the next would pass the bound on lines sent."
    )
    left_out: list[LeftOut] = Field(
        description="Each file read but not sent, in GitHub's order among the rest."
    )
    unread: int = Field(
        description="Changed files past the bound that were never read from GitHub, so "
        "are counted rather than named."
    )


class PullDiffUnreadable(BaseModel):
    """A pull request whose diff GitHub would not give, and why."""

    kind: Literal["pull_diff_unreadable"]
    id: str = Field(description="`diff:<pull request>`.")
    pull: int
    reason: str
