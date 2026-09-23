"""Staying fresh: something may have changed, so read again (ADR-0003).

A page watching an effort holds its stream open, and Wayfarer sends the effort
again whenever a re-read finds it changed. What sets off a re-read is a
conditional poll of GitHub, which never supplies data itself: a `304` means
nothing changed, and anything else only means "read again".

Each test runs the poll fast, so a rhythm is seen in a second rather than a minute.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Generator
from itertools import pairwise
from typing import Any

import pytest

from conftest import Launcher, get, stream
from github_stand_in import GitHub, Logged, Refusal
from wayfarer.read_model import HELD

pytestmark = pytest.mark.git

_FAST = {"WAYFARER_POLL_ACTIVE": "0.1", "WAYFARER_POLL_IDLE": "30"}


def _until(condition: Callable[[], bool], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "it never happened"
        time.sleep(0.02)


def _polls_after(github: GitHub, count: int, path: str = "/issues") -> list[Logged]:
    """Wait for `count` more polls of `path` than there are now, and return them all."""
    before = len(github.polls(path))
    _until(lambda: len(github.polls(path)) >= before + count)
    return github.polls(path)


def _watch(url: str, effort: int) -> Generator[dict[str, Any]]:
    return stream(f"{url}api/efforts/{effort}/stream")


def _states(effort: dict[str, Any]) -> dict[int, str]:
    return {ticket["number"]: ticket["state"] for ticket in effort["tickets"]}


def test_a_page_watching_an_effort_is_sent_it_at_once(wayfarer: Launcher, github: GitHub) -> None:
    spec, (ticket,) = github.effort("Watched", tickets=1)
    url = wayfarer.start(env=_FAST).url()

    page = _watch(url, spec.number)

    assert _states(next(page)) == {ticket.number: "takeable"}


def test_an_unchanged_github_is_not_re_read_and_costs_no_rate_budget(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, _ = github.effort("Quiet", tickets=2)
    url = wayfarer.start(env=_FAST).url()
    page = _watch(url, spec.number)
    next(page)
    spent = github.spent()

    polls = _polls_after(github, 5)

    assert {poll.status for poll in polls[-5:]} == {304}
    assert len(github.queries) == 1
    assert github.spent() == spent
    page.close()


def test_a_change_on_github_is_re_read_once_and_sent_to_the_page(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (ticket,) = github.effort("Moving", tickets=1)
    url = wayfarer.start(env=_FAST).url()
    page = _watch(url, spec.number)
    next(page)

    ticket.labels.append(HELD)

    assert _states(next(page)) == {ticket.number: "held"}
    _polls_after(github, 3)
    assert len(github.queries) == 2
    page.close()


def test_the_poll_runs_fast_while_a_page_is_open_and_slows_when_none_is(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, _ = github.effort("Rhythm", tickets=1)
    url = wayfarer.start(env=_FAST).url()
    _until(lambda: len(github.polls()) >= 1)
    time.sleep(1.0)
    assert len(github.polls()) == 1, "idle, it polled at the open rhythm"

    page = _watch(url, spec.number)
    next(page)
    _polls_after(github, 5)
    page.close()
    time.sleep(0.5)
    settled = len(github.polls())
    time.sleep(1.0)

    assert len(github.polls()) == settled, "with the page gone, it kept polling fast"


def _gaps(polls: list[Logged]) -> list[float]:
    return [later.at - earlier.at for earlier, later in pairwise(polls)]


@pytest.mark.parametrize(
    "refusal",
    [
        Refusal(429, {"Retry-After": "1"}),
        Refusal(403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "{in_one_second}"}),
    ],
    ids=["retry-after", "rate-limit-reset"],
)
def test_a_rate_limited_poll_waits_as_long_as_github_asks(
    wayfarer: Launcher, github: GitHub, refusal: Refusal
) -> None:
    spec, _ = github.effort("Refused", tickets=1)
    url = wayfarer.start(env=_FAST).url()
    page = _watch(url, spec.number)
    next(page)
    _polls_after(github, 2)

    headers = {
        name: value.format(in_one_second=int(time.time()) + 2)
        for name, value in refusal.headers.items()
    }
    github.refuse(Refusal(refusal.status, headers))
    polls = _polls_after(github, 3)

    refused = next(i for i, poll in enumerate(polls) if poll.status == refusal.status)
    assert polls[refused + 1].at - polls[refused].at >= 0.9
    page.close()


def test_a_poll_refused_without_saying_how_long_backs_off_further_each_time(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, _ = github.effort("Refused again", tickets=1)
    url = wayfarer.start(env=_FAST | {"WAYFARER_RATE_LIMIT_BACKOFF": "0.5"}).url()
    page = _watch(url, spec.number)
    next(page)
    _polls_after(github, 2)

    github.refuse(Refusal(403), Refusal(403))
    polls = _polls_after(github, 4)

    first = next(i for i, poll in enumerate(polls) if poll.status == 403)
    first_wait, second_wait, after = _gaps(polls[first : first + 4])
    assert first_wait >= 0.45
    assert second_wait >= 0.95
    assert after < 0.5, "a poll GitHub answered again did not return to the rhythm"
    page.close()


def test_the_poll_is_never_faster_than_github_asks(wayfarer: Launcher, github: GitHub) -> None:
    spec, _ = github.effort("Slower, please", tickets=1)
    github.poll_interval = 1
    url = wayfarer.start(env=_FAST).url()
    page = _watch(url, spec.number)
    next(page)

    polls = _polls_after(github, 2)

    assert min(_gaps(polls[-3:])) >= 0.9
    page.close()


def test_a_pull_requests_checks_are_noticed_though_its_ticket_never_changes(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, (ticket,) = github.effort("Checks", tickets=1)
    pull = github.pull_request(ticket, checks="PENDING")
    url = wayfarer.start(env=_FAST).url()
    page = _watch(url, spec.number)
    assert _states(next(page)) == {ticket.number: "in_review"}
    _polls_after(github, 2, path="/check-runs")

    pull.checks = "SUCCESS"

    assert _states(next(page)) == {ticket.number: "landing"}
    assert all(poll.status == 304 for poll in github.polls()[1:])
    page.close()


def test_a_merged_pull_request_is_no_longer_checked(wayfarer: Launcher, github: GitHub) -> None:
    spec, (ticket,) = github.effort("Merged", tickets=1)
    github.pull_request(ticket, state="MERGED", checks="SUCCESS")
    url = wayfarer.start(env=_FAST).url()
    page = _watch(url, spec.number)
    next(page)

    _polls_after(github, 5)

    assert github.polls("/check-runs") == []
    page.close()


def test_watching_an_effort_that_does_not_exist_is_not_found(
    wayfarer: Launcher, github: GitHub
) -> None:
    url = wayfarer.start(env=_FAST).url()

    response = get(f"{url}api/efforts/404/stream")

    assert response.status_code == 404
    assert "no issue #404" in response.json()["detail"]


def test_an_effort_deleted_while_watched_ends_its_stream(
    wayfarer: Launcher, github: GitHub
) -> None:
    spec, _ = github.effort("Going", tickets=1)
    url = wayfarer.start(env=_FAST).url()
    page = _watch(url, spec.number)
    next(page)

    github.delete(spec)

    assert next(page, None) is None


def test_a_poll_github_refuses_keeps_to_its_rhythm_and_keeps_asking(
    wayfarer: Launcher, github: GitHub
) -> None:
    wayfarer.start(env=_FAST | {"GH_TOKEN": "revoked", "WAYFARER_POLL_IDLE": "0.1"}).url()

    polls = _polls_after(github, 3)

    assert {poll.status for poll in polls} == {401}
