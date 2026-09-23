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

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        return cls(
            github_api=env.get("WAYFARER_GITHUB_API", cls.github_api),
            github_token=env.get("GH_TOKEN") or env.get("GITHUB_TOKEN") or None,
        )
