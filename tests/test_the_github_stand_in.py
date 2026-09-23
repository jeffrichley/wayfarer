"""The stand-in keeps the promises later tickets test against (`github_stand_in.py`).

The conditional poll is not built yet, so its half of the stand-in, the ETag'd
issue listing, is held here directly rather than through Wayfarer.
"""

from __future__ import annotations

import httpx
import pytest

from github_stand_in import GitHub

pytestmark = pytest.mark.unit


def _listing(github: GitHub, etag: str | None = None) -> httpx.Response:
    headers = {"If-None-Match": etag} if etag else {}
    return httpx.get(f"{github.api}/repos/octo/widgets/issues", headers=headers, timeout=5.0)


def test_an_unchanged_listing_answers_not_modified(github: GitHub) -> None:
    github.issue("Something")
    first = _listing(github)

    again = _listing(github, first.headers["ETag"])

    assert again.status_code == 304


def test_a_poke_changes_the_listing_and_its_etag(github: GitHub) -> None:
    issue = github.issue("Something")
    first = _listing(github)

    issue.labels.append("wayfarer:held")
    again = _listing(github, first.headers["ETag"])

    assert again.status_code == 200
    assert again.json()[0]["labels"] == [{"name": "wayfarer:held"}]


def test_a_stale_listing_stays_unchanged_while_github_moves_on(github: GitHub) -> None:
    issue = github.issue("Something")
    first = _listing(github)

    with github.stale():
        github.close(issue)
        assert _listing(github, first.headers["ETag"]).status_code == 304

    assert _listing(github, first.headers["ETag"]).status_code == 200
