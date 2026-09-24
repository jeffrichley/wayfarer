"""When a session goes wrong: whose failure it was decides what happens to its ticket.

If the agent actually ran, and crashed, reported nothing, ran out of time or was
stopped, the attempt failed: the ticket is Held with its work kept, on a draft pull
request when it left commits and in a comment when it left none. Anything else is
the environment's: the ticket goes back on the frontier with its automatic start
unspent, the cascade pauses, and one item is raised. A person retries a Held
ticket, continuing where it stopped or starting over (#41, deciding #20).

Each test serves Wayfarer with its sessions really running a scripted agent
(`cascading.py`), each ticket's sessions played from a list the test gives, and
reads the outcome back from GitHub, where it is kept (ADR-0002).
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pytest
from waystation import (
    AgentExited,
    CommandFailed,
    Errored,
    HookRaised,
    OutcomeInvalid,
    OutcomeMissing,
    Refused,
    RunFailed,
    TimedOut,
)
from waystation.agents import AgentCommand, AgentEvent
from waystation.testing import ScriptedAgent, ScriptedCommit

import cascading
from cascading import Gate, eventually, git, origin_clone
from conftest import Stream, post
from github_stand_in import LOGIN, GitHub, Issue, PullRequest
from wayfarer.endings import fault
from wayfarer.merge_queue import HELD_MARKER
from wayfarer.read_model import HELD
from wayfarer.store import Fault

pytestmark = pytest.mark.git

_DONE = {"status": "done", "summary": "Built it.", "open_findings": [], "assumptions": []}
_EFFORT_BRANCH = "effort/1-widgets"


def _widget(name: str = "widget.py") -> ScriptedCommit:
    return ScriptedCommit(message=f"Add {name}", files={name: f"# {name}\n"})


class _Broken:
    """An agent whose command cannot even be made: the agent never runs."""


@dataclass
class _Plays:
    """Each ticket's sessions, played in turn from the list a test gives; and what each
    session was handed, by ticket."""

    plays: dict[int, list[Any]] = field(default_factory=dict)
    handed: defaultdict[int, list[tuple[Sequence[str], str]]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def agent(self, args: Sequence[str]) -> _Played:
        return _Played(self, args)


@dataclass(frozen=True)
class _Played:
    plays: _Plays
    args: Sequence[str]

    def preflight(self) -> None:
        return None

    def command(self, prompt: str, outcome_schema: dict[str, Any]) -> AgentCommand:
        match = re.search(r"implement (\d+)", prompt)
        assert match is not None
        ticket = int(match[1])
        self.plays.handed[ticket].append((self.args, prompt))
        play = self.plays.plays[ticket].pop(0)
        if isinstance(play, _Broken):
            raise RuntimeError("The agent's command could not be made.")
        command: AgentCommand = play.command(prompt, outcome_schema)
        return command

    def parse(self, line: str) -> Sequence[AgentEvent]:
        return ScriptedAgent().parse(line)


def _printing() -> Any:
    """An agent that never stops printing, and never reports."""

    class Printing(ScriptedAgent):
        def command(self, prompt: str, outcome_schema: dict[str, Any]) -> AgentCommand:
            played = super().command(prompt, outcome_schema)
            return replace(played, script="while true; do echo tick; sleep 0.1; done")

    return Printing()


@dataclass
class _Wayfarer:
    url: str
    plays: _Plays
    clone: Path
    remote: Path


@pytest.fixture
def serve(tmp_path: Path, github: GitHub) -> Iterator[Any]:
    clone = origin_clone(tmp_path, github)
    serving: list[Any] = []

    def start(plays: dict[int, list[Any]], **settings: Any) -> _Wayfarer:
        played = _Plays(plays)
        context = cascading.serving(
            clone, tmp_path / "data", github, played.agent, Gate(), **settings
        )
        url = context.__enter__()
        serving.append(context)
        assert github.git is not None
        return _Wayfarer(url, played, clone, github.git)

    yield start
    for running in serving:
        running.__exit__(None, None, None)


def _page(url: str) -> Stream:
    return Stream(url, patience=20.0)


def _arm(url: str, effort: Issue) -> None:
    assert post(f"{url}api/efforts/{effort.number}/arm").status_code == 202


def _retry(url: str, ticket: Issue, start: str) -> None:
    assert post(f"{url}api/tickets/{ticket.number}/retry", {"start": start}).status_code == 202


def _pull(github: GitHub, ticket: Issue, *, state: str = "OPEN") -> PullRequest:
    [pull] = [p for p in github.pulls() if ticket.number in p.mentions and p.state == state]
    return pull


def _files(remote: Path, branch: str) -> list[str]:
    return git(remote, "ls-tree", "--name-only", branch).split()


def test_a_finished_session_opens_its_pull_request_from_its_ticket_branch_into_its_effort_branch(
    serve: Any, github: GitHub
) -> None:
    effort, (ticket,) = github.effort("Widgets", tickets=1)
    app = serve({ticket.number: [ScriptedAgent(outcome=_DONE, commits=[_widget()])]})

    with _page(app.url) as seen:
        _arm(app.url, effort)
        landing = seen.item(f"ticket:{ticket.number}", state="landing")

    pull = _pull(github, ticket)
    assert not pull.draft
    assert (pull.head, pull.base) == ("ticket/2-ticket-1", _EFFORT_BRANCH)
    assert landing["pull_request"]["number"] == pull.number
    # The effort branch was made at the trunk, and the ticket branch carries its work.
    assert git(app.remote, "rev-parse", _EFFORT_BRANCH) == git(app.remote, "rev-parse", "main")
    assert _files(app.remote, pull.head) == ["README.md", "widget.py"]
    assert HELD not in github.labels(ticket.number)


def test_an_attempt_that_failed_with_commits_opens_a_draft_saying_what_happened_then_the_summary_then_the_output(  # noqa: E501 - the behaviour, said whole
    serve: Any, github: GitHub
) -> None:
    effort, (ticket,) = github.effort("Widgets", tickets=1)
    crashing = ScriptedAgent(
        lines=["Reading the ticket.", "Writing the widget."],
        # Left for salvage to commit, so the output is only what the agent said.
        uncommitted={"widget.py": "# widget.py\n"},
        outcome={**_DONE, "summary": "Half the widget."},
        exit_code=3,
    )
    app = serve({ticket.number: [crashing]})

    with _page(app.url) as seen:
        _arm(app.url, effort)
        held = seen.item(f"ticket:{ticket.number}", state="held")

    pull = _pull(github, ticket)
    assert pull.draft
    assert pull.body == (
        f"For #{ticket.number}.\n"
        "\n"
        "**Held: The agent exited with code 3 before it reported.**\n"
        "\n"
        "## The last summary\n"
        "\n"
        "Half the widget.\n"
        "\n"
        "## The end of the output\n"
        "\n"
        "````text\n"
        "Reading the ticket.\n"
        "Writing the widget.\n"
        "````\n"
    )
    assert _files(app.remote, pull.head) == ["README.md", "widget.py"]
    # Still claimed, so still nobody else's to start.
    assert held["assignees"] == [LOGIN]


def test_an_attempt_that_left_no_commits_is_held_with_a_comment_saying_what_happened(
    serve: Any, github: GitHub
) -> None:
    effort, (ticket,) = github.effort("Widgets", tickets=1)
    app = serve({ticket.number: [ScriptedAgent(lines=["Thinking."])]})

    with _page(app.url) as seen:
        _arm(app.url, effort)
        seen.item(f"ticket:{ticket.number}", state="held")

    assert github.pulls() == []
    assert ticket.comments[-1] == f"**Held: The agent stopped without reporting.**\n\n{HELD_MARKER}"


@pytest.mark.parametrize(
    ("agent", "cap", "said"),
    [
        (ScriptedAgent(commits=[_widget()], linger=True), "session_silence", "printed nothing"),
        (_printing(), "session_wall", "ran out of time after 1 s"),
    ],
    ids=["silence", "wall"],
)
def test_a_session_past_a_time_cap_is_stopped_and_held_with_its_work_kept(
    serve: Any, github: GitHub, agent: Any, cap: str, said: str
) -> None:
    effort, (ticket,) = github.effort("Widgets", tickets=1)
    app = serve({ticket.number: [agent]}, **{cap: 1.0})

    with _page(app.url) as seen:
        _arm(app.url, effort)
        seen.item(f"ticket:{ticket.number}", state="held")

    held = ticket.comments[-1] if not github.pulls() else _pull(github, ticket).body
    assert said in held
    if cap == "session_silence":
        # What it committed before it went quiet is on its draft.
        assert _files(app.remote, _pull(github, ticket).head) == ["README.md", "widget.py"]


def test_a_failure_of_the_environment_sends_the_ticket_back_unspent_pauses_and_raises_one_item(
    serve: Any, github: GitHub
) -> None:
    effort, (ticket,) = github.effort("Widgets", tickets=1)
    # The agent's command cannot be made: the agent stage fails, but the agent never ran,
    # so by its type the failure is the environment's.
    app = serve({ticket.number: [_Broken(), ScriptedAgent(outcome=_DONE, commits=[_widget()])]})

    with _page(app.url) as seen:
        _arm(app.url, effort)
        cascade = seen.item(f"cascade:{effort.number}", paused=True)
        raised = seen.item("environment:session")
        released = seen.item(f"ticket:{ticket.number}", assignees=[], state="takeable")

        assert f"#{ticket.number}" in cascade["reason"]
        assert raised["kind"] == "environment"
        assert "went back on the frontier" in raised["reason"]
        assert HELD not in released["labels"]
        assert github.pulls() == []

        # Resumed, the cascade starts it again: its automatic start was never spent.
        post(f"{app.url}api/efforts/{effort.number}/resume")
        seen.item(f"ticket:{ticket.number}", state="landing")

    assert len(app.plays.handed[ticket.number]) == 2


def test_an_effort_branch_that_cannot_be_made_starts_no_session_and_spends_nothing(
    serve: Any, github: GitHub
) -> None:
    effort, (ticket,) = github.effort("Widgets", tickets=1)
    app = serve({ticket.number: [ScriptedAgent(outcome=_DONE, commits=[_widget()])]})
    refusing = app.remote / "hooks" / "pre-receive"
    refusing.write_text("#!/bin/sh\necho 'pushes are off' >&2\nexit 1\n")
    refusing.chmod(0o755)

    with _page(app.url) as seen:
        _arm(app.url, effort)
        raised = seen.item("environment:session")
        seen.item(f"ticket:{ticket.number}", assignees=[], state="takeable")
        assert "pushes are off" in raised["failed"][0]["detail"]
        assert app.plays.handed[ticket.number] == []

        # Once GitHub takes pushes again, resuming starts it after all.
        refusing.unlink()
        post(f"{app.url}api/efforts/{effort.number}/resume")
        seen.item(f"ticket:{ticket.number}", state="landing")


def test_a_retry_the_environment_failed_is_held_again_rather_than_stranded(
    serve: Any, github: GitHub
) -> None:
    effort, (ticket,) = github.effort("Widgets", tickets=1)
    app = serve({ticket.number: [ScriptedAgent(commits=[_widget()], exit_code=3), _Broken()]})

    with _page(app.url) as seen:
        _arm(app.url, effort)
        seen.item(f"ticket:{ticket.number}", state="held")
        _retry(app.url, ticket, "continue")
        raised = seen.item("environment:session")
        # Its automatic start is long spent, so on the frontier nothing would start it.
        held = seen.item(f"ticket:{ticket.number}", state="held")

    assert "held it again" in raised["reason"]
    assert held["assignees"] == [LOGIN]
    assert ticket.comments[-1].startswith("**Held: A retry could not run:")


def test_stopping_a_session_holds_its_ticket_with_its_work_on_a_draft(
    serve: Any, github: GitHub, tmp_path: Path
) -> None:
    effort, (ticket,) = github.effort("Widgets", tickets=1)
    working = tmp_path / "working"
    lingering = ScriptedAgent(commits=[_widget()], linger=True, linger_touch=str(working))
    app = serve({ticket.number: [lingering]})

    with _page(app.url) as seen:
        _arm(app.url, effort)
        # It lingers only once its work is committed.
        eventually(working.exists)
        post(f"{app.url}api/tickets/{ticket.number}/stop")
        seen.item(f"ticket:{ticket.number}", state="held")

    pull = _pull(github, ticket)
    assert pull.draft
    assert pull.body.startswith(f"For #{ticket.number}.\n\n**Held: You stopped it.**")
    assert _files(app.remote, pull.head) == ["README.md", "widget.py"]


def test_retrying_to_continue_goes_on_with_its_draft_and_opens_it_ready_once_done(
    serve: Any, github: GitHub
) -> None:
    effort, (ticket,) = github.effort("Widgets", tickets=1)
    crashing = ScriptedAgent(commits=[_widget()], exit_code=3)
    finishing = ScriptedAgent(outcome=_DONE, commits=[_widget("gadget.py")])
    app = serve({ticket.number: [crashing, finishing]})

    with _page(app.url) as seen:
        _arm(app.url, effort)
        seen.item(f"ticket:{ticket.number}", state="held")
        draft = _pull(github, ticket)
        # A person's start: it runs though the cascade is paused.
        post(f"{app.url}api/efforts/{effort.number}/pause")
        seen.item(f"cascade:{effort.number}", paused=True)
        _retry(app.url, ticket, "continue")
        seen.item(f"ticket:{ticket.number}", state="landing")

    pull = _pull(github, ticket)
    assert pull.number == draft.number
    assert not pull.draft
    assert pull.body == f"For #{ticket.number}.\n\nBuilt it.\n"
    # It went on from the draft's head, so both sessions' work is on the branch.
    assert _files(app.remote, pull.head) == ["README.md", "gadget.py", "widget.py"]
    (_, first), (args, prompt) = app.plays.handed[ticket.number]
    assert "The agent exited with code 3 before it reported." in prompt
    assert first == f"/mattpocock-skills:implement {ticket.number}"
    # No transcript came out of this sandbox, so it started cold, on a new conversation.
    assert args[0] == "--session-id"


def test_retrying_to_start_over_closes_the_draft_and_starts_afresh_on_the_effort_branch(
    serve: Any, github: GitHub
) -> None:
    effort, (ticket,) = github.effort("Widgets", tickets=1)
    crashing = ScriptedAgent(commits=[_widget()], exit_code=3)
    finishing = ScriptedAgent(outcome=_DONE, commits=[_widget("gadget.py")])
    app = serve({ticket.number: [crashing, finishing]})

    with _page(app.url) as seen:
        _arm(app.url, effort)
        seen.item(f"ticket:{ticket.number}", state="held")
        draft = _pull(github, ticket)
        _retry(app.url, ticket, "start_over")
        seen.item(f"ticket:{ticket.number}", state="landing")

    assert _pull(github, ticket, state="CLOSED").number == draft.number
    pull = _pull(github, ticket)
    assert not pull.draft
    # Afresh: the first session's work is not on the branch, though it is kept locally.
    assert _files(app.remote, pull.head) == ["README.md", "gadget.py"]
    kept = git(app.clone, "branch", "--list", "waystation/*", "--format=%(refname:short)")
    assert any(
        "widget.py" in git(app.clone, "ls-tree", "--name-only", branch).split()
        for branch in kept.split()
    )
    _, (_, prompt) = app.plays.handed[ticket.number]
    assert prompt == f"/mattpocock-skills:implement {ticket.number}"


def test_a_ticket_that_is_not_held_is_not_retried(serve: Any, github: GitHub) -> None:
    effort, (ticket,) = github.effort("Widgets", tickets=1)
    app = serve({ticket.number: [ScriptedAgent(outcome=_DONE, commits=[_widget()])]})

    with _page(app.url) as seen:
        _arm(app.url, effort)
        seen.item(f"ticket:{ticket.number}", state="landing")
        _retry(app.url, ticket, "start_over")
        post(f"{app.url}api/efforts/{effort.number}/read")
        seen.item(f"ticket:{ticket.number}", state="landing")

    eventually(lambda: len(app.plays.handed[ticket.number]) == 1)
    assert len(github.pulls()) == 1


def _failed(failure: Any) -> RunFailed:
    return RunFailed(
        run_id="r",
        name=None,
        base_sha=None,
        elapsed={},
        agent=None,
        series=None,
        preserved=None,
        stage="agent",
        failure=failure,
    )


@pytest.mark.parametrize(
    ("failure", "whose"),
    [
        (AgentExited(exit_code=1, stdout_tail="", stderr_tail=""), Fault.ATTEMPT),
        (OutcomeMissing(stdout_tail=""), Fault.ATTEMPT),
        (OutcomeInvalid(raw={}, error=None), Fault.ATTEMPT),  # type: ignore[arg-type]
        (TimedOut(bound="agent_silence", limit=1, elapsed=1), Fault.ATTEMPT),
        (TimedOut(bound="agent_wall", limit=1, elapsed=1), Fault.ATTEMPT),
        (Refused(reason="nonlinear_series", detail=""), Fault.ATTEMPT),
        (TimedOut(bound="workspace", limit=1, elapsed=1), Fault.ENVIRONMENT),
        (Refused(reason="dirty_tree", detail=""), Fault.ENVIRONMENT),
        (CommandFailed(argv=["git"], exit_code=1, stderr_tail=""), Fault.ENVIRONMENT),
        (Errored(exception=RuntimeError()), Fault.ENVIRONMENT),
        (HookRaised(hook="run_start", function="f", exception=RuntimeError()), Fault.ENVIRONMENT),
    ],
)
def test_whose_failure_it_was_is_decided_by_its_type_never_its_stage(
    failure: Any, whose: Fault
) -> None:
    assert fault(_failed(failure)) is whose
