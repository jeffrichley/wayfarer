"""The page's one stream: everything the browser holds, and each change to it (ADR-0004).

The store holds every item a page may show, keyed by id. A change is an upsert
or a removal, numbered in the order it happened, and every open page receives
each one. A page that connects gets a snapshot. One that reconnects carrying the
id of the last event it saw gets exactly the events it missed when the backlog
still holds them all, and a snapshot when it does not, so it never has a gap and
never sees an event twice.

An event's id carries an epoch drawn when the process starts, so an id from a
Wayfarer that has since restarted is never mistaken for one of this one's.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncGenerator, Iterable
from itertools import islice
from uuid import uuid4

from fastapi.sse import ServerSentEvent

from wayfarer.models import Item, Removal, Snapshot, Upsert

__all__ = ["Store"]


class Store:
    """Every item the browser holds, and the recent changes to them."""

    def __init__(self, backlog: int) -> None:
        # Twelve hex digits: enough that two runs never share one, short enough to
        # read in a trace of the stream.
        self._epoch = uuid4().hex[:12]
        self._items: dict[str, Item] = {}
        self._count = 0
        self._backlog: deque[Upsert | Removal] = deque(maxlen=backlog)
        self._changed = asyncio.Event()
        self._closed = False

    def get(self, id: str) -> Item | None:
        return self._items.get(id)

    def items(self) -> Iterable[Item]:
        return self._items.values()

    def upsert(self, item: Item) -> None:
        """Hold `item` in place of whatever had its id. Holding it already changes nothing."""
        if self._items.get(item.id) == item:
            return
        self._items[item.id] = item
        self._publish(Upsert(kind="upsert", item=item))

    def remove(self, id: str) -> None:
        if self._items.pop(id, None) is not None:
            self._publish(Removal(kind="removal", id=id))

    def close(self) -> None:
        """End every page's stream, so a stopping server has no response left open."""
        self._closed = True
        self._changed.set()

    async def events(self, last_event_id: str | None) -> AsyncGenerator[ServerSentEvent]:
        """A page's stream: resumed after `last_event_id` if it can be, else a snapshot first."""
        seen = self._resumable(last_event_id)
        while not self._closed:
            if seen is None or (missed := self._missed(seen)) is None:
                seen = self._count
                snapshot = Snapshot(kind="snapshot", items=list(self._items.values()))
                yield self._frame(snapshot, seen)
            elif not missed:
                await self._changed.wait()
            else:
                for change in missed:
                    seen += 1
                    yield self._frame(change, seen)

    def _publish(self, change: Upsert | Removal) -> None:
        self._count += 1
        self._backlog.append(change)
        # Waking every page, each of which waits on the next one.
        self._changed.set()
        self._changed = asyncio.Event()

    def _resumable(self, last_event_id: str | None) -> int | None:
        """How many changes a page that saw `last_event_id` had, if they were this process's."""
        epoch, _, count = (last_event_id or "").rpartition("-")
        if epoch != self._epoch or not count.isdigit() or int(count) > self._count:
            return None
        return int(count)

    def _missed(self, seen: int) -> list[Upsert | Removal] | None:
        """The changes after the first `seen`, or None when the backlog no longer holds them all."""
        if self._count - seen > len(self._backlog):
            return None
        return list(islice(self._backlog, len(self._backlog) - (self._count - seen), None))

    def _frame(self, event: Snapshot | Upsert | Removal, count: int) -> ServerSentEvent:
        return ServerSentEvent(data=event, id=f"{self._epoch}-{count}")
