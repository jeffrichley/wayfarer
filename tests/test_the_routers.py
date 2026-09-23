"""Each feature's routes live in their own module, so two tickets adding endpoints
touch different files, and `create_app` only builds services and includes them."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute

import wayfarer.routes
from wayfarer import app
from wayfarer.app import create_app

pytestmark = pytest.mark.unit


def _router_modules() -> list[str]:
    return [found.name for found in pkgutil.iter_modules(wayfarer.routes.__path__)]


def _declared_in_routers() -> set[tuple[str, str]]:
    declared: set[tuple[str, str]] = set()
    for name in _router_modules():
        module = importlib.import_module(f"wayfarer.routes.{name}")
        for route in module.router.routes:
            if isinstance(route, APIRoute) and route.include_in_schema:
                declared |= {(route.path, method.lower()) for method in route.methods or ()}
    return declared


def test_every_endpoint_the_app_serves_is_declared_in_a_router_module(tmp_path: Path) -> None:
    served = {
        (path, method)
        for path, operations in create_app(tmp_path).openapi()["paths"].items()
        for method in operations
    }

    assert served == _declared_in_routers()
    assert not re.search(r"@app\.(get|post|put|patch|delete|api_route)\(", inspect.getsource(app))


def test_routers_are_included_one_sorted_line_each_with_the_page_last() -> None:
    # Sorted, so two tickets adding a router insert at different lines instead of
    # both appending at the end; the page's catch-alls must match only what no
    # other route does, so it comes after them all.
    source = inspect.getsource(app)
    included = re.findall(r"app\.include_router\((\w+)_routes\.router\)", source)

    assert included == sorted(included)
    assert set(included) == set(_router_modules()) - {"page"}
    assert source.rindex("page.include(app)") > source.rindex("app.include_router(")
