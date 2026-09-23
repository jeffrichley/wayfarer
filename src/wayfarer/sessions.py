"""A session: one Waystation run of `/implement` against one ticket.

The session is handed exactly the slash command a person would type, and
nothing inlined beside it: it reads its own ticket and parent spec itself, with
a read-only token, and reports back the Outcome (`outcome.py`).

Wayfarer attaches its own hooks to each run and writes no flow script
(ADR-0001). They record the session in the store the moment it starts, write
every event to the session's own append-only file whether or not anyone is
watching, and put the session's beats on the page's stream as they change.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, override

from waystation import (
    AgentExit,
    AgentProvider,
    ClaudeCode,
    DockerSandbox,
    Flow,
    HookBundle,
    RunConflicted,
    RunContext,
    RunFailed,
    RunResult,
    RunSpec,
    SandboxBackend,
    Timeouts,
)
from waystation.agents import (
    AgentEvent,
    AgentLine,
    AgentText,
    AgentToolResult,
    AgentToolUse,
    OutcomeReported,
)
from waystation.results import AgentUsage

from wayfarer.beats import fold
from wayfarer.events import (
    AgentEnded,
    OutcomeSaid,
    SessionEnded,
    SessionEvent,
    SessionStarted,
    Text,
    ToolResult,
    ToolUse,
    Usage,
    read_events,
)
from wayfarer.gate import SESSION_GH_TOKEN
from wayfarer.github import Repo
from wayfarer.outcome import Outcome
from wayfarer.settings import Settings
from wayfarer.store import Purpose, SessionRow, Store
from wayfarer.stream import Store as Stream

__all__ = ["SessionEvent", "Sessions", "read_events", "replay"]


def _now() -> datetime:
    return datetime.now(UTC)


def replay(row: SessionRow, stream: Stream) -> None:
    """Put a recorded session's beats on `stream`, folded from its file as they were live."""
    for beat in fold(row.run_id, read_events(row.event_file)):
        stream.upsert(beat)


class Sessions:
    """Sessions against one clone, each run by `agent` in `sandbox`, told on `stream`."""

    def __init__(
        self,
        clone: Path,
        store: Store,
        repo: Repo,
        *,
        agent: AgentProvider,
        sandbox: SandboxBackend,
        settings: Settings,
        stream: Stream,
    ) -> None:
        stage = settings.stage_timeout
        bounds = Timeouts(
            workspace=stage,
            sandbox=stage,
            agent_silence=settings.session_silence,
            agent_wall=settings.session_wall,
            collect=stage,
            integrate=stage,
            # Teardown is the end of the sandbox stage, so it shares its cap.
            teardown=stage,
        )
        self._flow = Flow(clone, agent=agent, sandbox=sandbox, timeouts=bounds)
        self._store = store
        self._repo = repo
        self._stream = stream

    @classmethod
    def in_image(
        cls,
        clone: Path,
        store: Store,
        repo: Repo,
        image: str,
        settings: Settings,
        stream: Stream,
    ) -> Sessions:
        """Real sessions: Claude Code, in a container of the session image (ADR-0005)."""
        return cls(
            clone,
            store,
            repo,
            agent=ClaudeCode(),
            sandbox=DockerSandbox(image),
            settings=settings,
            stream=stream,
        )

    def spec(self, ticket: int) -> RunSpec[Outcome]:
        """The run of `/implement` on `ticket`; awaiting it runs the session."""
        # The namespaced form: it is what the CLI advertises, and a bare
        # `/code-review` collides with a bundled CLI skill of that name.
        prompt = f"/mattpocock-skills:implement {ticket}"
        recorder = _Recorder(self._store, self._stream, ticket, Purpose.BUILD)
        # The session's `gh` reads its ticket and parent spec with the read-only
        # token, as the only token it has; every write stays with Wayfarer. Read
        # now, as the run is described, and never stored.
        github = {"GH_REPO": str(self._repo)}
        if token := os.environ.get(SESSION_GH_TOKEN):
            github["GH_TOKEN"] = token
        return self._flow.run(prompt, outcome=Outcome).env(github).hooks(recorder)


