"""A session's story: its events folded into beats, grouped into Orient and cycles.

The fold is pure and beats are never stored (#8), as ADR-0003 derives rather
than stores. The same fold runs live, over
the events so far, and on replay, over the session's whole file, so a replay
can never disagree with what was watched live. A beat's id is the seq of its
first event, which is why re-folding keeps every id where it was.

- Consecutive reads and searches fold into one **Read**. Only another beat, or
  an edit, ends the run of them; a shell call that is no test run does not.
- An agent text block is a **Remark**.
- A test run is **Red** or **Green** by its exit status. A run is recognised
  only by the line `wf-test` prints last, the one text Wayfarer parses.
- Edits after a green that the next run keeps green are a **Refactor**, carrying
  that run. Otherwise the edits make no beat and the red opens the next cycle.
- One **Outcome** closes the session: the one it reported, or how it ended
  without one, cancelled or failed.
- A call with no result yet is **Working**, until its beat replaces it at the
  same id or it goes, having none, or the agent stops. Plumbing calls make nothing.

Chapter 0 is Orient: everything before the first red. A red after a green, or
the first red, opens the next cycle.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Any

from pydantic import ValidationError

from wayfarer.events import (
    AgentEnded,
    OutcomeSaid,
    SessionEnded,
    SessionEvent,
    Text,
    ToolResult,
    ToolUse,
)
from wayfarer.models import Beat, BeatKind, TestRun

__all__ = ["fold", "reported_run"]

# The line `wf-test` prints last (src/wayfarer/base/wf-test).
_SENTINEL = "::wf-test "

# A list of names longer than this reads as its first few "and N more": a beat is
# one sentence, and past three names a sentence stops being read.
_LISTED = 3


def fold(session: str, events: Iterable[SessionEvent]) -> list[Beat]:
    """Session `session`'s beats, in the order they happened."""
    story = _Story(session)
    for event in events:
        story.take(event)
    return story.beats()


@dataclass
class _Reading:
    """A run of reads and searches, told as the one Read beat its first call opened."""

    first: ToolUse
    files: list[str] = field(default_factory=list)
    searches: list[str] = field(default_factory=list)


