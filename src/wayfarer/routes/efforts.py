"""An effort: read its ticket graph, and steer its cascade."""

from __future__ import annotations

from fastapi import APIRouter, Response

from wayfarer.routes import Wired

router = APIRouter()


@router.post("/api/efforts/{number}/read", status_code=202)
async def read_effort(number: int, wired: Wired) -> Response:
    """Read an effort's ticket graph from GitHub afresh (ADR-0003)."""
    return wired.accept(wired.efforts.read(number))


@router.post("/api/efforts/{number}/arm", status_code=202)
async def arm(number: int, wired: Wired) -> Response:
    """Arm the effort's cascade, the only way a session ever starts; or resume it."""
    return wired.accept(wired.cascades.arm(number))


@router.post("/api/efforts/{number}/pause", status_code=202)
async def pause(number: int, wired: Wired) -> Response:
    """Start nothing new on the effort; its running sessions finish."""
    return wired.accept(wired.cascades.pause(number))


@router.post("/api/efforts/{number}/resume", status_code=202)
async def resume(number: int, wired: Wired) -> Response:
    """Resume the effort's cascade, starting what it can as of a fresh read."""
    return wired.accept(wired.cascades.resume(number))
