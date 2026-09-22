"""The HTTP surface: the JSON API under `/api`, and the React app at every other path."""

from __future__ import annotations

from importlib.metadata import version
from importlib.resources import files
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from wayfarer.models import Health

__all__ = ["create_app"]

# Built into the package by the hatch build hook (`hatch_build.py`), so the wheel
# carries it and a user needs no Node toolchain (ADR-0004).
_STATIC = Path(str(files("wayfarer") / "static"))

_NOT_BUILT = """\
<!doctype html>
<title>Wayfarer</title>
<p>The front end has not been built. Run <code>pnpm build</code> in <code>web/</code>,
or develop against the Vite dev server with <code>pnpm dev</code>.</p>
"""


def create_app() -> FastAPI:
    app = FastAPI(title="Wayfarer", version=version("wayfarer"))

    @app.get("/api/health")
    def health() -> Health:
        return Health(version=version("wayfarer"))

    # A mistyped API path is an error, not the page.
    @app.get("/api/{path:path}", include_in_schema=False)
    def no_such_api(path: str) -> None:
        raise HTTPException(status_code=404)

    index = _STATIC / "index.html"
    if (_STATIC / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=_STATIC / "assets"), name="assets")

    # Every path that is not the API is the single-page app, which routes itself.
    @app.get("/{path:path}", include_in_schema=False, response_model=None)
    def page(path: str) -> FileResponse | HTMLResponse:
        if index.is_file():
            return FileResponse(index)
        return HTMLResponse(_NOT_BUILT)

    return app
