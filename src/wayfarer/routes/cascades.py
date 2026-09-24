"""Every cascade at once: the environment's failure paused them all (#57)."""

from __future__ import annotations

from fastapi import APIRouter, Response

from wayfarer.routes import Wired

router = APIRouter()


@router.post("/api/cascades/resume", status_code=202)
async def resume_paused(services: Wired) -> Response:
    """Resume every cascade the environment paused, once the start gate admits a start;
    a cascade the person paused stays paused."""
    return services.accept(services.cascades.resume_paused())
