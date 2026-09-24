"""The chronicle: what happened to an effort, worked out from GitHub and the session rows (#45).

Driven as a person does: GitHub is changed underneath a running Wayfarer, as a
person, the cascade or Wayfarer's own landing changes it, sessions are written
into the store as the cascade writes them, and the lines are read off the page's
stream. The stand-in's clock moves on a minute with every event, so every line
here is a minute or more from the last. How a line reads is the browser's, and
`test_the_chronicle.py` holds it; these hold what each line says moved.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import httpx
import pytest

from conftest import Launcher, Stream, post
from github_stand_in import GitHub, Issue
from wayfarer.github import Repo
from wayfarer.merge_queue import LANDED_MARKER
from wayfarer.read_model import ASKED, HELD
from wayfarer.store import Purpose, Store

pytestmark = pytest.mark.git

_EFFORT_BRANCH = "effort/1-widgets"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def store(data_dir: Path) -> Iterator[Store]:
    """The repo's store, as the running Wayfarer finds it."""
    with closing(Store.for_repo(data_dir, Repo("octo", "widgets"))) as opened:
        yield opened


def _env(data_dir: Path) -> dict[str, str]:
    # Quick, so a change on GitHub is read again within a test's patience.
    return {"WAYFARER_DATA_DIR": str(data_dir), "WAYFARER_POLL_ACTIVE": "0.2"}


def _session(store: Store, github: GitHub, ticket: Issue, purpose: Purpose = Purpose.BUILD) -> None:
    """A session started on `ticket` now, as the cascade records one."""
    run_id = f"run-{ticket.number}-{len(store.sessions())}"
    store.session_started(run_id, ticket.number, purpose, github.now, store.event_file(run_id))


def _lines(items: dict[str, dict[str, Any]], effort: Issue) -> list[dict[str, Any]]:
    lines = [
        item
        for item in items.values()
        if item["kind"] == "chronicle_line" and item["effort"]["number"] == effort.number
    ]
    return sorted(lines, key=lambda line: (line["at"], line["id"]))


def _told(items: dict[str, dict[str, Any]], effort: Issue) -> list[str]:
    """What each of the effort's lines says moved, oldest first: its kind, its ticket,
    who moved it, and for a landing what it freed and which of those were started."""
    return [_moved(line["moved"]) for line in _lines(items, effort)]


def _moved(moved: dict[str, Any]) -> str:
    said = f"{moved['kind']} {moved['ticket']['title']}"
    by = moved.get("by")
    if isinstance(by, dict):
        said += f" by {by['login']}"
    elif by is not None:
        said += f" by {by}"
    for caused in ("freed", "started"):
        if moved.get(caused):
            said += f"; {caused} " + ", ".join(t["title"] for t in moved[caused])
    return said


def _chronicle(url: str, effort: Issue, expected: list[str]) -> list[dict[str, Any]]:
    """The effort's lines, once they read as `expected`."""
    with Stream(url, timeout=10.0) as page:
        post(f"{url}api/efforts/{effort.number}/read")
        try:
            page.until(lambda items: _told(items, effort) == expected)
        except httpx.ReadTimeout:
            pytest.fail(
                f"the chronicle never read as expected; it reads {_told(page.items, effort)}"
            )
        return _lines(page.items, effort)


def _land(github: GitHub, ticket: Issue) -> None:
    """Closed with the marked comment, as Wayfarer closes a ticket that landed: back to
    back, so GitHub stamps both to the same second."""
    at = github.now
    github.comment(ticket, f"Landed on `{_EFFORT_BRANCH}` at {'a' * 40}.\n\n{LANDED_MARKER}")
    github.now = at
    github.close(ticket)


def test_a_landing_folds_with_the_tickets_it_freed_and_what_the_cascade_started_on_them(
    wayfarer: Launcher, github: GitHub, store: Store, data_dir: Path
) -> None:
    spec, (flag, meter, scale, ruler, other) = github.effort("Widgets", tickets=5)
    flag.title, meter.title, scale.title = "Flag loudness", "Meter peaks", "Scale the meter"
    ruler.title, other.title = "Draw the ruler", "Pick a font"
    github.block(meter, by=flag)
    github.block(scale, by=flag)
    # Still blocked by a ticket that stays open, so this landing frees it not.
    github.block(ruler, by=flag)
    github.block(ruler, by=other)
    github.merged(github.pull_request(flag, base=_EFFORT_BRANCH))
    url = wayfarer.start(env=_env(data_dir)).url()

    # Wayfarer closes what merged as landed, and the cascade takes what that freed.
    _chronicle(
        url,
        spec,
        ["landed Flag loudness by wayfarer; freed Meter peaks, Scale the meter"],
    )
    github.assign(meter, github.viewer)
    _session(store, github, meter)
    [line] = _chronicle(
        url,
        spec,
        [
            "landed Flag loudness by wayfarer; freed Meter peaks, Scale the meter; "
            "started Meter peaks"
        ],
    )

    assert line["effort"] == {"number": spec.number, "title": spec.title}
    assert [t["number"] for t in line["moved"]["freed"]] == [meter.number, scale.number]


def test_two_independent_landings_a_minute_apart_stay_two_lines(
    wayfarer: Launcher, github: GitHub, data_dir: Path
) -> None:
    spec, (first, second) = github.effort("Widgets", tickets=2)
    first.title, second.title = "Flag loudness", "Meter peaks"
    github.merged(github.pull_request(first, base=_EFFORT_BRANCH))
    github.merged(github.pull_request(second, base=_EFFORT_BRANCH))
    url = wayfarer.start(env=_env(data_dir)).url()

    _chronicle(url, spec, ["landed Flag loudness by wayfarer", "landed Meter peaks by wayfarer"])


