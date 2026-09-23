"""The rules the HTTP surface cannot reach yet, held on the derivation itself.

A running session makes a ticket Building, but sessions arrive with the ticket
that runs one; auto-merge is on until the store lets a person turn it off. Every
other rule is tested through a read of the GitHub stand-in
(`test_the_read_model.py`).
"""

from __future__ import annotations

from typing import Any

import pytest

from wayfarer.models import Checks, PullRequest, TicketState
from wayfarer.read_model import derive_state

pytestmark = pytest.mark.unit


def _state(**facts: Any) -> TicketState:
    unremarkable: dict[str, Any] = {
        "open": True,
        "completed": False,
        "labels": [],
        "assignees": [],
        "open_blockers": 0,
        "pull_request": None,
        "building": False,
        "auto_merge": True,
    }
    return derive_state(**(unremarkable | facts))


def _ready(**fields: Any) -> PullRequest:
    unremarkable: dict[str, Any] = {
        "number": 7,
        "branch": "ticket/7-x",
        "base": "effort/1-x",
        "head_commit": "1" * 40,
        "draft": False,
        "merged": False,
        "merge_commit": None,
        "checks": None,
        "approved": False,
    }
    return PullRequest(**(unremarkable | fields))


def test_a_ticket_with_a_running_session_is_building_even_though_it_is_claimed() -> None:
    assert _state(building=True, assignees=["wayfarer"]) == TicketState.BUILDING


def test_a_pr_outranks_a_running_session() -> None:
    assert _state(building=True, pull_request=_ready(draft=True)) == TicketState.IN_REVIEW


def test_with_auto_merge_off_a_ready_green_pr_waits_in_review_until_approved() -> None:
    assert _state(auto_merge=False, pull_request=_ready()) == TicketState.IN_REVIEW
    assert (
        _state(auto_merge=False, pull_request=_ready(approved=True, checks=Checks.PASSING))
        == TicketState.LANDING
    )
