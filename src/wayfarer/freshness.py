"""The one signal the read model runs on: something may have changed, so re-read.

Nothing that raises it carries data (ADR-0003). Wayfarer's own writes raise it
the moment they are made, and the poll raises it when GitHub answers anything but
`304 Not Modified` (`poll.py`). Whoever holds a `Watch` re-reads when it fires.

A watch is also a reason to stay fresh: while one is held, the poll runs at the
open rhythm, and every pull request a watch awaits has its checks polled too,
because checks never change the issue the poll lists.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Iterator
from contextlib import contextmanager

__all__ = ["Freshness", "Watch"]


class Freshness:
    def __init__(self) -> None:
        self._version = 0
        self._poked = asyncio.Event()
        self._watches: set[Watch] = set()
        self._attention = asyncio.Event()

    def poke(self) -> None:
        """Something may have changed: wake every watch."""
        self._version += 1
        # Swapped rather than cleared, so every waiter on the old one wakes.
        self._poked.set()
        self._poked = asyncio.Event()

    @property
    def version(self) -> int:
        """How many times it has fired; a watch may start from any earlier count."""
        return self._version

    @contextmanager
    def watch(self, since: int | None = None) -> Iterator[Watch]:
        """Held for as long as a page is open or a cascade is armed.

        Its first `changed` returns at once if the signal has fired since `since`,
        so a read made before the watch began misses nothing.
        """
        watch = Watch(self, self._version if since is None else since)
        self._watches.add(watch)
        self._notice()
        try:
            yield watch
        finally:
            self._watches.discard(watch)
            self._notice()

    @property
    def watched(self) -> bool:
        return bool(self._watches)

    @property
    def awaited(self) -> set[str]:
        """The branches of every pull request some watch awaits."""
        return set().union(*(watch.awaiting for watch in self._watches))

    async def attention_changed(self, timeout: float) -> None:
        """Returns when a watch starts or ends, or after `timeout` seconds."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._attention.wait(), timeout)

    def _notice(self) -> None:
        self._attention.set()
        self._attention = asyncio.Event()


class Watch:
    """One watcher's hold on the signal."""

    def __init__(self, freshness: Freshness, seen: int) -> None:
        self._freshness = freshness
        self._seen = seen
        self.awaiting: frozenset[str] = frozenset()
        """The branches of the pull requests this watcher is waiting on."""

    async def changed(self) -> None:
        """Returns once something may have changed since it last returned.

        Pokes that land while the watcher is busy re-reading fold into one.
        """
        while self._seen == self._freshness._version:
            await self._freshness._poked.wait()
        self._seen = self._freshness._version
