"""The read model: an effort's whole ticket graph, read from GitHub in one query.

An effort is its spec issue, and its tickets are that issue's sub-issues. One
GraphQL read returns every ticket with its labels, assignees, blocking summary
and pull request, and each ticket's state is derived from those facts on the
spot. Nothing is stored: ask again and it reads again (ADR-0002, ADR-0003).

Blocking is GitHub's own issue dependencies, never text in a ticket's body.

A ticket's pull request is one that mentions it from its ticket branch,
`ticket/<n>-…`. GitHub links a PR through closing keywords only when it targets
the default branch, and ticket PRs target the effort branch, so the link is read
from the cross-reference the mention leaves on the ticket's timeline instead.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

from wayfarer.github import GitHub, NoSuchIssue
from wayfarer.models import Checks, Effort, PullRequest, Ticket, TicketState

__all__ = ["ASKED", "HELD", "derive_state", "read_effort"]

ASKED = "wayfarer:asked"
HELD = "wayfarer:held"

# Leaf connections cost the same whatever their size, so each asks for GitHub's
# maximum of 100; only `subIssues` multiplies, and its page size is a setting.
_EFFORT = """
query Effort($owner: String!, $name: String!, $effort: Int!, $perPage: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    issue(number: $effort) {
      number
      title
      subIssues(first: $perPage, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          number
          title
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
                    isDraft
                    state
                    reviewDecision
                    statusCheckRollup { state }
                  }
                }
              }
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


async def read_effort(
    github: GitHub,
    number: int,
    *,
    per_page: int,
    auto_merge: bool,
    running: Collection[int] = frozenset(),
) -> Effort:
    """Effort `number` as GitHub has it now. `running` is the tickets with a live session."""
    nodes: list[dict[str, Any]] = []
    after: str | None = None
    while True:
        repository = await github.query(_EFFORT, effort=number, perPage=per_page, after=after)
        issue = repository["issue"]
        if issue is None:
            raise NoSuchIssue(f"{github.repo} has no issue #{number}.")
        page = issue["subIssues"]
        nodes += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    tickets = [_ticket(node, auto_merge=auto_merge, running=running) for node in nodes]
    return Effort(number=issue["number"], title=issue["title"], tickets=tickets)


def _ticket(node: dict[str, Any], *, auto_merge: bool, running: Collection[int]) -> Ticket:
    number: int = node["number"]
    labels = [label["name"] for label in node["labels"]["nodes"]]
    assignees = [user["login"] for user in node["assignees"]["nodes"]]
    open_blockers: int = node["issueDependenciesSummary"]["blockedBy"]
    pull_request = _pull_request(number, node["timelineItems"]["nodes"])
    return Ticket(
        number=number,
        title=node["title"],
        state=derive_state(
            open=node["state"] == "OPEN",
            completed=node["stateReason"] in ("COMPLETED", None),
            labels=labels,
            assignees=assignees,
            open_blockers=open_blockers,
            pull_request=pull_request,
            building=number in running,
            auto_merge=auto_merge,
        ),
        labels=labels,
        assignees=assignees,
        blocked_by=[blocker["number"] for blocker in node["blockedBy"]["nodes"]],
        open_blockers=open_blockers,
        pull_request=pull_request,
    )


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
        draft=chosen["isDraft"],
        merged=chosen["state"] == "MERGED",
        checks=_CHECKS[rollup["state"]] if rollup else None,
        approved=chosen["reviewDecision"] == "APPROVED",
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
