"""What a session has changed, file by file, as At work's rail shows it (#56).

Each session is recorded Claude Code output played back through a real run
(`claude_stream.py`), and what it changed is read the way a page reads it: from
the item the session puts on the stream as it goes.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from claude_stream import DONE, Replayed, calls, init, reports, returns
from waystation import NoSandbox

from wayfarer import stream
from wayfarer.github import Repo
from wayfarer.models import Changes
from wayfarer.sessions import Sessions, replay
from wayfarer.settings import Settings
from wayfarer.store import Store

pytestmark = pytest.mark.git


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    with closing(Store.open(tmp_path / "data")) as opened:
        yield opened


@pytest.fixture
def page() -> stream.Store:
    return stream.Store(backlog=10_000)


def _run(host_repo: Path, store: Store, page: stream.Store, *lines: str) -> str:
    """Run a session that prints `lines`, watched by `page`; its run id."""
    sessions = Sessions(
        host_repo,
        store,
        Repo("octo", "widgets"),
        agent=lambda _: Replayed([init(), *lines, reports(DONE)]),
        sandbox=NoSandbox(),
        settings=Settings(),
        stream=page,
    )
    asyncio.run(sessions.spec(7).perform())
    return store.sessions()[-1].run_id


def _edit(id: str, name: str, *, error: bool = False, **given: Any) -> list[str]:
    return [calls(id, name, **given), returns(id, "Error" if error else "ok", is_error=error)]


def _changed(page: stream.Store, session: str) -> list[tuple[str, int, int]]:
    changes = page.get(f"changes:{session}")
    assert isinstance(changes, Changes)
    return [(f.path, f.added, f.removed) for f in changes.files]


def test_each_file_a_session_edits_is_counted_once_with_the_lines_it_added_and_removed(
    host_repo: Path, store: Store, page: stream.Store
) -> None:
    session = _run(
        host_repo,
        store,
        page,
        *_edit("w1", "Write", file_path="/workspace/src/limits.py", content="A = 1\nB = 2\n"),
        *_edit(
            "e1",
            "Edit",
            file_path="/workspace/src/widgets.py",
            old_string="def make():\n    return 1\n",
            new_string="def make():\n    return limit()\n",
        ),
        *_edit(
            "e2",
            "Edit",
            file_path="/workspace/src/limits.py",
            old_string="B = 2\n",
            new_string="B = 3\nC = 4\n",
        ),
    )

    # In the order each was first touched; the unchanged line around an edit is not counted.
    assert _changed(page, session) == [("src/limits.py", 4, 1), ("src/widgets.py", 1, 1)]


def test_an_edit_the_tool_refused_changes_nothing(
    host_repo: Path, store: Store, page: stream.Store
) -> None:
    session = _run(
        host_repo,
        store,
        page,
        *_edit(
            "e1",
            "Edit",
            error=True,
            file_path="/workspace/src/widgets.py",
            old_string="nowhere",
            new_string="x",
        ),
    )

    assert _changed(page, session) == []


def test_a_replayed_session_shows_the_same_changes_it_showed_live(
    host_repo: Path, store: Store, page: stream.Store
) -> None:
    session = _run(
        host_repo,
        store,
        page,
        *_edit("w1", "Write", file_path="/workspace/README.md", content="widgets\nand more\n"),
    )
    again = stream.Store(backlog=100)

    replay(store.sessions()[-1], again)

    assert _changed(again, session) == _changed(page, session) == [("README.md", 2, 0)]
