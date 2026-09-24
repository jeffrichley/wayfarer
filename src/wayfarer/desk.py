"""The review desk's queue: Needs you, in an order that holds still while the person
works through it (#57, docs/screens/review-desk.md).

Home shows Needs you in live order; the desk freezes its own copy when the person
arrives, so the list never reshuffles under their cursor. What each item says
stays live. An item that arrives later joins at the bottom, marked new, unless it
is an environment failure: that stopped everything, so it goes first. An item
that no longer needs the person stays where it was, saying what happened, so
their place in the queue never jumps. Arriving again re-ranks it.

The frozen order is the only thing kept, and only in memory: a restarted Wayfarer
has a desk nobody is on, so it shows the live order until someone arrives.
"""

from __future__ import annotations

from wayfarer.models import (
    Desk,
    DeskEntry,
    EnvironmentFailure,
    Need,
    NeedClosed,
    NeedHeld,
    NeedQuestion,
    NeedReview,
    NeedsYou,
    Orphan,
    ShipEffort,
    Ticket,
    TicketState,
    UnknownContainer,
)
from wayfarer.stream import Store as Stream

__all__ = ["DeskPage", "key"]


def key(need: Need) -> str:
    """What names `need` for as long as it lasts: its ticket, for an item on one, since
    a ticket's item may turn from a question to a hold and is still the same item."""
    if isinstance(need, NeedQuestion | NeedHeld | NeedReview | NeedClosed):
        return f"ticket:{need.ticket.number}"
    return need.id


class DeskPage:
    """The desk's item on one stream, kept derived from Needs you there."""

    def __init__(self, stream: Stream) -> None:
        self._stream = stream
        # The queue as the person found it, and each entry as last seen: None until
        # someone arrives, when the desk is the live order.
        self._frozen: dict[str, Need] | None = None
        self._new: set[str] = set()

    def arrived(self) -> None:
        """The person arrived at the desk: its order is re-ranked, and holds from now."""
        self._frozen = {key(need): need for need in self._live()}
        self._new = set()
        self.refresh()

    async def follow(self) -> None:
        """Derive the desk again after every change to the stream, until it closes."""
        while not self._stream.closed:
            self.refresh()
            await self._stream.changed()

    def refresh(self) -> None:
        live = {key(need): need for need in self._live()}
        if self._frozen is None:
            entries = [DeskEntry(key=k, need=n, new=False, resolved=None) for k, n in live.items()]
        else:
            for k, need in live.items():
                if k not in self._frozen:
                    self._new.add(k)
                    if isinstance(need, EnvironmentFailure):
                        # It stopped everything, so it is never below anything, even
                        # arriving late (#24): the one new item that goes first.
                        self._frozen = {k: need, **self._frozen}
                self._frozen[k] = need
            entries = [
                DeskEntry(
                    key=k,
                    need=need,
                    new=k in self._new,
                    resolved=None if k in live else self._happened(need),
                )
                for k, need in self._frozen.items()
            ]
        self._stream.upsert(Desk(kind="desk", id="desk", entries=entries))

    def _live(self) -> list[Need]:
        needs = self._stream.get("needs_you")
        return needs.items if isinstance(needs, NeedsYou) else []

    def _happened(self, need: Need) -> str:
        """What became of an item that no longer needs the person, said from where
        things stand now."""
        match need:
            case EnvironmentFailure():
                return "Cleared · the cascades can start again"
            case ShipEffort():
                return "Shipped"
            case Orphan():
                return "Reaped · its ticket is held"
            case UnknownContainer():
                return "Gone"
        ticket = self._stream.get(f"ticket:{need.ticket.number}")
        state = ticket.state if isinstance(ticket, Ticket) else None
        if state is TicketState.LANDED:
            return "Landed"
        if state is TicketState.LANDING:
            return "Landing · in the merge queue"
        building = state is TicketState.BUILDING
        match need:
            case NeedClosed():
                return "Its session ended"
            case _ if state is TicketState.CLOSED:
                return "Closed without landing"
            case NeedQuestion():
                return "Answered · the session resumed" if building else "Answered"
            case NeedHeld():
                return "Retried · a session is building" if building else "Released"
            case NeedReview():
                return "Resolved"
