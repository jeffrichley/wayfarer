"""Settings read from the environment Wayfarer was launched in."""

from __future__ import annotations

from pathlib import Path

import pytest
from platformdirs import user_data_dir

from wayfarer.settings import Settings

pytestmark = pytest.mark.unit


def test_unset_it_tries_port_7431_first_where_the_dev_server_proxies() -> None:
    assert Settings.from_env({}).port == 7431


def test_sessions_are_written_down_where_wayfarer_data_dir_says(tmp_path: Path) -> None:
    assert Settings.from_env({"WAYFARER_DATA_DIR": str(tmp_path)}).data_dir == tmp_path


def test_unset_sessions_are_written_down_outside_any_checkout() -> None:
    assert Settings.from_env({}).data_dir == Path(user_data_dir("wayfarer"))


def test_a_ready_green_pr_lands_unapproved_unless_wayfarer_auto_merge_is_off() -> None:
    assert Settings.from_env({}).auto_merge
    assert not Settings.from_env({"WAYFARER_AUTO_MERGE": "0"}).auto_merge
