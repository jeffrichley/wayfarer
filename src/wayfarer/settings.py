"""Every bound and default Wayfarer runs with, named in one place.

Credentials come only from the environment Wayfarer was launched in, and are
never stored.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

__all__ = ["Settings"]


@dataclass(frozen=True)
class Settings:
    github_api: str = "https://api.github.com"
    """Where GitHub's API is. `WAYFARER_GITHUB_API` points it elsewhere, such as a stand-in."""
    github_token: str | None = None
    """The person's token, from `GH_TOKEN` or else `GITHUB_TOKEN`, as `gh` reads them."""
    github_timeout: float = 30.0
    """Seconds one request to GitHub may take before the read fails."""
    tickets_per_page: int = 50
    """Tickets read per GraphQL query. Each costs about (1 + 4 x this) / 100 points,
    so 50 keeps a thirty-ticket effort to one query of 2 points, inside the 3 its
    budget allows; 100 would cost 4 (ADR-0003)."""
    auto_merge: bool = True
    """Whether a ready, green PR lands without a person's approval. Per repo, default on."""
    poll_active: float = 10.0
    """Seconds between polls of GitHub while a cascade is armed or a page is open (ADR-0003)."""
    poll_idle: float = 60.0
    """Seconds between polls of GitHub when nothing is watching (ADR-0003)."""
    rate_limit_backoff: float = 60.0
    """Seconds the poll waits after GitHub refuses it without saying how long, doubled on
    each refusal in a row. GitHub asks for at least a minute before retrying."""
    rate_limit_backoff_max: float = 900.0
    """The longest that doubling may grow to, so a poll refused for a long spell still
    notices within a quarter of an hour once GitHub answers again."""

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        return cls(
            github_api=env.get("WAYFARER_GITHUB_API", cls.github_api),
            github_token=env.get("GH_TOKEN") or env.get("GITHUB_TOKEN") or None,
            poll_active=float(env.get("WAYFARER_POLL_ACTIVE", cls.poll_active)),
            poll_idle=float(env.get("WAYFARER_POLL_IDLE", cls.poll_idle)),
            rate_limit_backoff=float(
                env.get("WAYFARER_RATE_LIMIT_BACKOFF", cls.rate_limit_backoff)
            ),
        )
