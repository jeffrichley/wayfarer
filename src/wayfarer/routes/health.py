"""Whether the app is up, and which version it runs."""

from __future__ import annotations

from fastapi import APIRouter

from wayfarer.models import Health
from wayfarer.routes import Wired

router = APIRouter()


# Handlers are async so they run on the loop every agent run shares (ADR-0001),
# not in a thread pool beside it.
@router.get("/api/health")
async def health(wired: Wired) -> Health:
    return Health(version=wired.running)
