"""The session image (ADR-0005)."""

from __future__ import annotations

from fastapi import APIRouter, Response

from wayfarer.routes import Wired

router = APIRouter()


@router.post("/api/image/read", status_code=202)
async def read_image(wired: Wired) -> Response:
    """Read what the session image would be now (ADR-0005)."""
    return wired.accept(wired.images.read())


@router.post("/api/image/build", status_code=202)
async def build_image(wired: Wired) -> Response:
    """Build the session image. Builds happen only here, when a person clicks."""
    return wired.accept(wired.images.build())
