"""A session: one Waystation run of `/implement` against one ticket.

The session is handed exactly the slash command a person would type, and
nothing inlined beside it: it reads its own ticket and parent spec itself, with
a read-only token, and reports back the Outcome (`outcome.py`).

Wayfarer attaches its own hooks to each run and writes no flow script
(ADR-0001). They record the session in the store the moment it starts, and
write every event to the session's own append-only file whether or not anyone
is watching.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal, override

from pydantic import BaseModel, Field, TypeAdapter
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
    AgentToolKind,
    AgentToolResult,
    AgentToolUse,
    OutcomeReported,
)
from waystation.results import AgentUsage

from wayfarer.gate import SESSION_GH_TOKEN
from wayfarer.github import Repo
from wayfarer.outcome import Outcome
from wayfarer.settings import Settings
from wayfarer.store import Purpose, Store

__all__ = ["SessionEvent", "Sessions", "read_events"]


# Each event is stamped with `seq`, its place in the file, and `at`, when
# Wayfarer received it. They are normalised events, never beats: beats are
# derived from them, and never stored.


class RunStarted(BaseModel):
    """The session began, handed `prompt`."""

    kind: Literal["run_start"] = "run_start"
    seq: int
    at: datetime
    ticket: int
    prompt: str


class Text(BaseModel):
    """Something the agent said."""

    kind: Literal["text"] = "text"
    seq: int
    at: datetime
    text: str


class ToolUse(BaseModel):
    """A tool the agent called. `id` pairs it with its `tool_result`."""

    kind: Literal["tool_use"] = "tool_use"
    seq: int
    at: datetime
    id: str
    name: str
    tool: AgentToolKind = Field(description="What the tool does, whichever agent it is.")
    input: dict[str, Any]


class ToolResult(BaseModel):
    """What a tool the agent called returned."""

    kind: Literal["tool_result"] = "tool_result"
    seq: int
    at: datetime
    id: str
    is_error: bool
    text: str


class OutcomeSaid(BaseModel):
    """The Outcome the agent reported, as it said it, before it was validated."""

    kind: Literal["outcome"] = "outcome"
    seq: int
    at: datetime
    raw: Any


class Usage(BaseModel):
    """What the agent reported spending so far."""

    kind: Literal["usage"] = "usage"
    seq: int
    at: datetime
    input_tokens: int
    output_tokens: int
    turns: int | None


class AgentEnded(BaseModel):
    """The agent stopped: `exit_code` is -1 when it was stopped rather than exited."""

    kind: Literal["agent_end"] = "agent_end"
    seq: int
    at: datetime
    exit_code: int
    hanging: bool
    cancelled: bool


class RunEnded(BaseModel):
    """The session ended, and how: `succeeded`, `conflicted` or `failed`.

    A cancelled session has no end: Waystation reports nothing for it.
    """

    kind: Literal["run_end"] = "run_end"
    seq: int
    at: datetime
    result: Literal["succeeded", "conflicted", "failed"]
    stage: str | None = Field(description="Where a failed session failed; null otherwise.")
    failure: str | None = Field(description="How a failed session failed; null otherwise.")


SessionEvent = Annotated[
    RunStarted | Text | ToolUse | ToolResult | OutcomeSaid | Usage | AgentEnded | RunEnded,
    Field(discriminator="kind"),
]

_EVENT: TypeAdapter[SessionEvent] = TypeAdapter(SessionEvent)


def read_events(path: Path) -> list[SessionEvent]:
    """Every event in a session's file, in the order it was written."""
    return [_EVENT.validate_json(line) for line in path.read_text().splitlines()]


def _now() -> datetime:
    return datetime.now(UTC)


class Sessions:
    """Sessions against one clone, each run by `agent` in `sandbox`."""

    def __init__(
        self,
        clone: Path,
        store: Store,
        repo: Repo,
        *,
        agent: AgentProvider,
        sandbox: SandboxBackend,
        settings: Settings,
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

    @classmethod
    def in_image(
        cls, clone: Path, store: Store, repo: Repo, image: str, settings: Settings
    ) -> Sessions:
        """Real sessions: Claude Code, in a container of the session image (ADR-0005)."""
        return cls(
            clone, store, repo, agent=ClaudeCode(), sandbox=DockerSandbox(image), settings=settings
        )

    def spec(self, ticket: int) -> RunSpec[Outcome]:
        """The run of `/implement` on `ticket`; awaiting it runs the session."""
        # The namespaced form: it is what the CLI advertises, and a bare
        # `/code-review` collides with a bundled CLI skill of that name.
        prompt = f"/mattpocock-skills:implement {ticket}"
        recorder = _Recorder(self._store, ticket, Purpose.BUILD)
        # The session's `gh` reads its ticket and parent spec with the read-only
        # token, as the only token it has; every write stays with Wayfarer. Read
        # now, as the run is described, and never stored.
        github = {"GH_REPO": str(self._repo)}
        if token := os.environ.get(SESSION_GH_TOKEN):
            github["GH_TOKEN"] = token
        return self._flow.run(prompt, outcome=Outcome).env(github).hooks(recorder)


class _Recorder(HookBundle):
    """Writes one session down: its row in the store, and its event file."""

    def __init__(self, store: Store, ticket: int, purpose: Purpose) -> None:
        self._store = store
        self._ticket = ticket
        self._purpose = purpose
        self._file: Path | None = None
        self._seq = 0

    @override
    def on_run_start(self, ctx: RunContext) -> None:
        self._file = self._store.directory / "sessions" / f"{ctx.run_id}.jsonl"
        self._file.parent.mkdir(parents=True, exist_ok=True)
        started = _now()
        self._store.session_started(ctx.run_id, self._ticket, self._purpose, started, self._file)
        self._write(RunStarted(seq=0, at=started, ticket=self._ticket, prompt=ctx.prompt))

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

    def _normalised(self, event: AgentEvent, at: datetime) -> BaseModel:
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
            event = RunEnded(
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
            event = RunEnded(seq=self._seq, at=ended, result=kind, stage=None, failure=None)
            outcome = result.outcome
        self._write(event)
        self._store.session_ended(ctx.run_id, ended, outcome)

    def _write(self, event: BaseModel) -> None:
        assert self._file is not None
        with self._file.open("a", encoding="utf-8") as file:
            file.write(event.model_dump_json() + "\n")
        self._seq += 1
