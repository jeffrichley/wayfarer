"""At work's lanes, as the server derives them from everything else it holds (#56).

Wayfarer is served in this process with its sessions really running recorded Claude
Code output, each ticket's its own (`claude_stream.Playing`), and running until the
test ends. What the screen draws from the lanes is `test_the_at_work_screen.py`'s.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from claude_stream import Playing, edits, runs_tests, says

from cascading import playing
from conftest import Stream, post
from github_stand_in import GitHub
from wayfarer.asking import ASKED

pytestmark = pytest.mark.git

WHICH = "Should a book with no credits fail the export or warn?"
ASKING = {
    "questions": [
        {
            "question": WHICH,
            "header": "Credits",
            "options": [
                {"label": "Fail", "description": "The export stops."},
                {"label": "Warn", "description": "The export carries on."},
            ],
            "multiSelect": False,
        }
    ]
}
CRITERIA = "## Acceptance criteria\n\n- [ ] Credits are checked\n- [ ] A missing one fails\n"


@pytest.fixture
def agent(tmp_path: Path) -> Playing:
    released = tmp_path / "released"
    released.mkdir()
    return Playing(released)


@pytest.fixture
def url(tmp_path: Path, github: GitHub, agent: Playing) -> Iterator[str]:
    with playing(tmp_path, github, agent) as served:
        yield served


def _page(url: str) -> Stream:
    return Stream(url, patience=20.0, derived=True)


def test_every_running_session_has_a_lane_telling_its_own_story_as_it_goes(
    url: str, agent: Playing, github: GitHub
) -> None:
    effort, (fold, measure) = github.effort("Widgets", tickets=2)
    fold.body = CRITERIA
    agent.first[fold.number] = [
        says("Reading the fold."),
        *runs_tests("t1", exit=1, failed=1, failing=["test_fold"]),
        *edits("e1", "/workspace/src/fold.py"),
    ]
    agent.then[fold.number] = [*runs_tests("t2", exit=0, passed=4), says("Folding works.")]
    agent.first[measure.number] = [*runs_tests("t1", exit=0, passed=2), says("Measuring next.")]

    with _page(url) as page:
        assert post(f"{url}api/efforts/{effort.number}/arm").status_code == 202
        page.item(f"lane:{fold.number}", latest="1 failing: test_fold")
        second = page.item(f"lane:{measure.number}", latest="Measuring next.")
        agent.let_go(fold.number)
        first = page.item(f"lane:{fold.number}", latest="Folding works.")

    assert first["state"] == second["state"] == "building"
    assert first["effort"] == {"number": effort.number, "title": "Widgets"}
    assert first["ticket"] == {"number": fold.number, "title": fold.title}
    assert first["branch"] == f"ticket/{fold.number}-ticket-1"
    assert first["started"] is not None
    assert first["criteria"] == ["Credits are checked", "A missing one fails"]
    assert [mark["passed"] for mark in first["rhythm"]] == [False, True]
    assert [mark["passed"] for mark in second["rhythm"]] == [True]
    assert second["criteria"] == []
    assert first["last_green"] == first["rhythm"][1]["at"]
    assert first["changes"] == [{"path": "src/fold.py", "added": 1, "removed": 1}]
    assert second["changes"] == []
    # Each lane is its own session's story.
    assert len(first["sessions"]) == len(second["sessions"]) == 1
    assert first["sessions"] != second["sessions"]
    assert first["question"] is None


def test_a_ticket_that_asked_keeps_its_lane_with_its_question_and_answering_resumes_it(
    url: str, agent: Playing, github: GitHub
) -> None:
    effort, (ticket,) = github.effort("Exports", tickets=1)
    agent.first[ticket.number] = [
        *runs_tests("t1", exit=1, failed=1, failing=["test_credits"]),
        *edits("e1", "/workspace/src/credits.py"),
    ]
    agent.asking[ticket.number] = ASKING
    agent.then[ticket.number] = [
        *edits("e2", "/workspace/src/credits.py"),
        *runs_tests("t2", exit=0, passed=5),
        says("Warning on no credits, as you said."),
    ]

    with _page(url) as page:
        assert post(f"{url}api/efforts/{effort.number}/arm").status_code == 202
        asked = page.item(f"lane:{ticket.number}", state="asked")
        assert asked["latest"] == WHICH
        assert asked["question"]["questions"][0]["question"] == WHICH
        assert [o["label"] for o in asked["question"]["questions"][0]["options"]] == [
            "Fail",
            "Warn",
        ]

        answered = post(f"{url}api/tickets/{ticket.number}/answer", {"answers": {WHICH: "Warn"}})
        assert answered.status_code == 202
        resumed = page.item(
            f"lane:{ticket.number}", state="building", latest="Warning on no credits, as you said."
        )

    assert ASKED not in github.labels(ticket.number)
    # The session that carried on continues the story the asking one told.
    [asking] = asked["sessions"]
    assert resumed["sessions"][0] == asking
    assert len(resumed["sessions"]) == 2
    assert [mark["passed"] for mark in resumed["rhythm"]] == [False, True]
    assert resumed["changes"] == [{"path": "src/credits.py", "added": 2, "removed": 2}]
    assert resumed["question"] is None
