"""A stand-in for Waystation's continuous queue (waystation#113), deleted when it ships.

A fan-out reads its whole batch before anything starts, so it cannot grow as
tickets free; the cascade needs runs submitted one at a time, the moment each is
takeable. This has the queue's interface over Waystation's public calls: submit
a spec, an optional cap, and a block whose end stops every run. Each run is a
task of its own, because stopping one ticket means cancelling its task and no
other, and each is preflighted as it starts, not as it was queued.

Iterating results as they complete is the real queue's too, and is left out
until something here reads them that way.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any, Self

from waystation import RunResult, RunSpec

__all__ = ["Queue"]


class Queue:
    """Runs submitted one at a time, at most `max_concurrency` at once."""

    def __init__(self, max_concurrency: int | None = None) -> None:
        # FIFO, so runs start in the order they arrived as slots free.
        self._slots = asyncio.Semaphore(max_concurrency) if max_concurrency else None
        # The loop holds tasks weakly, so each is held here until it ends.
        self._runs: set[asyncio.Task[Any]] = set()
        self._stopped = False

    def submit[T](self, spec: RunSpec[T]) -> asyncio.Task[RunResult[T]]:
        """Run `spec` once a slot is free; its task, to await or cancel. Once the
        queue has stopped, the task is cancelled before the run begins."""
        run = asyncio.create_task(self._run(spec))
        self._runs.add(run)
        run.add_done_callback(self._runs.discard)
        if self._stopped:
            run.cancel()
        return run

    async def _run[T](self, spec: RunSpec[T]) -> RunResult[T]:
        async with self._slots or contextlib.nullcontext():
            # `perform` preflights for itself, so the check is as of now.
            return await spec.perform()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        """Stop every run, and return once each has wound down, its work kept
        (Waystation ADR-0017)."""
        self._stopped = True
        runs = list(self._runs)
        for run in runs:
            run.cancel()
        if runs:
            await asyncio.wait(runs)
