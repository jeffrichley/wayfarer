"""What a Wayfarer before this one left: its sessions that never finished."""

from __future__ import annotations

from fastapi import APIRouter, Response

from wayfarer.routes import Wired

router = APIRouter()


@router.post("/api/sessions/{run_id}/reap", status_code=202)
async def reap(run_id: str, services: Wired) -> Response:
    """Remove whatever the orphan `run_id` left running, and hold its ticket."""
    return services.accept(services.restart.reap(run_id))
