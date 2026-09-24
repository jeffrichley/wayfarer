"""A session's events told as a story: its beats, grouped into Orient and cycles.

Each session here is recorded Claude Code output played back through a real run
(`claude_stream.py`), and the story is read the way a page reads it: from the
items on the stream, which the session puts there as it goes.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest
from claude_stream import (
    DONE,
    Replayed,
    calls,
    edits,
    init,
    reads,
    reports,
    returns,
    runs_tests,
    says,
)
from waystation import NoSandbox
from waystation.testing import ScriptedAgent

from wayfarer import stream
from wayfarer.github import Repo
from wayfarer.models import Beat, BeatKind, Removal, Upsert
from wayfarer.sessions import Sessions, replay
from wayfarer.settings import Settings
from wayfarer.store import Store

pytestmark = pytest.mark.git


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    with closing(Store.open(tmp_path / "data")) as opened:
        yield opened


def _run(host_repo: Path, store: Store, page: stream.Store, *lines: str | list[str]) -> str:
    """Run a session that prints `lines`, watched by `page`; its run id."""
    flat = [init()]
    for line in lines:
        flat.extend([line] if isinstance(line, str) else line)
    sessions = Sessions(
        host_repo,
        store,
        Repo("octo", "widgets"),
        agent=lambda _: Replayed(flat),
        sandbox=NoSandbox(),
        settings=Settings(),
        stream=page,
    )
    asyncio.run(sessions.spec(7).perform())
    return store.sessions()[-1].run_id


def _story(page: stream.Store) -> list[Beat]:
    """The beats the page holds, in the order they happened."""
    return sorted((item for item in page.items() if isinstance(item, Beat)), key=lambda b: b.seq)


def _told(page: stream.Store) -> list[tuple[str, int, str]]:
    """Each beat as (kind, chapter, text)."""
    return [(beat.beat.value, beat.chapter, beat.text) for beat in _story(page)]


def _changes(page: stream.Store) -> list[Upsert | Removal]:
    """Every change the page's stream carried, in order, read as a reconnecting page would."""

    async def read() -> list[Upsert | Removal]:
        events = page.events(None)
        snapshot = await anext(events)
        await events.aclose()
        epoch, _, count = str(snapshot.id).rpartition("-")
        changes: list[Upsert | Removal] = []
        replayed = page.events(f"{epoch}-0")
        for _ in range(int(count)):
            changes.append((await anext(replayed)).data)
        await replayed.aclose()
        return changes

    return asyncio.run(read())


@pytest.fixture
def page() -> stream.Store:
    return stream.Store(backlog=10_000)


def test_consecutive_reads_and_searches_fold_into_one_beat(
    host_repo: Path, store: Store, page: stream.Store
) -> None:
    _run(
        host_repo,
        store,
        page,
        reads("r1", "/workspace/README.md"),
        [calls("s1", "Grep", pattern="limit"), returns("s1", "…")],
        reads("r2", "/workspace/src/widgets.py"),
        reads("r3", "/workspace/src/limits.py"),
        [calls("b1", "Bash", command="ls src"), returns("b1", "widgets.py")],
        reads("r4", "/workspace/src/fold.py"),
        says("The limit is not enforced anywhere."),
        reads("r5", "/workspace/tests/test_widgets.py"),
        reports(DONE),
    )

    assert _told(page) == [
        ("read", 0, "Read README.md, widgets.py and 2 more; searched for “limit”"),
        ("remark", 0, "The limit is not enforced anywhere."),
        ("read", 0, "Read test_widgets.py"),
        ("outcome", 0, "Added the widget."),
    ]


def test_a_test_run_is_red_or_green_by_its_exit_status_with_the_names_the_runner_wrote(
    host_repo: Path, store: Store, page: stream.Store
) -> None:
    _run(
        host_repo,
        store,
        page,
        runs_tests(
            "t1",
            exit=1,
            passed=11,
            failed=2,
            failing=["test_a_widget_past_the_limit_is_refused", "test_the_limit_is_ten"],
            output="FAILED test_a_widget_past_the_limit_is_refused",
        ),
        runs_tests("t2", exit=0, passed=13, failed=0),
        runs_tests("t3", exit=2, output="collection error"),
        reports(DONE),
    )

    red, green, unnamed, _ = _story(page)
    assert (red.beat, red.text) == (
        BeatKind.RED,
        "2 failing: test_a_widget_past_the_limit_is_refused and test_the_limit_is_ten",
    )
    assert red.run is not None
    assert red.run.model_dump() == {
        "exit": 1,
        "passed": 11,
        "failed": 2,
        "failing": ["test_a_widget_past_the_limit_is_refused", "test_the_limit_is_ten"],
    }
    assert red.output == "Exit code 1\nFAILED test_a_widget_past_the_limit_is_refused"
    assert (green.beat, green.text, green.output) == (BeatKind.GREEN, "13 passing", None)
    assert (unnamed.beat, unnamed.text) == (BeatKind.RED, "Failing, exit 2")


def test_only_wf_tests_own_line_makes_a_test_run(
    host_repo: Path, store: Store, page: stream.Store
) -> None:
    _run(
        host_repo,
        store,
        page,
        [
            calls("b1", "Bash", command="pytest", description="Run pytest by hand"),
            returns("b1", "Exit code 1\n3 FAILED", is_error=True),
        ],
        [
            calls("b2", "Bash", command="cat log", description="Read the log"),
            returns("b2", "::wf-test is how tests run"),
        ],
        reports(DONE),
    )

    assert _told(page) == [("outcome", 0, "Added the widget.")]


