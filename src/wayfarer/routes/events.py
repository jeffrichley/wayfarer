"""The stream, the only way data reaches the browser (ADR-0004)."""

from __future__ import annotations

from collections.abc import AsyncIterable
from typing import Annotated

from fastapi import APIRouter, Header
from fastapi.sse import EventSourceResponse

from wayfarer.models import WireEvent
from wayfarer.routes import Wired

router = APIRouter()


# The annotation puts every event's shape in the schema the browser's types come
# from; each goes out framed with its id, which FastAPI sends as it is. An open
# stream is an open page, which keeps the poll at its open rhythm (ADR-0003).
@router.get("/api/events", response_class=EventSourceResponse)
async def events(
    wired: Wired,
    last_event_id: Annotated[str | None, Header()] = None,
) -> AsyncIterable[WireEvent]:
    with wired.efforts.watched():
        async for framed in wired.store.events(last_event_id):
            yield framed  # type: ignore[misc]  # a ServerSentEvent framing a WireEvent
