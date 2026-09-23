"""The HTTP surface: the JSON API under `/api`, and the React app at every other path."""

from __future__ import annotations

from collections.abc import AsyncIterable
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.sse import EventSourceResponse
from fastapi.staticfiles import StaticFiles

from wayfarer.github import GitHub, GitHubError, NoSuchIssue, NotConnected
from wayfarer.image import Build, Images, NoLayer
from wayfarer.models import BuildEvent, Effort, Health, ImageStatus
from wayfarer.read_model import read_effort
from wayfarer.settings import Settings

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


async def _last_build(request: Request) -> Build:
    # A dependency, so a missing build is a 404 before its stream starts.
    images: Images = request.app.state.images
    if images.last_build is None:
        raise HTTPException(status_code=404, detail="No build has been asked for.")
    return images.last_build


LastBuild = Annotated[Build, Depends(_last_build)]


def create_app(
    repo: Path, settings: Settings | None = None, github: GitHub | None = None
) -> FastAPI:
    """The app for the clone whose working tree is `repo`, reading GitHub through
    `github`; without one, every read of GitHub says so."""
    settings = settings or Settings()
    github = github or GitHub(None, settings)
    running = version("wayfarer")
    app = FastAPI(title="Wayfarer", version=running)
    images = Images(repo)
    app.state.images = images

    # Handlers are async so they run on the loop every agent run shares (ADR-0001),
    # not in a thread pool beside it.
    @app.get("/api/health")
    async def health() -> Health:
        return Health(version=running)

    # Read afresh on every ask; nothing is kept between reads (ADR-0002). A plain
    # GET until the SSE stream exists (#31), which then carries this as its
    # snapshot, the only way data reaches the browser (ADR-0004).
    @app.get("/api/efforts/{number}")
    async def effort(number: int) -> Effort:
        try:
            return await read_effort(
                github,
                number,
                per_page=settings.tickets_per_page,
                auto_merge=settings.auto_merge,
            )
        except NotConnected as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except NoSuchIssue as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except GitHubError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @app.get("/api/image")
    async def image() -> ImageStatus:
        return await images.status()

    @app.post("/api/image/build", status_code=202, responses={409: {"description": "No layer"}})
    async def build_image() -> None:
        """Build the session image. Builds happen only here, when a person clicks."""
        try:
            images.build()
        except NoLayer as refusal:
            raise HTTPException(status_code=409, detail=str(refusal)) from None

    # The build's output, from its first line. Until the page's one stream lands
    # (#31), a build streams on its own (ADR-0004).
    @app.get("/api/image/build", response_class=EventSourceResponse)
    async def build_output(
        build: LastBuild,
    ) -> AsyncIterable[BuildEvent]:
        async for event in build.events():
            yield event

    # A mistyped API path is an error, not the page.
    @app.get("/api/{path:path}", include_in_schema=False)
    async def no_such_api(path: str) -> None:
        raise HTTPException(status_code=404)

    index = _STATIC / "index.html"
    if (_STATIC / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=_STATIC / "assets"), name="assets")

    # Every path that is not the API is the single-page app, which routes itself.
    @app.get("/{path:path}", include_in_schema=False, response_model=None)
    async def page(path: str) -> FileResponse | HTMLResponse:
        if index.is_file():
            return FileResponse(index)
        return HTMLResponse(_NOT_BUILT)

    return app
