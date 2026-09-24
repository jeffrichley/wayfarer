"""What a session has changed: its edits folded into a line count per file.

Folded from the session's events as its beats are (`beats.py`), live and on
replay alike, and never stored. It is what the edits said, not a diff: the
workspace is inside the sandbox, and nothing is read out of it while it runs. An
edit counts only the lines it changed, not those it carried along unchanged; an
edit the tool refused counts nothing.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from wayfarer.events import SessionEvent, ToolResult, ToolUse
from wayfarer.models import Changes, FileChange

__all__ = ["changed"]

# Where Waystation's Docker sandbox mounts a session's workspace
# (`waystation.sandbox._docker_plans.WORKSPACE`), which a path is shown relative to.
_WORKSPACE = PurePosixPath("/workspace")


@dataclass
class _Count:
    added: int = 0
    removed: int = 0


def changed(session: str, events: Iterable[SessionEvent]) -> Changes:
    """Session `session`'s changes so far, one file each, in the order first changed."""
    calls: dict[str, ToolUse] = {}
    counts: dict[str, _Count] = {}
    # What each file was last written whole as, so writing it again counts the difference.
    written: dict[str, str] = {}
    for event in events:
        match event:
            case ToolUse(tool="edit"):
                calls[event.id] = event
            case ToolResult(is_error=False) if (call := calls.pop(event.id, None)) is not None:
                _count(call.input, counts, written)
            case _:
                pass
    return Changes(
        kind="changes",
        id=f"changes:{session}",
        session=session,
        files=[FileChange(path=p, added=c.added, removed=c.removed) for p, c in counts.items()],
    )


def _count(given: dict[str, Any], counts: dict[str, _Count], written: dict[str, str]) -> None:
    """Count one accepted edit: a `Write` of a whole file, or an `Edit` of part of one.
    Any other edit tool names its file otherwise, and is not counted."""
    path = given.get("file_path")
    if not isinstance(path, str):
        return
    shown = _shown(path)
    if isinstance(content := given.get("content"), str):
        old, new = written.get(shown, ""), content
        written[shown] = content
    else:
        old, new = str(given.get("old_string", "")), str(given.get("new_string", ""))
    count = counts.setdefault(shown, _Count())
    before, after = old.splitlines(), new.splitlines()
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=before, b=after).get_opcodes():
        if tag != "equal":
            count.removed += i2 - i1
            count.added += j2 - j1


def _shown(path: str) -> str:
    given = PurePosixPath(path)
    return str(given.relative_to(_WORKSPACE)) if given.is_relative_to(_WORKSPACE) else path
