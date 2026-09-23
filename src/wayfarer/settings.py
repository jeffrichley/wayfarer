"""Every bound and default Wayfarer runs with, named in one place.

Credentials come only from the environment Wayfarer was launched in, and are
never stored.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_dir

__all__ = ["Settings"]

# The per-user data directory, by each platform's own convention.
_DATA_DIR = Path(user_data_dir("wayfarer"))


@dataclass(frozen=True)
class Settings:
    port: int = 7431
    """The port Wayfarer tries first, falling back to any free one when it is taken.
    The Vite dev server proxies the API here (web/vite.config.ts). `WAYFARER_PORT`
    changes it, and 0 asks for whatever port is free."""
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
    docker_timeout: float = 10.0
    """Seconds the start gate waits for the Docker daemon to answer. One that has not
    answered by then is as good as down, and a wedged one must not hang every start."""
    cap: int = 3
    """How many sessions may run at once, one number shared by every armed cascade on
    the repo, so the machine stays usable. Per repo, default 3."""
    auto_merge: bool = True
    """Whether a ready, green PR lands without a person's approval. Per repo, default on."""
    stream_backlog: int = 1000
    """Changes kept for a page that reconnects. One that missed more is sent a snapshot
    instead, which costs it nothing but bytes, so this only bounds memory."""
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

    data_dir: Path = _DATA_DIR
    """Where each repo's store and its sessions' event files live, outside any checkout.
    `WAYFARER_DATA_DIR` moves it."""
    session_silence: float = 20 * 60.0
    """Seconds a session's agent may print nothing before it is stopped. Long, because a
    long test run prints nothing."""
    session_wall: float = 2 * 60 * 60.0
    """Seconds a session's agent may run in all before it is stopped."""
    stage_timeout: float = 10 * 60.0
    """Seconds each of a session's workspace, sandbox, collect and integrate stages may
    take, which only a hang would reach. Every Waystation bound is unbounded unless set."""

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        return cls(
            port=int(env.get("WAYFARER_PORT", cls.port)),
            github_api=env.get("WAYFARER_GITHUB_API", cls.github_api),
            github_token=env.get("GH_TOKEN") or env.get("GITHUB_TOKEN") or None,
            poll_active=float(env.get("WAYFARER_POLL_ACTIVE", cls.poll_active)),
            poll_idle=float(env.get("WAYFARER_POLL_IDLE", cls.poll_idle)),
            rate_limit_backoff=float(
                env.get("WAYFARER_RATE_LIMIT_BACKOFF", cls.rate_limit_backoff)
            ),
            data_dir=Path(env.get("WAYFARER_DATA_DIR") or cls.data_dir),
        )
