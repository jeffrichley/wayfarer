"""Whether the app is up, and which version it runs."""

from __future__ import annotations

from fastapi import APIRouter

from wayfarer.models import Health
from wayfarer.routes import Wired

router = APIRouter()


@router.get("/api/health")
async def health(services: Wired) -> Health:
    return Health(version=services.running)
