"""The browser's types are generated from the schema, so every shape must reach it."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from wayfarer import models

pytestmark = pytest.mark.unit


def test_every_model_the_browser_sees_is_in_the_schema_its_types_come_from() -> None:
    printed = subprocess.run(
        [sys.executable, "-m", "wayfarer.schema"], capture_output=True, text=True, check=True
    )

    schemas = json.loads(printed.stdout)["components"]["schemas"]

    assert set(models.__all__) <= set(schemas)
