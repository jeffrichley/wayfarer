"""The HTTP surface: the JSON API under `/api`, and the React app at every other path."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterable, AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.sse import EventSourceResponse
from fastapi.staticfiles import StaticFiles

from wayfarer.gate import StartGate
from wayfarer.github import GitHub, GitHubError, NoSuchIssue, NotConnected
from wayfarer.image import Build, Images, NoLayer
from wayfarer.models import BuildEvent, Effort, GateStatus, Health, ImageStatus
from wayfarer.poll import poll
from wayfarer.read_model import read_effort
from wayfarer.settings import Settings

__all__ = ["create_app"]

_log = logging.getLogger(__name__)

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


def _report_death(task: asyncio.Task[None]) -> None:
    """A poll that died leaves every page stale while it still serves, so say so."""
    if not task.cancelled() and task.exception() is not None:
        _log.error("The poll of GitHub stopped; pages will not refresh.", exc_info=task.exception())


async def _read(app: FastAPI, number: int) -> Effort:
    """Effort `number` read afresh; nothing is kept between reads (ADR-0002)."""
    github: GitHub = app.state.github
    settings: Settings = app.state.settings
    try:
        return await read_effort(
            github, number, per_page=settings.tickets_per_page, auto_merge=settings.auto_merge
        )
    except NotConnected as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except NoSuchIssue as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except GitHubError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


async def _first_read(request: Request, number: int) -> tuple[int, Effort]:
    # A dependency, so an effort that cannot be read is an error before its stream
    # starts. The signal's count is taken first, so a change during the read is
    # not missed by the watch that follows it.
    github: GitHub = request.app.state.github
    seen = github.freshness.version
    return seen, await _read(request.app, number)


FirstRead = Annotated[tuple[int, Effort], Depends(_first_read)]


def create_app(
    repo: Path, settings: Settings | None = None, github: GitHub | None = None
) -> FastAPI:
    """The app for the clone whose working tree is `repo`, reading GitHub through
    `github`; without one, every read of GitHub says so."""
    settings = settings or Settings()
    github = github or GitHub(None, settings)
    running = version("wayfarer")

    # The poll runs for as long as the app serves, on the same loop (ADR-0001).
    @asynccontextmanager
    async def polling(app: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(poll(github, settings))
        task.add_done_callback(_report_death)
        yield
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    app = FastAPI(title="Wayfarer", version=running, lifespan=polling)
    images = Images(repo)
    app.state.images = images
    app.state.github = github
    app.state.settings = settings
    gate = StartGate(repo, images, settings)

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
        return await _read(app, number)

    # The effort now, then again each time a re-read finds it changed (ADR-0003).
    # An open stream is an open page, which keeps the poll at the open rhythm and
    # has the checks of each PR it shows polled. It streams on its own until the
    # page's one stream lands (#31), which then carries it (ADR-0004).
    @app.get("/api/efforts/{number}/stream", response_class=EventSourceResponse)
    async def effort_stream(number: int, first: FirstRead) -> AsyncIterable[Effort]:
        seen, effort = first
        with github.freshness.watch(seen) as watch:
            last: Effort | None = None
            while True:
                if effort != last:
                    yield effort
                    last = effort
                watch.awaiting = frozenset(
                    ticket.pull_request.branch
                    for ticket in effort.tickets
                    if ticket.pull_request is not None and not ticket.pull_request.merged
                )
                await watch.changed()
                try:
                    effort = await _read(app, number)
                except HTTPException:
                    # The page reconnects, and its first read reports the failure.
                    return

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

    @app.get("/api/gate")
    async def start_gate() -> GateStatus:
        return await gate.status()

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
