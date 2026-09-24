"""Talking to GitHub: which repo the clone is, GraphQL reads of it, and REST.

GitHub is the record (ADR-0002). This module only moves bytes; what they mean is
the read model's business (`read_model.py`). Every write it makes raises the
signal to re-read (ADR-0003), so what Wayfarer wrote is read straight back.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from wayfarer.freshness import Freshness
from wayfarer.settings import Settings

__all__ = [
    "Answer",
    "GitHub",
    "GitHubError",
    "NoSuchIssue",
    "NotConnected",
    "RateLimited",
    "Repo",
    "ref",
    "repo_of",
]

# `https://github.com/o/r.git`, `git@github.com:o/r.git`, `ssh://git@github.com/o/r`.
_REMOTE = re.compile(r"[:/](?P<owner>[^/:]+)/(?P<name>[^/]+?)(?:\.git)?/?$")


class NotConnected(Exception):
    """Wayfarer has no way to read GitHub: no GitHub remote, or no token."""


class NoSuchIssue(Exception):
    """The repo has no issue with that number."""


class GitHubError(Exception):
    """GitHub refused a read, or could not be reached."""


class RateLimited(GitHubError):
    """GitHub turned a request away with `403` or `429`, and asks Wayfarer to wait."""

    def __init__(self, status: int, wait: float | None) -> None:
        super().__init__(f"GitHub is rate limiting Wayfarer ({status}).")
        self.wait = wait
        """Seconds GitHub asked for, or None when it did not say."""


@dataclass(frozen=True)
class Answer:
    """What a conditional read heard: whether anything changed, and how to ask next."""

    changed: bool
    etag: str | None
    poll_interval: float
    """Seconds GitHub asks between polls of this path; 0 when it does not say."""


@dataclass(frozen=True)
class Repo:
    owner: str
    name: str

    def __str__(self) -> str:
        return f"{self.owner}/{self.name}"


def repo_of(clone: Path) -> Repo | None:
    """The GitHub repo a clone was cloned from, read from its `origin` remote."""
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"], cwd=clone, capture_output=True, text=True
    )
    match = _REMOTE.search(result.stdout.strip()) if result.returncode == 0 else None
    return Repo(match["owner"], match["name"]) if match else None


def ref(branch: str) -> str:
    """A branch as a path segment. GitHub takes `ticket/7-x` encoded or bare."""
    return quote(branch, safe="")


class GitHub:
    """Reads and writes of one repo, authenticated as the person who launched Wayfarer."""

    def __init__(
        self, repo: Repo | None, settings: Settings, freshness: Freshness | None = None
    ) -> None:
        self.repo = repo
        self.freshness = freshness or Freshness()
        self._settings = settings
        self._login: str | None = None

    def _connected(self) -> tuple[Repo, dict[str, str]]:
        if self.repo is None:
            raise NotConnected("This clone has no GitHub remote named origin.")
        if self._settings.github_token is None:
            raise NotConnected("No GitHub token: set GH_TOKEN or GITHUB_TOKEN.")
        return self.repo, {"Authorization": f"bearer {self._settings.github_token}"}

    async def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=self._settings.github_timeout) as client:
                response = await client.request(
                    method, f"{self._settings.github_api}{path}", **kwargs
                )
        except httpx.HTTPError as error:
            _raise_if_cancelled(error)
            raise GitHubError(f"GitHub could not be reached: {error}") from error
        _raise_if_cancelled()
        return response

    async def login(self) -> str:
        """Who Wayfarer writes to GitHub as: the person whose token it holds."""
        if self._login is None:
            _, auth = self._connected()
            response = await self._send("GET", "/user", headers=auth)
            if response.status_code != 200:
                raise GitHubError(f"GitHub would not say whose token this is: {response.text}")
            self._login = str(response.json()["login"])
        return self._login

    async def query(self, document: str, **variables: Any) -> dict[str, Any]:
        """The `data` of `document`, run with `owner` and `name` filled in. Its
        `repository` is always there: a repo GitHub cannot find raises instead."""
        repo, auth = self._connected()
        response = await self._send(
            "POST",
            "/graphql",
            headers=auth,
            json={
                "query": document,
                "variables": {"owner": repo.owner, "name": repo.name, **variables},
            },
        )
        if response.status_code != 200:
            raise GitHubError(f"GitHub refused the read ({response.status_code}): {response.text}")
        body: dict[str, Any] = response.json()
        # GitHub reports a missing issue as an error beside a null field, so the
        # null is the fact and the error is only its explanation.
        repository: dict[str, Any] | None = (body.get("data") or {}).get("repository")
        if body.get("errors") and not _only_not_found(body["errors"]):
            raise GitHubError(f"GitHub refused the read: {body['errors']}")
        if repository is None:
            raise NoSuchIssue(f"{self.repo} was not found on GitHub.")
        data: dict[str, Any] = body["data"]
        return data

    async def conditional(
        self, path: str, etag: str | None, params: dict[str, str] | None = None
    ) -> Answer:
        """Whether the repo's REST `path` differs from the answer that carried `etag`.

        GitHub states a `304` "does not count against your primary rate limit", so
        asking about something unchanged costs nothing (ADR-0003).
        """
        headers = {"If-None-Match": etag} if etag else {}
        response = await self._rest("GET", path, headers=headers, params=params)
        _raise_if_refused(response, (200, 304))
        return Answer(
            changed=response.status_code == 200,
            etag=response.headers.get("ETag", etag),
            poll_interval=_seconds(response.headers.get("X-Poll-Interval")) or 0.0,
        )

    async def read(self, path: str, params: dict[str, str] | None = None) -> Any:
        """What GitHub answers one REST read of the repo's `path`, for what GraphQL does
        not carry, such as a pull request's patches."""
        response = await self._rest("GET", path, params=params)
        _raise_if_refused(response, (200,))
        return response.json()

    async def write(self, method: str, path: str, body: dict[str, Any]) -> Any:
        """Send one REST write to the repo's `path`, and return what GitHub answered.

        Whatever comes back, the write may have landed, so the signal to re-read
        is raised either way (ADR-0003). Nothing it returns is believed as state.
        """
        try:
            response = await self._rest(method, path, json=body)
        finally:
            self.freshness.poke()
        if response.is_error:
            raise GitHubError(f"GitHub refused the write ({response.status_code}): {response.text}")
        # Some writes, such as deleting a branch, answer `204 No Content`.
        return response.json() if response.content else None

    async def mutate(self, document: str, **variables: Any) -> dict[str, Any]:
        """Send one GraphQL write, for what REST cannot do, and return its `data`.

        As with `write`, the signal to re-read is raised whatever comes back
        (ADR-0003), and nothing it returns is believed as state.
        """
        _, auth = self._connected()
        try:
            response = await self._send(
                "POST", "/graphql", headers=auth, json={"query": document, "variables": variables}
            )
        finally:
            self.freshness.poke()
        body: dict[str, Any] = response.json() if response.status_code == 200 else {}
        if response.status_code != 200 or body.get("errors"):
            raise GitHubError(f"GitHub refused the write ({response.status_code}): {response.text}")
        data: dict[str, Any] = body["data"]
        return data

    async def _rest(
        self, method: str, path: str, headers: dict[str, str] | None = None, **kwargs: Any
    ) -> httpx.Response:
        repo, auth = self._connected()
        return await self._send(
            method,
            f"/repos/{repo.owner}/{repo.name}{path}",
            headers=auth | (headers or {}),
            **kwargs,
        )