class _Story:
    def __init__(self, session: str) -> None:
        self._session = session
        self._beats: dict[int, Beat] = {}
        self._pending: dict[str, ToolUse] = {}
        self._chapter = 0
        # None until the first test run, then whether the last one passed.
        self._last_green: bool | None = None
        self._edits_since_green: list[ToolUse] = []
        self._reading: _Reading | None = None
        self._closing: OutcomeSaid | None = None

    def beats(self) -> list[Beat]:
        return [self._beats[seq] for seq in sorted(self._beats)]

    def take(self, event: SessionEvent) -> None:
        match event:
            case Text(text=text) if text.strip():
                self._reading = None
                self._add(event, BeatKind.REMARK, text.strip())
            case ToolUse(tool="read" | "search"):
                self._read(event)
            case ToolUse(tool="edit"):
                self._reading = None
                if self._last_green:
                    self._edits_since_green.append(event)
                self._working(event, f"Editing {_file(event)}")
            case ToolUse(tool="shell"):
                self._working(event, _given(event, "description", "command") or event.name)
            case ToolResult():
                self._returned(event)
            case OutcomeSaid(raw=raw):
                self._reading = None
                self._closing = event
                summary = raw.get("summary") if isinstance(raw, dict) else None
                text = summary if isinstance(summary, str) else "Reported its outcome."
                self._add(event, BeatKind.OUTCOME, text)
            case AgentEnded():
                self._stopped(event)
            case SessionEnded():
                self._ended(event)
            case _:
                # The start, usage, silent text and plumbing calls.
                pass

    def _add(
        self,
        first: SessionEvent,
        kind: BeatKind,
        text: str,
        *,
        run: TestRun | None = None,
        output: str | None = None,
    ) -> None:
        self._beats[first.seq] = Beat(
            kind="beat",
            id=f"beat:{self._session}:{first.seq}",
            session=self._session,
            seq=first.seq,
            beat=kind,
            at=first.at,
            chapter=self._chapter,
            text=text,
            run=run,
            output=output,
        )

    def _working(self, call: ToolUse, text: str) -> None:
        self._pending[call.id] = call
        self._add(call, BeatKind.WORKING, text)

    def _read(self, call: ToolUse) -> None:
        reading = self._reading = self._reading or _Reading(call)
        if call.tool == "read":
            _once(reading.files, _file(call))
        else:
            _once(reading.searches, f"“{_given(call, 'pattern', 'query') or call.name}”")
        parts = []
        if reading.files:
            parts.append(f"Read {_listed(reading.files)}")
        if reading.searches:
            searched = "searched" if reading.files else "Searched"
            parts.append(f"{searched} for {_listed(reading.searches)}")
        self._add(reading.first, BeatKind.READ, "; ".join(parts))

    def _returned(self, result: ToolResult) -> None:
        call = self._pending.pop(result.id, None)
        if call is None:
            return
        del self._beats[call.seq]
        if call.tool == "shell" and (ran := _test_run(result.text)) is not None:
            run, output = ran
            self._reading = None
            self._tested(call, run, output)

    def _tested(self, call: ToolUse, run: TestRun, output: str) -> None:
        green = run.exit == 0
        if green and self._last_green and self._edits_since_green:
            first = self._edits_since_green[0]
            files: list[str] = []
            for edit in self._edits_since_green:
                _once(files, _file(edit))
            still = f"still {run.passed} passing" if run.passed is not None else "still passing"
            self._add(first, BeatKind.REFACTOR, f"Refactored {_listed(files)}; {still}", run=run)
        elif green:
            text = f"{run.passed} passing" if run.passed is not None else "Passing"
            self._add(call, BeatKind.GREEN, text, run=run)
        else:
            if self._last_green is not False:
                self._chapter += 1
            self._add(call, BeatKind.RED, _failing(run), run=run, output=output)
        self._last_green = green
        self._edits_since_green = []

    def _stopped(self, stop: AgentEnded) -> None:
        # Nothing is still working once the agent has stopped.
        for call in self._pending.values():
            del self._beats[call.seq]
        self._pending.clear()
        # A cancelled session has no end (events.SessionEnded), so it closes here.
        if stop.cancelled and self._closing is None:
            self._add(stop, BeatKind.OUTCOME, "Stopped before it reported an outcome.")

    def _ended(self, end: SessionEnded) -> None:
        if end.result == "failed":
            self._add(
                self._closing or end,
                BeatKind.OUTCOME,
                f"Ended without an outcome: it failed at {end.stage}.",
            )
        elif self._closing is None:
            self._add(end, BeatKind.OUTCOME, "Ended without an outcome.")


def reported_run(printed: str) -> TestRun | None:
    """The run `wf-test` reported in its own line, last in `printed`; None when it did not."""
    ran = _test_run(printed)
    return ran[0] if ran else None


def _test_run(printed: str) -> tuple[TestRun, str] | None:
    """The run `wf-test` reported last in `printed`, and everything else it printed."""
    lines = printed.splitlines()
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].startswith(_SENTINEL):
            try:
                run = TestRun.model_validate(json.loads(lines[index].removeprefix(_SENTINEL)))
            except (ValueError, ValidationError):
                return None
            return run, "\n".join(lines[:index] + lines[index + 1 :]).strip()
    return None


def _failing(run: TestRun) -> str:
    count = run.failed if run.failed is not None else len(run.failing) or None
    if count is None:
        return f"Failing, exit {run.exit}"
    if run.failing:
        return f"{count} failing: {_listed(run.failing)}"
    return f"{count} failing"


def _file(call: ToolUse) -> str:
    path = _given(call, "file_path", "notebook_path", "path")
    return PurePath(path).name if path else call.name


def _given(call: ToolUse, *names: str) -> str | None:
    """The first of `names` the call was given as a string, which is how it names its subject."""
    given: dict[str, Any] = call.input
    return next((v for n in names if isinstance(v := given.get(n), str) and v), None)


def _once(names: list[str], name: str) -> None:
    if name not in names:
        names.append(name)


def _listed(names: Sequence[str]) -> str:
    if len(names) > _LISTED:
        return f"{', '.join(names[: _LISTED - 1])} and {len(names) - _LISTED + 1} more"
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"
