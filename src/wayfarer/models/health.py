"""That the process is up."""

from __future__ import annotations

from pydantic import BaseModel

__all__ = [
    "Health",
]


class Health(BaseModel):
    """That the process is up, and which Wayfarer it is."""

    version: str
