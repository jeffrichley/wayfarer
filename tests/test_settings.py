"""Settings read from the environment Wayfarer was launched in."""

from __future__ import annotations

import pytest

from wayfarer.settings import Settings

pytestmark = pytest.mark.unit


def test_unset_it_tries_port_7431_first_where_the_dev_server_proxies() -> None:
    assert Settings.from_env({}).port == 7431
