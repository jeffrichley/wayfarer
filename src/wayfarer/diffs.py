"""A pull request's diff, read from GitHub for the review desk (#109).

The desk asks for a pull request's diff when it opens a review, and it is read
then: the pull request's head, then its changed files with their patches, each
patch parsed into lines with their old and new numbers. It is read again
whenever the head of that pull request moves on the stream, which a push does.
Nothing of it is stored (ADR-0003): a restarted Wayfarer reads it again when the
desk next asks.

How much is sent is bounded (`Settings.diff_lines`): files are sent in GitHub's
order until the next would pass the bound, and that file and every one after it
is left out, named with its counts. Paging stops there, so the files on pages
never read are only counted.
"""

from __future__ import annotations

import asyncio
import re
from collections import defaultdict

from wayfarer.github import GitHub, GitHubError, NotConnected
from wayfarer.models import (
    DiffFile,
    DiffLine,
    LeftOut,
    Omission,
    PullDiff,
    PullDiffUnreadable,
    Ticket,
)
from wayfarer.settings import Settings
from wayfarer.stream import Store as Stream

__all__ = ["Diffs", "lines"]

# GitHub's most files to a page, so a pull request takes the fewest reads.
_PER_PAGE = 100

# A hunk's header: where its lines start in the old file and in the new.
_HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def lines(patch: str) -> list[DiffLine]:
    """A file's patch, as GitHub gives it, as its lines with their old and new numbers."""
    parsed: list[DiffLine] = []
    old = new = 0
    # Not `splitlines`, which also splits at a form feed or a line separator in the code.
    for text in patch.split("\n"):
        if hunk := _HUNK.match(text):
            old, new = int(hunk[1]), int(hunk[2])
            continue
        sign, code = text[:1], text[1:]
        if sign == "+":
            parsed.append(DiffLine(old=None, new=new, code=code))
            new += 1
        elif sign == "-":
            parsed.append(DiffLine(old=old, new=None, code=code))
            old += 1
        elif sign == " ":
            parsed.append(DiffLine(old=old, new=new, code=code))
            old += 1
            new += 1
        # Anything else, such as "\ No newline at end of file", is not a line.
    return parsed


class Diffs:
    """Each pull request's diff the desk asked for, kept read as its head moves."""

    def __init__(self, github: GitHub, stream: Stream, settings: Settings) -> None:
        self._github = github
        self._stream = stream
        self._settings = settings
        # Each pull request asked for, and its head as the stream had it when last read.
        self._heads: dict[int, str | None] = {}
        # One read of a pull request at a time, in the order asked, so an older read
        # never lands over a newer one.
        self._reading: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        # asyncio keeps only a weak reference to a task, so each re-read is held here.
        self._rereads: set[asyncio.Task[None]] = set()

    async def read(self, pull: int) -> None:
        """Read `pull`'s diff onto the stream, and read it again whenever its head moves."""
        self._heads[pull] = self._head(pull)
        await self._read(pull)

    async def follow(self) -> None:
        """Read a diff again each time its pull request's head moves, until the stream closes."""
        while not self._stream.closed:
            for pull, seen in self._heads.items():
                head = self._head(pull)
                if head is not None and head != seen:
                    self._heads[pull] = head
                    task = asyncio.create_task(self._read(pull))
                    self._rereads.add(task)
                    task.add_done_callback(self._rereads.discard)
            await self._stream.changed()

    def _head(self, pull: int) -> str | None:
        """`pull`'s head as its ticket on the stream has it; None if no ticket there has it."""
        for item in self._stream.items():
            if isinstance(item, Ticket) and item.pull_request and item.pull_request.number == pull:
                return item.pull_request.head_commit
        return None

    async def _read(self, pull: int) -> None:
        async with self._reading[pull]:
            try:
                diff: PullDiff | PullDiffUnreadable = await self._diff(pull)
            except (NotConnected, GitHubError) as error:
                diff = PullDiffUnreadable(
                    kind="pull_diff_unreadable", id=f"diff:{pull}", pull=pull, reason=str(error)
                )
            self._stream.upsert(diff)

    async def _diff(self, pull: int) -> PullDiff:
        found = await self._github.read(f"/pulls/{pull}")
        changed: int = found["changed_files"]
        room = self._settings.diff_lines
        files: list[DiffFile] = []
        left_out: list[LeftOut] = []
        read = 0
        full = False
        page = 1
        while not full and read < changed:
            listed = await self._github.read(
                f"/pulls/{pull}/files", {"per_page": str(_PER_PAGE), "page": str(page)}
            )
            # GitHub lists at most 3000 files, so a larger pull request runs out of
            # pages before its files; those it never lists are counted as unread.
            if not listed:
                break
            for file in listed:
                read += 1
                patch: str | None = file.get("patch")
                shown = None if patch is None or full else lines(patch)
                if shown is not None and len(shown) <= room:
                    room -= len(shown)
                    files.append(DiffFile(path=file["filename"], lines=shown))
                    continue
                full = full or patch is not None
                why = Omission.NO_PATCH if patch is None else Omission.BOUND
                left_out.append(
                    LeftOut(
                        path=file["filename"],
                        added=file["additions"],
                        removed=file["deletions"],
                        why=why,
                    )
                )
            page += 1
        return PullDiff(
            kind="pull_diff",
            id=f"diff:{pull}",
            pull=pull,
            head_commit=found["head"]["sha"],
            files=files,
            left_out=left_out,
            unread=changed - read,
        )
