"""Each effort's ticket graph: worked out afresh from what the stream holds whenever it
changes, and sent as an item of its own, since the browser never folds or derives
(ADR-0004). The canvas only measures the cards and asks elkjs where they go.

The rules are #23's (docs/screens/ticket-graph.md). Only Landed folds into the start
line, because a Landing ticket can still turn Held; a ticket closed without landing
is off the graph, and frees what it blocked as a landing does. A ticket's step is how
many tickets still to land stand between it and a session, so the frontier is step 0
at every size. An edge is implied, and not drawn, when another of the ticket's
blockers already waits on that one; an edge from landed work leaves the start line.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from functools import cache

from wayfarer.models import (
    Blocker,
    Cascade,
    Effort,
    GraphCard,
    Item,
    Mention,
    Neighbour,
    Tally,
    Ticket,
    TicketGraph,
    TicketState,
    Wire,
)
from wayfarer.store import Store
from wayfarer.stream import Store as Stream

__all__ = ["Graphs", "derive"]

# A card is full this many steps out from the frontier, and name-only beyond,
# unless its ticket is in flight or waiting on the person (docs/screens/ticket-graph.md).
_FULL_WITHIN = 1
_ALWAYS_FULL = (
    TicketState.BUILDING,
    TicketState.LANDING,
    TicketState.IN_REVIEW,
    TicketState.ASKED,
    TicketState.HELD,
    TicketState.TAKEABLE,
)


class Graphs:
    """Every effort's graph on one stream, kept derived from everything else it holds."""

    def __init__(self, stream: Stream, record: Callable[[], Store] | None) -> None:
        """`record` opens the repo's store, which says when each running session
        started; a clone with no GitHub repo has none."""
        self._stream = stream
        self._record = record

    async def follow(self) -> None:
        """Derive every graph again after each change to the stream, until it closes."""
        while not self._stream.closed:
            self.refresh()
            await self._stream.changed()

    def refresh(self) -> None:
        """Put each effort's graph as the stream now has it on the stream, where it differs."""
        started = self._started()
        graphs = derive(list(self._stream.items()), started=started)
        for drawn in graphs:
            self._stream.upsert(drawn)
        kept = {drawn.id for drawn in graphs}
        for item in list(self._stream.items()):
            if isinstance(item, TicketGraph) and item.id not in kept:
                self._stream.remove(item.id)

    def _started(self) -> dict[int, datetime]:
        """When the session now running on each ticket started."""
        if self._record is None:
            return {}
        return {row.ticket: row.started for row in self._record().sessions() if row.ended is None}


def derive(items: Iterable[Item], *, started: dict[int, datetime]) -> list[TicketGraph]:
    """Every effort's graph as `items` have it; `started` says when each ticket's
    running session started."""
    held = list(items)
    tickets = {item.id: item for item in held if isinstance(item, Ticket)}
    cascades = {item.effort: item for item in held if isinstance(item, Cascade)}
    efforts = sorted((i for i in held if isinstance(i, Effort)), key=lambda e: e.number)
    # The slots taken, as the cascades count them: claimed or running, every effort's.
    taken = sum(cascade.running for cascade in cascades.values())
    return [
        _graph(
            effort,
            [tickets[id] for id in effort.tickets if id in tickets],
            started,
            at_cap=_at_cap(cascades.get(effort.number), taken),
        )
        for effort in efforts
    ]


def _at_cap(cascade: Cascade | None, taken: int) -> bool:
    """Whether a takeable ticket waits on a slot: its cascade is armed and running, and
    the cap every cascade shares is full."""
    return cascade is not None and cascade.armed and not cascade.paused and taken >= cascade.cap


