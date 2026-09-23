"""Talking to GitHub: which repo the clone is, GraphQL reads of it, and REST.

GitHub is the record (ADR-0002). This module only moves bytes; what they mean is
the read model's business (`read_model.py`). Every write it makes raises the
signal to re-read (ADR-0003), so what Wayfarer wrote is read straight back.
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
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

    def _connected(self) -> tuple[Repo, dict[str, str]]:
        if self.repo is None:
            raise NotConnected("This clone has no GitHub remote named origin.")
        if self._settings.github_token is None:
            raise NotConnected("No GitHub token: set GH_TOKEN or GITHUB_TOKEN.")
        return self.repo, {"Authorization": f"bearer {self._settings.github_token}"}

    async def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=self._settings.github_timeout) as client:
                return await client.request(method, f"{self._settings.github_api}{path}", **kwargs)
        except httpx.HTTPError as error:
            raise GitHubError(f"GitHub could not be reached: {error}") from error

    async def query(self, document: str, **variables: Any) -> dict[str, Any]:
        """The `repository` field of `document`, run with `owner` and `name` filled in."""
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
        return repository

    async def conditional(
        self, path: str, etag: str | None, params: dict[str, str] | None = None
    ) -> Answer:
        """Whether the repo's REST `path` differs from the answer that carried `etag`.

        GitHub states a `304` "does not count against your primary rate limit", so
        asking about something unchanged costs nothing (ADR-0003).
        """
        repo, auth = self._connected()
        headers = auth | ({"If-None-Match": etag} if etag else {})
        response = await self._send(
            "GET", f"/repos/{repo.owner}/{repo.name}{path}", headers=headers, params=params
        )
        if response.status_code in (403, 429):
            raise RateLimited(response.status_code, _asked_wait(response.headers))
        if response.status_code not in (200, 304):
            raise GitHubError(f"GitHub refused the read ({response.status_code}): {response.text}")
        return Answer(
            changed=response.status_code == 200,
            etag=response.headers.get("ETag", etag),
            poll_interval=float(response.headers.get("X-Poll-Interval", 0)),
        )

    async def write(self, method: str, path: str, body: dict[str, Any]) -> Any:
        """Send one REST write to the repo's `path`, and return what GitHub answered.

        Whatever comes back, the write may have landed, so the signal to re-read
        is raised either way (ADR-0003). Nothing it returns is believed as state.
        """
        repo, auth = self._connected()
        try:
            response = await self._send(
                method, f"/repos/{repo.owner}/{repo.name}{path}", headers=auth, json=body
            )
        finally:
            self.freshness.poke()
        if response.is_error:
            raise GitHubError(f"GitHub refused the write ({response.status_code}): {response.text}")
        return response.json()


def _asked_wait(headers: httpx.Headers) -> float | None:
    """How long GitHub asked for, by its documented rate-limit headers.

    https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api#handle-rate-limit-errors-appropriately
    """
    if "Retry-After" in headers:
        return float(headers["Retry-After"])
    if headers.get("X-RateLimit-Remaining") == "0" and "X-RateLimit-Reset" in headers:
        return max(0.0, float(headers["X-RateLimit-Reset"]) - time.time())
    return None


def _only_not_found(errors: list[dict[str, Any]]) -> bool:
    return all(error.get("type") == "NOT_FOUND" for error in errors)
