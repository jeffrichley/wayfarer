"""One Wayfarer per clone.

Two processes on one clone would each believe they own the cascade, and would
contend for the repo through the host-git lock that Waystation only serialises
inside one process (ADR-0001). So the first instance holds an OS lock on a file in
the clone's git directory, and a second one refuses instead of starting.

The OS drops the lock when the process dies, however it dies, so a crash never
leaves a clone locked. A clean exit also removes the file.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
from pathlib import Path
from types import TracebackType
from typing import IO, Self

__all__ = ["AlreadyRunning", "InstanceLock", "NotAClone", "find_clone", "find_worktree"]

_LOCK_NAME = "wayfarer.lock"


class NotAClone(Exception):
    """Wayfarer was started outside a git clone."""


class AlreadyRunning(Exception):
    """Another Wayfarer already holds this clone."""

    def __init__(self, holder: str) -> None:
        super().__init__(
            f"Wayfarer is already running for this clone ({holder}). "
            "Only one may run per clone, because two would contend for the same repo."
        )


def find_clone(cwd: Path) -> Path:
    """The git directory shared by every worktree of the clone `cwd` is in."""
    return _rev_parse(cwd, "--path-format=absolute", "--git-common-dir")


def find_worktree(cwd: Path) -> Path:
    """The top of the working tree `cwd` is in, where the repo's files are."""
    return _rev_parse(cwd, "--show-toplevel")


def _rev_parse(cwd: Path, *args: str) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise NotAClone(
            f"{cwd} is not inside a git clone. Run wayfarer inside a clone of the repo "
            "it should work on."
        )
    return Path(result.stdout.strip())


class InstanceLock:
    """Held for the life of the process: `with InstanceLock(git_dir) as lock:`."""

    def __init__(self, git_dir: Path) -> None:
        self._path = git_dir / _LOCK_NAME
        self._file: IO[str] | None = None

    def __enter__(self) -> Self:
        while True:
            file = self._path.open("a+", encoding="utf-8")
            if not _try_lock(file):
                file.seek(0)
                holder = _describe(file.read())
                file.close()
                raise AlreadyRunning(holder)
            # The previous holder may have removed the file between our open and our
            # lock, leaving us holding a lock on a file nobody else can see.
            if _same_file(file, self._path):
                break
            _unlock(file)
            file.close()
        self._file = file
        self.announce()
        return self

    def announce(self, url: str | None = None) -> None:
        """Record who holds the clone, so a refused instance can say."""
        assert self._file is not None
        self._file.seek(0)
        self._file.truncate()
        self._file.write(json.dumps({"pid": os.getpid(), "url": url}))
        self._file.flush()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._file is not None
        # Removed while still locked, so no other instance can be mid-way through
        # taking it.
        self._path.unlink(missing_ok=True)
        _unlock(self._file)
        self._file.close()
        self._file = None


def _describe(content: str) -> str:
    try:
        holder = json.loads(content)
    except ValueError:
        return "it is still starting"
    if holder.get("url"):
        return f"pid {holder['pid']}, serving at {holder['url']}"
    return f"pid {holder['pid']}, still starting"


def _same_file(file: IO[str], path: Path) -> bool:
    try:
        on_disk = path.stat()
    except FileNotFoundError:
        return False
    held = os.fstat(file.fileno())
    return (held.st_dev, held.st_ino) == (on_disk.st_dev, on_disk.st_ino)


def _try_lock(file: IO[str]) -> bool:
    try:
        fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def _unlock(file: IO[str]) -> None:
    fcntl.flock(file.fileno(), fcntl.LOCK_UN)
