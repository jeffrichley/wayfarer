"""The conditional poll: the one outside source of the signal to re-read (ADR-0003).

Each round asks GitHub whether the repo's issues changed, carrying the ETag of its
last answer, and then asks the same of every awaited pull request's checks, since
checks never change the issue the listing shows. A `304` changes nothing and
costs nothing; any other answer only pokes, and is never read as data.

Rounds come every `poll_active` seconds while something watches and every
`poll_idle` otherwise, never faster than GitHub's `X-Poll-Interval`, and a rate
limit holds the next round off for as long as GitHub asked or, when it did not
say, for a backoff that doubles with each refusal in a row.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from wayfarer.github import GitHub, GitHubError, NotConnected, RateLimited, ref
from wayfarer.settings import Settings

__all__ = ["poll"]

_log = logging.getLogger(__name__)


async def poll(github: GitHub, settings: Settings) -> None:
    """Poll until cancelled. Returns at once when there is no GitHub to poll."""
    await _Poll(github, settings).run()


class _Poll:
    def __init__(self, github: GitHub, settings: Settings) -> None:
        self._github = github
        self._settings = settings
        self._etags: dict[str, str | None] = {}
        self._refusals = 0
        # Fixed for the life of the poll: a new `since` is a new URL, whose first
        # answer is never a `304`.
        self._listing = {
            "state": "all",
            "sort": "updated",
            "direction": "desc",
            "since": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            # Any update puts an issue first, so one is enough to see a change.
            "per_page": "1",
        }

    async def run(self) -> None:
        while True:
            started = time.monotonic()
            try:
                floor = await self._round()
                self._refusals = 0
            except NotConnected:
                return
            except RateLimited as refusal:
                floor = self._back_off(refusal)
            await self._rest(started, floor)

    async def _round(self) -> float:
        """Ask about the issues and every awaited PR; the slowest rhythm GitHub asked for."""
        paths = ["/issues"] + [
            f"/commits/{ref(branch)}/{checks}"
            for branch in sorted(self._github.freshness.awaited)
            # Check runs from Actions and apps, and the statuses older CI posts.
            for checks in ("check-runs", "status")
        ]
        # Forget PRs no longer awaited, so one awaited again starts afresh.
        self._etags = {path: self._etags.get(path) for path in paths}
        floor = 0.0
        for path in paths:
            try:
                answer = await self._github.conditional(
                    path,
                    self._etags[path],
                    self._listing if path == "/issues" else None,
                )
            except RateLimited:
                raise
            except GitHubError as error:
                # One path refused, such as checks a token may not read, holds up
                # no other; it is asked again next round.
                _log.warning("The poll of GitHub failed, and will try again: %s", error)
                continue
            self._etags[path] = answer.etag
            floor = max(floor, answer.poll_interval)
            # A first answer pokes too: a watch that read before it may have missed
            # a change that only this answer's ETag now hides.
            if answer.changed:
                self._github.freshness.poke()
        return floor

    def _back_off(self, refusal: RateLimited) -> float:
        self._refusals += 1
        if refusal.wait is not None:
            return refusal.wait
        doubled = self._settings.rate_limit_backoff * 2.0 ** (self._refusals - 1)
        return min(doubled, self._settings.rate_limit_backoff_max)

    async def _rest(self, since: float, floor: float) -> None:
        """Wait out the rhythm from `since`, but at least `floor`.

        A watch starting or ending changes the rhythm, so it is re-read then, and a
        page opened on an idle Wayfarer does not wait out the idle rhythm.
        """
        freshness = self._github.freshness
        while True:
            rhythm = self._settings.poll_active if freshness.watched else self._settings.poll_idle
            remaining = since + max(rhythm, floor) - time.monotonic()
            if remaining <= 0:
                return
            await freshness.attention_changed(remaining)
