"""The read model: an effort's whole ticket graph, read from GitHub in one query.

An effort is its spec issue, and its tickets are that issue's sub-issues. One
GraphQL read returns every ticket with its labels, assignees, blocking summary
and pull request, and each ticket's state is derived from those facts on the
spot. Nothing is kept for the next read: ask again and it reads again (ADR-0002,
ADR-0003). What a read finds goes to the page's stream, an effort and each of its
tickets an item of its own, so a read that changes one ticket sends that ticket
alone (ADR-0004).

Blocking is GitHub's own issue dependencies, never text in a ticket's body.

A ticket's pull request is one that mentions it from its ticket branch,
`ticket/<n>-…`. GitHub links a PR through closing keywords only when it targets
the default branch, and ticket PRs target the effort branch, so the link is read
from the cross-reference the mention leaves on the ticket's timeline instead.

The same read brings each ticket's timeline of assignments, labels, closes and
comments, and whose token Wayfarer holds, which is all the chronicle is told from
(`chronicle.py`). Its lines go to the stream beside the tickets.
"""

from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from collections.abc import Awaitable, Callable, Collection, Container, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from wayfarer.asking import ASKED, latest
from wayfarer.freshness import Watch
from wayfarer.github import GitHub, GitHubError, NoSuchIssue, NotConnected
from wayfarer.models import (
    Checks,
    ChronicleLine,
    Effort,
    EffortUnreadable,
    PullRequest,
    Ticket,
    TicketState,
)
from wayfarer.settings import Settings
from wayfarer.stream import Store

__all__ = ["ASKED", "HELD", "Efforts", "Event", "History", "derive_state", "read_effort"]

HELD = "wayfarer:held"

# Leaf connections cost the same whatever their size, so each asks for GitHub's
# maximum of 100; only `subIssues` multiplies, and its page size is a setting.
# `events` is the chronicle's, apart from the cross-references so neither crowds
# the other out of its last 100.
_EFFORT = """
query Effort($owner: String!, $name: String!, $effort: Int!, $perPage: Int!, $after: String) {
  viewer { login }
  repository(owner: $owner, name: $name) {
    defaultBranchRef { name }
    issue(number: $effort) {
      number
      title
      subIssues(first: $perPage, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          number
          title
          body
          state
          stateReason
          labels(first: 100) { nodes { name } }
          assignees(first: 100) { nodes { login } }
          issueDependenciesSummary { blockedBy }
          blockedBy(first: 100) { nodes { number } }
          timelineItems(itemTypes: [CROSS_REFERENCED_EVENT], last: 100) {
            nodes {
              ... on CrossReferencedEvent {
                source {
                  ... on PullRequest {
                    number
                    headRefName
                    headRefOid
                    baseRefName
                    isDraft
                    state
                    reviewDecision
                    statusCheckRollup { state }
                    mergeCommit { oid }
                    createdAt
                  }
                }
              }
            }
          }
          events: timelineItems(
            itemTypes: [
              ASSIGNED_EVENT
              UNASSIGNED_EVENT
              LABELED_EVENT
              UNLABELED_EVENT
              CLOSED_EVENT
              REOPENED_EVENT
              ISSUE_COMMENT
            ]
            last: 100
          ) {
            nodes {
              __typename
              ... on AssignedEvent {
                createdAt actor { login } assignee { ... on User { login } }
              }
              ... on UnassignedEvent {
                createdAt actor { login } assignee { ... on User { login } }
              }
              ... on LabeledEvent { createdAt actor { login } label { name } }
              ... on UnlabeledEvent { createdAt actor { login } label { name } }
              ... on ClosedEvent { createdAt actor { login } stateReason }
              ... on ReopenedEvent { createdAt actor { login } }
              ... on IssueComment { createdAt author { login } body }
            }
          }
        }
      }
    }
  }
}
"""

_CHECKS = {
    "SUCCESS": Checks.PASSING,
    "PENDING": Checks.PENDING,
    "EXPECTED": Checks.PENDING,
    "FAILURE": Checks.FAILING,
    "ERROR": Checks.FAILING,
}


@dataclass(frozen=True)
class Event:
    """One event on a ticket's timeline, as GitHub reported it."""

    kind: str
    """GitHub's type name: `AssignedEvent`, `ClosedEvent`, `IssueComment`, …"""
    at: datetime
    actor: str | None
    """Who made it; None when GitHub no longer knows, as for a deleted account."""
    subject: str | None = None
    """The assignee's login, or the label's name."""
    reason: str | None = None
    """Why a close closed: `COMPLETED`, `NOT_PLANNED`, …"""
    body: str | None = None


@dataclass(frozen=True)
class History:
    """What one read of an effort found beyond its ticket graph."""

    viewer: str
    """The login of the token Wayfarer holds: the person's own."""
    timelines: dict[int, list[Event]]
    """Each ticket's events, oldest first."""


