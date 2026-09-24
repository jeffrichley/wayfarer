"""A session: one Waystation run against one ticket, `/implement` or a resolver.

The session is handed exactly the slash command a person would type, and
nothing inlined beside it: it reads its own ticket and parent spec itself, with
a read-only token, and reports back the Outcome (`outcome.py`).

Wayfarer attaches its own hooks to each run and writes no flow script
(ADR-0001). They record the session in the store the moment it starts, write
every event to the session's own append-only file whether or not anyone is
watching, and put the session's beats on the page's stream as they change.

A session's conversation is named by Wayfarer as it starts, so its transcript can
be found and carried out as its agent ends, sandbox still up, and carried back
into a later session that resumes it: a Continue, or an answered question (#20).
Nothing else about a conversation is Wayfarer's to know.
"""

from __future__ import annotations

import base64
import logging
import os
import re
import shlex
import uuid
from collections.abc import Callable, Mapping, Sequence
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

from wayfarer.asking import ASKING, QUESTION
from wayfarer.beats import fold
from wayfarer.changes import changed
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

__all__ = ["TRANSCRIPT", "AgentFor", "SessionEvent", "Sessions", "read_events", "replay"]

_log = logging.getLogger(__name__)

AgentFor = Callable[[Sequence[str]], AgentProvider]
"""The agent a session runs, given the arguments Wayfarer adds to its command line."""

TRANSCRIPT = "transcript.jsonl"
"""Where a session's transcript is kept among the files it carried out."""

# Where Claude Code keeps a conversation, under the home of whoever runs it: one
# directory per working directory, named for it (`_project`).
_PROJECTS = ".claude/projects"


def _now() -> datetime:
    return datetime.now(UTC)


def replay(row: SessionRow, stream: Stream) -> None:
    """Put a recorded session's beats and changes on `stream`, folded from its file as
    they were live."""
    events = read_events(row.event_file)
    for beat in fold(row.run_id, events):
        stream.upsert(beat)
    stream.upsert(changed(row.run_id, events))


