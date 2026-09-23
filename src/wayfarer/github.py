"""Talking to GitHub: which repo the clone is, and GraphQL reads of it.

GitHub is the record (ADR-0002). This module only moves bytes; what they mean is
the read model's business (`read_model.py`).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from wayfarer.settings import Settings

__all__ = ["GitHub", "GitHubError", "NoSuchIssue", "NotConnected", "Repo", "repo_of"]

# `https://github.com/o/r.git`, `git@github.com:o/r.git`, `ssh://git@github.com/o/r`.
_REMOTE = re.compile(r"[:/](?P<owner>[^/:]+)/(?P<name>[^/]+?)(?:\.git)?/?$")


class NotConnected(Exception):
    """Wayfarer has no way to read GitHub: no GitHub remote, or no token."""


class NoSuchIssue(Exception):
    """The repo has no issue with that number."""


class GitHubError(Exception):
    """GitHub refused a read, or could not be reached."""


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


class GitHub:
    """GraphQL reads of one repo, authenticated as the person who launched Wayfarer."""

    def __init__(self, repo: Repo | None, settings: Settings) -> None:
        self.repo = repo
        self._settings = settings

    async def query(self, document: str, **variables: Any) -> dict[str, Any]:
        """The `repository` field of `document`, run with `owner` and `name` filled in."""
        if self.repo is None:
            raise NotConnected("This clone has no GitHub remote named origin.")
        if self._settings.github_token is None:
            raise NotConnected("No GitHub token: set GH_TOKEN or GITHUB_TOKEN.")
        try:
            async with httpx.AsyncClient(timeout=self._settings.github_timeout) as client:
                response = await client.post(
                    f"{self._settings.github_api}/graphql",
                    headers={"Authorization": f"bearer {self._settings.github_token}"},
                    json={
                        "query": document,
                        "variables": {
                            "owner": self.repo.owner,
                            "name": self.repo.name,
                            **variables,
                        },
                    },
                )
        except httpx.HTTPError as error:
            raise GitHubError(f"GitHub could not be reached: {error}") from error
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


def _only_not_found(errors: list[dict[str, Any]]) -> bool:
    return all(error.get("type") == "NOT_FOUND" for error in errors)
