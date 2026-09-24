"""The HTTP surface: the JSON API under `/api`, and the React app at every other path.

`create_app` builds the services and includes each feature's router
(`wayfarer.routes`); the handlers live there.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version
from pathlib import Path

from fastapi import FastAPI
from waystation import DockerSandbox, SandboxBackend

from wayfarer.cascade import Cascades, Gate, SessionsFor
from wayfarer.chronicle import chronicle
from wayfarer.endings import Endings
from wayfarer.gate import StartGate
from wayfarer.github import GitHub
from wayfarer.graph import Graphs
from wayfarer.home import HomePage
from wayfarer.image import Images
from wayfarer.merge_queue import MergeQueue
from wayfarer.models import ChronicleLine, Effort, Ticket
from wayfarer.poll import poll
from wayfarer.queue import Queue
from wayfarer.read_model import Efforts, History
from wayfarer.restart import Containers, DockerContainers, Restart
from wayfarer.routes import Services, page
from wayfarer.routes import efforts as efforts_routes
from wayfarer.routes import events as events_routes
from wayfarer.routes import gate as gate_routes
from wayfarer.routes import health as health_routes
from wayfarer.routes import home as home_routes
from wayfarer.routes import image as image_routes
from wayfarer.routes import restart as restart_routes
from wayfarer.routes import tickets as tickets_routes
from wayfarer.sessions import Sessions
from wayfarer.settings import Settings
from wayfarer.store import Store as Record
from wayfarer.stream import Store

__all__ = ["create_app"]

_log = logging.getLogger(__name__)


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
    containers: Containers | None = None,
) -> FastAPI:
    """The app for the clone whose working tree is `repo`, reading GitHub through
    `github`; without one, every read of GitHub says so. `store` is what the page's
    stream carries, which whoever runs the server closes as it stops.

    Sessions run Claude Code in the session image, admitted by the start gate
    (ADR-0005). `sessions` and `gate` replace both only for a test, which runs
    Waystation's scripted agent outside Docker; Wayfarer offers no way to do so.
    Such a session leaves no container, so the test says what `containers` a
    restart finds in place of Docker's.
    """
    settings = settings or Settings()
    github = github or GitHub(None, settings)
    store = store or Store(settings.stream_backlog)
    running = version("wayfarer")
    images = Images(repo, store)
    start_gate = StartGate(repo, images, settings)

    def in_image(record: Record) -> Sessions:
        # The gate admitted this start, so the repo is known and its image is built.
        tag = images.current()
        assert github.repo is not None and tag is not None
        return Sessions.in_image(repo, record, github.repo, tag, settings, store)

    def sandbox() -> SandboxBackend | None:
        """Where the merge queue re-tests: the session image as it stands, which is the
        repo's toolchain, and never anywhere unsandboxed (ADR-0005)."""
        current = images.current()
        return None if current is None else DockerSandbox(current)

    def resolvers() -> Sessions | None:
        """Where a conflict's resolver session runs: where a build does, recording into
        the same store, so its one resolver session is remembered across restarts."""
        if sessions is None and images.current() is None:
            return None
        return (sessions or in_image)(cascades.record())

    runs = Queue(settings.cap)
    queue = MergeQueue(
        repo,
        github,
        settings,
        sandbox,
        stream=store,
        resolvers=resolvers,
        # Under the cap every session shares, a build or a resolver alike.
        submit=runs.submit,
        pause=lambda effort, why: cascades.pause_itself(effort, why),
    )

    def tell(effort: Effort, tickets: list[Ticket], history: History) -> list[ChronicleLine]:
        # An effort was read, so there is a repo and its record opens.
        return chronicle(effort, tickets, history, cascades.record().sessions())

    efforts = Efforts(github, store, settings, line=queue.line, telling=tell)
    cascades = Cascades(
        efforts,
        github,
        store,
        settings,
        gate or start_gate,
        sessions or in_image,
        runs,
        Endings(repo, github, settings),
    )
    home = HomePage(store, github.repo, cascades.record, auto_merge=settings.auto_merge)
    graphs = Graphs(store, None if github.repo is None else cascades.record)
    restart = Restart(store, github, cascades, efforts, containers or DockerContainers(settings))

    # The poll, and the re-reads it sets off, run for as long as the app serves,
    # on the same loop (ADR-0001, ADR-0003). Stopping stops every session, each
    # keeping its work, as Ctrl-C does.
    @asynccontextmanager
    async def keeping_up(app: FastAPI) -> AsyncIterator[None]:
        # What the last Wayfarer recorded is read before anything is served; GitHub
        # and Docker after, while it serves.
        restart.recall()
        tasks = [
            asyncio.create_task(poll(github, settings)),
            asyncio.create_task(efforts.follow()),
            asyncio.create_task(home.follow()),
            asyncio.create_task(graphs.follow()),
            asyncio.create_task(restart.recover()),
        ]
        for task in tasks:
            task.add_done_callback(_report_death)
        async with runs:
            yield
            # The reads stop first, since a read may start a session, and only then
            # do the sessions, so none starts after the rest were stopped.
            for task in tasks:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        await queue.stop()
        cascades.close()

    app = FastAPI(title="Wayfarer", version=running, lifespan=keeping_up)
    app.state.services = Services(
        cascades=cascades,
        efforts=efforts,
        home=home,
        images=images,
        restart=restart,
        running=running,
        start_gate=start_gate,
        store=store,
    )
    # One line per feature, sorted, so two tickets adding routers insert at
    # different places rather than both appending at the end.
    app.include_router(efforts_routes.router)
    app.include_router(events_routes.router)
    app.include_router(gate_routes.router)
    app.include_router(health_routes.router)
    app.include_router(home_routes.router)
    app.include_router(image_routes.router)
    app.include_router(restart_routes.router)
    app.include_router(tickets_routes.router)
    page.include(app)
    return app
