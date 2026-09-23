"""A write by Wayfarer is followed at once by a read of what it wrote (ADR-0003).

Nothing on the HTTP surface writes to GitHub yet; the cascade's claim is the
first command that will. Until then this holds the promise on the GitHub client
itself, against the stand-in, with no poll running: only the write can wake the
watch.
"""

from __future__ import annotations

import asyncio

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
        effort = await read_effort(client, spec.number, per_page=50, auto_merge=True)
        return effort.tickets[0].assignees

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