def test_only_a_ticket_moving_earns_a_line_never_a_stage_a_pull_request_or_a_resolver(
    wayfarer: Launcher, github: GitHub, store: Store, data_dir: Path
) -> None:
    spec, (ticket,) = github.effort("Widgets", tickets=1)
    ticket.title = "Flag loudness"
    github.label(ticket, "ready-for-agent")
    github.comment(ticket, "Looks good to me.")
    github.pull_request(ticket, base=_EFFORT_BRANCH, draft=True)
    github.label(ticket, HELD)
    github.unlabel(ticket, HELD)
    # Replaying its commits onto the effort branch is landing, not a retry.
    _session(store, github, ticket, Purpose.RESOLVE)
    _land(github, ticket)
    url = wayfarer.start(env=_env(data_dir)).url()

    # Letting it land ends in the landing, so it has no line of its own (#51).
    _chronicle(url, spec, ["held Flag loudness", "landed Flag loudness by wayfarer"])


def test_who_acted_is_read_from_the_kind_of_event_and_never_from_the_token(
    wayfarer: Launcher, github: GitHub, store: Store, data_dir: Path
) -> None:
    names = ["Taken", "Mine", "Theirs", "Rebuilt", "Asked", "Asked them", "Held", "Dropped", "Done"]
    spec, tickets = github.effort("Widgets", tickets=len(names))
    for ticket, name in zip(tickets, names, strict=True):
        ticket.title = name
    taken, mine, theirs, rebuilt, asked, asked_them, held, dropped, done = tickets

    # Every write Wayfarer makes wears the person's login, as it does on GitHub.
    github.assign(taken, github.viewer)
    _session(store, github, taken)
    github.assign(mine, github.viewer)
    # A session once ran on it, but none started when it was taken this time.
    _session(store, github, rebuilt)
    github.assign(theirs, "octocat", by="octocat")
    github.assign(rebuilt, "octocat", by="octocat")
    github.label(asked, ASKED)
    github.unlabel(asked, ASKED)
    _session(store, github, asked)
    github.label(asked_them, ASKED)
    github.unlabel(asked_them, ASKED, by="octocat")
    github.label(held, HELD)
    github.unlabel(held, HELD)
    _session(store, github, held)
    github.close(dropped, "NOT_PLANNED", by="octocat")
    github.close(done)
    url = wayfarer.start(env=_env(data_dir)).url()

    _chronicle(
        url,
        spec,
        [
            "taken Taken by wayfarer",
            "taken Mine by you",
            "taken Theirs by octocat",
            "taken Rebuilt by octocat",
            "asked Asked",
            "answered Asked by you",
            "asked Asked them",
            "answered Asked them by octocat",
            "held Held",
            "retried Held",
            "closed Dropped by octocat",
            "closed Done by you",
        ],
    )


def test_a_retry_says_whether_it_continued_or_started_over(
    wayfarer: Launcher, github: GitHub, store: Store, data_dir: Path
) -> None:
    spec, (kept, fresh) = github.effort("Widgets", tickets=2)
    kept.title, fresh.title = "Kept", "Fresh"
    for ticket, purpose in ((kept, Purpose.CONTINUE), (fresh, Purpose.START_OVER)):
        github.label(ticket, HELD)
        github.unlabel(ticket, HELD)
        _session(store, github, ticket, purpose)
    url = wayfarer.start(env=_env(data_dir)).url()

    lines = _chronicle(url, spec, ["held Kept", "retried Kept", "held Fresh", "retried Fresh"])

    assert [line["moved"]["over"] for line in lines if line["moved"]["kind"] == "retried"] == [
        False,
        True,
    ]


def test_the_chronicle_rebuilds_identically_after_a_restart(
    wayfarer: Launcher, github: GitHub, store: Store, data_dir: Path
) -> None:
    spec, (flag, meter) = github.effort("Widgets", tickets=2)
    flag.title, meter.title = "Flag loudness", "Meter peaks"
    github.block(meter, by=flag)
    github.label(flag, HELD)
    github.unlabel(flag, HELD)
    _land(github, flag)
    github.assign(meter, github.viewer)
    _session(store, github, meter)
    expected = [
        "held Flag loudness",
        "landed Flag loudness by wayfarer; freed Meter peaks; started Meter peaks",
    ]

    running = wayfarer.start(env=_env(data_dir))
    before = _chronicle(running.url(), spec, expected)
    assert running.interrupt() == 0
    after = _chronicle(wayfarer.start(env=_env(data_dir)).url(), spec, expected)

    assert after == before


def test_a_reopened_ticket_frees_what_it_blocks_again_when_it_lands(
    wayfarer: Launcher, github: GitHub, store: Store, data_dir: Path
) -> None:
    spec, (flag, meter) = github.effort("Widgets", tickets=2)
    flag.title, meter.title = "Flag loudness", "Meter peaks"
    github.block(meter, by=flag)
    github.close(flag, by="octocat")
    github.reopen(flag, by="octocat")
    _land(github, flag)
    github.assign(meter, github.viewer)
    _session(store, github, meter)
    url = wayfarer.start(env=_env(data_dir)).url()

    _chronicle(
        url,
        spec,
        [
            "closed Flag loudness by octocat",
            "landed Flag loudness by wayfarer; freed Meter peaks; started Meter peaks",
        ],
    )