Telling = Callable[[Effort, list[Ticket], History], list[ChronicleLine]]
"""The chronicle of one read of an effort (`chronicle.py`)."""


class Efforts:
    """The efforts a page has asked to read, each read into the stream on request and
    read again whenever something may have changed (ADR-0003)."""

    def __init__(
        self,
        github: GitHub,
        store: Store,
        settings: Settings,
        line: Callable[[Effort, list[Ticket]], Awaitable[list[Ticket]]],
        telling: Telling,
    ) -> None:
        """`line` is the merge queue's: handed each read, it gives each Landing ticket
        its place in line. `telling` is the chronicle of each read."""
        self._github = github
        self._store = store
        self._settings = settings
        self._line = line
        self._telling = telling
        self._reading: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._followed: set[int] = set()
        self._pages: set[Watch] = set()
        self.building: Container[int] = frozenset()
        """The tickets a session is running on, which only this process knows."""
        self.then: Callable[[int], Awaitable[None]] | None = None
        """Called with an effort's number after each read of it: the cascade's cue."""

    async def read(self, number: int) -> None:
        """Read effort `number` from GitHub, put what changed on the stream, and follow it."""
        self._followed.add(number)
        # One read of an effort at a time, taken in the order asked, so an older
        # read never lands over a newer one.
        async with self._reading[number]:
            await self._read(number)
        self._await_open_pulls()
        if self.then is not None:
            await self.then(number)

    async def follow(self) -> None:
        """Read every followed effort again each time the signal fires, until cancelled."""
        # Not held as a watch: following is no reason to poll fast, and an open
        # page, which is, holds one of its own (`watched`).
        signal = Watch(self._github.freshness, self._github.freshness.version)
        while True:
            await signal.changed()
            for number in sorted(self._followed):
                await self.read(number)

    @contextmanager
    def watched(self) -> Iterator[None]:
        """Held while a page is open: the poll keeps its open rhythm, and polls the
        checks of every open pull request the page may be shown."""
        with self._github.freshness.watch() as watch:
            self._pages.add(watch)
            self._await_open_pulls()
            try:
                yield
            finally:
                self._pages.discard(watch)

    def _await_open_pulls(self) -> None:
        # Checks never change the issue the poll lists, so each open PR is polled
        # on its own (ADR-0003).
        awaiting = frozenset(
            item.pull_request.branch
            for item in self._store.items()
            if isinstance(item, Ticket)
            and item.pull_request is not None
            and not item.pull_request.merged
        )
        for page in self._pages:
            page.awaiting = awaiting

    async def _read(self, number: int) -> None:
        id = f"effort:{number}"
        held = self._store.get(id)
        before = held.tickets if isinstance(held, Effort) else []
        try:
            effort, tickets, history = await read_effort(
                self._github,
                number,
                per_page=self._settings.tickets_per_page,
                auto_merge=self._settings.auto_merge,
                building=self.building,
            )
        except (NotConnected, NoSuchIssue, GitHubError) as error:
            self._store.upsert(
                EffortUnreadable(kind="effort_unreadable", id=id, number=number, reason=str(error))
            )
        else:
            # Tickets before the effort, so it never names one the page lacks.
            for ticket in await self._line(effort, tickets):
                self._store.upsert(ticket)
            self._tell(effort, tickets, history)
            self._store.upsert(effort)
        named = {
            ticket
            for item in self._store.items()
            if isinstance(item, Effort)
            for ticket in item.tickets
        }
        for ticket_id in before:
            if ticket_id not in named:
                self._store.remove(ticket_id)

    def _tell(self, effort: Effort, tickets: list[Ticket], history: History) -> None:
        # Rebuilt whole on every read and never stored (#22): an unchanged line is
        # not sent again, and one no longer told goes.
        lines = self._telling(effort, tickets, history)
        for line in lines:
            self._store.upsert(line)
        told = {line.id for line in lines}
        for item in self._store.items():
            if (
                isinstance(item, ChronicleLine)
                and item.effort.number == effort.number
                and item.id not in told
            ):
                self._store.remove(item.id)


async def read_effort(
    github: GitHub,
    number: int,
    *,
    per_page: int,
    auto_merge: bool,
    building: Container[int] = frozenset(),
) -> tuple[Effort, list[Ticket], History]:
    """Effort `number` and its tickets as GitHub has them now, and their history."""
    nodes: list[dict[str, Any]] = []
    after: str | None = None
    while True:
        data = await github.query(_EFFORT, effort=number, perPage=per_page, after=after)
        repository = data["repository"]
        issue = repository["issue"]
        if issue is None:
            raise NoSuchIssue(f"{github.repo} has no issue #{number}.")
        page = issue["subIssues"]
        nodes += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    tickets = [_ticket(node, auto_merge=auto_merge, building=building) for node in nodes]
    effort = Effort(
        kind="effort",
        id=f"effort:{number}",
        number=issue["number"],
        title=issue["title"],
        trunk=repository["defaultBranchRef"]["name"],
        tickets=[ticket.id for ticket in tickets],
    )
    history = History(
        viewer=data["viewer"]["login"],
        timelines={node["number"]: [_event(e) for e in node["events"]["nodes"]] for node in nodes},
    )
    return effort, tickets, history


