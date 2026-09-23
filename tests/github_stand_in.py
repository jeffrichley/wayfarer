"""A stand-in for GitHub that every test drives Wayfarer against, never a live repo.

It holds one repo's issues and pull requests in memory and speaks the two things
Wayfarer reads: GitHub's GraphQL API, over a subset of GitHub's real schema, and
the REST issue listing the conditional poll will use (ADR-0003). A test changes
it as a person on GitHub would, and it can be made to misbehave on purpose:

- **poked**: change an issue or a pull request, and the next read sees it;
- **stale**: freeze what reads return while changes pile up behind it;
- **unchanged**: the REST listing carries an ETag and answers a matching
  `If-None-Match` with `304 Not Modified`;
- **disagreeing**: nothing stops a test closing a ticket a session is still on.

The GraphQL schema below uses GitHub's own type and field names, and graphql-core
validates every query against it, so a misspelt field fails here as it would on
GitHub. Every query is also priced with GitHub's documented point formula, so a
test can hold a read to its budget. The one check this cannot make is that the
subset matches the real schema; `test_real_github.py` does.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import socket
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from graphql import (
    FieldNode,
    FragmentDefinitionNode,
    FragmentSpreadNode,
    GraphQLResolveInfo,
    InlineFragmentNode,
    IntValueNode,
    OperationDefinitionNode,
    SelectionSetNode,
    VariableNode,
    build_schema,
    graphql_sync,
    parse,
)

TOKEN = "stand-in-token"

_SCHEMA = build_schema("""
type Query {
  repository(owner: String!, name: String!): Repository
  rateLimit: RateLimit
}

type RateLimit { cost: Int! limit: Int! remaining: Int! }

type Repository { issue(number: Int!): Issue }

enum IssueState { OPEN CLOSED }
enum IssueStateReason { COMPLETED NOT_PLANNED DUPLICATE REOPENED }
enum PullRequestState { OPEN CLOSED MERGED }
enum PullRequestReviewDecision { APPROVED CHANGES_REQUESTED REVIEW_REQUIRED }
enum StatusState { ERROR EXPECTED FAILURE PENDING SUCCESS }
enum IssueTimelineItemsItemType { CROSS_REFERENCED_EVENT CLOSED_EVENT }

type PageInfo { hasNextPage: Boolean! endCursor: String }

type Issue {
  number: Int!
  title: String!
  state: IssueState!
  stateReason: IssueStateReason
  labels(first: Int, after: String): LabelConnection
  assignees(first: Int, after: String): UserConnection!
  issueDependenciesSummary: IssueDependenciesSummary!
  blockedBy(first: Int, after: String): IssueConnection!
  subIssues(first: Int, after: String): IssueConnection!
  timelineItems(
    itemTypes: [IssueTimelineItemsItemType!], first: Int, last: Int
  ): IssueTimelineItemsConnection!
}

type IssueConnection { nodes: [Issue] pageInfo: PageInfo! totalCount: Int! }
type Label { name: String! }
type LabelConnection { nodes: [Label] }
type User { login: String! }
type UserConnection { nodes: [User] }

type IssueDependenciesSummary {
  blockedBy: Int!
  totalBlockedBy: Int!
  blocking: Int!
  totalBlocking: Int!
}

type StatusCheckRollup { state: StatusState! }

type PullRequest {
  number: Int!
  headRefName: String!
  baseRefName: String!
  isDraft: Boolean!
  state: PullRequestState!
  merged: Boolean!
  reviewDecision: PullRequestReviewDecision
  statusCheckRollup: StatusCheckRollup
}

