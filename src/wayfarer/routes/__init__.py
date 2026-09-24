"""Each feature's routes, one `APIRouter` per module, which `create_app` includes.

What a handler needs reaches it as `Wired`, the services `create_app` built and
left on `app.state`, the way FastAPI's "bigger applications" guide has it, so a
feature's endpoints add a module here and touch no other handler. Handlers are
async so they run on the loop every agent run shares (ADR-0001), not in a thread
pool beside it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Request, Response

from wayfarer.asking import Asker
from wayfarer.cascade import Cascades
from wayfarer.desk import DeskPage
from wayfarer.gate import StartGate
from wayfarer.home import HomePage
from wayfarer.image import Images
from wayfarer.read_model import Efforts
from wayfarer.restart import Restart
from wayfarer.stream import Store

__all__ = ["Services", "Wired"]


@dataclass(kw_only=True)
class Services:
    """What the routers reach: the services one app runs on, one sorted line each,
    so two tickets adding a service insert at different places."""

    asker: Asker
    cascades: Cascades
    desk: DeskPage
    efforts: Efforts
    home: HomePage
    images: Images
    restart: Restart
    running: str
    start_gate: StartGate
    store: Store
    # A command's work outlives its request, and asyncio keeps only a weak
    # reference to a task, so each is held here until it is done.
    working: set[asyncio.Task[None]] = field(default_factory=set)

    def accept(self, work: Coroutine[None, None, None]) -> Response:
        """Start `work` and say only that it was accepted; its effect comes back over
        the stream like any other change (ADR-0004)."""
        task = asyncio.create_task(work)
        self.working.add(task)
        task.add_done_callback(self.working.discard)
        return Response(status_code=202)


def _services(request: Request) -> Services:
    """The services `create_app` left on the app serving `request`."""
    services: Services = request.app.state.services
    return services


Wired = Annotated[Services, Depends(_services)]
