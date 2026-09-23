"""One ticket's session."""

from __future__ import annotations

from fastapi import APIRouter, Response

from wayfarer.routes import Wired

router = APIRouter()


@router.post("/api/tickets/{number}/stop", status_code=202)
async def stop(number: int, services: Wired) -> Response:
    """Stop the ticket's session, keeping its work, and hold the ticket."""
    return services.accept(services.cascades.stop(number))