def test_edits_after_a_green_that_stay_green_read_as_a_refactor(
    host_repo: Path, store: Store, page: stream.Store
) -> None:
    _run(
        host_repo,
        store,
        page,
        runs_tests("t1", exit=1, failed=1, failing=["test_limit"]),
        edits("e1", "/workspace/src/widgets.py"),
        runs_tests("t2", exit=0, passed=4, failed=0),
        edits("e2", "/workspace/src/widgets.py"),
        edits("e3", "/workspace/src/limits.py"),
        edits("e4", "/workspace/src/widgets.py"),
        runs_tests("t3", exit=0, passed=4, failed=0),
        reports(DONE),
    )

    assert _told(page) == [
        ("red", 1, "1 failing: test_limit"),
        ("green", 1, "4 passing"),
        ("refactor", 1, "Refactored widgets.py and limits.py; still 4 passing"),
        ("outcome", 1, "Added the widget."),
    ]
    refactor = _story(page)[2]
    assert refactor.run is not None and refactor.run.exit == 0


def test_edits_after_a_green_that_go_red_belong_to_the_next_cycle(
    host_repo: Path, store: Store, page: stream.Store
) -> None:
    _run(
        host_repo,
        store,
        page,
        runs_tests("t1", exit=0, passed=3, failed=0),
        says("Now the limit."),
        edits("e1", "/workspace/tests/test_widgets.py"),
        runs_tests("t2", exit=1, failed=1, failing=["test_limit"]),
        edits("e2", "/workspace/src/widgets.py"),
        runs_tests("t3", exit=1, failed=1, failing=["test_limit"]),
        edits("e3", "/workspace/src/widgets.py"),
        runs_tests("t4", exit=0, passed=4, failed=0),
        edits("e4", "/workspace/tests/test_widgets.py"),
        runs_tests("t5", exit=1, failed=1, failing=["test_limit_is_ten"]),
        runs_tests("t6", exit=0, passed=5, failed=0),
        reports(DONE),
    )

    assert _told(page) == [
        ("green", 0, "3 passing"),
        ("remark", 0, "Now the limit."),
        ("red", 1, "1 failing: test_limit"),
        ("red", 1, "1 failing: test_limit"),
        ("green", 1, "4 passing"),
        ("red", 2, "1 failing: test_limit_is_ten"),
        ("green", 2, "5 passing"),
        ("outcome", 2, "Added the widget."),
    ]


def test_a_call_with_no_result_yet_is_a_working_row_that_its_beat_replaces(
    host_repo: Path, store: Store, page: stream.Store
) -> None:
    _run(
        host_repo,
        store,
        page,
        edits("e1", "/workspace/src/widgets.py"),
        runs_tests("t1", exit=1, failed=1, failing=["test_limit"]),
        reports(DONE),
    )

    told: list[tuple[str, str]] = []
    for change in _changes(page):
        if isinstance(change, Removal):
            told.append(("removed", change.id))
        elif isinstance(change.item, Beat):
            told.append((change.item.id, f"{change.item.beat.value}: {change.item.text}"))
    (edit, editing), removed, (run, running), (ran, red), *_ = told
    assert editing == "working: Editing widgets.py"
    assert removed == ("removed", edit)
    assert running == "working: Run the tests"
    assert (ran, red) == (run, "red: 1 failing: test_limit")


def test_one_outcome_beat_closes_even_a_session_that_reported_none(
    host_repo: Path, store: Store, page: stream.Store
) -> None:
    invented = {**DONE, "open_findings": [{"severity": "low"}]}
    sessions = Sessions(
        host_repo,
        store,
        Repo("octo", "widgets"),
        agent=lambda _: ScriptedAgent(outcome=invented),
        sandbox=NoSandbox(),
        settings=Settings(),
        stream=page,
    )
    asyncio.run(sessions.spec(7).perform())

    [closing_beat] = [beat for beat in _story(page) if beat.beat is BeatKind.OUTCOME]
    assert closing_beat.text.startswith("Ended without an outcome")


def test_a_cancelled_session_stops_working_and_closes_all_the_same(
    host_repo: Path, store: Store, page: stream.Store
) -> None:
    # The agent keeps running once the tests start, until it is cancelled.
    lines = [init(), calls("t1", "Bash", command="wf-test", description="Run the tests")]
    sessions = Sessions(
        host_repo,
        store,
        Repo("octo", "widgets"),
        agent=lambda _: Replayed(lines, lingers=True),
        sandbox=NoSandbox(),
        settings=Settings(),
        stream=page,
    )

    async def cancelled_while_working() -> None:
        running = asyncio.create_task(sessions.spec(7).perform())
        async with asyncio.timeout(20):
            while not any(beat.beat is BeatKind.WORKING for beat in _story(page)):
                await asyncio.sleep(0.05)
        running.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await running

    asyncio.run(cancelled_while_working())

    assert _told(page) == [("outcome", 0, "Stopped before it reported an outcome.")]


def test_replaying_a_recorded_session_tells_the_story_that_was_watched_live(
    host_repo: Path, store: Store, page: stream.Store
) -> None:
    lines: list[str | list[str]] = [
        reads("r1", "/workspace/README.md"),
        says("Starting with the limit."),
        runs_tests("t1", exit=1, failed=1, failing=["test_limit"]),
        edits("e1", "/workspace/src/widgets.py"),
        runs_tests("t2", exit=0, passed=4, failed=0),
        edits("e2", "/workspace/src/widgets.py"),
        runs_tests("t3", exit=0, passed=4, failed=0),
        reports(DONE),
    ]
    run = _run(host_repo, store, page, *lines)
    live = _story(page)

    later = stream.Store(backlog=10_000)
    [row] = store.sessions()
    replay(row, later)

    assert _story(later) == live
    assert [beat.id for beat in live] == [f"beat:{run}:{beat.seq}" for beat in live]
    assert {beat.session for beat in live} == {run}
