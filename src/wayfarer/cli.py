"""The `wayfarer` console script: run it inside a clone, and a page opens."""

from __future__ import annotations

import asyncio
import socket
import sys
import webbrowser
from pathlib import Path

import uvicorn

from wayfarer.app import create_app
from wayfarer.github import GitHub, repo_of
from wayfarer.instance import AlreadyRunning, InstanceLock, NotAClone, find_clone, find_worktree
from wayfarer.settings import Settings
from wayfarer.store import Store as Sessions
from wayfarer.stream import Store

__all__ = ["main"]

# Localhost only: nothing else on the network may drive a person's agents.
_HOST = "127.0.0.1"


def _bind(port: int) -> socket.socket:
    """A socket on `port`, or on any free one when that is taken."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # So a restart can take its port back while the last run's
    # connections linger in TIME_WAIT.
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((_HOST, port))
    except OSError:
        sock.bind((_HOST, 0))
    return sock


class _Server(uvicorn.Server):
    """uvicorn, ending every page's stream as it stops.

    A stream never ends by itself, and uvicorn waits for every response to finish
    before it stops, so an open page would otherwise hold Ctrl-C off forever.
    sse-starlette meets the same problem by hooking uvicorn's exit.
    """

    def __init__(self, config: uvicorn.Config, store: Store) -> None:
        super().__init__(config)
        self._store = store

    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        self._store.close()
        await super().shutdown(sockets)


async def _serve(lock: InstanceLock, repo: Path) -> None:
    settings = Settings.from_env()
    sock = _bind(settings.port)
    port = sock.getsockname()[1]
    url = f"http://{_HOST}:{port}/"

    store = Store(settings.stream_backlog)
    origin = repo_of(repo)
    # Opened on the loop's own thread, which is the only one that reads it.
    sessions = Sessions.for_repo(settings.data_dir, origin) if origin else None
    app = create_app(repo, settings, GitHub(origin, settings), store, sessions)
    server = _Server(uvicorn.Config(app, log_level="warning"), store)
    serving = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        while not server.started and not serving.done():
            await asyncio.sleep(0.05)
        if server.started:
            lock.announce(url)
            print(f"Wayfarer is serving at {url}", flush=True)
            await asyncio.to_thread(webbrowser.open, url)
        await serving
    finally:
        if sessions is not None:
            sessions.close()


def main() -> None:
    try:
        cwd = Path.cwd()
        with InstanceLock(find_clone(cwd)) as lock:
            asyncio.run(_serve(lock, find_worktree(cwd)))
    except (NotAClone, AlreadyRunning) as refusal:
        sys.exit(f"wayfarer: {refusal}")
    except KeyboardInterrupt:
        # Ctrl-C is how a person stops Wayfarer, not a crash. uvicorn has already
        # shut down by the time it re-raises the signal it captured.
        pass