class Sessions:
    """Sessions against one clone, each run by `agent` in `sandbox`, told on `stream`."""

    def __init__(
        self,
        clone: Path,
        store: Store,
        repo: Repo,
        *,
        agent: AgentFor,
        sandbox: SandboxBackend,
        settings: Settings,
        stream: Stream,
        carry_out: Sequence[str] = (),
    ) -> None:
        """`carry_out` names more files, by their path under the sandbox's home, that each
        session carries out beside its transcript."""
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
        self._agent_for = agent
        self._flow = Flow(clone, agent=agent(()), sandbox=sandbox, timeouts=bounds)
        self._carry_out = tuple(carry_out)
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
            agent=lambda args: ClaudeCode(args=(*ASKING, *args)),
            sandbox=DockerSandbox(image),
            settings=settings,
            stream=stream,
            carry_out=[QUESTION],
        )

    def spec(
        self,
        ticket: int,
        *,
        base: str = "HEAD",
        purpose: Purpose = Purpose.BUILD,
        prompt: str | None = None,
    ) -> RunSpec[Outcome]:
        """The run of `/implement` on `ticket` from `base`; awaiting it runs the session.
        `prompt` says more after the slash command, which only a retry has to say."""
        # The namespaced form: it is what the CLI advertises, and a bare
        # `/code-review` collides with a bundled CLI skill of that name.
        command = f"/mattpocock-skills:implement {ticket}"
        told = command if prompt is None else f"{command}\n\n{prompt}"
        return self._run(ticket, purpose, told, base, str(uuid.uuid4()), resuming=False)

    def resume(
        self,
        ticket: int,
        run_id: str,
        *,
        base: str,
        prompt: str,
        cold: str,
        purpose: Purpose,
        files_in: Mapping[str, bytes] | None = None,
    ) -> RunSpec[Outcome]:
        """A session carrying on session `run_id`'s conversation from `base`, told `prompt`.
        Its transcript goes in as the sandbox starts, with each of `files_in` at its path
        under the sandbox's home. With the transcript lost, it starts cold instead: a
        fresh conversation, told `cold` after the slash command."""
        row = self._store.session(run_id)
        transcript = self.carried(run_id, TRANSCRIPT)
        if row.conversation is None or transcript is None:
            return self.spec(ticket, base=base, purpose=purpose, prompt=cold)
        carrying = {_TRANSCRIPT_IN: transcript, **(files_in or {})}
        return self._run(ticket, purpose, prompt, base, row.conversation, resuming=True).hooks(
            _CarryIn(carrying, row.conversation)
        )

    def carried(self, run_id: str, path: str) -> bytes | None:
        """The file at `path` that session `run_id` carried out, or None if it did not."""
        kept = self._store.carried(run_id) / path
        return kept.read_bytes() if kept.is_file() else None

    def _run(
        self,
        ticket: int,
        purpose: Purpose,
        prompt: str,
        base: str,
        conversation: str,
        *,
        resuming: bool,
    ) -> RunSpec[Outcome]:
        recorder = _Recorder(
            self._store, self._stream, ticket, purpose, conversation, self._carry_out
        )
        return (
            self._flow.run(prompt, outcome=Outcome)
            .agent(self._agent(conversation, resuming=resuming))
            .base(base)
            .env(self._github())
            .hooks(recorder)
        )

    def _agent(self, conversation: str, *, resuming: bool) -> AgentProvider:
        """The one place a session's agent is made, so a resume runs it exactly as the
        session it resumes did, but for which conversation it names."""
        return self._agent_for(("--resume" if resuming else "--session-id", conversation))

    def resolver(self, ticket: int, *, onto: str, branch: str) -> RunSpec[Outcome]:
        """A resolver session: `ticket`'s commits on the host branch `branch` replayed onto
        `onto`, one at a time, conflicts and all. Its commits are kept, landing nowhere, for
        the merge queue to take again (Waystation ADR-0015)."""
        prompt = _RESOLVE.format(ticket=ticket, branch=branch)
        conversation = str(uuid.uuid4())
        return self._run(
            ticket, Purpose.RESOLVE, prompt, onto, conversation, resuming=False
        ).extra_refs(branch)

    def resolved(self, ticket: int) -> bool:
        """Whether `ticket` has had its one resolver session: one whose agent ran, or that
        never ended. A resolver the environment stopped before its agent started is not one."""
        return any(
            row.ticket == ticket
            and row.purpose is Purpose.RESOLVE
            and (
                row.ended is None or any(e.kind == "agent_end" for e in read_events(row.event_file))
            )
            for row in self._store.sessions()
        )

    def _github(self) -> dict[str, str]:
        """The session's `gh` reads its ticket and parent spec with the read-only token,
        as the only token it has; every write stays with Wayfarer. Read now, as the run
        is described, and never stored."""
        github = {"GH_REPO": str(self._repo)}
        if token := os.environ.get(SESSION_GH_TOKEN):
            github["GH_TOKEN"] = token
        return github


# A resolver's job is narrow: the ticket's own work, replayed, and nothing more.
_RESOLVE = """Ticket #{ticket}'s commits conflict with this branch, which moved on after they were \
written. They are on the branch `{branch}`. Replay them onto this branch one at a time, \
oldest first, with `git cherry-pick`, resolving each conflict so that both what this \
branch now holds and what the commit meant survive. Change nothing else. Then run \
`wf-test`, and fix only what the replay broke. Report `done` once every commit is \
replayed and `wf-test` passes, and `not_done` otherwise.
"""


# Where a resumed transcript goes among the files carried in: `_CarryIn` puts it
# where Claude Code looks for it from the sandbox's own working directory.
_TRANSCRIPT_IN = f"{_PROJECTS}/{{project}}/{{conversation}}.jsonl"


def _project(workspace: str) -> str:
    """The directory Claude Code keeps a working directory's conversations in: its path
    with every character but a letter or digit made a dash."""
    return re.sub(r"[^A-Za-z0-9]", "-", workspace)