union ReferencedSubject = Issue | PullRequest
type CrossReferencedEvent { source: ReferencedSubject! willCloseTarget: Boolean! }
type ClosedEvent { createdAt: String! }
union IssueTimelineItems = CrossReferencedEvent | ClosedEvent
type IssueTimelineItemsConnection { nodes: [IssueTimelineItems] }
""")


@dataclass
class Issue:
    number: int
    title: str
    state: str = "OPEN"
    state_reason: str | None = None
    labels: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    parent: int | None = None
    blocked_by: list[int] = field(default_factory=list)


@dataclass
class PullRequest:
    number: int
    head: str
    base: str = "main"
    draft: bool = False
    state: str = "OPEN"
    review: str | None = None
    # None is a PR with no checks at all.
    checks: str | None = None
    # The issues its body or commits mention, which is what puts a
    # cross-reference on each of their timelines.
    mentions: list[int] = field(default_factory=list)


@dataclass
class _Repo:
    issues: dict[int, Issue] = field(default_factory=dict)
    pulls: dict[int, PullRequest] = field(default_factory=dict)


class GitHub:
    """One repo on the stand-in: `owner/name`, served at `api`."""

    def __init__(self, owner: str, name: str) -> None:
        self.owner = owner
        self.name = name
        self._live = _Repo()
        self._frozen: _Repo | None = None
        self._next_number = 1
        self._lock = threading.Lock()
        self.queries: list[str] = []
        self.points: list[int] = []
        self.api = ""
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    # -- the repo, changed as a person on GitHub would -------------------------

    def issue(self, title: str, **fields: Any) -> Issue:
        with self._lock:
            issue = Issue(self._take_number(), title, **fields)
            self._live.issues[issue.number] = issue
            return issue

    def effort(self, title: str, tickets: int = 0) -> tuple[Issue, list[Issue]]:
        """A spec issue and `tickets` open sub-issues under it."""
        spec = self.issue(title, labels=["ready-for-agent"])
        return spec, [self.issue(f"Ticket {i + 1}", parent=spec.number) for i in range(tickets)]

    def pull_request(self, ticket: Issue, **fields: Any) -> PullRequest:
        """A PR from the ticket's own branch that mentions it, as Wayfarer opens one."""
        with self._lock:
            fields.setdefault("head", f"ticket/{ticket.number}-work")
            fields.setdefault("mentions", [ticket.number])
            pull = PullRequest(self._take_number(), **fields)
            self._live.pulls[pull.number] = pull
            return pull

    def block(self, ticket: Issue, *, by: Issue) -> None:
        ticket.blocked_by.append(by.number)

    def close(self, issue: Issue, reason: str = "COMPLETED") -> None:
        issue.state = "CLOSED"
        issue.state_reason = reason

    def _take_number(self) -> int:
        number = self._next_number
        self._next_number += 1
        return number

    # -- misbehaving on purpose -------------------------------------------------

    @contextmanager
    def stale(self) -> Iterator[None]:
        """Reads return the repo as it is now, whatever changes meanwhile."""
        with self._lock:
            self._frozen = _snapshot(self._live)
        try:
            yield
        finally:
            with self._lock:
                self._frozen = None

    def _visible(self) -> _Repo:
        return self._frozen if self._frozen is not None else self._live

    # -- serving ----------------------------------------------------------------

    def start(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        self.api = f"http://127.0.0.1:{sock.getsockname()[1]}"
        self._server = uvicorn.Server(uvicorn.Config(self._app(), log_level="warning"))
        self._thread = threading.Thread(
            target=self._server.run, kwargs={"sockets": [sock]}, daemon=True
        )
        self._thread.start()
        deadline = time.monotonic() + 10
        while not self._server.started:
            assert time.monotonic() < deadline, "the GitHub stand-in never started"
            time.sleep(0.01)

    def stop(self) -> None:
        assert self._server is not None and self._thread is not None
        self._server.should_exit = True
        self._thread.join(timeout=10)

    def _app(self) -> FastAPI:
        app = FastAPI()

        @app.post("/graphql")
        async def graphql_endpoint(request: Request) -> Response:
            if request.headers.get("authorization") != f"bearer {TOKEN}":
                return JSONResponse({"message": "Bad credentials"}, status_code=401)
            body = await request.json()
            return JSONResponse(self._graphql(body["query"], body.get("variables") or {}))

        @app.get("/repos/{owner}/{name}/issues")
        async def list_issues(owner: str, name: str, request: Request) -> Response:
            with self._lock:
                listing = [_rest_issue(i) for i in self._visible().issues.values()]
            etag = '"' + hashlib.sha1(json.dumps(listing).encode()).hexdigest() + '"'
            if request.headers.get("if-none-match") == etag:
                return Response(status_code=304, headers={"ETag": etag})
            return JSONResponse(listing, headers={"ETag": etag})

        return app

    def _graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self.queries.append(query)
            self.points.append(points(query, variables))
            result = graphql_sync(
                _SCHEMA,
                query,
                root_value=_Root(self, self._visible()),
                variable_values=variables,
                field_resolver=_resolve,
            )
        response: dict[str, Any] = {"data": result.data}
        if result.errors:
            response["errors"] = [
                {**e.formatted, "type": "NOT_FOUND"}
                if isinstance(e.original_error, _NotFound)
                else e.formatted
                for e in result.errors
            ]
        return response


def _snapshot(repo: _Repo) -> _Repo:
    return copy.deepcopy(repo)


def _rest_issue(issue: Issue) -> dict[str, Any]:
    return {
        "number": issue.number,
        "title": issue.title,
        "state": issue.state.lower(),
        "labels": [{"name": n} for n in issue.labels],
        "assignees": [{"login": a} for a in issue.assignees],
    }


# -- resolving the schema over the in-memory repo --------------------------------


@dataclass
class _Root:
    github: GitHub
    repo: _Repo


@dataclass
class _Node:
    """Anything a resolver returns: a GitHub object or a connection, with its
    fields computed lazily from the repo it was read from."""

    typename: str
    fields: dict[str, Any]


def _resolve(source: Any, info: GraphQLResolveInfo, **args: Any) -> Any:
    name = info.field_name
    if isinstance(source, _Root):
        if name == "repository":
            ours = (args["owner"], args["name"]) == (source.github.owner, source.github.name)
            return _repository(source.repo) if ours else None
        return None
    value = source.fields[name]
    return value(**args) if callable(value) else value


class _NotFound(Exception):
    """What GitHub reports, beside a null, for an object that does not exist."""


def _repository(repo: _Repo) -> _Node:
    def issue(number: int) -> _Node:
        found = repo.issues.get(number)
        if found is None:
            raise _NotFound(f"Could not resolve to an Issue with the number of {number}.")
        return _issue(repo, found)

    return _Node("Repository", {"issue": issue})


def _connection(items: list[Any], first: int | None, after: str | None) -> _Node:
    start = int(after) if after else 0
    end = len(items) if first is None else start + first
    page = items[start:end]
    return _Node(
        "Connection",
        {
            "nodes": page,
            "totalCount": len(items),
            "pageInfo": _Node(
                "PageInfo",
                {"hasNextPage": end < len(items), "endCursor": str(end) if page else None},
            ),
        },
    )


def _issue(repo: _Repo, issue: Issue) -> _Node:
    # Lazy, so a read builds only as deep as its query asks.
    def paged(items: Callable[[], list[Any]]) -> Any:
        return lambda first=None, after=None: _connection(items(), first, after)

    blockers = [repo.issues[n] for n in issue.blocked_by]
    blocking = [i for i in repo.issues.values() if issue.number in i.blocked_by]

    def timeline_items(
        itemTypes: list[str] | None = None, first: int | None = None, last: int | None = None
    ) -> _Node:
        events = [
            _Node(
                "CrossReferencedEvent",
                {"source": _pull_request(p), "willCloseTarget": p.base == "main"},
            )
            for p in sorted(repo.pulls.values(), key=lambda p: p.number)
            if issue.number in p.mentions
        ]
        if itemTypes is not None and "CROSS_REFERENCED_EVENT" not in itemTypes:
            events = []
        if last is not None:
            events = events[-last:]
        return _Node("Connection", {"nodes": events})

    return _Node(
        "Issue",
        {
            "number": issue.number,
            "title": issue.title,
            "state": issue.state,
            "stateReason": issue.state_reason,
            "labels": paged(lambda: [_Node("Label", {"name": n}) for n in issue.labels]),
            "assignees": paged(lambda: [_Node("User", {"login": a}) for a in issue.assignees]),
            "issueDependenciesSummary": _Node(
                "IssueDependenciesSummary",
                {
                    "blockedBy": sum(b.state == "OPEN" for b in blockers),
                    "totalBlockedBy": len(blockers),
                    "blocking": sum(b.state == "OPEN" for b in blocking),
                    "totalBlocking": len(blocking),
                },
            ),
            "blockedBy": paged(lambda: [_issue(repo, b) for b in blockers]),
            "subIssues": paged(
                lambda: [
                    _issue(repo, c)
                    for c in sorted(repo.issues.values(), key=lambda i: i.number)
                    if c.parent == issue.number
                ]
            ),
            "timelineItems": timeline_items,
        },
    )


def _pull_request(pull: PullRequest) -> _Node:
    return _Node(
        "PullRequest",
        {
            "number": pull.number,
            "headRefName": pull.head,
            "baseRefName": pull.base,
            "isDraft": pull.draft,
            "state": pull.state,
            "merged": pull.state == "MERGED",
            "reviewDecision": pull.review,
            "statusCheckRollup": _Node("StatusCheckRollup", {"state": pull.checks})
            if pull.checks
            else None,
        },
    )


def _resolve_type(value: _Node, *_: Any) -> str:
    return value.typename


for _union in ("ReferencedSubject", "IssueTimelineItems"):
    _SCHEMA.type_map[_union].resolve_type = _resolve_type  # type: ignore[attr-defined]


# -- GitHub's point formula --------------------------------------------------------


def points(query: str, variables: dict[str, Any]) -> int:
    """What GitHub charges for `query`, by its documented formula.

    Every connection costs one request per node of its parent that could reach
    it, assuming each connection returns its full `first`/`last`; the sum is
    divided by 100 and rounded to the nearest whole number, with a minimum of 1.
    https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api
    """
    document = parse(query)
    fragments = {
        d.name.value: d for d in document.definitions if isinstance(d, FragmentDefinitionNode)
    }

    def limit(node: FieldNode) -> int | None:
        for argument in node.arguments:
            if argument.name.value in ("first", "last"):
                value = argument.value
                if isinstance(value, VariableNode):
                    return int(variables[value.name.value])
                assert isinstance(value, IntValueNode)
                return int(value.value)
        return None

    def requests(selections: SelectionSetNode | None, parents: int) -> int:
        if selections is None:
            return 0
        total = 0
        for selection in selections.selections:
            if isinstance(selection, FieldNode):
                size = limit(selection)
                if size is None:
                    total += requests(selection.selection_set, parents)
                else:
                    total += parents + requests(selection.selection_set, parents * size)
            elif isinstance(selection, InlineFragmentNode):
                total += requests(selection.selection_set, parents)
            elif isinstance(selection, FragmentSpreadNode):
                total += requests(fragments[selection.name.value].selection_set, parents)
        return total

    total = sum(
        requests(d.selection_set, 1)
        for d in document.definitions
        if isinstance(d, OperationDefinitionNode)
    )
    return max(1, math.floor(total / 100 + 0.5))
