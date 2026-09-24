"""Whose failure a session was is decided by the failure's type, never its stage (#20).

The agent actually ran, and failed: the attempt's, and its ticket is Held. Anything
else is the environment's, and its ticket goes back on the frontier. How each is
answered is held at the HTTP surface in `test_when_a_session_goes_wrong.py`; here is
the whole table, one failure of each type.
"""

from __future__ import annotations

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

from wayfarer.endings import fault
from wayfarer.store import Fault

pytestmark = pytest.mark.unit


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
