"""Home, the line: worked out afresh from what the stream holds whenever it changes.

What the page shows on home is derived here and sent as items of its own, since
the browser never folds or derives (ADR-0004): the masthead and At work (`Home`),
one row per effort on the line (`LineRow`), and everything waiting on the person
in live order (`NeedsYou`). Nothing of it is stored but the last visit, which the
store keeps (#58).

The headline counts from the end of the visit before this one. A visit ends when
the person leaves home, and a new one begins when they arrive afresh; a reload is
the same visit, so a refresh keeps the headline they were reading.

Needs you is ranked as #24 decided: an environment failure pinned first and
unscored; then each ticket's item by what it holds up, its own ticket plus every
open ticket downstream, ties going to whatever has waited longest; then what holds
up no ticket: shipping an effort, then the sessions a Wayfarer before this one never
saw finish, then the containers nobody here can account for, then a ticket GitHub
closed while its session runs, which is flagged and never stopped (ADR-0002).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from wayfarer.github import Repo
from wayfarer.models import (
    Asked,
    ChronicleLine,
    Effort,
    EnvironmentFailure,
    GateStatus,
    Held,
    Home,
    Item,
    LineRow,
    LineStations,
    Mention,
    Need,
    NeedClosed,
    NeedHeld,
    NeedQuestion,
    NeedReview,
    NeedsYou,
    Orphan,
    PullRequest,
    ShipEffort,
    Station,
    Ticket,
    TicketState,
    UnknownContainer,
    Working,
)
from wayfarer.models.read_model import Checks
from wayfarer.store import Store
from wayfarer.stream import Store as Stream

__all__ = ["HomePage", "derive"]

type _OnATicket = NeedQuestion | NeedHeld | NeedReview

_STATIONS: list[Station] = ["wayfinder", "spec", "tickets", "build", "review", "landed"]

# The station a ticket in each state has reached. One closed without landing left
# the line, and sits at none.
_AT: dict[TicketState, Station] = {
    TicketState.TAKEABLE: "tickets",
    TicketState.BLOCKED: "tickets",
    TicketState.BUILDING: "build",
    TicketState.ASKED: "build",
    TicketState.HELD: "build",
    TicketState.IN_REVIEW: "review",
    TicketState.LANDING: "review",
    TicketState.LANDED: "landed",
}

_OVER = (TicketState.LANDED, TicketState.CLOSED)

# The headline's lead, by the kind of the top item: every one short enough that the
# longest headline stays under 14 words (docs/design/data-and-commands.md).
_LEADS = {
    "environment": "Every cascade is paused",
    "question": "An agent has stopped to ask you something",
    "held": "A ticket is held, waiting on you",
    "review": "A pull request is waiting on your approval",
    "ship": "An effort is ready to ship",
    "orphan": "A session was cut off before it finished",
    "unknown_container": "An unknown container is still running",
    "closed": "A ticket was closed while its session runs",
}

_NUMBERS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]


def _count(n: int) -> str:
    return _NUMBERS[n] if n < len(_NUMBERS) else str(n)


def _tickets(n: int) -> str:
    return f"{_count(n)} {'ticket' if n == 1 else 'tickets'}"


class HomePage:
    """Home's items on one stream, kept derived from everything else it holds."""

    def __init__(
        self, stream: Stream, repo: Repo | None, record: Callable[[], Store], *, auto_merge: bool
    ) -> None:
        """`record` opens the repo's store, which holds the last visit; only a clone
        with a GitHub repo has one."""
        self._stream = stream
        self._repo = repo
        self._record = record
        self._auto_merge = auto_merge

    def arrived(self) -> None:
        """The person arrived at home afresh: a new visit, counting from the last."""
        if self._repo is not None:
            self._record().arrived_home()
        self.refresh()

    def left(self) -> None:
        """The person left home: their visit ends now."""
        if self._repo is not None:
            self._record().left_home(datetime.now(UTC))

    async def follow(self) -> None:
        """Derive home again after every change to the stream, until it closes."""
        while not self._stream.closed:
            self.refresh()
            await self._stream.changed()

    def refresh(self) -> None:
        """Put home as the stream now has it on the stream, where it differs."""
        since = self._record().since() if self._repo is not None else None
        home, rows, needs = derive(
            list(self._stream.items()),
            repo=self._repo,
            since=since,
            auto_merge=self._auto_merge,
        )
        # Rows before what counts them, as tickets go before their effort.
        for row in rows:
            self._stream.upsert(row)
        kept = {row.id for row in rows}
        for item in list(self._stream.items()):
            if isinstance(item, LineRow) and item.id not in kept:
                self._stream.remove(item.id)
        self._stream.upsert(needs)
        self._stream.upsert(home)


