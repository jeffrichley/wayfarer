"""The browser's types are generated from the schema, so every shape must reach it."""

from __future__ import annotations

import inspect
import json
import pkgutil
import subprocess
import sys
from enum import Enum
from importlib import import_module

import pytest
from pydantic import BaseModel

from wayfarer import models

pytestmark = pytest.mark.unit


def _shapes() -> dict[str, type]:
    """Every model and enum defined in any area module of `wayfarer.models`."""
    shapes: dict[str, type] = {}
    for area in pkgutil.iter_modules(models.__path__, f"{models.__name__}."):
        module = import_module(area.name)
        for name, value in vars(module).items():
            if (
                inspect.isclass(value)
                and issubclass(value, BaseModel | Enum)
                and value.__module__ == module.__name__
            ):
                shapes[name] = value
    return shapes


def test_every_model_the_browser_sees_is_in_the_schema_its_types_come_from() -> None:
    printed = subprocess.run(
        [sys.executable, "-m", "wayfarer.schema"], capture_output=True, text=True, check=True
    )

    schemas = json.loads(printed.stdout)["components"]["schemas"]

    assert set(_shapes()) <= set(schemas)


def test_every_model_the_browser_sees_is_reachable_from_the_models_package() -> None:
    assert {name: getattr(models, name, None) for name in _shapes()} == _shapes()