class _CarryIn(HookBundle):
    """Puts files into a session's sandbox as it starts, each at its path under its home."""

    def __init__(self, files: Mapping[str, bytes], conversation: str) -> None:
        self._files = files
        self._conversation = conversation

    @override
    async def on_sandbox_ready(self, ctx: RunContext) -> None:
        sandbox = ctx.sandbox
        for template, content in self._files.items():
            path = template.format(
                project=_project(sandbox.workspace), conversation=self._conversation
            )
            script = 'mkdir -p "$(dirname "$HOME/$1")" && base64 -d > "$HOME/$1"'
            put = await sandbox.exec(
                [*sandbox.shell, script, "carry-in", path],
                stdin=base64.b64encode(content).decode(),
            )
            if put.exit_code != 0:
                # A resume without its transcript is not the session it claims to be.
                msg = f"Could not carry {path} into the sandbox: {put.stderr.strip()}"
                raise RuntimeError(msg)


async def _carry_out(ctx: RunContext, paths: Mapping[str, str], into: Path) -> None:
    """Each of `paths` found in the sandbox, by its pattern under its home, kept in `into`
    under its name. One that is missing is left out: a session need not have made it."""
    sandbox = ctx.sandbox
    for name, pattern in paths.items():
        # The pattern is Wayfarer's own, never the agent's, so it is spliced in unquoted
        # for the shell to expand.
        script = f'set -- "$HOME"/{pattern}; [ -f "$1" ] && base64 < "$1"'
        found = await sandbox.exec([*sandbox.shell, script])
        if found.exit_code != 0:
            continue
        kept = into / name
        kept.parent.mkdir(parents=True, exist_ok=True)
        kept.write_bytes(base64.b64decode("".join(found.stdout.split())))


class _Recorder(HookBundle):
    """Writes one session down: its row in the store, and its event file.

    It tells the session on the stream as it goes, folding every event so far
    after each one, exactly as a replay folds the file (`beats.py`). As the agent
    ends it carries the session's transcript out, with `carry_out` beside it.
    """

    def __init__(
        self,
        store: Store,
        stream: Stream,
        ticket: int,
        purpose: Purpose,
        conversation: str,
        carry_out: Sequence[str],
    ) -> None:
        self._store = store
        self._stream = stream
        self._ticket = ticket
        self._purpose = purpose
        self._conversation = conversation
        self._carry_out = {
            TRANSCRIPT: f"{_PROJECTS}/*/{shlex.quote(conversation)}.jsonl",
            **{path: shlex.quote(path) for path in carry_out},
        }
        self._file: Path | None = None
        self._run_id = ""
        self._events: list[SessionEvent] = []
        self._told: set[str] = set()

    @override
    def on_run_start(self, ctx: RunContext) -> None:
        self._run_id = ctx.run_id
        self._file = self._store.event_file(ctx.run_id)
        started = _now()
        self._store.session_started(
            ctx.run_id, self._ticket, self._purpose, started, self._file, self._conversation
        )
        self._write(SessionStarted(seq=0, at=started, ticket=self._ticket, prompt=ctx.prompt))

    @override
    def on_agent_output(self, ctx: RunContext, line: AgentLine) -> None:
        at = _now()
        for event in line.events:
            self._write(self._normalised(event, at))

    @override
    async def on_agent_end(self, ctx: RunContext, exit: AgentExit) -> None:
        try:
            await _carry_out(ctx, self._carry_out, self._store.carried(ctx.run_id))
        except Exception:
            # Losing the transcript costs a resume its memory, never the session its work.
            _log.warning("Session %s's files could not be carried out.", ctx.run_id, exc_info=True)
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
        """Put the session's beats and changes as they now stand on the stream (ADR-0004)."""
        self._stream.upsert(changed(self._run_id, self._events))
        beats = fold(self._run_id, self._events)
        for beat in beats:
            # An unchanged beat is not sent again (stream.Store.upsert).
            self._stream.upsert(beat)
        told = {beat.id for beat in beats}
        for gone in self._told - told:
            self._stream.remove(gone)
        self._told = told
