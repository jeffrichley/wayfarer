"""The chronicle: what happened to an effort, told as tickets moving.

A pure function of the effort's ticket timelines on GitHub and the session rows
in the store. Nothing of it is stored, so a restart or a second look rebuilds the
same lines with the same ids, and it outlives the event files that go when an
effort ships (#22, ADR-0003).

Only a ticket moving earns a line, in the shapes `models.ChronicleLine` holds:
taken, asked, answered, held, retried, landed, closed. A stage, a pull request, a
re-test or a resolver session never does; each reaches the chronicle only as the
movement it ends in. Letting a Held ticket land has no line of its own (#51): it
ends in the landing.

Lines fold by cause, never by time. A landing carries what it directly caused:
the tickets it made takeable, and which of them the cascade then took. Two
unrelated landings a minute apart stay two lines.

Who acted is read from the kind of event, not from the timeline's actor, because
Wayfarer writes with the person's token and its writes wear their login. Taken,
asked, held and landed read passively. An assignment is the cascade's when the
ticket has a session row, and a person's otherwise; a close is Wayfarer's
landing when a comment carrying `LANDED_MARKER` came before it, and a person's
otherwise. A person's movement is "you" for the token's own login, and names
any other.

A retry is a Held ticket cleared with a session after it; whether it started
over is that session's purpose. The asked gist and the held reason are left null:
their sources are #42 and the comments a hold leaves.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Literal

from wayfarer.merge_queue import LANDED_MARKER
from wayfarer.models import (
    Answered,
    Asked,
    ChronicleLine,
    Closed,
    Effort,
    Held,
    Landed,
    Mention,
    Retried,
    Someone,
    Taken,
    Ticket,
)
from wayfarer.read_model import ASKED, HELD, Event, History
from wayfarer.store import Purpose, SessionRow

__all__ = ["chronicle"]

# Who a movement names when GitHub no longer knows who made it: a deleted account.
_NOBODY = Someone(login="Someone")

type _Moved = Taken | Asked | Answered | Held | Retried | Landed | Closed
type _Person = Literal["you"] | Someone


def chronicle(
    effort: Effort, tickets: Sequence[Ticket], history: History, sessions: Iterable[SessionRow]
) -> list[ChronicleLine]:
    """Every line the effort's tickets have earned, oldest first."""
    return _Telling(effort, tickets, history, sessions).lines()


