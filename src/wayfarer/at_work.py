"""At work's lanes: one for every ticket with a session on it, or whose session stopped
to ask, worked out afresh from what the stream holds whenever it changes and sent as
items of their own, since the browser never folds or derives (ADR-0004).

A lane tells one story: its latest session's, and every session that one carried on
from. A resume of an answered question, or a person's Continue, is the same
conversation in a fresh container (#42), so what it did before stays in the story;
a start, afresh or over, begins a new one.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import NamedTuple

from wayfarer.endings import work_branch
from wayfarer.models import (
    Beat,
    BeatKind,
    Changes,
    Effort,
    FileChange,
    Item,
    Lane,
    Mention,
    TestMark,
    Ticket,
    TicketState,
)
from wayfarer.store import Purpose, SessionRow, Store
from wayfarer.stream import Store as Stream

__all__ = ["AtWork", "Story", "derive"]

# The beats that rest on a test run: a refactor is confirmed by the green that kept it.
_RUNS = (BeatKind.RED, BeatKind.GREEN, BeatKind.REFACTOR)

# The sessions that carry on the conversation of the one before them.
_CARRYING_ON = (Purpose.RESUME, Purpose.CONTINUE)


class Story(NamedTuple):
    """The sessions one ticket's story is told from, oldest first, and when the latest
    of them started."""

    sessions: list[str]
    started: datetime


class AtWork:
    """Every lane on one stream, kept derived from everything else it holds."""

    def __init__(self, stream: Stream, record: Callable[[], Store] | None) -> None:
        """`record` opens the repo's store, which says which sessions tell each ticket's
        story; a clone with no GitHub repo has none."""
        self._stream = stream
        self._record = record

    async def follow(self) -> None:
        """Derive every lane again after each change to the stream, until it closes."""
        while not self._stream.closed:
            self.refresh()
            await self._stream.changed()

    def refresh(self) -> None:
        """Put each lane as the stream now has it on the stream, where it differs."""
        lanes = derive(list(self._stream.items()), stories=self._stories())
        for lane in lanes:
            self._stream.upsert(lane)
        kept = {lane.id for lane in lanes}
        for item in list(self._stream.items()):
            if isinstance(item, Lane) and item.id not in kept:
                self._stream.remove(item.id)

    def _stories(self) -> dict[int, Story]:
        """Each ticket's story, as the store's sessions tell it."""
        if self._record is None:
            return {}
        by_ticket: dict[int, list[SessionRow]] = {}
        for row in sorted(self._record().sessions(), key=lambda row: row.started):
            by_ticket.setdefault(row.ticket, []).append(row)
        return {ticket: _story(rows) for ticket, rows in by_ticket.items()}


def _story(rows: list[SessionRow]) -> Story:
    """The latest of `rows` and each session it carried on from. A resolver session
    carries on nothing, and nothing carries on from one."""
    latest = rows[-1]
    told = [latest]
    earlier = [row for row in rows[:-1] if row.purpose is not Purpose.RESOLVE]
    while told[0].purpose in _CARRYING_ON and earlier:
        told.insert(0, earlier.pop())
    return Story([row.run_id for row in told], latest.started)


def derive(items: Iterable[Item], *, stories: dict[int, Story]) -> list[Lane]:
    """Every lane as `items` have it, in ticket order; `stories` says which sessions tell
    each ticket's story."""
    held = list(items)
    tickets = {item.id: item for item in held if isinstance(item, Ticket)}
    beats: dict[str, list[Beat]] = {}
    for beat in sorted((i for i in held if isinstance(i, Beat)), key=lambda b: b.seq):
        beats.setdefault(beat.session, []).append(beat)
    changes = {item.session: item for item in held if isinstance(item, Changes)}
    lanes = [
        _lane(ticket, effort, stories.get(ticket.number), beats, changes)
        for effort in (item for item in held if isinstance(item, Effort))
        for ticket_id in effort.tickets
        if (ticket := tickets.get(ticket_id)) is not None and _at_work(ticket)
    ]
    return sorted(lanes, key=lambda lane: lane.ticket.number)


def _at_work(ticket: Ticket) -> bool:
    """A session is on it now, or its session stopped to ask and waits on an answer."""
    return ticket.live or ticket.state in (TicketState.BUILDING, TicketState.ASKED)


def _lane(
    ticket: Ticket,
    effort: Effort,
    story: Story | None,
    beats: dict[str, list[Beat]],
    changes: dict[str, Changes],
) -> Lane:
    asked = ticket.question if ticket.state is TicketState.ASKED else None
    question = asked if asked is not None and not asked.answered else None
    sessions = story.sessions if story is not None else []
    told = [beat for session in sessions for beat in beats.get(session, [])]
    if question is not None and question.questions:
        latest: str | None = question.questions[0].question
    else:
        latest = told[-1].text if told else None
    last_green = next(
        (b.at for b in reversed(told) if b.beat in _RUNS and b.run and b.run.exit == 0), None
    )
    return Lane(
        kind="lane",
        id=f"lane:{ticket.number}",
        ticket=Mention(number=ticket.number, title=ticket.title),
        effort=Mention(number=effort.number, title=effort.title),
        state=ticket.state,
        branch=work_branch(ticket),
        sessions=sessions,
        started=story.started if story is not None else None,
        latest=latest,
        criteria=ticket.criteria,
        rhythm=[
            TestMark(passed=beat.run.exit == 0, at=beat.at)
            for beat in told
            if beat.beat in _RUNS and beat.run is not None
        ],
        last_green=last_green,
        changes=_changed(changes.get(session) for session in sessions),
        question=question,
    )


def _changed(each: Iterable[Changes | None]) -> list[FileChange]:
    """Every file the story's sessions changed, their counts added up, in the order each
    was first changed."""
    total: dict[str, FileChange] = {}
    for changes in each:
        for file in changes.files if changes is not None else []:
            was = total.get(file.path, FileChange(path=file.path, added=0, removed=0))
            total[file.path] = FileChange(
                path=file.path, added=was.added + file.added, removed=was.removed + file.removed
            )
    return list(total.values())
