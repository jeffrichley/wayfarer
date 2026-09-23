"""The stand-in's GraphQL is a subset of GitHub's; this holds the read to the real one.

Spends real rate budget with the token `gh` is logged in with, so it is `live`
and never runs by default or in CI: `uv run pytest -m live`.
"""

from __future__ import annotations

import asyncio
import subprocess
from typing import Any

import httpx
import pytest

from wayfarer.github import GitHub, Repo, ref
from wayfarer.merge_queue import _PULL, _PULL_ID, _READY, _TO_DRAFT
from wayfarer.read_model import _EFFORT
from wayfarer.settings import Settings

pytestmark = pytest.mark.live

# Wayfarer's own first slice: a spec issue with over thirty sub-issues.
_OWNER, _NAME, _EFFORT_NUMBER = "jeffrichley", "wayfarer", 27


def _token() -> str:
    return subprocess.run(
        ["gh", "auth", "token"], capture_output=True, text=True, check=True
    ).stdout.strip()


def test_the_read_holds_against_real_github_within_its_point_budget() -> None:
    token = _token()
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


def test_the_merge_queue_reads_when_pull_requests_became_ready_for_one_point() -> None:
    # Two of Wayfarer's own merged pull requests.
    aliases = "".join(_PULL % {"number": number} for number in (75, 76))
    priced = (_READY % aliases).replace("repository(", "rateLimit { cost } repository(", 1)

    response = httpx.post(
        "https://api.github.com/graphql",
        headers={"Authorization": f"bearer {_token()}"},
        json={"query": priced, "variables": {"owner": _OWNER, "name": _NAME}},
        timeout=Settings().github_timeout,
    )

    body = response.json()
    assert "errors" not in body, body["errors"]
    assert body["data"]["repository"]["pr75"]["createdAt"]
    assert body["data"]["rateLimit"]["cost"] <= 1


def test_holding_a_ticket_asks_real_github_for_its_pull_request_in_words_it_knows() -> None:
    def ask(document: str, **variables: object) -> dict[str, Any]:
        response = httpx.post(
            "https://api.github.com/graphql",
            headers={"Authorization": f"bearer {_token()}"},
            json={"query": document, "variables": variables},
            timeout=Settings().github_timeout,
        )
        body: dict[str, Any] = response.json()
        return body

    found = ask(_PULL_ID, owner=_OWNER, name=_NAME, number=75)
    assert "errors" not in found, found["errors"]
    assert found["data"]["repository"]["pullRequest"]["id"]
    # Asked of no pull request at all, so nothing is changed: the only error is that
    # there is no such node, which GitHub says only of a draft request it understood.
    drafted = ask(_TO_DRAFT, id="PR_no_such_pull_request")
    assert [error["type"] for error in drafted["errors"]] == ["NOT_FOUND"]


@pytest.mark.parametrize(
    "path",
    ["/issues", f"/commits/{ref('main')}/check-runs", f"/commits/{ref('main')}/status"],
)
def test_real_github_answers_the_polls_second_ask_with_not_modified(path: str) -> None:
    github = GitHub(Repo(_OWNER, _NAME), Settings(github_token=_token()))

    async def twice() -> tuple[bool, bool]:
        first = await github.conditional(path, None)
        again = await github.conditional(path, first.etag)
        return first.changed, again.changed

    assert asyncio.run(twice()) == (True, False)