def derive(
    items: Iterable[Item], *, repo: Repo | None, since: datetime | None, auto_merge: bool
) -> tuple[Home, list[LineRow], NeedsYou]:
    """Home as `items` have it, counting what changed from `since`."""
    held = list(items)
    tickets = {item.id: item for item in held if isinstance(item, Ticket)}
    efforts = sorted((i for i in held if isinstance(i, Effort)), key=lambda e: e.number)
    lines = sorted((i for i in held if isinstance(i, ChronicleLine)), key=lambda line: line.at)
    graph = {
        effort.number: [tickets[id] for id in effort.tickets if id in tickets] for effort in efforts
    }

    rows = [_row(effort, graph[effort.number]) for effort in efforts]
    waiting = [
        need
        for effort in efforts
        for ticket in graph[effort.number]
        if (need := _need(effort, ticket, graph[effort.number], lines, auto_merge)) is not None
    ]
    needs = NeedsYou(
        kind="needs_you",
        id="needs_you",
        items=[
            *_environment(held),
            *sorted(waiting, key=_rank),
            *sorted((i for i in held if isinstance(i, ShipEffort)), key=lambda s: s.effort),
            *sorted((i for i in held if isinstance(i, Orphan)), key=lambda o: o.started),
            *sorted((i for i in held if isinstance(i, UnknownContainer)), key=lambda c: c.id),
            *_closed(efforts, graph),
        ],
    )

    active = [e for e in efforts if graph[e.number] and not _done(graph[e.number])]
    landings = [
        line for line in lines if line.moved.kind == "landed" and (since is None or line.at > since)
    ]
    home = Home(
        kind="home",
        id="home",
        repo=None if repo is None else str(repo),
        headline=_headline(needs.items[0] if needs.items else None, len(landings), since),
        standfirst=[_standfirst(e, graph[e.number], waiting) for e in active],
        moving=len(active),
        since=since,
        working=[
            Working(ticket=_mention(ticket), effort=_mention(effort))
            for effort in efforts
            for ticket in sorted(graph[effort.number], key=lambda t: t.number)
            if ticket.state is TicketState.BUILDING
        ],
    )
    return home, rows, needs


def _mention(thing: Effort | Ticket) -> Mention:
    return Mention(number=thing.number, title=thing.title)


def _done(tickets: list[Ticket]) -> bool:
    return all(ticket.state in _OVER for ticket in tickets)


def _row(effort: Effort, tickets: list[Ticket]) -> LineRow:
    at: dict[Station, list[TicketState]] = {station: [] for station in _STATIONS}
    for ticket in tickets:
        if (station := _AT.get(ticket.state)) is not None:
            at[station].append(ticket.state)
    # The spec is behind every effort Wayfarer reads, so the course reaches it at least.
    reached = max(
        (i for i, station in enumerate(_STATIONS) if at[station]),
        default=_STATIONS.index("spec"),
    )
    return LineRow(
        kind="line_row",
        id=f"line:{effort.number}",
        effort=_mention(effort),
        reached=_STATIONS[reached],
        done=bool(tickets) and _done(tickets),
        total=sum(ticket.state is not TicketState.CLOSED for ticket in tickets),
        stations=LineStations(
            tickets=at["tickets"], build=at["build"], review=at["review"], landed=at["landed"]
        ),
    )


def _environment(items: list[Item]) -> list[EnvironmentFailure]:
    """Whatever failure of the environment stands now: what the start gate last raised,
    and what the merge queue raised for a red effort branch."""
    raised = [i.raised for i in items if isinstance(i, GateStatus) and i.raised is not None]
    return raised + [i for i in items if isinstance(i, EnvironmentFailure)]


def _closed(efforts: list[Effort], graph: dict[int, list[Ticket]]) -> list[NeedClosed]:
    """Every ticket GitHub closed while a session of Wayfarer's still runs on it."""
    return [
        NeedClosed(kind="closed", ticket=_mention(ticket), effort=_mention(effort))
        for effort in efforts
        for ticket in sorted(graph[effort.number], key=lambda t: t.number)
        if ticket.live and ticket.state in _OVER
    ]


