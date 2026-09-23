"""The pull request gate: a finished session's pull request opens ready or as a draft.

Nothing on the HTTP surface opens a pull request: the cascade does, as each
session ends (#37). Until then the seam is the gate itself, driven against the
stand-in as the cascade will drive it, and what it opened is read back from
GitHub, which is the only place the decision is kept (ADR-0002).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from github_stand_in import TOKEN, GitHub, PullRequest
from wayfarer.github import GitHub as Client
from wayfarer.github import Repo
from wayfarer.models import TicketState
from wayfarer.outcome import Outcome
from wayfarer.pull_requests import PullRequestGate
from wayfarer.read_model import HELD, read_effort
from wayfarer.settings import Settings

pytestmark = pytest.mark.unit

_EFFORT_BRANCH = "effort/1-widgets"


def _client(github: GitHub) -> Client:
    return Client(
        Repo(github.owner, github.name), Settings(github_api=github.api, github_token=TOKEN)
    )


def _finding(axis: str, kind: str, **fields: Any) -> dict[str, Any]:
    return {"axis": axis, "kind": kind, "what": f"A {axis} {kind}.", "cites": "A rule"} | fields


def _outcome(status: str = "done", findings: list[dict[str, Any]] | None = None) -> Outcome:
    return Outcome.model_validate(
        {
            "status": status,
            "summary": "Added the widget.",
            "open_findings": findings or [],
            "assumptions": [],
        }
    )


def _open(github: GitHub, outcome: Outcome) -> tuple[PullRequest, TicketState]:
    """The pull request the gate opens for a session on a fresh ticket, and the
    state the ticket reads as afterwards."""
    spec, (ticket,) = github.effort("Widgets", tickets=1)
    client = _client(github)

    async def open_and_read() -> TicketState:
        await PullRequestGate(client).open(
            ticket=ticket.number,
            title=ticket.title,
            branch=f"ticket/{ticket.number}-widget",
            effort_branch=_EFFORT_BRANCH,
            outcome=outcome,
        )
        _, (read,), _ = await read_effort(client, spec.number, per_page=50, auto_merge=True)
        return read.state

    state = asyncio.run(open_and_read())
    [pull] = github.pulls()
    return pull, state


def test_a_finished_session_with_nothing_blocking_opens_a_ready_pull_request_on_the_effort_branch(
    github: GitHub,
) -> None:
    pull, state = _open(github, _outcome())

    assert not pull.draft
    assert pull.base == _EFFORT_BRANCH
    assert pull.head.startswith("ticket/")
    assert pull.title == "Ticket 1"
    assert state == TicketState.LANDING


def test_an_unfinished_session_opens_a_draft_and_holds_its_ticket(github: GitHub) -> None:
    pull, state = _open(github, _outcome(status="not_done"))

    assert pull.draft
    assert github.labels(pull.mentions[0]) == [HELD]
    assert state == TicketState.HELD


@pytest.mark.parametrize(
    ("axis", "kind", "draft"),
    [
        ("spec", "blocking", True),
        # Any spec finding blocks, whatever the session called it.
        ("spec", "judgement", True),
        ("standards", "blocking", True),
        ("standards", "judgement", False),
    ],
)
def test_a_spec_finding_or_a_standard_breach_always_blocks_and_a_judgement_call_never_does(
    github: GitHub, axis: str, kind: str, draft: bool
) -> None:
    pull, state = _open(github, _outcome(findings=[_finding(axis, kind)]))

    assert pull.draft is draft
    assert state == (TicketState.HELD if draft else TicketState.LANDING)


def test_the_body_carries_the_summary_the_findings_by_axis_with_citations_and_the_assumptions(
    github: GitHub,
) -> None:
    outcome = Outcome.model_validate(
        {
            "status": "done",
            "summary": "Added the widget.\n\nTested at the HTTP surface.",
            "open_findings": [
                {
                    "axis": "standards",
                    "kind": "judgement",
                    "what": "The helper is long.",
                    "cites": "Keep functions short",
                },
                {
                    "axis": "spec",
                    "kind": "blocking",
                    "what": "Widgets past the limit are accepted.",
                    "cites": "A widget past the limit is refused",
                    "file": "src/widgets.py",
                    "line": 12,
                },
                {
                    "axis": "standards",
                    "kind": "blocking",
                    "what": "A bound is a bare number.",
                    "cites": "Every bound is a named setting.",
                    "file": "src/widgets.py",
                },
            ],
            "assumptions": [
                {"what": "Widgets are counted per repo.", "why": "The spec is silent."}
            ],
        }
    )

    pull, _ = _open(github, outcome)

    assert pull.body == (
        "For #2.\n"
        "\n"
        "Added the widget.\n"
        "\n"
        "Tested at the HTTP surface.\n"
        "\n"
        "## Findings\n"
        "\n"
        "### Spec\n"
        "\n"
        "- **Blocking:** Widgets past the limit are accepted. (`src/widgets.py:12`)\n"
        "  > A widget past the limit is refused\n"
        "\n"
        "### Standards\n"
        "\n"
        "- **Judgement call:** The helper is long.\n"
        "  > Keep functions short\n"
        "- **Blocking:** A bound is a bare number. (`src/widgets.py`)\n"
        "  > Every bound is a named setting.\n"
        "\n"
        "## Assumed\n"
        "\n"
        "- **Widgets are counted per repo.** The spec is silent.\n"
    )


def test_a_body_with_nothing_left_open_is_the_summary_alone(github: GitHub) -> None:
    pull, _ = _open(github, _outcome())

    assert pull.body == "For #2.\n\nAdded the widget.\n"
