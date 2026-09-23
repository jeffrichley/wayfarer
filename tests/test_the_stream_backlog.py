"""The stream's backlog is bounded, so a page that missed more than it holds starts over.

Held on the store itself: the backlog is a setting of a thousand changes, more
than a test at the HTTP surface should make just to spill it.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from wayfarer.models import EffortUnreadable
from wayfarer.stream import Store

pytestmark = pytest.mark.unit


def _unreadable(number: int) -> EffortUnreadable:
    return EffortUnreadable(
        kind="effort_unreadable", id=f"effort:{number}", number=number, reason="gone"
    )


async def _first(store: Store, last_event_id: str | None) -> tuple[str, Any]:
    stream = store.events(last_event_id)
    event = await anext(stream)
    await stream.aclose()
    assert event.id is not None
    return event.id, event.data


def test_a_page_that_missed_more_than_the_backlog_holds_gets_a_snapshot() -> None:
    async def scenario() -> None:
        store = Store(backlog=2)
        seen, _ = await _first(store, None)
        for number in (1, 2, 3):
            store.upsert(_unreadable(number))

        _, event = await _first(store, seen)

        assert event.kind == "snapshot"
        assert [item.number for item in event.items] == [1, 2, 3]

    asyncio.run(scenario())


def test_a_page_that_missed_no_more_than_the_backlog_holds_gets_just_those() -> None:
    async def scenario() -> None:
        store = Store(backlog=2)
        store.upsert(_unreadable(1))
        seen, _ = await _first(store, None)
        store.upsert(_unreadable(2))
        store.upsert(_unreadable(3))

        _, event = await _first(store, seen)

        assert event.kind == "upsert"
        assert event.item.number == 2

    asyncio.run(scenario())