def _need(
    effort: Effort,
    ticket: Ticket,
    tickets: list[Ticket],
    lines: list[ChronicleLine],
    auto_merge: bool,
) -> _OnATicket | None:
    def waited(kind: str) -> datetime | None:
        """When the chronicle last told the ticket moving to where it waits now."""
        told = [
            line.at
            for line in lines
            if line.moved.kind == kind
            and isinstance(line.moved, Asked | Held)
            and line.moved.ticket.number == ticket.number
        ]
        return told[-1] if told else None

    mention, of = _mention(ticket), _mention(effort)
    holds_up, starts = _holds_up(ticket, tickets), _starts(ticket, tickets)
    match ticket.state:
        case TicketState.ASKED:
            return NeedQuestion(
                kind="question",
                ticket=mention,
                effort=of,
                holds_up=holds_up,
                starts=starts,
                since=waited("asked"),
                gist=None,
            )
        case TicketState.HELD:
            return NeedHeld(
                kind="held",
                ticket=mention,
                effort=of,
                holds_up=holds_up,
                starts=starts,
                since=waited("held"),
                reason=None,
            )
        case TicketState.IN_REVIEW if (pull := _for_approval(ticket, auto_merge)) is not None:
            return NeedReview(
                kind="review",
                ticket=mention,
                effort=of,
                holds_up=holds_up,
                starts=starts,
                # A review is not a chronicle line, so it waits from its pull request.
                since=pull.opened,
            )
    return None


def _for_approval(ticket: Ticket, auto_merge: bool) -> PullRequest | None:
    """Its pull request, when that is clean and green and waiting only on the person,
    because auto-merge is off."""
    pull = ticket.pull_request
    waiting = (
        not auto_merge
        and pull is not None
        and not pull.draft
        and pull.checks in (None, Checks.PASSING)
        and not pull.approved
    )
    return pull if waiting else None


def _holds_up(ticket: Ticket, tickets: list[Ticket]) -> int:
    """The ticket itself, and every open ticket downstream of it, each counted once."""
    downstream: set[int] = set()
    frontier = [ticket.number]
    while frontier:
        blocker = frontier.pop()
        for t in tickets:
            if blocker in t.blocked_by and t.number not in downstream and t.state not in _OVER:
                downstream.add(t.number)
                frontier.append(t.number)
    return 1 + len(downstream - {ticket.number})


def _starts(ticket: Ticket, tickets: list[Ticket]) -> int:
    """The tickets it alone keeps off the frontier: takeable the moment it lands."""
    return sum(
        ticket.number in t.blocked_by
        and t.state is TicketState.BLOCKED
        and t.open_blockers == 1
        and not t.assignees
        and t.pull_request is None
        for t in tickets
    )


def _rank(need: _OnATicket) -> tuple[int, bool, datetime, int]:
    # Most held up first; then the longest waiting, what the chronicle has not dated last.
    waited = need.since or datetime.max.replace(tzinfo=UTC)
    return (-need.holds_up, need.since is None, waited, need.ticket.number)


def _headline(top: Need | None, landed: int, since: datetime | None) -> str:
    landings = f"{_tickets(landed)} landed" if landed else ""
    if top is not None:
        lead = _LEADS[top.kind]
        return f"{lead}, and {landings}." if landings else f"{lead}."
    if since is None:
        return f"{landings.capitalize()} so far." if landings else "Nothing has landed yet."
    if landings:
        return f"{landings.capitalize()} since you last looked."
    return "Nothing has moved since you last looked."


def _standfirst(effort: Effort, tickets: list[Ticket], waiting: list[_OnATicket]) -> str:
    building = sum(ticket.state is TicketState.BUILDING for ticket in tickets)
    on_you = sum(need.effort.number == effort.number for need in waiting)
    landed = sum(ticket.state is TicketState.LANDED for ticket in tickets)
    total = sum(ticket.state is not TicketState.CLOSED for ticket in tickets)
    if building:
        agents = "One agent is" if building == 1 else f"{_count(building).capitalize()} agents are"
        lead = f"{agents} building {effort.title}"
    else:
        lead = f"Nothing is building on {effort.title}"
    counts = [f"{landed} of {total} landed" if landed else "nothing landed yet"]
    if on_you:
        counts.insert(0, f"{_tickets(on_you)} waiting on you")
    return f"{lead}, with {' and '.join(counts)}."
