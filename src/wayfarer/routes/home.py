"""Home: the person arriving and leaving, which is what the headline counts from (#58)."""

from __future__ import annotations

from fastapi import APIRouter, Response

from wayfarer.routes import Wired

router = APIRouter()


@router.post("/api/home/arrived", status_code=202)
async def arrived(services: Wired) -> Response:
    """A new visit to home: its headline counts from when the last one ended. A reload
    is the same visit, and the page does not say it arrived."""

    async def arrive() -> None:
        services.home.arrived()

    return services.accept(arrive())


@router.post("/api/home/left", status_code=202)
async def left(services: Wired) -> Response:
    """The person left home, which ends their visit; the page says so as it goes."""

    async def leave() -> None:
        services.home.left()

    return services.accept(leave())
