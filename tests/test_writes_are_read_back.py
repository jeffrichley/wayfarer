"""A write by Wayfarer is followed at once by a read of what it wrote (ADR-0003).

The cascade's claim is read back before its session is submitted
(`test_the_cascade.py`). This holds the promise on the GitHub client itself,
against the stand-in, with no poll running: only the write can wake the watch.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from github_stand_in import TOKEN, GitHub
from wayfarer.github import GitHub as Client
from wayfarer.github import GitHubError, Repo
from wayfarer.read_model import read_effort
from wayfarer.settings import Settings

pytestmark = pytest.mark.unit


def _client(github: GitHub, token: str = TOKEN) -> Client:
    return Client(
        Repo(github.owner, github.name), Settings(github_api=github.api, github_token=token)
    )


def test_a_claim_by_wayfarer_is_read_back_straight_away(github: GitHub) -> None:
    spec, (ticket,) = github.effort("Claimed", tickets=1)
    client = _client(github)

    async def claim_and_read_back() -> list[str]:
        with client.freshness.watch() as watch:
            await client.write(
                "POST", f"/issues/{ticket.number}/assignees", {"assignees": ["wayfarer"]}
            )
            await asyncio.wait_for(watch.changed(), timeout=1.0)
        _, tickets = await read_effort(client, spec.number, per_page=50, auto_merge=True)
        return tickets[0].assignees

    assert asyncio.run(claim_and_read_back()) == ["wayfarer"]


def test_a_refused_write_is_still_read_back_since_it_may_have_landed(github: GitHub) -> None:
    _, (ticket,) = github.effort("Refused", tickets=1)
    client = _client(github, token="revoked")

    async def refused() -> None:
        with client.freshness.watch() as watch:
            with pytest.raises(GitHubError, match="Bad credentials"):
                await client.write(
                    "POST", f"/issues/{ticket.number}/assignees", {"assignees": ["wayfarer"]}
                )
            await asyncio.wait_for(watch.changed(), timeout=1.0)

    asyncio.run(refused())


async def _refused_on_cancel(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> Any:
    """A connect that anyio, cancelled mid-attempt, reports as a failed connect."""
    try:
        await asyncio.sleep(60)
    except asyncio.CancelledError:
        raise httpx.ConnectError("All connection attempts failed") from None


async def _answered_on_cancel(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> Any:
    """A request whose cancel anyio absorbed, so it answers after all."""
    try:
        await asyncio.sleep(60)
    except asyncio.CancelledError:
        return httpx.Response(200, json={})


@pytest.mark.parametrize("swallowing", [_refused_on_cancel, _answered_on_cancel])
def test_a_cancelled_request_is_cancelled_even_when_the_http_library_swallows_it(
    github: GitHub, monkeypatch: pytest.MonkeyPatch, swallowing: Any
) -> None:
    # Otherwise the poll reads it as a failed round, carries on, and stopping the
    # app waits on it forever.
    monkeypatch.setattr(httpx.AsyncClient, "request", swallowing)
    client = _client(github)

    async def cancelled_mid_request() -> None:
        request = asyncio.create_task(client.conditional("/issues", None))
        await asyncio.sleep(0.05)
        request.cancel()
        await request

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(cancelled_mid_request())
