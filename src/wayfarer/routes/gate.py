"""The start gate's checks (ADR-0005)."""

from __future__ import annotations

from fastapi import APIRouter, Response

from wayfarer.routes import Wired

router = APIRouter()


@router.post("/api/gate/read", status_code=202)
async def read_gate(wired: Wired) -> Response:
    """Run the start gate's six checks afresh. Looking raises nothing for a person."""

    async def read() -> None:
        wired.store.upsert(await wired.start_gate.status())

    return wired.accept(read())
