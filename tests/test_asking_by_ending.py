"""Asking by ending: the question on the ticket, and a person's answer to it (#42).

A question comment and the `wayfarer:asked` label are the whole of the state, so
these put them on the GitHub stand-in underneath a running Wayfarer, as a session
that asked leaves them, and read what the page is told. Answering is driven both
ways a person does it: from Wayfarer, and by hand on GitHub.

How a session comes to ask, and how an answer resumes it, is in
`test_a_session_that_asks.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from conftest import Launcher, Stream, post, quick
from github_stand_in import GitHub, Issue
from wayfarer.asking import ASKED, question_comment
from wayfarer.models import Choice, Question

pytestmark = pytest.mark.git

_WHICH = Question(
    question="Should a book with no credits fail the export or warn?",
    header="Credits",
    options=[
        Choice(label="Fail", description="The export stops, naming the book."),
        Choice(label="Warn", description="The export carries on, and says so."),
    ],
    multi_select=False,
)
_WHERE = Question(
    question="Where does the warning go?",
    header="Warning",
    options=[Choice(label="The log", description="Only the log says so.")],
    multi_select=False,
)


def _ask(github: GitHub, ticket: Issue, *questions: Question, session: str = "run-1") -> None:
    """Leave `ticket` as a session that asked leaves it: claimed, the question, the label."""
    github.assign(ticket, "wayfarer")
    github.comment(ticket, question_comment(session, questions))
    github.label(ticket, ASKED)


def _read(url: str, effort: Issue) -> Stream:
    page = Stream(url, patience=20.0)
    post(f"{url}api/efforts/{effort.number}/read")
    page.item(f"effort:{effort.number}")
    return page


def _answer(url: str, ticket: Issue, answers: dict[str, str]) -> httpx.Response:
    return httpx.post(
        f"{url}api/tickets/{ticket.number}/answer", json={"answers": answers}, timeout=5.0
    )


def test_an_asked_ticket_shows_its_question_with_every_option_as_the_session_asked(
    wayfarer: Launcher, github: GitHub
) -> None:
    effort, (ticket,) = github.effort("Exports", tickets=1)
    _ask(github, ticket, _WHICH, _WHERE, session="run-7")
    url = wayfarer.start().url()

    with _read(url, effort) as page:
        read = page.items[f"ticket:{ticket.number}"]

    assert read["state"] == "asked"
    assert read["question"] == {
        "session": "run-7",
        "questions": [_WHICH.model_dump(), _WHERE.model_dump()],
        "answered": False,
        "answers": None,
    }


def test_the_question_comment_reads_on_github_without_wayfarer(github: GitHub) -> None:
    body = question_comment("run-1", [_WHICH])

    # A person on their phone sees the question and its options, not the marker's JSON.
    shown = body.split("<!--")[0]
    assert "Should a book with no credits fail the export or warn?" in shown
    assert "**Fail**: The export stops, naming the book." in shown
    assert "**Warn**: The export carries on, and says so." in shown
    assert f"remove the `{ASKED}` label" in shown


def test_answering_from_wayfarer_posts_the_answer_and_takes_the_label_off(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    effort, (ticket,) = github.effort("Exports", tickets=1)
    _ask(github, ticket, _WHICH, _WHERE, session="run-7")
    url = wayfarer.start(env=quick(tmp_path)).url()
    answers = {_WHICH.question: "Warn", _WHERE.question: "Somewhere the author will see it."}

    with _read(url, effort) as page:
        assert _answer(url, ticket, answers).status_code == 202
        read = page.item(f"ticket:{ticket.number}", state="blocked")

    assert ASKED not in github.labels(ticket.number)
    assert "Somewhere the author will see it." in ticket.comments[-1]
    # Still claimed: the session it resumes is still its own.
    assert read["assignees"] == ["wayfarer"]
    assert read["question"]["answered"] is True
    assert read["question"]["answers"] == answers


def test_answering_by_hand_on_github_takes_every_reply_after_the_question_as_the_answer(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    effort, (ticket,) = github.effort("Exports", tickets=1)
    _ask(github, ticket, _WHICH, _WHERE)
    url = wayfarer.start(env=quick(tmp_path)).url()

    with _read(url, effort) as page:
        github.comment(ticket, "Warn, please.", by="octocat")
        github.comment(ticket, "And put it in the export summary.", by="octocat")
        github.unlabel(ticket, ASKED, by="octocat")
        read = page.item(f"ticket:{ticket.number}", state="blocked")

    said = "Warn, please.\n\nAnd put it in the export summary."
    assert read["question"]["answered"] is True
    assert read["question"]["answers"] == {_WHICH.question: said, _WHERE.question: said}


def test_a_reply_left_while_the_label_stays_is_not_yet_an_answer(
    wayfarer: Launcher, github: GitHub
) -> None:
    effort, (ticket,) = github.effort("Exports", tickets=1)
    _ask(github, ticket, _WHICH)
    github.comment(ticket, "Thinking about it.", by="octocat")
    url = wayfarer.start().url()

    with _read(url, effort) as page:
        read = page.items[f"ticket:{ticket.number}"]

    assert read["state"] == "asked"
    assert read["question"]["answered"] is False
    assert read["question"]["answers"] is None


def test_a_label_taken_off_with_no_reply_is_answered_with_nothing(
    wayfarer: Launcher, github: GitHub
) -> None:
    effort, (ticket,) = github.effort("Exports", tickets=1)
    _ask(github, ticket, _WHICH)
    github.unlabel(ticket, ASKED, by="octocat")
    url = wayfarer.start().url()

    with _read(url, effort) as page:
        read = page.items[f"ticket:{ticket.number}"]

    assert read["question"]["answered"] is True
    assert read["question"]["answers"] == {}


def test_only_the_latest_question_is_the_tickets_question(
    wayfarer: Launcher, github: GitHub
) -> None:
    effort, (ticket,) = github.effort("Exports", tickets=1)
    _ask(github, ticket, _WHICH, session="run-1")
    github.comment(ticket, "Warn.", by="octocat")
    github.unlabel(ticket, ASKED, by="octocat")
    # Resumed, it asked again.
    github.comment(ticket, question_comment("run-2", [_WHERE]))
    github.label(ticket, ASKED)
    url = wayfarer.start().url()

    with _read(url, effort) as page:
        read = page.items[f"ticket:{ticket.number}"]

    assert read["question"]["session"] == "run-2"
    assert read["question"]["questions"] == [_WHERE.model_dump()]
    assert read["question"]["answered"] is False


def test_a_ticket_that_never_asked_has_no_question_and_a_mangled_marker_is_none(
    wayfarer: Launcher, github: GitHub
) -> None:
    effort, (never, mangled) = github.effort("Exports", tickets=2)
    github.comment(mangled, "<!-- wayfarer:question {not json} -->")
    mangled.labels.append(ASKED)
    url = wayfarer.start().url()

    with _read(url, effort) as page:
        items = page.items

    assert items[f"ticket:{never.number}"]["question"] is None
    assert items[f"ticket:{mangled.number}"]["question"] is None


def test_answering_a_ticket_that_is_not_waiting_on_an_answer_changes_nothing(
    wayfarer: Launcher, github: GitHub
) -> None:
    effort, (unasked,) = github.effort("Exports", tickets=1)
    url = wayfarer.start().url()

    with _read(url, effort):
        assert _answer(url, unasked, {"Anything?": "No."}).status_code == 202
        # An answer to an unread ticket, too, which the page has never seen.
        assert _answer(url, Issue(999, "Unread"), {"Anything?": "No."}).status_code == 202

    assert unasked.comments == []


def test_the_chronicle_and_needs_you_quote_what_the_session_asked(
    wayfarer: Launcher, github: GitHub
) -> None:
    effort, (ticket,) = github.effort("Exports", tickets=1)
    _ask(github, ticket, _WHICH, _WHERE)
    url = wayfarer.start().url()

    with Stream(url, patience=20.0, derived=True) as page:
        post(f"{url}api/efforts/{effort.number}/read")
        page.until(lambda items: _needs(items) != [])
        [asked] = [
            i
            for i in page.items.values()
            if i["kind"] == "chronicle_line" and i["moved"]["kind"] == "asked"
        ]
        [need] = _needs(page.items)

    assert asked["moved"]["gist"] == _WHICH.question
    assert need["kind"] == "question"
    assert need["gist"] == _WHICH.question


def _needs(items: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        need
        for item in items.values()
        if item["kind"] == "needs_you"
        for need in item["items"]
        if need.get("kind") == "question"
    ]
