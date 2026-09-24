"""An effort: read its ticket graph, and steer its cascade; and every cascade at once."""

from __future__ import annotations

from fastapi import APIRouter, Response

from wayfarer.routes import Wired

router = APIRouter()


@router.post("/api/efforts/{number}/read", status_code=202)
async def read_effort(number: int, services: Wired) -> Response:
    """Read an effort's ticket graph from GitHub afresh (ADR-0003)."""
    return services.accept(services.efforts.read(number))


@router.post("/api/efforts/{number}/arm", status_code=202)
async def arm(number: int, services: Wired) -> Response:
    """Arm the effort's cascade, the only way a session ever starts; or resume it."""
    return services.accept(services.cascades.arm(number))


@router.post("/api/efforts/{number}/pause", status_code=202)
async def pause(number: int, services: Wired) -> Response:
    """Start nothing new on the effort; its running sessions finish."""
    return services.accept(services.cascades.pause(number))


@router.post("/api/efforts/{number}/resume", status_code=202)
async def resume(number: int, services: Wired) -> Response:
    """Resume the effort's cascade, starting what it can as of a fresh read."""
    return services.accept(services.cascades.resume(number))


@router.post("/api/cascades/resume", status_code=202)
async def resume_paused(services: Wired) -> Response:
    """Resume every cascade the environment paused, once the start gate admits a start;
    a cascade the person paused stays paused."""
    return services.accept(services.cascades.resume_paused())
