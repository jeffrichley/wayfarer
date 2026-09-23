"""The HTTP surface: the JSON API under `/api`, and the React app at every other path."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterable, AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.sse import EventSourceResponse
from fastapi.staticfiles import StaticFiles

from wayfarer.cascade import Cascades, Gate, SessionsFor
from wayfarer.gate import StartGate
from wayfarer.github import GitHub
from wayfarer.image import Images
from wayfarer.models import Health, WireEvent
from wayfarer.poll import poll
from wayfarer.queue import Queue
from wayfarer.read_model import Efforts
from wayfarer.sessions import Sessions
from wayfarer.settings import Settings
from wayfarer.store import Store as Record
from wayfarer.stream import Store

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


def _report_death(task: asyncio.Task[None]) -> None:
    """A poll or a follow that died leaves every page stale while it still serves, so say so."""
    if not task.cancelled() and task.exception() is not None:
        _log.error(
            "Keeping up with GitHub stopped; pages will not refresh.", exc_info=task.exception()
        )


def create_app(
    repo: Path,
    settings: Settings | None = None,
    github: GitHub | None = None,
    store: Store | None = None,
    *,
    sessions: SessionsFor | None = None,
    gate: Gate | None = None,
) -> FastAPI:
    """The app for the clone whose working tree is `repo`, reading GitHub through
    `github`; without one, every read of GitHub says so. `store` is what the page's
    stream carries, which whoever runs the server closes as it stops.

    Sessions run Claude Code in the session image, admitted by the start gate
    (ADR-0005). `sessions` and `gate` replace both only for a test, which runs
    Waystation's scripted agent outside Docker; Wayfarer offers no way to do so.
    """
    settings = settings or Settings()
    github = github or GitHub(None, settings)
    store = store or Store(settings.stream_backlog)
    running = version("wayfarer")
    images = Images(repo, store)
    efforts = Efforts(github, store, settings)
    start_gate = StartGate(repo, images, settings)

    def in_image(record: Record) -> Sessions:
        # The gate admitted this start, so the repo is known and its image is built.
        tag = images.current()
        assert github.repo is not None and tag is not None
        return Sessions.in_image(repo, record, github.repo, tag, settings)

    queue = Queue(settings.cap)
    cascades = Cascades(
        efforts, github, store, settings, gate or start_gate, sessions or in_image, queue
    )

    # The poll, and the re-reads it sets off, run for as long as the app serves,
    # on the same loop (ADR-0001, ADR-0003). Stopping stops every session, each
    # keeping its work, as Ctrl-C does.
    @asynccontextmanager
    async def keeping_up(app: FastAPI) -> AsyncIterator[None]:
        tasks = [asyncio.create_task(poll(github, settings)), asyncio.create_task(efforts.follow())]
        for task in tasks:
            task.add_done_callback(_report_death)
        async with queue:
            yield
        for task in tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        cascades.close()

    app = FastAPI(title="Wayfarer", version=running, lifespan=keeping_up)
    # A command's work outlives its request, and asyncio keeps only a weak
    # reference to a task, so each is held here until it is done.
    working: set[asyncio.Task[None]] = set()

    def accept(work: Coroutine[None, None, None]) -> Response:
        """Start `work` and say only that it was accepted; its effect comes back over
        the stream like any other change (ADR-0004)."""
        task = asyncio.create_task(work)
        working.add(task)
        task.add_done_callback(working.discard)
        return Response(status_code=202)

    # Handlers are async so they run on the loop every agent run shares (ADR-0001),
    # not in a thread pool beside it.
    @app.get("/api/health")
    async def health() -> Health:
        return Health(version=running)

    # The only way data reaches the browser (ADR-0004). The annotation puts every
    # event's shape in the schema the browser's types come from; each goes out
    # framed with its id, which FastAPI sends as it is. An open stream is an open
    # page, which keeps the poll at its open rhythm (ADR-0003).
    @app.get("/api/events", response_class=EventSourceResponse)
    async def events(
        last_event_id: Annotated[str | None, Header()] = None,
    ) -> AsyncIterable[WireEvent]:
        with efforts.watched():
            async for framed in store.events(last_event_id):
                yield framed  # type: ignore[misc]  # a ServerSentEvent framing a WireEvent

    @app.post("/api/efforts/{number}/read", status_code=202)
    async def read_effort(number: int) -> Response:
        """Read an effort's ticket graph from GitHub afresh (ADR-0003)."""
        return accept(efforts.read(number))

    @app.post("/api/image/read", status_code=202)
    async def read_image() -> Response:
        """Read what the session image would be now (ADR-0005)."""
        return accept(images.read())

    @app.post("/api/gate/read", status_code=202)
    async def read_gate() -> Response:
        """Run the start gate's six checks afresh. Looking raises nothing for a person."""

        async def read() -> None:
            store.upsert(await start_gate.status())

        return accept(read())

    @app.post("/api/image/build", status_code=202)
    async def build_image() -> Response:
        """Build the session image. Builds happen only here, when a person clicks."""
        return accept(images.build())

    @app.post("/api/efforts/{number}/arm", status_code=202)
    async def arm(number: int) -> Response:
        """Arm the effort's cascade, the only way a session ever starts; or resume it."""
        return accept(cascades.arm(number))

    @app.post("/api/efforts/{number}/pause", status_code=202)
    async def pause(number: int) -> Response:
        """Start nothing new on the effort; its running sessions finish."""
        return accept(cascades.pause(number))

    @app.post("/api/efforts/{number}/resume", status_code=202)
    async def resume(number: int) -> Response:
        """Resume the effort's cascade, starting what it can as of a fresh read."""
        return accept(cascades.resume(number))

    @app.post("/api/tickets/{number}/stop", status_code=202)
    async def stop(number: int) -> Response:
        """Stop the ticket's session, keeping its work, and hold the ticket."""
        return accept(cascades.stop(number))

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