def _event(node: dict[str, Any]) -> Event:
    actor = node.get("actor") or node.get("author")
    subject = (node.get("assignee") or {}).get("login") or (node.get("label") or {}).get("name")
    return Event(
        kind=node["__typename"],
        at=datetime.fromisoformat(node["createdAt"]),
        actor=actor["login"] if actor else None,
        subject=subject,
        reason=node.get("stateReason"),
        body=node.get("body"),
    )


def _ticket(node: dict[str, Any], *, auto_merge: bool, building: Container[int]) -> Ticket:
    number: int = node["number"]
    labels = [label["name"] for label in node["labels"]["nodes"]]
    assignees = [user["login"] for user in node["assignees"]["nodes"]]
    open_blockers: int = node["issueDependenciesSummary"]["blockedBy"]
    events = [_event(e) for e in node["events"]["nodes"]]
    pull_request = _pull_request(number, node["timelineItems"]["nodes"])
    is_open = node["state"] == "OPEN"
    return Ticket(
        kind="ticket",
        id=f"ticket:{number}",
        number=number,
        title=node["title"],
        state=derive_state(
            open=is_open,
            completed=node["stateReason"] in ("COMPLETED", None),
            labels=labels,
            assignees=assignees,
            open_blockers=open_blockers,
            pull_request=pull_request,
            building=number in building,
            auto_merge=auto_merge,
        ),
        open=is_open,
        labels=labels,
        assignees=assignees,
        blocked_by=[blocker["number"] for blocker in node["blockedBy"]["nodes"]],
        open_blockers=open_blockers,
        pull_request=pull_request,
        live=number in building,
        question=latest(events),
        criteria=criteria(node["body"]),
        # The merge queue's to say, from an order this read does not ask for.
        place_in_line=None,
    )


# A ticket's criteria are the items under its "Acceptance criteria" heading, ticked or
# not, as `/to-tickets` writes them.
_CRITERIA = re.compile(r"^#+\s*acceptance criteria\s*$", re.IGNORECASE)
_HEADING = re.compile(r"^#+\s")
_ITEM = re.compile(r"^[-*]\s+(?:\[[ xX]\]\s+)?(.+?)\s*$")


def criteria(body: str) -> list[str]:
    """The acceptance criteria in a ticket's `body`, in order and as worded."""
    found: list[str] = []
    within = False
    for line in body.splitlines():
        if _HEADING.match(line):
            within = bool(_CRITERIA.match(line))
        elif within and (item := _ITEM.match(line)):
            found.append(item[1])
    return found


def _pull_request(ticket: int, timeline: list[dict[str, Any]]) -> PullRequest | None:
    """The merged PR from the ticket's branch if there is one, else the latest open one."""
    branch = f"ticket/{ticket}-"
    pulls = [
        event["source"]
        for event in timeline
        if event and event["source"].get("headRefName", "").startswith(branch)
    ]
    merged = [pull for pull in pulls if pull["state"] == "MERGED"]
    open_ = [pull for pull in pulls if pull["state"] == "OPEN"]
    chosen = (merged or open_ or [None])[-1]
    if chosen is None:
        return None
    rollup = chosen["statusCheckRollup"]
    return PullRequest(
        number=chosen["number"],
        branch=chosen["headRefName"],
        base=chosen["baseRefName"],
        head_commit=chosen["headRefOid"],
        draft=chosen["isDraft"],
        merged=chosen["state"] == "MERGED",
        merge_commit=(chosen["mergeCommit"] or {}).get("oid"),
        checks=_CHECKS[rollup["state"]] if rollup else None,
        approved=chosen["reviewDecision"] == "APPROVED",
        opened=datetime.fromisoformat(chosen["createdAt"]),
    )


def derive_state(
    *,
    open: bool,
    completed: bool,
    labels: Collection[str],
    assignees: Collection[str],
    open_blockers: int,
    pull_request: PullRequest | None,
    building: bool,
    auto_merge: bool,
) -> TicketState:
    """The first state a ticket matches, in the documented priority order."""
    if (pull_request is not None and pull_request.merged) or (not open and completed):
        return TicketState.LANDED
    if not open:
        return TicketState.CLOSED
    if ASKED in labels:
        return TicketState.ASKED
    if HELD in labels:
        return TicketState.HELD
    if pull_request is not None:
        green = pull_request.checks in (None, Checks.PASSING)
        if not pull_request.draft and green and (auto_merge or pull_request.approved):
            return TicketState.LANDING
        return TicketState.IN_REVIEW
    if building:
        return TicketState.BUILDING
    if open_blockers == 0 and not assignees:
        return TicketState.TAKEABLE
    return TicketState.BLOCKED
