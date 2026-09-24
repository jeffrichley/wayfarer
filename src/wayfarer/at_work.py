"""At work's lanes: one for every ticket with a session on it, or whose session stopped
to ask, worked out afresh from what the stream holds whenever it changes and sent as
items of their own, since the browser never folds or derives (ADR-0004).

A lane's story is its latest session's: a resume is a session of its own, so a
ticket that asked and was answered tells the story from where it carried on.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime

from wayfarer.endings import ticket_branch
from wayfarer.models import (
    Beat,
    BeatKind,
    Effort,
    Item,
    Lane,
    Mention,
    TestMark,
    Ticket,
    TicketState,
)
from wayfarer.store import Store
from wayfarer.stream import Store as Stream

__all__ = ["AtWork", "derive"]

# The beats that rest on a test run: a refactor is confirmed by the green that kept it.
_RUNS = (BeatKind.RED, BeatKind.GREEN, BeatKind.REFACTOR)


class AtWork:
    """Every lane on one stream, kept derived from everything else it holds."""

    def __init__(self, stream: Stream, record: Callable[[], Store] | None) -> None:
        """`record` opens the repo's store, which says which session is each ticket's
        latest and when it started; a clone with no GitHub repo has none."""
        self._stream = stream
        self._record = record

    async def follow(self) -> None:
        """Derive every lane again after each change to the stream, until it closes."""
        while not self._stream.closed:
            self.refresh()
            await self._stream.changed()

    def refresh(self) -> None:
        """Put each lane as the stream now has it on the stream, where it differs."""
        lanes = derive(list(self._stream.items()), latest=self._latest())
        for lane in lanes:
            self._stream.upsert(lane)
        kept = {lane.id for lane in lanes}
        for item in list(self._stream.items()):
            if isinstance(item, Lane) and item.id not in kept:
                self._stream.remove(item.id)

    def _latest(self) -> dict[int, tuple[str, datetime]]:
        """Each ticket's latest session, and when it started."""
        if self._record is None:
            return {}
        rows = sorted(self._record().sessions(), key=lambda row: row.started)
        return {row.ticket: (row.run_id, row.started) for row in rows}


def derive(items: Iterable[Item], *, latest: dict[int, tuple[str, datetime]]) -> list[Lane]:
    """Every lane as `items` have it, in ticket order; `latest` says which session is each
    ticket's latest, and when it started."""
    held = list(items)
    tickets = {item.id: item for item in held if isinstance(item, Ticket)}
    story: dict[str, list[Beat]] = {}
    for beat in sorted((i for i in held if isinstance(i, Beat)), key=lambda b: b.seq):
        story.setdefault(beat.session, []).append(beat)
    lanes = [
        _lane(ticket, effort, latest.get(ticket.number), story)
        for effort in (item for item in held if isinstance(item, Effort))
        for id in effort.tickets
        if (ticket := tickets.get(id)) is not None and _at_work(ticket)
    ]
    return sorted(lanes, key=lambda lane: lane.ticket.number)


def _at_work(ticket: Ticket) -> bool:
    """A session is on it now, or its session stopped to ask and waits on an answer."""
    return ticket.live or ticket.state in (TicketState.BUILDING, TicketState.ASKED)


def _lane(
    ticket: Ticket,
    effort: Effort,
    latest: tuple[str, datetime] | None,
    story: dict[str, list[Beat]],
) -> Lane:
    asked = ticket.question if ticket.state is TicketState.ASKED else None
    question = asked if asked is not None and not asked.answered else None
    session, started = latest if latest is not None else (None, None)
    beats = story.get(session, []) if session is not None else []
    if question is not None and question.questions:
        said: str | None = question.questions[0].question
    else:
        said = beats[-1].text if beats else None
    return Lane(
        kind="lane",
        id=f"lane:{ticket.number}",
        ticket=Mention(number=ticket.number, title=ticket.title),
        effort=Mention(number=effort.number, title=effort.title),
        state=ticket.state,
        branch=ticket.pull_request.branch if ticket.pull_request else ticket_branch(ticket),
        session=session,
        started=started,
        latest=said,
        criteria=ticket.criteria,
        rhythm=[
            TestMark(passed=beat.run.exit == 0, at=beat.at)
            for beat in beats
            if beat.beat in _RUNS and beat.run is not None
        ],
        question=question,
    )
