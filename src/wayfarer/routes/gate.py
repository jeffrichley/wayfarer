"""The start gate's checks (ADR-0005)."""

from __future__ import annotations

from fastapi import APIRouter, Response

from wayfarer.routes import Wired

router = APIRouter()


@router.post("/api/gate/read", status_code=202)
async def read_gate(services: Wired) -> Response:
    """Run the start gate's six checks afresh. Looking raises nothing for a person."""

    async def read() -> None:
        services.store.upsert(await services.start_gate.status())

    return services.accept(read())
