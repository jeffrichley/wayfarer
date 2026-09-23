"""The store: one file per repo, outside the checkout."""

from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest

from wayfarer.github import Repo
from wayfarer.store import Purpose, Store

pytestmark = pytest.mark.unit


def test_each_repo_keeps_its_own_sessions_under_its_owner_and_name(tmp_path: Path) -> None:
    with (
        closing(Store.for_repo(tmp_path, Repo("octo", "widgets"))) as widgets,
        closing(Store.for_repo(tmp_path, Repo("octo", "gadgets"))) as gadgets,
    ):
        widgets.session_started("a1", 7, Purpose.BUILD, datetime.now(UTC), tmp_path / "a1.jsonl")

        assert widgets.directory == tmp_path / "octo" / "widgets"
        assert [row.run_id for row in widgets.sessions()] == ["a1"]
        assert gadgets.sessions() == []


def test_a_session_recorded_survives_the_store_being_opened_again(tmp_path: Path) -> None:
    with closing(Store.open(tmp_path)) as first:
        first.session_started("a1", 7, Purpose.BUILD, datetime.now(UTC), tmp_path / "a1.jsonl")

    with closing(Store.open(tmp_path)) as again:
        [row] = again.sessions()

    assert (row.run_id, row.ticket, row.ended) == ("a1", 7, None)
