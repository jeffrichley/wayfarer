"""Asking by ending: a session's question on its ticket, and a person's answer (#19, #42).

A session asks with Claude Code's own `AskUserQuestion`, and the image's hook
defers the call (`base/wf-ask`): the session ends there and its slot frees. The
hook wrote the question down, the session carried it out as its agent ended, and
Wayfarer posts it on the ticket as one **question comment**, carrying a hidden
marker naming the session and holding the question whole, and labels the ticket
`wayfarer:asked`. The ticket stays assigned. That comment and that label are the
whole of the state (ADR-0002): nothing about a question is stored.

A person answers from Wayfarer, which posts an **answer comment** with a
matching marker and takes the label off; or on GitHub, by replying and taking
the label off themselves. **Taking the label off is the signal.** Answered by
hand, every comment after the question, up to the label coming off, answers each
of its questions.

An answered question resumes its session, in a fresh container, carrying on the
same conversation (`cascade.py`); the answer is carried in for the hook to hand
back, and the hook never reads GitHub.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from wayfarer.github import GitHub
from wayfarer.models import Asking, Choice, Question, Ticket, TicketState
from wayfarer.stream import Store as Stream

if TYPE_CHECKING:
    from wayfarer.read_model import Event

__all__ = [
    "ANSWER",
    "ASKED",
    "ASKING",
    "QUESTION",
    "RESUMED",
    "Asker",
    "answer_comment",
    "cold",
    "gist",
    "latest",
    "parse_questions",
    "question_comment",
    "resumed",
]

ASKED = "wayfarer:asked"

QUESTION = ".wayfarer/question.json"
"""Where the image's hook writes a question, under the sandbox's home (`base/wf-ask`)."""
ANSWER = ".wayfarer/answer.json"
"""Where a resume carries the answer in, under the sandbox's home, for the hook to give."""

# Every marker Wayfarer leaves is an HTML comment starting so, which GitHub renders
# as nothing; a comment carrying none is a person's own.
_MARKED = "<!-- wayfarer:"
_QUESTION_MARK = re.compile(r"<!-- wayfarer:question (\{.*?\}) -->", re.DOTALL)
_ANSWER_MARK = re.compile(r"<!-- wayfarer:answer (\{.*?\}) -->", re.DOTALL)

# Given to each question a person took the label off without answering.
_UNANSWERED = "No answer was given. Decide for yourself, and record it as an assumption."

RESUMED = "Your question was answered. Carry on from where you asked."
"""What a resume is told, beside the answer the hook hands back."""

ASKING = (
    "--mcp-config",
    json.dumps({"mcpServers": {"wayfarer": {"command": "/usr/local/bin/wf-ask-tool"}}}),
    "--permission-prompt-tool",
    "mcp__wayfarer__ask",
)
"""What a session is run with so it can ask: in print mode `AskUserQuestion` exists
only once a permission prompt tool is named, and the image's stub is that tool
(`base/wf-ask-tool`). A resume is run with the same, so its hook fires again."""

# What a resume whose transcript was lost is told after the slash command: the
# question and its answer, since nothing remembers them.
_COLD = """An earlier session on this ticket stopped to ask a person something, and was \
answered. Its commits, if it made any, are on this branch. Carry on from them.

{asked}
"""


def parse_questions(raw: bytes) -> list[Question]:
    """The questions in the `AskUserQuestion` input the hook wrote down."""
    asked: dict[str, Any] = json.loads(raw)
    return [
        Question(
            question=str(q["question"]),
            header=str(q.get("header", "")),
            options=[
                Choice(label=str(o["label"]), description=str(o.get("description", "")))
                for o in q.get("options", [])
            ],
            multi_select=bool(q.get("multiSelect", False)),
        )
        for q in asked.get("questions", [])
    ]


def question_comment(session: str, questions: Sequence[Question]) -> str:
    """The question comment: each question with its options, then the marker."""
    parts = [
        "**This ticket's session stopped to ask you something.** Answer from Wayfarer, or "
        f"reply here and remove the `{ASKED}` label, and it carries on where it asked."
    ]
    for q in questions:
        heading = f"### {q.header}: {q.question}" if q.header else f"### {q.question}"
        options = "\n".join(f"- **{o.label}**: {o.description}" for o in q.options)
        parts.append(f"{heading}\n\n{options}" if options else heading)
    held = {"session": session, "questions": [q.model_dump() for q in questions]}
    parts.append(f"<!-- wayfarer:question {_quoted(held)} -->")
    return "\n\n".join(parts) + "\n"


