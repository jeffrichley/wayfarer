"""The desk: the person arriving, which is when its order is re-ranked (#57)."""

from __future__ import annotations

from fastapi import APIRouter, Response

from wayfarer.routes import Wired

router = APIRouter()


@router.post("/api/desk/arrived", status_code=202)
async def arrived(services: Wired) -> Response:
    """The person arrived at the desk: its queue is re-ranked, and holds its order from
    now while they work through it. A reload is the same visit, and the page does not
    say it arrived."""

    async def arrive() -> None:
        services.desk.arrived()

    return services.accept(arrive())
