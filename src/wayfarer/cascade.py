"""The cascade: arming an effort is the only way a session ever starts.

From arming on, Wayfarer starts a session on every takeable ticket, up to a cap
shared by every armed cascade on the repo, and starts whatever each landing
frees. It acts after every read of an armed effort, and only on what that read
found, because GitHub is the record (ADR-0002): a landing is seen as the read
that finds a blocker closed, and a session ending raises the signal to re-read.

A ticket is takeable on GitHub's own terms — open, every blocker closed, nobody
on it, no pull request, neither held nor asked — so a ticket a person has taken
is left alone. Wayfarer claims it by assigning it to the person it writes as,
and submits its session only once a later read shows the claim landed and
nobody else's beside it: the claim is what stops a restarted Wayfarer starting
it twice. Each ticket is started automatically at most once, which the store's
session rows remember across restarts.

Pausing starts nothing new and lets running sessions finish. Stopping one ticket
cancels its session, its work kept, and holds the ticket. With nothing it may
start and nothing under way, an armed cascade waits on a person; once every
ticket is closed it disarms and raises shipping the effort.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from wayfarer.github import GitHub, GitHubError
from wayfarer.models import (
    Cascade,
    Effort,
    EnvironmentFailure,
    GateStatus,
    ShipEffort,
    Ticket,
    TicketState,
)
from wayfarer.queue import Queue
from wayfarer.read_model import HELD, Efforts
from wayfarer.sessions import Sessions
from wayfarer.settings import Settings
from wayfarer.store import Store
from wayfarer.stream import Store as Stream

__all__ = ["Cascades", "Gate", "SessionsFor"]

_log = logging.getLogger(__name__)

_DONE = (TicketState.LANDED, TicketState.CLOSED)

SessionsFor = Callable[[Store], Sessions]
"""The sessions a start runs, recording into the store it is given."""


class Gate(Protocol):
    """What must hold before a session starts (`gate.StartGate`)."""

    async def admit(self) -> EnvironmentFailure | None: ...

    async def status(self) -> GateStatus: ...


class Cascades:
    """Every cascade on one repo, sharing one cap."""

    def __init__(
        self,
        efforts: Efforts,
        github: GitHub,
        stream: Stream,
        settings: Settings,
        gate: Gate,
        sessions: SessionsFor,
        queue: Queue,
    ) -> None:
        self._efforts = efforts
        self._github = github
        self._stream = stream
        self._settings = settings
        self._gate = gate
        self._sessions = sessions
        self._queue = queue
        self._running: dict[int, asyncio.Task[Any]] = {}
        # Claimed on GitHub, and waiting for a read to show the claim landed.
        self._claimed: set[int] = set()
        # One cascade decision at a time, so two reads never claim one slot twice.
        self._deciding = asyncio.Lock()
        self._opened: Store | None = None
        # Why each cascade that paused itself did; a person's pause needs no reason.
        self._why: dict[int, str] = {}
        # The read model marks what runs here, and cues the cascade after each read.
        efforts.building = self._running.keys()
        efforts.then = self._after_read

    async def arm(self, effort: int) -> None:
        """Arm `effort`'s cascade, or resume it if paused, and start what it can."""
        await self._efforts.read(effort)
        async with self._deciding:
            if not isinstance(self._stream.get(f"effort:{effort}"), Effort):
                return  # Unreadable: the read has already said why, in its place.
            self._store().arm(effort)
            self._why.pop(effort, None)
            # The gate is asked as a cascade is armed, as well as before each start.
            if await self._gate.admit() is not None:
                await self._gate_refused(effort)
            await self._decide(effort)

    async def pause(self, effort: int) -> None:
        """Start nothing new on `effort`; its running sessions finish."""
        async with self._deciding:
            self._store().pause(effort)
            await self._decide(effort)

    async def resume(self, effort: int) -> None:
        """Start what `effort`'s cascade can again, as of a fresh read."""
        self._store().resume(effort)
        self._why.pop(effort, None)
        await self._efforts.read(effort)

    async def stop(self, ticket: int) -> None:
        """Cancel the session on `ticket`, keeping its work, and hold the ticket."""
        running = self._running.get(ticket)
        if running is None:
            return
        running.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await running
        # A cancelled run reports nothing, so its end is written here.
        store = self._store()
        for row in store.sessions():
            if row.ticket == ticket and row.ended is None:
                store.session_ended(row.run_id, datetime.now(UTC), None)
        # Still claimed, so still nobody else's to start.
        await self._github.write("POST", f"/issues/{ticket}/labels", {"labels": [HELD]})

    def close(self) -> None:
        if self._opened is not None:
            self._opened.close()

    async def _after_read(self, effort: int) -> None:
        async with self._deciding:
            await self._decide(effort)

    async def _decide(self, number: int) -> None:
        """Act on what the last read of effort `number` found, and say where it stands."""
        effort = self._stream.get(f"effort:{number}")
        if not isinstance(effort, Effort):
            return
        tickets = [t for id in effort.tickets if isinstance(t := self._stream.get(id), Ticket)]
        store = self._store()
        cascade = store.cascades()
        armed, paused = number in cascade, cascade.get(number, False)
        await self._read_back(tickets, submitting=armed and not paused)
        if armed and tickets and all(ticket.state in _DONE for ticket in tickets):
            store.disarm(number)
            armed = paused = False
            self._stream.upsert(
                ShipEffort(kind="ship", id=f"ship:{number}", effort=number, title=effort.title)
            )
        elif armed and not paused and not await self._start(number, tickets, store):
            paused = True
        self._publish(number, tickets, store, armed=armed, paused=paused)

    async def _read_back(self, tickets: list[Ticket], *, submitting: bool) -> None:
        """Submit each ticket this read shows is claimed by Wayfarer alone (ADR-0002)."""
        for ticket in tickets:
            if ticket.number not in self._claimed:
                continue
            login = await self._github.login()
            if login not in ticket.assignees:
                # A read from before the claim: GitHub took the write, so a later read
                # will show it. Until then it stays claimed, and holds its slot.
                continue
            self._claimed.discard(ticket.number)
            if submitting and ticket.assignees == [login] and _takeable_but_for_the_claim(ticket):
                self._submit(ticket.number)
            else:
                # Someone else took it too, or the cascade paused meanwhile: let it go.
                await self._github.write(
                    "DELETE", f"/issues/{ticket.number}/assignees", {"assignees": [login]}
                )

    async def _start(self, effort: int, tickets: list[Ticket], store: Store) -> bool:
        """Claim every ticket it may start while the cap has room; False if it had to pause."""
        for ticket in self._startable(tickets, store):
            if len(self._running) + len(self._claimed) >= self._settings.cap:
                break
            if await self._gate.admit() is not None:
                await self._gate_refused(effort)
                return False
            try:
                login = await self._github.login()
                await self._github.write(
                    "POST", f"/issues/{ticket.number}/assignees", {"assignees": [login]}
                )
            except GitHubError as error:
                # The environment's failure, not the ticket's. Pausing is also what
                # stops a retry on every read, since a refused write still pokes one.
                self._paused_itself(
                    effort, f"GitHub refused to let Wayfarer claim #{ticket.number}: {error}"
                )
                return False
            # The write raised the signal, so the read that shows the claim is coming.
            self._claimed.add(ticket.number)
        return True

    async def _gate_refused(self, effort: int) -> None:
        """The gate refused: pause, and show the one item it raised. Running sessions carry on."""
        self._paused_itself(effort, "The start gate refused a start.")
        self._stream.upsert(await self._gate.status())

    def _paused_itself(self, effort: int, why: str) -> None:
        _log.warning("The cascade on #%s paused: %s", effort, why)
        self._store().pause(effort)
        self._why[effort] = why

    def _startable(self, tickets: list[Ticket], store: Store) -> list[Ticket]:
        """The takeable tickets never started automatically, in the effort's order."""
        started = store.built() | self._running.keys() | self._claimed
        return [t for t in tickets if t.state is TicketState.TAKEABLE and t.number not in started]

    def _submit(self, ticket: int) -> None:
        run = self._queue.submit(self._sessions(self._store()).spec(ticket))
        self._running[ticket] = run
        run.add_done_callback(lambda ended: self._ended(ticket, ended))
        # Its card is now building: re-read.
        self._github.freshness.poke()

    def _ended(self, ticket: int, run: asyncio.Task[Any]) -> None:
        self._running.pop(ticket, None)
        if not run.cancelled() and (error := run.exception()) is not None:
            _log.error("The session on #%s could not run.", ticket, exc_info=error)
        # Its slot is free and its card no longer building: re-read, and start what can.
        self._github.freshness.poke()

    def _publish(
        self, number: int, tickets: list[Ticket], store: Store, *, armed: bool, paused: bool
    ) -> None:
        takeable = len(self._startable(tickets, store))
        mine = {ticket.number for ticket in tickets}
        running = len(mine & (self._running.keys() | self._claimed))
        cap = self._settings.cap
        self._stream.upsert(
            Cascade(
                kind="cascade",
                id=f"cascade:{number}",
                effort=number,
                armed=armed,
                paused=paused,
                waiting=armed and not paused and not running and not takeable,
                takeable=takeable,
                running=running,
                cap=cap,
                offer=f"{_tickets(takeable)} takeable now, up to {cap} at a time",
                reason=self._why.get(number) if armed and paused else None,
            )
        )

    def _store(self) -> Store:
        """The repo's store, opened on first need: only a readable effort needs it."""
        if self._opened is None:
            assert self._github.repo is not None, "an effort was read, so there is a repo"
            self._opened = Store.for_repo(self._settings.data_dir, self._github.repo)
            # A restart never spends unasked: every cascade armed before it comes back paused.
            self._opened.pause_all()
        return self._opened


def _takeable_but_for_the_claim(ticket: Ticket) -> bool:
    """Open, unblocked, no PR, neither held nor asked: only the claim keeps it from takeable."""
    return (
        ticket.state is TicketState.BLOCKED
        and ticket.open_blockers == 0
        and ticket.pull_request is None
    )


def _tickets(count: int) -> str:
    if count == 1:
        return "1 ticket is"
    return f"{count or 'No'} tickets are"
