"""A ticket's pull request: read its diff, as the desk does when it opens a review."""

from __future__ import annotations

from fastapi import APIRouter, Response

from wayfarer.routes import Wired

router = APIRouter()


@router.post("/api/pulls/{number}/read", status_code=202)
async def read_diff(number: int, services: Wired) -> Response:
    """Read the pull request's diff from GitHub afresh, and again each time its head
    moves; it arrives on the stream as `diff:<number>` (ADR-0003)."""
    return services.accept(services.diffs.read(number))
