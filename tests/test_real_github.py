"""The stand-in's GraphQL is a subset of GitHub's; this holds the read to the real one.

Spends real rate budget with the token `gh` is logged in with, so it is `live`
and never runs by default or in CI: `uv run pytest -m live`.
"""

from __future__ import annotations

import subprocess

import httpx
import pytest

from wayfarer.read_model import _EFFORT
from wayfarer.settings import Settings

pytestmark = pytest.mark.live

# Wayfarer's own first slice: a spec issue with over thirty sub-issues.
_OWNER, _NAME, _EFFORT_NUMBER = "jeffrichley", "wayfarer", 27


def test_the_read_holds_against_real_github_within_its_point_budget() -> None:
    token = subprocess.run(
        ["gh", "auth", "token"], capture_output=True, text=True, check=True
    ).stdout.strip()
    priced = _EFFORT.replace("repository(", "rateLimit { cost } repository(", 1)

    response = httpx.post(
        "https://api.github.com/graphql",
        headers={"Authorization": f"bearer {token}"},
        json={
            "query": priced,
            "variables": {
                "owner": _OWNER,
                "name": _NAME,
                "effort": _EFFORT_NUMBER,
                "perPage": Settings().tickets_per_page,
            },
        },
        timeout=Settings().github_timeout,
    )

    body = response.json()
    assert "errors" not in body, body["errors"]
    assert len(body["data"]["repository"]["issue"]["subIssues"]["nodes"]) >= 30
    assert body["data"]["rateLimit"]["cost"] <= 3
