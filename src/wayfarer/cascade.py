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

Each session starts on its effort branch's head, and its end is answered by
whose failure it was, if it failed (#41). A finished session or a failed attempt
leaves its work and its reason on GitHub (`endings.py`). A failure of the
environment releases the ticket back to the frontier, its automatic start
unspent, pauses the cascade and raises one item, as a refused start gate does.
A ticket Held after a failed attempt is retried only by a person, who chooses to
continue where its session stopped or start over; either is the person's start,
not the cascade's.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Coroutine
from datetime import UTC, datetime
from typing import Any, Protocol

from waystation import (
    OutcomeMissing,
    PreflightError,
    RunFailed,
    RunResult,
    RunSpec,
    StageError,
)

from wayfarer.endings import STOPPED, Endings, fault, what_happened
from wayfarer.github import GitHub, GitHubError
from wayfarer.models import (
    Cascade,
    Effort,
    EnvironmentFailure,
    GateCheck,
    GateStatus,
    RetryFrom,
    ShipEffort,
    Ticket,
    TicketState,
)
from wayfarer.outcome import Outcome
from wayfarer.queue import Queue
from wayfarer.read_model import HELD, Efforts
from wayfarer.sessions import Sessions, read_events
from wayfarer.settings import Settings
from wayfarer.store import Fault, Purpose, SessionRow, Store
from wayfarer.stream import Store as Stream

__all__ = ["QUESTION", "Asked", "Cascades", "Gate", "SessionsFor"]

_log = logging.getLogger(__name__)

SessionsFor = Callable[[Store], Sessions]
"""The sessions a start runs, recording into the store it is given."""

Asked = Callable[[int, str, bytes | None], Awaitable[bool]]
"""Whether a session that ended without reporting did so to ask a question: given its
ticket, its run id and the question file it carried out, if any. True takes the
ending over, and the ticket is not Held (#42)."""

QUESTION = ".wayfarer/question.json"
"""Where a session that ends to ask leaves its question, under its sandbox's home (#42)."""

# Environment failures that happen around a session rather than inside it.
_ENVIRONMENT = (PreflightError, StageError, OSError, TimeoutError, GitHubError)

# The id of the one item a session the environment failed raises, whichever ticket it was on.
_RAISED = "environment:session"

# What a retry that continues tells the session it resumes, or one it starts cold.
_CONTINUE = """Your last session on this ticket stopped before it was done: {why} \
Carry on from where it stopped, then report as before."""
_CONTINUE_COLD = """An earlier session on this ticket stopped before it was done: {why} \
Its commits are on this branch. Carry on from them."""
_HELD_FOR_A_PERSON = "It was held for a person to decide."


_SpecFor = Callable[[Sessions, Ticket, Effort], Awaitable[RunSpec[Outcome]]]
"""How a session on a ticket is described, once it is known where it starts."""


async def _never_asked(ticket: int, run_id: str, question: bytes | None) -> bool:
    return False


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
        endings: Endings,
        asked: Asked = _never_asked,
    ) -> None:
        self._efforts = efforts
        self._github = github
        self._stream = stream
        self._settings = settings
        self._gate = gate
        self._sessions = sessions
        self._queue = queue
        self._endings = endings
        self._asked = asked
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
            self.record().arm(effort)
            self._why.pop(effort, None)
            self._stream.remove(_RAISED)
            # The gate is asked as a cascade is armed, as well as before each start.
            if await self._gate.admit() is not None:
                await self._gate_refused(effort)
            await self._decide(effort)

    async def pause(self, effort: int) -> None:
        """Start nothing new on `effort`; its running sessions finish."""
        async with self._deciding:
            self.record().pause(effort)
            await self._decide(effort)

    async def resume(self, effort: int) -> None:
        """Start what `effort`'s cascade can again, as of a fresh read."""
        self.record().resume(effort)
        self._why.pop(effort, None)
        self._stream.remove(_RAISED)
        await self._efforts.read(effort)

    async def stop(self, ticket: int) -> None:
        """Cancel the session on `ticket`, keeping its work, and hold the ticket: a failed
        attempt, with its work on a draft pull request, or a comment when it had none."""
        running = self._running.get(ticket)
        if running is None:
            return
        running.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await running
        # A cancelled run reports nothing, so its end is written here.
        store = self.record()
        stopped = [row for row in store.sessions() if row.ticket == ticket and row.ended is None]
        for row in stopped:
            store.session_ended(row.run_id, datetime.now(UTC), None)
            store.failed(row.run_id, Fault.ATTEMPT, STOPPED)
        # Still claimed, so still nobody else's to start.
        found = self._find(ticket)
        run_id = stopped[-1].run_id if stopped else None
        try:
            if found is None:
                raise GitHubError("the ticket was not read, so its work cannot be published")
            await self._endings.ended(
                *found,
                preserved=await self._endings.kept(run_id) if run_id else None,
                outcome=None,
                why=STOPPED,
                events=read_events(stopped[-1].event_file) if stopped else [],
                over=False,
            )
        except _ENVIRONMENT:
            # Its work stays on its preservation branch; the ticket is held regardless.
            _log.warning("Ticket #%s's stopped work was not published.", ticket, exc_info=True)
            with contextlib.suppress(GitHubError):
                await self._github.write("POST", f"/issues/{ticket}/labels", {"labels": [HELD]})

    async def retry(self, ticket: int, how: RetryFrom) -> None:
        """Start a person's session on a Held ticket, clearing its hold: continuing where its
        last session stopped, or starting over on its effort branch's head, which closes
        its pull request. Either is the person's start, never the cascade's (#20)."""
        async with self._deciding:
            found = self._find(ticket)
            if found is None or ticket in self._running:
                return
            held, effort = found
            if held.state is not TicketState.HELD:
                return
            if await self._gate.admit() is not None:
                await self._gate_refused(effort.number)
                return
            pull = held.pull_request
            over = how is RetryFrom.START_OVER
            try:
                await self._github.write("DELETE", f"/issues/{ticket}/labels/{HELD}", {})
                if over and pull is not None and not pull.merged:
                    await self._github.write("PATCH", f"/pulls/{pull.number}", {"state": "closed"})
            except GitHubError:
                _log.warning("Ticket #%s could not be retried.", ticket, exc_info=True)
                return
            if over:
                held = held.model_copy(update={"pull_request": None})
            spec = self._from_head(Purpose.START_OVER) if over else self._continuing
            self._begin(ticket, self._run(held, effort, spec))

    async def _continuing(
        self, sessions: Sessions, ticket: Ticket, effort: Effort
    ) -> RunSpec[Outcome]:
        """A session going on from where the ticket's last one stopped: from its pull
        request's head, or else its preservation branch, resuming its conversation."""
        last = self._last(ticket.number)
        pull = ticket.pull_request
        if pull is not None and not pull.merged:
            base = await self._endings.branch_head(pull.branch)
        elif last is not None and (kept := await self._endings.kept(last.run_id)):
            base = kept
        else:
            base = await self._endings.effort_head(effort)
        why = (last.why if last else None) or _HELD_FOR_A_PERSON
        cold = _CONTINUE_COLD.format(why=why)
        if last is None:
            return sessions.spec(ticket.number, base=base, purpose=Purpose.CONTINUE, prompt=cold)
        return sessions.resume(
            ticket.number,
            last.run_id,
            base=base,
            prompt=_CONTINUE.format(why=why),
            cold=cold,
            purpose=Purpose.CONTINUE,
        )

    def _last(self, ticket: int) -> SessionRow | None:
        """The ticket's last session that built it, not one that resolved a conflict."""
        built = [
            row
            for row in self.record().sessions()
            if row.ticket == ticket and row.purpose is not Purpose.RESOLVE
        ]
        return built[-1] if built else None

    def _find(self, ticket: int) -> tuple[Ticket, Effort] | None:
        """The ticket as last read, and the effort it is in."""
        read = self._stream.get(f"ticket:{ticket}")
        if not isinstance(read, Ticket):
            return None
        for effort in self._stream.items():
            if isinstance(effort, Effort) and read.id in effort.tickets:
                return read, effort
        return None

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
        store = self.record()
        cascade = store.cascades()
        armed, paused = number in cascade, cascade.get(number, False)
        await self._read_back(effort, tickets, submitting=armed and not paused)
        if armed and tickets and not any(ticket.open for ticket in tickets):
            store.disarm(number)
            armed = paused = False
            self._stream.upsert(
                ShipEffort(kind="ship", id=f"ship:{number}", effort=number, title=effort.title)
            )
        elif armed and not paused and not await self._start(number, tickets, store):
            paused = True
        self._publish(number, tickets, store, armed=armed, paused=paused)

    async def _read_back(self, effort: Effort, tickets: list[Ticket], *, submitting: bool) -> None:
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
                self._submit(ticket, effort)
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
                self.pause_itself(
                    effort, f"GitHub refused to let Wayfarer claim #{ticket.number}: {error}"
                )
                return False
            # The write raised the signal, so the read that shows the claim is coming.
            self._claimed.add(ticket.number)
        return True

    async def _gate_refused(self, effort: int) -> None:
        """The gate refused: pause, and show the one item it raised. Running sessions carry on."""
        self.pause_itself(effort, "The start gate refused a start.")
        self._stream.upsert(await self._gate.status())

    def pause_itself(self, effort: int, why: str) -> None:
        """Pause `effort`'s cascade for a failure of the environment, saying `why`: its
        running sessions finish, and the next read shows it paused."""
        _log.warning("The cascade on #%s paused: %s", effort, why)
        self.record().pause(effort)
        self._why[effort] = why

    def _startable(self, tickets: list[Ticket], store: Store) -> list[Ticket]:
        """The takeable tickets never started automatically, in the effort's order."""
        started = store.built() | self._running.keys() | self._claimed
        return [t for t in tickets if t.state is TicketState.TAKEABLE and t.number not in started]

    def _submit(self, ticket: Ticket, effort: Effort) -> None:
        self._begin(ticket.number, self._run(ticket, effort, self._from_head(Purpose.BUILD)))

    def _from_head(self, purpose: Purpose) -> _SpecFor:
        """A session from the effort branch's head: the cascade's build, or a start over."""

        async def spec(sessions: Sessions, ticket: Ticket, effort: Effort) -> RunSpec[Outcome]:
            head = await self._endings.effort_head(effort)
            return sessions.spec(ticket.number, base=head, purpose=purpose)

        return spec

    def _begin(self, ticket: int, work: Coroutine[Any, Any, None]) -> None:
        run = asyncio.create_task(work)
        self._running[ticket] = run
        run.add_done_callback(lambda ended: self._ended(ticket, ended))
        # Its card is now building: re-read.
        self._github.freshness.poke()

    async def _run(
        self,
        ticket: Ticket,
        effort: Effort,
        spec: _SpecFor,
    ) -> None:
        """Run one session on `ticket` under the shared cap, and answer how it ended."""
        sessions = self._sessions(self.record())
        try:
            result = await self._queue.submit(await spec(sessions, ticket, effort))
        except _ENVIRONMENT as error:
            # Before any session ran: nothing of the ticket's was spent.
            await self._released(ticket, effort, _detail(error))
            return
        await self._answer(sessions, ticket, effort, result)

    async def _answer(
        self, sessions: Sessions, ticket: Ticket, effort: Effort, result: RunResult[Outcome]
    ) -> None:
        """Answer a session's end by whose failure it was, if it failed (#20)."""
        store = self.record()
        why = None
        if isinstance(result, RunFailed):
            why = what_happened(result)
            whose = fault(result)
            store.failed(result.run_id, whose, why)
            if whose is Fault.ENVIRONMENT:
                await self._released(ticket, effort, why)
                return
            if isinstance(result.failure, OutcomeMissing) and await self._asked(
                ticket.number, result.run_id, sessions.carried(result.run_id, QUESTION)
            ):
                return
        row = store.session(result.run_id)
        try:
            await self._endings.ended(
                ticket,
                effort,
                preserved=result.preserved,
                outcome=None if isinstance(result, RunFailed) else result.outcome,
                why=why,
                events=read_events(row.event_file),
                over=row.purpose is Purpose.START_OVER,
            )
        except _ENVIRONMENT as error:
            # Its work is kept on its preservation branch, but GitHub never heard of it.
            store.failed(result.run_id, Fault.ENVIRONMENT, _detail(error))
            await self._released(ticket, effort, _detail(error))

    async def _released(self, ticket: Ticket, effort: Effort, detail: str) -> None:
        """A failure of the environment, not the ticket's: let the ticket go back on the
        frontier, pause the cascade and raise one item, as a refused start gate does.

        A person's retry is held again instead: its ticket spent its automatic start
        long ago, so on the frontier nothing would ever start it."""
        retried = ticket.number in self.record().built()
        where = "held it again" if retried else "the ticket went back on the frontier"
        reason = (
            f"A session on #{ticket.number} failed for a reason that was not its own, so {where}."
        )
        _log.warning("The session on #%s failed by the environment: %s", ticket.number, detail)
        self.pause_itself(effort.number, reason)
        self._stream.upsert(
            EnvironmentFailure(
                kind="environment",
                id=_RAISED,
                reason=reason,
                failed=[GateCheck(name="A session can run", passed=False, detail=detail)],
            )
        )
        try:
            if retried:
                await self._endings.hold_saying(ticket.number, f"A retry could not run: {detail}")
                return
            login = await self._github.login()
            await self._github.write(
                "DELETE", f"/issues/{ticket.number}/assignees", {"assignees": [login]}
            )
        except GitHubError:
            _log.warning("Ticket #%s could not be released.", ticket.number, exc_info=True)

    def _ended(self, ticket: int, run: asyncio.Task[Any]) -> None:
        self._running.pop(ticket, None)
        if not run.cancelled() and (error := run.exception()) is not None:
            _log.error("The session on #%s ended unanswered.", ticket, exc_info=error)
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

    def record(self) -> Store:
        """The repo's store, opened on first need: only a readable effort needs it."""
        if self._opened is None:
            assert self._github.repo is not None, "an effort was read, so there is a repo"
            self._opened = Store.for_repo(self._settings.data_dir, self._github.repo)
            # A restart never spends unasked: every cascade armed before it comes back paused.
            self._opened.pause_all()
        return self._opened


def _detail(error: Exception) -> str:
    """What an environment failure said, in words a person can act on."""
    if isinstance(error, StageError):
        return repr(error.failure)
    return str(error) or type(error).__name__


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
