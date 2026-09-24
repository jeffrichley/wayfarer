"""One ticket's session: stop it, or answer what it asked."""

from __future__ import annotations

from fastapi import APIRouter, Response

from wayfarer.models import Answer
from wayfarer.routes import Wired

router = APIRouter()


@router.post("/api/tickets/{number}/stop", status_code=202)
async def stop(number: int, services: Wired) -> Response:
    """Stop the ticket's session, keeping its work, and hold the ticket."""
    return services.accept(services.cascades.stop(number))


@router.post("/api/tickets/{number}/answer", status_code=202)
async def answer(number: int, answer: Answer, services: Wired) -> Response:
    """Answer the ticket's question, which resumes its session."""
    return services.accept(services.asker.answer(number, answer.answers))
