"""One ticket: stop its session, answer what it asked, or send it into the merge queue."""

from __future__ import annotations

from fastapi import APIRouter, Response

from wayfarer.models import Answer, Retry
from wayfarer.routes import Wired

router = APIRouter()


@router.post("/api/tickets/{number}/stop", status_code=202)
async def stop(number: int, services: Wired) -> Response:
    """Stop the ticket's session, keeping its work, and hold the ticket."""
    return services.accept(services.cascades.stop(number))


@router.post("/api/tickets/{number}/retry", status_code=202)
async def retry(number: int, retry: Retry, services: Wired) -> Response:
    """Retry a Held ticket, continuing where its session stopped or starting over."""
    return services.accept(services.cascades.retry(number, retry.start))


@router.post("/api/tickets/{number}/answer", status_code=202)
async def answer(number: int, answer: Answer, services: Wired) -> Response:
    """Answer the ticket's question, which resumes its session."""
    return services.accept(services.asker.answer(number, answer.answers))


@router.post("/api/tickets/{number}/let-it-land", status_code=202)
async def let_it_land(number: int, services: Wired) -> Response:
    """Let a Held ticket's pull request land: ready, and unheld, so it joins the queue."""
    return services.accept(services.joining.let_it_land(number))


@router.post("/api/tickets/{number}/land-it", status_code=202)
async def land_it(number: int, services: Wired) -> Response:
    """With auto-merge off, approve a clean, green pull request so it joins the queue."""
    return services.accept(services.joining.land_it(number))
