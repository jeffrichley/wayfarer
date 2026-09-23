"""Every shape that crosses to the browser, defined once.

FastAPI publishes these as OpenAPI, and `web/src/api.gen.ts` is generated from
that schema (`pnpm gen:types`), so the browser's types never drift from these
(ADR-0004).
"""

from __future__ import annotations

from pydantic import BaseModel

__all__ = ["Health"]


class Health(BaseModel):
    """That the process is up, and which Wayfarer it is."""

    version: str