def answer_comment(session: str, answers: Mapping[str, str]) -> str:
    """The answer comment Wayfarer posts for a person: each answer, then the marker."""
    said = "\n\n".join(f"**{question}**\n\n{answer}" for question, answer in answers.items())
    held = {"session": session, "answers": dict(answers)}
    return f"Answered from Wayfarer.\n\n{said}\n\n<!-- wayfarer:answer {_quoted(held)} -->\n"


def _quoted(held: object) -> str:
    # `<` and `>` escaped, so nothing a session wrote can close the comment early.
    return json.dumps(held).replace("<", "\\u003c").replace(">", "\\u003e")


def latest(timeline: Sequence[Event]) -> Asking | None:
    """The ticket's latest question, as its timeline has it; None if it was never asked."""
    for at in range(len(timeline) - 1, -1, -1):
        asked = _question(timeline[at])
        if asked is not None:
            session, questions = asked
            return _answered(session, questions, timeline[at + 1 :])
    return None


def gist(timeline: Sequence[Event], upto: int) -> str | None:
    """The question asked before event `upto`, as a chronicle line quotes it."""
    for e in reversed(timeline[:upto]):
        asked = _question(e)
        if asked is not None:
            _, questions = asked
            return questions[0].question if questions else None
    return None


def resumed(asking: Asking) -> dict[str, str]:
    """What the hook hands back: an answer for each question, whether or not a person
    wrote one."""
    given = asking.answers or {}
    return {q.question: given.get(q.question) or _UNANSWERED for q in asking.questions}


def cold(asking: Asking, answers: Mapping[str, str]) -> str:
    """What a resume that starts cold is told: each question, and its answer."""
    asked = "\n\n".join(
        f"You asked: {q.question}\nThe answer: {answers[q.question]}" for q in asking.questions
    )
    return _COLD.format(asked=asked)


def _question(e: Event) -> tuple[str, list[Question]] | None:
    if e.kind != "IssueComment" or e.body is None:
        return None
    found = _QUESTION_MARK.search(e.body)
    if found is None:
        return None
    try:
        held = json.loads(found.group(1))
        questions = [Question.model_validate(q) for q in held["questions"]]
        return str(held["session"]), questions
    except (ValueError, KeyError, TypeError, ValidationError):
        return None  # A marker someone edited by hand says nothing to trust.


def _answered(session: str, questions: list[Question], after: Sequence[Event]) -> Asking:
    """The question as it stands after `after`: answered once the label came off."""
    unlabelled = next(
        (i for i, e in enumerate(after) if e.kind == "UnlabeledEvent" and e.subject == ASKED),
        None,
    )
    if unlabelled is None:
        return Asking(session=session, questions=questions, answered=False, answers=None)
    comments = [e.body for e in after[:unlabelled] if e.kind == "IssueComment" and e.body]
    return Asking(
        session=session,
        questions=questions,
        answered=True,
        answers=_answers(session, questions, comments),
    )


def _answers(session: str, questions: list[Question], comments: list[str]) -> dict[str, str]:
    for body in reversed(comments):
        found = _ANSWER_MARK.search(body)
        if found is None:
            continue
        try:
            held = json.loads(found.group(1))
        except ValueError:
            continue
        if held.get("session") == session and isinstance(held.get("answers"), dict):
            return {str(q): str(a) for q, a in held["answers"].items()}
    said = "\n\n".join(body.strip() for body in comments if _MARKED not in body)
    return {q.question: said for q in questions} if said else {}


class Asker:
    """Puts a session's question on its ticket, and a person's answer after it."""

    def __init__(self, github: GitHub, stream: Stream) -> None:
        self._github = github
        self._stream = stream

    async def asked(self, ticket: int, run_id: str, question: bytes | None) -> bool:
        """Whether session `run_id` on `ticket` ended to ask, as the question file it
        carried out says. If it did, its question is posted on the ticket and the ticket
        labelled asked, and the ending is this, never a hold.

        The comment comes first, so a read between the two never finds a label with no
        question."""
        if question is None:
            return False
        body = question_comment(run_id, parse_questions(question))
        await self._github.write("POST", f"/issues/{ticket}/comments", {"body": body})
        await self._github.write("POST", f"/issues/{ticket}/labels", {"labels": [ASKED]})
        return True

    async def answer(self, ticket: int, answers: Mapping[str, str]) -> None:
        """Answer `ticket`'s question as a person would on GitHub: the answer comment, then
        the label off, which is the signal. A ticket not waiting on one is left alone."""
        read = self._stream.get(f"ticket:{ticket}")
        if not isinstance(read, Ticket) or read.state is not TicketState.ASKED:
            return
        if read.question is None or read.question.answered:
            return
        body = answer_comment(read.question.session, answers)
        await self._github.write("POST", f"/issues/{ticket}/comments", {"body": body})
        await self._github.write("DELETE", f"/issues/{ticket}/labels/{ASKED}", {})
