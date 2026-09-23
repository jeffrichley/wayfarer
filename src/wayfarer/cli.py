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


async def _serve(lock: InstanceLock, repo: Path) -> None:
    settings = Settings.from_env()
    sock = _bind(settings.port)
    port = sock.getsockname()[1]
    url = f"http://{_HOST}:{port}/"

    app = create_app(repo, settings, GitHub(repo_of(repo), settings))
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
    serving = asyncio.create_task(server.serve(sockets=[sock]))
    while not server.started and not serving.done():
        await asyncio.sleep(0.05)
    if server.started:
        lock.announce(url)
        print(f"Wayfarer is serving at {url}", flush=True)
        await asyncio.to_thread(webbrowser.open, url)
    await serving


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
