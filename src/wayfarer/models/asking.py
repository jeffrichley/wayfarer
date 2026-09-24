"""What a session asked by ending, and a person's answer to it (#19, #42)."""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = ["Answer", "Asking", "Choice", "Question"]


class Choice(BaseModel):
    """One answer a session offered."""

    label: str
    description: str = Field(description="What picking it means, as the session put it.")


class Question(BaseModel):
    """One thing a session asked: `AskUserQuestion` carries one to four."""

    question: str = Field(description="The question, whole; its answer is keyed by it.")
    header: str = Field(description="A short label for it, as the session gave one.")
    options: list[Choice]
    multi_select: bool = Field(description="Whether more than one option may be picked.")


class Asking(BaseModel):
    """A ticket's latest question, as its question comment on GitHub holds it. That
    comment and the `wayfarer:asked` label are the whole of the state (ADR-0002)."""

    session: str = Field(description="The run id of the session that asked.")
    questions: list[Question]
    answered: bool = Field(
        description="The label came off after the question was posted: a person answered, "
        "and the session resumes."
    )
    answers: dict[str, str] | None = Field(
        description="Each question's answer, keyed by the question; null until answered. "
        "Answered on GitHub by hand, every comment after the question answers each question."
    )


class Answer(BaseModel):
    """A person's answer to a ticket's question, sent from Wayfarer."""

    answers: dict[str, str] = Field(
        description="An answer for each question, keyed by the question: an option's label, "
        "or words of the person's own."
    )
