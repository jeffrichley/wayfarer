"""The React app at every path that is not the API; included after every other router,
since its catch-alls must match only what nothing else does."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

__all__ = ["include"]

# Built into the package by the hatch build hook (`hatch_build.py`), so the wheel
# carries it and a user needs no Node toolchain (ADR-0004).
_STATIC = Path(str(files("wayfarer") / "static"))
_INDEX = _STATIC / "index.html"

_NOT_BUILT = """\
<!doctype html>
<title>Wayfarer</title>
<p>The front end has not been built. Run <code>pnpm build</code> in <code>web/</code>,
or develop against the Vite dev server with <code>pnpm dev</code>.</p>
"""

router = APIRouter()


# A mistyped API path is an error, not the page.
@router.get("/api/{path:path}", include_in_schema=False)
async def no_such_api(path: str) -> None:
    raise HTTPException(status_code=404)


# Every path that is not the API is the single-page app, which routes itself.
@router.get("/{path:path}", include_in_schema=False, response_model=None)
async def page(path: str) -> FileResponse | HTMLResponse:
    if _INDEX.is_file():
        return FileResponse(_INDEX)
    return HTMLResponse(_NOT_BUILT)


def include(app: FastAPI) -> None:
    """Serve the page's assets and then the page, behind every route already included."""
    if (_STATIC / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=_STATIC / "assets"), name="assets")
    app.include_router(router)
