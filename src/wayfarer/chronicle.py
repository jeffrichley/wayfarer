"""The chronicle: what happened to an effort, told as tickets moving.

A pure function of the effort's ticket timelines on GitHub and the session rows
in the store. Nothing of it is stored, so a restart or a second look rebuilds the
same lines with the same ids, and it outlives the event files that go when an
effort ships (#22, ADR-0003).

Only a ticket moving earns a line: taken, asked, answered, held, let land,
retried, landed, closed. A stage, a pull request, a re-test or a resolver session
never does; each reaches the chronicle only as the movement it ends in.

Lines fold by cause, never by time. A close, landed or not, carries what it
directly caused: the tickets it made takeable, and which of them the cascade
then took. Two unrelated landings a minute apart stay two lines.

Who acted is read from the kind of event, not from the timeline's actor, because
Wayfarer writes with the person's token and its writes wear their login. Taken,
asked, held and landed read passively. An assignment is the cascade's when the
ticket has a session row, and a person's otherwise; a close is Wayfarer's
landing when a comment carrying `LANDED_MARKER` came before it, and a person's
otherwise. A person's movement reads "You" for the token's own login, and names
any other.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime

from wayfarer.models import ChronicleLine, Effort, LinePart, Movement, Ticket
from wayfarer.pull_requests import LANDED_MARKER
from wayfarer.read_model import ASKED, HELD, Event, History
from wayfarer.store import Purpose, SessionRow

__all__ = ["chronicle"]

# Who a movement names when GitHub no longer knows who made it: a deleted account.
_NOBODY = "Someone"


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
        self._titles = {ticket.number: ticket.title for ticket in tickets}
        self._viewer = history.viewer
        self._timelines = {t.number: history.timelines.get(t.number, []) for t in tickets}
        # A resolver session is landing, and never a resume or a retry.
        self._builds: defaultdict[int, list[datetime]] = defaultdict(list)
        for row in sessions:
            if row.purpose is Purpose.BUILD:
                self._builds[row.ticket].append(row.started)
        self._closed = {
            number: closes[0].at
            for number, timeline in self._timelines.items()
            if (closes := [e for e in timeline if e.kind == "ClosedEvent"])
        }
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
        ticket = self._ticket(number)
        match e.kind, e.subject:
            case "AssignedEvent", _ if (number, e.at) not in self._folded:
                if self._builds[number]:
                    return self._line(number, e, Movement.TAKEN, [ticket, _words(" was taken.")])
                who = self._who(e.subject)
                return self._line(
                    number, e, Movement.TAKEN, [_words(f"{who} took "), ticket, _words(".")]
                )
            case "LabeledEvent", label if label == ASKED:
                return self._line(number, e, Movement.ASKED, [ticket, _words(" asked a question.")])
            case "LabeledEvent", label if label == HELD:
                return self._line(number, e, Movement.HELD, [ticket, _words(" was held.")])
            case "UnlabeledEvent", label if label == ASKED:
                parts = [_words(f"{self._who(e.actor)} answered "), ticket]
                resumed = self._session_after(number, e.at, timeline, ASKED)
                parts.append(_words(", and its session resumed." if resumed else "."))
                return self._line(number, e, Movement.ANSWERED, parts)
            case "UnlabeledEvent", label if label == HELD:
                by = self._who(e.actor)
                if self._session_after(number, e.at, timeline, HELD):
                    return self._line(
                        number, e, Movement.RETRIED, [_words(f"{by} retried "), ticket, _words(".")]
                    )
                return self._line(
                    number, e, Movement.LET_LAND, [_words(f"{by} let "), ticket, _words(" land.")]
                )
        return None

    def _close(self, number: int, e: Event, timeline: list[Event]) -> ChronicleLine:
        ticket = self._ticket(number)
        if e.reason == "COMPLETED" and self._marked(e, timeline):
            movement, parts = Movement.LANDED, [ticket, _words(" landed.")]
        elif e.reason == "COMPLETED":
            movement, parts = (
                Movement.CLOSED,
                [_words(f"{self._who(e.actor)} closed "), ticket, _words(".")],
            )
        else:
            movement = Movement.CLOSED
            parts = [
                _words(f"{self._who(e.actor)} closed "),
                ticket,
                _words(" without landing it."),
            ]
        freed = [t.number for t in self._tickets if number in t.blocked_by and self._freed(t, e.at)]
        if freed:
            taken = [n for n in freed if self._taken_after(n, e.at)]
            parts += [_words(" "), *self._names(freed), _words(" reached the frontier")]
            if taken == freed:
                parts.append(_words(" and was taken." if len(taken) == 1 else " and were taken."))
            elif taken:
                parts += [_words(", and "), *self._names(taken)]
                parts.append(_words(" was taken." if len(taken) == 1 else " were taken."))
            else:
                parts.append(_words("."))
        return self._line(number, e, movement, parts)

    def _marked(self, close: Event, timeline: list[Event]) -> bool:
        """Whether a landing comment came after the ticket's last close and before this one."""
        since = [e for e in timeline if e.at < close.at]
        before = [e for e in since if e.kind == "ClosedEvent"]
        after = before[-1].at if before else None
        return any(
            e.kind == "IssueComment" and LANDED_MARKER in (e.body or "")
            for e in since
            if after is None or e.at > after
        )

    def _freed(self, ticket: Ticket, at: datetime) -> bool:
        """Whether the close at `at` put `ticket` on the frontier: its last blocker to
        close, while it was open and nobody was on it."""
        blockers = [self._closed.get(b) for b in ticket.blocked_by]
        # A blocker outside the effort, or still open, leaves it blocked as far as
        # this effort's timelines can tell.
        if any(closed is None for closed in blockers):
            return False
        if max(closed for closed in blockers if closed is not None) != at:
            return False
        closed = self._closed.get(ticket.number)
        if closed is not None and closed <= at:
            return False
        on: set[str] = set()
        for e in self._timelines[ticket.number]:
            if e.at >= at:
                break
            if e.kind == "AssignedEvent" and e.subject:
                on.add(e.subject)
            elif e.kind == "UnassignedEvent":
                on.discard(e.subject or "")
        return not on

    def _taken_after(self, number: int, at: datetime) -> bool:
        """Whether the cascade took `number` as the first thing after `at`, and if so
        fold that taking into the line of the close at `at`."""
        taking = next(
            (e for e in self._timelines[number] if e.kind == "AssignedEvent" and e.at > at), None
        )
        if taking is None or not self._builds[number]:
            return False
        self._folded.add((number, taking.at))
        return True

    def _session_after(self, number: int, at: datetime, timeline: list[Event], label: str) -> bool:
        """Whether a build started on `number` after `at`, before `label` went back on."""
        again = next(
            (
                e.at
                for e in timeline
                if e.kind == "LabeledEvent" and e.subject == label and e.at > at
            ),
            None,
        )
        return any(
            at < started and (again is None or started < again) for started in self._builds[number]
        )

    def _who(self, login: str | None) -> str:
        if login is None:
            return _NOBODY
        return "You" if login == self._viewer else login

    def _ticket(self, number: int) -> LinePart:
        return LinePart(text=self._titles[number], ticket=number)

    def _names(self, numbers: list[int]) -> list[LinePart]:
        """`A`, `A and B`, `A, B and C`."""
        parts: list[LinePart] = []
        for i, number in enumerate(numbers):
            if i:
                parts.append(_words(" and " if i == len(numbers) - 1 else ", "))
            parts.append(self._ticket(number))
        return parts

    def _line(
        self, number: int, e: Event, movement: Movement, parts: list[LinePart]
    ) -> ChronicleLine:
        return ChronicleLine(
            kind="chronicle_line",
            id=f"chronicle:{self._effort.number}:{number}:{movement.value}:{e.at.isoformat()}",
            effort=self._effort.number,
            effort_title=self._effort.title,
            at=e.at,
            movement=movement,
            parts=parts,
        )


def _words(text: str) -> LinePart:
    return LinePart(text=text, ticket=None)
