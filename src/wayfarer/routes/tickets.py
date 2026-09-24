"""One ticket's session."""

from __future__ import annotations

from fastapi import APIRouter, Response

from wayfarer.models import Retry
from wayfarer.routes import Wired

router = APIRouter()


@router.post("/api/tickets/{number}/stop", status_code=202)
async def stop(number: int, services: Wired) -> Response:
    """Stop the ticket's session, keeping its work, and hold the ticket."""
    return services.accept(services.cascades.stop(number))


@router.post("/api/tickets/{number}/retry", status_code=202)
async def retry(number: int, retry: Retry, services: Wired) -> Response:
    """Retry a Held ticket, continuing where its session stopped or starting over."""
    return services.accept(services.cascades.retry(number, retry.start))
