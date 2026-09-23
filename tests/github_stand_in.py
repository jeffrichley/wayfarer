"""A stand-in for GitHub that every test drives Wayfarer against, never a live repo.

It holds one repo's issues and pull requests in memory and speaks what Wayfarer
reads and writes: GitHub's GraphQL API, over a subset of GitHub's real schema; the
REST issue listing and commit checks the conditional poll uses (ADR-0003); and the
REST writes Wayfarer makes: claiming, labelling, commenting on and closing an issue,
and opening and merging a pull request. A test changes it as a person on GitHub
would, and it can be made to misbehave on purpose:

- **poked**: change an issue or a pull request, and the next read sees it;
- **stale**: freeze what reads return while changes pile up behind it;
- **unchanged**: every REST read carries an ETag and answers a matching
  `If-None-Match` with `304 Not Modified`, which spends no rate budget;
- **rate-limited**: refuse the next REST reads with `403` or `429`, or ask for a
  slower poll with `X-Poll-Interval`;
- **disagreeing**: nothing stops a test closing a ticket a session is still on;
- **unmergeable**: a pull request can refuse to merge, as one with a conflict does.

Every REST request is logged in `requests`, so a test can see the poll's rhythm.

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
import re
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

type Repository { issue(number: Int!): Issue defaultBranchRef: Ref }
type Ref { name: String! }

enum IssueState { OPEN CLOSED }
enum IssueStateReason { COMPLETED NOT_PLANNED DUPLICATE REOPENED }
enum PullRequestState { OPEN CLOSED MERGED }
enum PullRequestReviewDecision { APPROVED CHANGES_REQUESTED REVIEW_REQUIRED }
enum StatusState { ERROR EXPECTED FAILURE PENDING SUCCESS }
enum IssueTimelineItemsItemType { CROSS_REFERENCED_EVENT CLOSED_EVENT }
scalar GitObjectID

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
type Commit { oid: GitObjectID! }

type PullRequest {
  number: Int!
  headRefName: String!
  headRefOid: GitObjectID!
  baseRefName: String!
  isDraft: Boolean!
  state: PullRequestState!
  merged: Boolean!
  reviewDecision: PullRequestReviewDecision
  statusCheckRollup: StatusCheckRollup
  mergeCommit: Commit
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
    # Every comment's body, oldest first.
    comments: list[str] = field(default_factory=list)


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
    title: str = ""
    body: str = ""
    # The commit at its head, which a push moves.
    head_commit: str = "1" * 40
    # False is a PR GitHub will not merge, as it will not one with a conflict.
    mergeable: bool = True
    # The commit its merge made on its base; None until it merges.
    merge_commit: str | None = None


@dataclass(frozen=True)
class Refusal:
    """A REST read GitHub turned away, and the headers it gave."""

    status: int
    headers: dict[str, str] = field(default_factory=dict)
    message: str = "API rate limit exceeded"


@dataclass(frozen=True)
class Logged:
    """One REST request the stand-in answered: which, how, and when (monotonic)."""

    method: str
    path: str
    status: int
    at: float


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
        self.requests: list[Logged] = []
        self.poll_interval: int | None = None
        self._refusals: list[Refusal] = []
        self._forbidden: list[str] = []
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

    def merged(self, pull: PullRequest) -> None:
        """Merged, as a person merges one by hand on GitHub."""
        with self._lock:
            self._merge(pull)

    def pulls(self) -> list[PullRequest]:
        with self._lock:
            return sorted(self._live.pulls.values(), key=lambda p: p.number)

    def labels(self, number: int) -> list[str]:
        with self._lock:
            return list(self._live.issues[number].labels)

    def _merge(self, pull: PullRequest) -> None:
        pull.state = "MERGED"
        pull.merge_commit = hashlib.sha1(f"merge {pull.number}".encode()).hexdigest()

    def block(self, ticket: Issue, *, by: Issue) -> None:
        ticket.blocked_by.append(by.number)

    def close(self, issue: Issue, reason: str = "COMPLETED") -> None:
        issue.state = "CLOSED"
        issue.state_reason = reason

    def delete(self, issue: Issue) -> None:
        """Gone, as an admin deletes an issue: every read says it never existed."""
        with self._lock:
            del self._live.issues[issue.number]

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

    def refuse(self, *refusals: Refusal) -> None:
        """Answer the next REST reads with these, one each, then serve again."""
        with self._lock:
            self._refusals += refusals

    def forbid(self, path: str) -> None:
        """Refuse every read of paths ending in `path`, as GitHub refuses a token
        without the permission that path needs."""
        with self._lock:
            self._forbidden.append(path)

    def _visible(self) -> _Repo:
        return self._frozen if self._frozen is not None else self._live

    # -- what Wayfarer asked -----------------------------------------------------

    def polls(self, path: str = "/issues") -> list[Logged]:
        """The REST reads of paths ending in `path`, in order."""
        with self._lock:
            return [r for r in self.requests if r.method == "GET" and r.path.endswith(path)]

    def spent(self) -> int:
        """REST requests that count against the rate limit: all but a `304`."""
        with self._lock:
            return sum(r.status != 304 for r in self.requests)

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
            body = await request.json()
            return JSONResponse(self._graphql(body["query"], body.get("variables") or {}))

        @app.middleware("http")
        async def log(request: Request, call_next: Any) -> Response:
            # Every request needs the token, as GitHub's do.
            response: Response
            if request.headers.get("authorization") != f"bearer {TOKEN}":
                response = JSONResponse({"message": "Bad credentials"}, status_code=401)
            else:
                response = await call_next(request)
            if request.url.path != "/graphql":
                with self._lock:
                    self.requests.append(
                        Logged(
                            request.method, request.url.path, response.status_code, time.monotonic()
                        )
                    )
            return response

        @app.get("/repos/{owner}/{name}/issues")
        async def list_issues(owner: str, name: str, request: Request) -> Response:
            with self._lock:
                listing = [_rest_issue(i) for i in self._visible().issues.values()]
            return self._conditional(request, listing)

        # GitHub takes a branch as the ref, slashes and all, encoded or not.
        @app.get("/repos/{owner}/{name}/commits/{ref:path}/check-runs")
        async def check_runs(owner: str, name: str, ref: str, request: Request) -> Response:
            state = self._checks_on(ref)
            runs = [] if state is None else [_check_run(state)]
            return self._conditional(request, {"total_count": len(runs), "check_runs": runs})

        # The combined status: statuses posted by CI that does not use check runs.
        # This stand-in's CI posts check runs only, so it is always empty.
        @app.get("/repos/{owner}/{name}/commits/{ref:path}/status")
        async def status(owner: str, name: str, ref: str, request: Request) -> Response:
            return self._conditional(request, {"state": "pending", "total_count": 0})

        @app.post("/repos/{owner}/{name}/issues/{number}/labels")
        async def label(owner: str, name: str, number: int, request: Request) -> Response:
            body = await request.json()
            with self._lock:
                issue = self._live.issues[number]
                issue.labels += [n for n in body["labels"] if n not in issue.labels]
                return JSONResponse([{"name": n} for n in issue.labels])

        @app.post("/repos/{owner}/{name}/issues/{number}/comments")
        async def comment(owner: str, name: str, number: int, request: Request) -> Response:
            body = await request.json()
            with self._lock:
                self._live.issues[number].comments.append(body["body"])
                return JSONResponse({"body": body["body"]}, status_code=201)

        @app.patch("/repos/{owner}/{name}/issues/{number}")
        async def edit_issue(owner: str, name: str, number: int, request: Request) -> Response:
            body = await request.json()
            with self._lock:
                issue = self._live.issues[number]
                if body.get("state") == "closed":
                    issue.state = "CLOSED"
                    issue.state_reason = (body.get("state_reason") or "completed").upper()
                return JSONResponse(_rest_issue(issue))

        @app.post("/repos/{owner}/{name}/pulls")
        async def open_pull(owner: str, name: str, request: Request) -> Response:
            body = await request.json()
            with self._lock:
                pull = PullRequest(
                    self._take_number(),
                    head=body["head"],
                    base=body["base"],
                    draft=body.get("draft", False),
                    title=body["title"],
                    body=body.get("body") or "",
                    mentions=[int(n) for n in re.findall(r"#(\d+)", body.get("body") or "")],
                )
                self._live.pulls[pull.number] = pull
                return JSONResponse({"number": pull.number, "draft": pull.draft}, status_code=201)

        # GitHub answers `405` for a PR it will not merge: a draft, or a conflict.
        @app.put("/repos/{owner}/{name}/pulls/{number}/merge")
        async def merge(owner: str, name: str, number: int, request: Request) -> Response:
            with self._lock:
                pull = self._live.pulls[number]
                if pull.draft or pull.state != "OPEN" or not pull.mergeable:
                    return JSONResponse(
                        {"message": "Pull Request is not mergeable"}, status_code=405
                    )
                self._merge(pull)
                return JSONResponse({"sha": pull.merge_commit, "merged": True})

        @app.post("/repos/{owner}/{name}/issues/{number}/assignees")
        async def assign(owner: str, name: str, number: int, request: Request) -> Response:
            body = await request.json()
            with self._lock:
                issue = self._live.issues[number]
                issue.assignees += [a for a in body["assignees"] if a not in issue.assignees]
                return JSONResponse(_rest_issue(issue), status_code=201)

        return app

    def _checks_on(self, ref: str) -> str | None:
        with self._lock:
            pulls = [p for p in self._visible().pulls.values() if p.head == ref]
        return pulls[-1].checks if pulls else None

    def _conditional(self, request: Request, body: Any) -> Response:
        """`body` with an ETag, or a refusal or `304` as GitHub would give instead."""
        with self._lock:
            refusal = self._refusals.pop(0) if self._refusals else None
            if any(request.url.path.endswith(path) for path in self._forbidden):
                refusal = Refusal(403, message="Resource not accessible by personal access token")
            interval = self.poll_interval
        if refusal is not None:
            return JSONResponse(
                {"message": refusal.message},
                status_code=refusal.status,
                headers=refusal.headers,
            )
        headers = {"ETag": 'W/"' + hashlib.sha1(json.dumps(body).encode()).hexdigest() + '"'}
        if interval is not None:
            headers["X-Poll-Interval"] = str(interval)
        if request.headers.get("if-none-match") == headers["ETag"]:
            return Response(status_code=304, headers=headers)
        return JSONResponse(body, headers=headers)

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


def _check_run(state: str) -> dict[str, Any]:
    if state in ("PENDING", "EXPECTED"):
        return {"status": "in_progress", "conclusion": None}
    return {"status": "completed", "conclusion": "success" if state == "SUCCESS" else "failure"}


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

    return _Node("Repository", {"issue": issue, "defaultBranchRef": _Node("Ref", {"name": "main"})})


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
            "headRefOid": pull.head_commit,
            "baseRefName": pull.base,
            "isDraft": pull.draft,
            "state": pull.state,
            "merged": pull.state == "MERGED",
            "reviewDecision": pull.review,
            "statusCheckRollup": _Node("StatusCheckRollup", {"state": pull.checks})
            if pull.checks
            else None,
            "mergeCommit": _Node("Commit", {"oid": pull.merge_commit})
            if pull.merge_commit
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