def _graph(
    effort: Effort, tickets: list[Ticket], started: dict[int, datetime], *, at_cap: bool
) -> TicketGraph:
    by = {t.number: t for t in tickets}
    landed = {n for n, t in by.items() if t.state is TicketState.LANDED}
    # What is drawn: every ticket still to land. A closed one is off the graph.
    live = {n for n, t in by.items() if t.state not in (TicketState.LANDED, TicketState.CLOSED)}

    def blockers(n: int) -> list[int]:
        """Its blockers on the graph or folded into the start line, in ticket order."""
        return sorted(b for b in by[n].blocked_by if b in live or b in landed)

    @cache
    def ancestors(n: int, through: frozenset[int]) -> frozenset[int]:
        """Everything `n` waits on through tickets in `through`, however far back."""
        found: set[int] = set()
        for b in blockers(n):
            found.add(b)
            if b in through:
                found |= ancestors(b, through)
        return frozenset(found)

    everything = frozenset(live | landed)
    still = frozenset(live)

    def implied_via(n: int, b: int) -> int | None:
        """The other blocker of `n` that already waits on `b`, if any. An edge from a
        blocker still to land is implied only through tickets still to land, so a
        ticket's step is kept whatever landed out of order."""
        through = still if b in live else everything
        return next((c for c in blockers(n) if c != b and b in ancestors(c, through)), None)

    @cache
    def step(n: int) -> int:
        open_ = [b for b in blockers(n) if b in live]
        return 1 + max(step(b) for b in open_) if open_ else 0

    downstream: dict[int, set[int]] = {n: set() for n in live}
    for n in live:
        for b in ancestors(n, still) & still:
            downstream[b].add(n)

    wires: list[Wire] = []
    cards: list[GraphCard] = []
    for n in sorted(live):
        ticket = by[n]
        vias = {b: implied_via(n, b) for b in blockers(n)}
        drawn = [b for b, via in vias.items() if via is None]
        opened = [b for b in drawn if b in live]
        wires += [Wire(blocker=b, blocked=n, kind="open") for b in opened]
        # Every landed blocker leaves the start line on one wire, and a ticket with
        # nothing to wait on hangs off it.
        if any(b in landed for b in drawn):
            wires.append(Wire(blocker=None, blocked=n, kind="met"))
        elif not opened:
            wires.append(Wire(blocker=None, blocked=n, kind="start"))
        cards.append(
            GraphCard(
                ticket=_mention(ticket),
                state=ticket.state,
                step=step(n),
                size="full"
                if step(n) <= _FULL_WITHIN or ticket.state in _ALWAYS_FULL
                else "name-only",
                waiting_on=[_mention(by[b]) for b in blockers(n) if b in live],
                since=started.get(n) if ticket.state is TicketState.BUILDING else None,
                at_cap=at_cap and ticket.state is TicketState.TAKEABLE,
                blocked_by=[
                    Blocker(
                        ticket=_mention(by[b]),
                        state=by[b].state,
                        via=None if via is None else _mention(by[via]),
                    )
                    for b, via in vias.items()
                ],
                unblocks=[
                    Neighbour(ticket=_mention(by[d]), state=by[d].state)
                    for d in sorted(live)
                    if n in by[d].blocked_by
                ],
                upstream=sorted(ancestors(n, still) & still),
                downstream=sorted(downstream[n]),
            )
        )

    return TicketGraph(
        kind="ticket_graph",
        id=f"graph:{effort.number}",
        effort=effort.number,
        tally=[
            Tally(state=state, count=count)
            for state in TicketState
            if state is not TicketState.CLOSED and (count := sum(t.state is state for t in tickets))
        ],
        landed=[_mention(by[n]) for n in _in_dependency_order(landed, by)],
        cards=cards,
        wires=wires,
    )


def _in_dependency_order(numbers: set[int], by: dict[int, Ticket]) -> list[int]:
    """`numbers` with every blocker before what it blocks, ties in ticket order."""
    ordered: list[int] = []
    left = set(numbers)
    while left:
        ready = min(
            (n for n in left if not any(b in left for b in by[n].blocked_by)),
            # A cycle on GitHub has no first ticket; take the lowest and carry on.
            default=min(left),
        )
        ordered.append(ready)
        left.remove(ready)
    return ordered


def _mention(ticket: Ticket) -> Mention:
    return Mention(number=ticket.number, title=ticket.title)