def _raise_if_cancelled(cause: BaseException | None = None) -> None:
    """Raise the cancel a request swallowed.

    anyio reports a connect cancelled mid-attempt as a failed connect, and can
    absorb a cancel while it closes a connection, so a request may fail or even
    return after its task was cancelled. A cancel must still cancel, or whatever
    awaits the task, such as the app stopping, waits forever.
    """
    task = asyncio.current_task()
    if task is not None and task.cancelling():
        raise asyncio.CancelledError from cause


# GitHub's rules for its rate-limit responses:
# https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api#handle-rate-limit-errors-appropriately


def _raise_if_refused(response: httpx.Response, answers: tuple[int, ...]) -> None:
    """Raise unless a read was answered with one of `answers`."""
    if _rate_limited(response):
        raise RateLimited(response.status_code, _asked_wait(response.headers))
    if response.status_code not in answers:
        raise GitHubError(f"GitHub refused the read ({response.status_code}): {response.text}")


def _rate_limited(response: httpx.Response) -> bool:
    """A `429`, or a `403` that says it is a rate limit. Any other `403` is a
    permission GitHub withholds, which waiting will not fix."""
    if response.status_code == 429:
        return True
    return response.status_code == 403 and (
        "Retry-After" in response.headers
        or response.headers.get("X-RateLimit-Remaining") == "0"
        or "rate limit" in response.text.lower()
    )


def _asked_wait(headers: httpx.Headers) -> float | None:
    """How long GitHub asked for, or None when it did not say."""
    if "Retry-After" in headers:
        return _seconds(headers["Retry-After"])
    if headers.get("X-RateLimit-Remaining") == "0":
        reset = _seconds(headers.get("X-RateLimit-Reset"))
        return None if reset is None else max(0.0, reset - time.time())
    return None


def _seconds(value: str | None) -> float | None:
    """A header's seconds, or an HTTP date as seconds from now; None if neither."""
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        pass
    try:
        return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
    except (TypeError, ValueError):
        return None


def _only_not_found(errors: list[dict[str, Any]]) -> bool:
    return all(error.get("type") == "NOT_FOUND" for error in errors)