class _Recorder(HookBundle):
    """Writes one session down: its row in the store, and its event file.

    It tells the session on the stream as it goes, folding every event so far
    after each one, exactly as a replay folds the file (`beats.py`).
    """

    def __init__(self, store: Store, stream: Stream, ticket: int, purpose: Purpose) -> None:
        self._store = store
        self._stream = stream
        self._ticket = ticket
        self._purpose = purpose
        self._file: Path | None = None
        self._run_id = ""
        self._events: list[SessionEvent] = []
        self._told: set[str] = set()

    @override
    def on_run_start(self, ctx: RunContext) -> None:
        self._run_id = ctx.run_id
        self._file = self._store.event_file(ctx.run_id)
        started = _now()
        self._store.session_started(ctx.run_id, self._ticket, self._purpose, started, self._file)
        self._write(SessionStarted(seq=0, at=started, ticket=self._ticket, prompt=ctx.prompt))

    @override
    def on_agent_output(self, ctx: RunContext, line: AgentLine) -> None:
        at = _now()
        for event in line.events:
            self._write(self._normalised(event, at))

    @override
    def on_agent_end(self, ctx: RunContext, exit: AgentExit) -> None:
        self._write(
            AgentEnded(
                seq=self._seq,
                at=_now(),
                exit_code=exit.exit_code,
                hanging=exit.hanging,
                cancelled=exit.cancelled,
            )
        )

    def _normalised(
        self, event: AgentEvent, at: datetime
    ) -> Text | ToolUse | ToolResult | OutcomeSaid | Usage:
        seq = self._seq
        match event:
            case AgentText(text=text):
                return Text(seq=seq, at=at, text=text)
            case AgentToolUse(name=name, input=given, id=id, kind=tool):
                return ToolUse(seq=seq, at=at, id=id, name=name, tool=tool, input=dict(given))
            case AgentToolResult(id=id, is_error=is_error, text=text):
                return ToolResult(seq=seq, at=at, id=id, is_error=is_error, text=text)
            case OutcomeReported(raw=raw):
                return OutcomeSaid(seq=seq, at=at, raw=raw)
            case AgentUsage():
                return Usage(
                    seq=seq,
                    at=at,
                    input_tokens=event.input_tokens,
                    output_tokens=event.output_tokens,
                    turns=event.turns,
                )

    @override
    def on_run_end(self, ctx: RunContext, result: RunResult[Any]) -> None:
        ended = _now()
        if isinstance(result, RunFailed):
            event = SessionEnded(
                seq=self._seq,
                at=ended,
                result="failed",
                stage=result.stage,
                failure=repr(result.failure),
            )
            outcome = None
        else:
            kind: Literal["succeeded", "conflicted"] = (
                "conflicted" if isinstance(result, RunConflicted) else "succeeded"
            )
            event = SessionEnded(seq=self._seq, at=ended, result=kind, stage=None, failure=None)
            outcome = result.outcome
        self._write(event)
        self._store.session_ended(ctx.run_id, ended, outcome)

    @property
    def _seq(self) -> int:
        return len(self._events)

    def _write(self, event: SessionEvent) -> None:
        assert self._file is not None
        with self._file.open("a", encoding="utf-8") as file:
            file.write(event.model_dump_json() + "\n")
        self._events.append(event)
        self._tell()

    def _tell(self) -> None:
        """Put the session's beats as they now stand on the stream (ADR-0004)."""
        beats = fold(self._run_id, self._events)
        for beat in beats:
            # An unchanged beat is not sent again (stream.Store.upsert).
            self._stream.upsert(beat)
        told = {beat.id for beat in beats}
        for gone in self._told - told:
            self._stream.remove(gone)
        self._told = told