class _Telling:
    """One telling of one effort's chronicle."""

    def __init__(
        self,
        effort: Effort,
        tickets: Sequence[Ticket],
        history: History,
        sessions: Iterable[SessionRow],
    ) -> None:
        self._effort = effort
        self._tickets = tickets
        self._mentions = {t.number: Mention(number=t.number, title=t.title) for t in tickets}
        self._viewer = history.viewer
        self._timelines = {t.number: history.timelines.get(t.number, []) for t in tickets}
        # A resolver session is landing, and never a resume or a retry.
        self._builds: defaultdict[int, list[datetime]] = defaultdict(list)
        self._sessions: defaultdict[int, list[tuple[datetime, Purpose]]] = defaultdict(list)
        for row in sessions:
            if row.purpose is Purpose.BUILD:
                self._builds[row.ticket].append(row.started)
            if row.purpose is not Purpose.RESOLVE:
                self._sessions[row.ticket].append((row.started, row.purpose))
        # Takings told inside the line of the close that freed them.
        self._folded: set[tuple[int, datetime]] = set()

    def lines(self) -> list[ChronicleLine]:
        # Every close first, so each claims the takings it folds before they are told.
        closes = [
            self._close(number, e, timeline)
            for number, timeline in self._timelines.items()
            for e in timeline
            if e.kind == "ClosedEvent"
        ]
        others = [
            line
            for number, timeline in self._timelines.items()
            for e in timeline
            if (line := self._movement(number, e, timeline)) is not None
        ]
        return sorted(closes + others, key=lambda line: (line.at, line.id))

    def _movement(self, number: int, e: Event, timeline: list[Event]) -> ChronicleLine | None:
        ticket = self._mentions[number]
        match e.kind, e.subject:
            case "AssignedEvent", _ if (number, e.at) not in self._folded:
                if self._cascade_took(number, e):
                    return self._line(number, e, Taken(kind="taken", ticket=ticket, by="wayfarer"))
                by = self._who(e.subject)
                return self._line(number, e, Taken(kind="taken", ticket=ticket, by=by))
            case "LabeledEvent", label if label == ASKED:
                return self._line(number, e, Asked(kind="asked", ticket=ticket, gist=None))
            case "LabeledEvent", label if label == HELD:
                return self._line(number, e, Held(kind="held", ticket=ticket, reason=None))
            case "UnlabeledEvent", label if label == ASKED:
                by = self._who(e.actor)
                return self._line(number, e, Answered(kind="answered", ticket=ticket, by=by))
            # Cleared with no session after it, it was let land, which ends in the landing.
            case "UnlabeledEvent", label if label == HELD and (
                after := self._session_after(number, e.at, timeline, HELD)
            ):
                over = {Purpose.START_OVER: True, Purpose.CONTINUE: False}.get(after)
                return self._line(number, e, Retried(kind="retried", ticket=ticket, over=over))
        return None

    def _close(self, number: int, e: Event, timeline: list[Event]) -> ChronicleLine:
        ticket = self._mentions[number]
        if not (e.reason == "COMPLETED" and self._marked(e, timeline)):
            return self._line(
                number, e, Closed(kind="closed", ticket=ticket, by=self._who(e.actor))
            )
        freed = [t.number for t in self._tickets if number in t.blocked_by and self._freed(t, e)]
        started = [n for n in freed if self._taken_after(n, e, timeline)]
        landed = Landed(
            kind="landed",
            ticket=ticket,
            by="wayfarer",
            freed=[self._mentions[n] for n in freed],
            started=[self._mentions[n] for n in started],
        )
        return self._line(number, e, landed)

    def _marked(self, close: Event, timeline: list[Event]) -> bool:
        """Whether a landing comment came after the ticket's last close and before this one.

        Judged by the timeline's order, not its times: Wayfarer comments and closes
        back to back, and GitHub stamps both to the same second."""
        marked = False
        for e in timeline:
            if e is close:
                return marked
            if e.kind == "ClosedEvent":
                marked = False
            elif e.kind == "IssueComment" and LANDED_MARKER in (e.body or ""):
                marked = True
        return marked

    def _freed(self, ticket: Ticket, close: Event) -> bool:
        """Whether `close` put `ticket` on the frontier: the last of its blockers to
        close, while it was open and nobody was on it."""
        for blocker in ticket.blocked_by:
            timeline = self._timelines.get(blocker)
            # A blocker outside the effort leaves it blocked as far as this
            # effort's timelines can tell.
            if timeline is None:
                return False
            closing = any(e is close for e in timeline)
            if not closing and not self._closed(blocker, close.at, before=True):
                return False
        if self._closed(ticket.number, close.at, before=False):
            return False
        on: set[str] = set()
        for e in self._timelines[ticket.number]:
            if e.at >= close.at:
                break
            if e.kind == "AssignedEvent" and e.subject:
                on.add(e.subject)
            elif e.kind == "UnassignedEvent":
                on.discard(e.subject or "")
        return not on

    def _closed(self, number: int, at: datetime, *, before: bool) -> bool:
        """Whether `number` stood closed just before `at`, or at `at` itself."""
        closed = False
        for e in self._timelines[number]:
            if e.at > at or (before and e.at == at):
                break
            if e.kind == "ClosedEvent":
                closed = True
            elif e.kind == "ReopenedEvent":
                closed = False
        return closed

    def _cascade_took(self, number: int, taking: Event) -> bool:
        """Whether the cascade made `taking`: a build started on the ticket after it,
        and before anyone was put on it again. Otherwise a person took it."""
        again = next(
            (
                e.at
                for e in self._timelines[number]
                if e.kind == "AssignedEvent" and e.at > taking.at
            ),
            None,
        )
        return any(
            taking.at <= started and (again is None or started < again)
            for started in self._builds[number]
        )

    def _taken_after(self, number: int, close: Event, closer: list[Event]) -> bool:
        """Whether the cascade took `number` as the first thing after `close`, before
        the ticket it closed was reopened; if so, that taking folds into its line."""
        reopened = next(
            (e.at for e in closer if e.kind == "ReopenedEvent" and e.at > close.at), None
        )
        taking = next(
            (e for e in self._timelines[number] if e.kind == "AssignedEvent" and e.at > close.at),
            None,
        )
        if taking is None or (reopened is not None and taking.at > reopened):
            return False
        if not self._cascade_took(number, taking):
            return False
        self._folded.add((number, taking.at))
        return True

    def _session_after(
        self, number: int, at: datetime, timeline: list[Event], label: str
    ) -> Purpose | None:
        """Why the first session that started on `number` after `at` ran, if one did
        before `label` went back on."""
        again = next(
            (
                e.at
                for e in timeline
                if e.kind == "LabeledEvent" and e.subject == label and e.at > at
            ),
            None,
        )
        return next(
            (
                purpose
                for started, purpose in sorted(self._sessions[number])
                if at < started and (again is None or started < again)
            ),
            None,
        )

    def _who(self, login: str | None) -> _Person:
        if login is None:
            return _NOBODY
        return "you" if login == self._viewer else Someone(login=login)

    def _line(self, number: int, e: Event, moved: _Moved) -> ChronicleLine:
        return ChronicleLine(
            kind="chronicle_line",
            id=f"chronicle:{self._effort.number}:{number}:{moved.kind}:{e.at.isoformat()}",
            at=e.at,
            effort=Mention(number=self._effort.number, title=self._effort.title),
            moved=moved,
        )
