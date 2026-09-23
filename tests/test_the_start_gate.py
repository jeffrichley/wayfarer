"""The start gate: six things checked before any session starts, said in plain words.

Each test launches Wayfarer in an environment it controls, because the
environment Wayfarer was started from is the only place a credential comes from.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any

import pytest

from conftest import Launcher, build_layer, commit_layer, get
from wayfarer.gate import API_KEY, OAUTH_TOKEN, SESSION_GH_TOKEN, StartGate
from wayfarer.image import Images
from wayfarer.settings import Settings

pytestmark = pytest.mark.git

CHECKS = [
    "Docker is running",
    "the session image is built",
    "the session image passed its probe",
    "an agent credential is set",
    "the clone has a git identity",
    "a read-only GitHub token is set",
]

SECRET = "sk-ant-not-a-real-key-5f2c"


@pytest.fixture
def launched(tmp_path: Path) -> dict[str, str | None]:
    """An environment with every credential set, and no git config but the clone's own."""
    empty = tmp_path / "gitconfig"
    empty.write_text("")
    return {
        "ANTHROPIC_API_KEY": SECRET,
        "CLAUDE_CODE_OAUTH_TOKEN": None,
        "WAYFARER_SESSION_GH_TOKEN": "github_pat_not-a-real-token",
        "GIT_CONFIG_GLOBAL": str(empty),
        "GIT_CONFIG_NOSYSTEM": "1",
    }


def _identify(clone: Path) -> None:
    subprocess.run(["git", "config", "user.name", "Octo Cat"], cwd=clone, check=True)
    subprocess.run(["git", "config", "user.email", "octo@example.com"], cwd=clone, check=True)


def _gate(url: str) -> dict[str, Any]:
    response = get(f"{url}api/gate")
    assert response.status_code == 200
    gate: dict[str, Any] = response.json()
    return gate


def _checks(gate: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {check["name"]: check for check in gate["checks"]}


def test_the_gate_runs_all_six_checks_in_order(
    wayfarer: Launcher, launched: dict[str, str | None]
) -> None:
    url = wayfarer.start(env=launched).url()

    assert [check["name"] for check in _gate(url)["checks"]] == CHECKS


def test_every_check_says_what_it_found_even_after_an_earlier_one_fails(
    wayfarer: Launcher, launched: dict[str, str | None]
) -> None:
    url = wayfarer.start(env={**launched, "ANTHROPIC_API_KEY": None}).url()

    gate = _gate(url)

    assert gate["passed"] is False
    assert all(check["detail"] for check in gate["checks"])


def test_with_no_agent_credential_the_gate_names_the_variables_to_set(
    wayfarer: Launcher, launched: dict[str, str | None]
) -> None:
    url = wayfarer.start(env={**launched, "ANTHROPIC_API_KEY": None}).url()

    check = _checks(_gate(url))["an agent credential is set"]

    assert check["passed"] is False
    assert "ANTHROPIC_API_KEY" in check["detail"]
    assert "CLAUDE_CODE_OAUTH_TOKEN" in check["detail"]


def test_an_empty_credential_is_no_credential(
    wayfarer: Launcher, launched: dict[str, str | None]
) -> None:
    url = wayfarer.start(env={**launched, "ANTHROPIC_API_KEY": ""}).url()

    assert _checks(_gate(url))["an agent credential is set"]["passed"] is False


def test_an_oauth_token_is_a_credential_too(
    wayfarer: Launcher, launched: dict[str, str | None]
) -> None:
    url = wayfarer.start(
        env={**launched, "ANTHROPIC_API_KEY": None, "CLAUDE_CODE_OAUTH_TOKEN": "oauth-token"}
    ).url()

    check = _checks(_gate(url))["an agent credential is set"]

    assert check["passed"] is True
    assert "CLAUDE_CODE_OAUTH_TOKEN" in check["detail"]


def test_the_api_key_wins_when_both_kinds_of_credential_are_set(
    wayfarer: Launcher, launched: dict[str, str | None]
) -> None:
    url = wayfarer.start(env={**launched, "CLAUDE_CODE_OAUTH_TOKEN": "oauth-token"}).url()

    check = _checks(_gate(url))["an agent credential is set"]

    assert check["passed"] is True
    assert check["detail"].startswith("ANTHROPIC_API_KEY")


def test_no_credential_ever_leaves_the_process(
    wayfarer: Launcher, launched: dict[str, str | None]
) -> None:
    url = wayfarer.start(env=launched).url()

    assert SECRET not in get(f"{url}api/gate").text
    assert SECRET not in get(f"{url}openapi.json").text


def test_a_clone_with_no_git_identity_fails_the_gate_saying_how_to_set_one(
    wayfarer: Launcher, launched: dict[str, str | None]
) -> None:
    url = wayfarer.start(env=launched).url()

    check = _checks(_gate(url))["the clone has a git identity"]

    assert check["passed"] is False
    assert "git config user.name" in check["detail"]
    assert "git config user.email" in check["detail"]


def test_a_clone_with_a_git_identity_passes_that_check(
    wayfarer: Launcher, clone: Path, launched: dict[str, str | None]
) -> None:
    _identify(clone)
    url = wayfarer.start(env=launched).url()

    check = _checks(_gate(url))["the clone has a git identity"]

    assert check["passed"] is True
    assert "Octo Cat <octo@example.com>" in check["detail"]


def test_with_no_read_only_github_token_the_gate_names_the_variable_to_set(
    wayfarer: Launcher, launched: dict[str, str | None]
) -> None:
    url = wayfarer.start(env={**launched, "WAYFARER_SESSION_GH_TOKEN": None}).url()

    check = _checks(_gate(url))["a read-only GitHub token is set"]

    assert check["passed"] is False
    assert "WAYFARER_SESSION_GH_TOKEN" in check["detail"]


def test_with_no_docker_daemon_the_image_checks_fail_rather_than_wait_on_it(
    wayfarer: Launcher, clone: Path, launched: dict[str, str | None], tmp_path: Path
) -> None:
    commit_layer(clone, "FROM wayfarer-base\n")
    nobody = f"unix://{tmp_path / 'no-docker.sock'}"
    url = wayfarer.start(env={**launched, "DOCKER_HOST": nobody}).url()

    checks = _checks(_gate(url))

    assert checks["Docker is running"]["passed"] is False
    assert checks["the session image is built"]["passed"] is False
    assert checks["the session image passed its probe"]["passed"] is False
    assert "Docker is not running" in checks["the session image is built"]["detail"]


def test_a_repo_with_no_layer_fails_the_image_check_with_the_refusal(
    wayfarer: Launcher, launched: dict[str, str | None]
) -> None:
    url = wayfarer.start(env=launched).url()

    check = _checks(_gate(url))["the session image is built"]

    assert check["passed"] is False
    assert ".wayfarer/Dockerfile" in check["detail"]


@pytest.mark.docker
def test_an_image_nobody_has_built_fails_the_image_check_saying_so(
    wayfarer: Launcher, clone: Path, launched: dict[str, str | None]
) -> None:
    commit_layer(clone, "FROM wayfarer-base\nRUN echo never-built-4c1d\n")
    url = wayfarer.start(env=launched).url()
    tag = get(f"{url}api/image").json()["tag"]

    checks = _checks(_gate(url))

    assert checks["the session image is built"]["passed"] is False
    assert tag in checks["the session image is built"]["detail"]
    assert checks["the session image passed its probe"]["passed"] is False


def test_nothing_is_raised_for_a_person_just_by_looking_at_the_gate(
    wayfarer: Launcher, launched: dict[str, str | None]
) -> None:
    url = wayfarer.start(env={**launched, "ANTHROPIC_API_KEY": None}).url()

    assert _gate(url)["raised"] is None


# Before each start, the cascade asks the gate to admit it. These drive that
# question in-process, because nothing over HTTP starts a session yet (#37).


def _without_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(API_KEY, raising=False)
    monkeypatch.delenv(OAUTH_TOKEN, raising=False)


def _admit_many(gate: StartGate, times: int) -> list[Any]:
    async def admit_all() -> list[Any]:
        return list(await asyncio.gather(*(gate.admit() for _ in range(times))))

    return asyncio.run(admit_all())


def test_ten_tickets_refused_at_once_raise_one_item_not_ten(
    clone: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _without_credential(monkeypatch)
    gate = StartGate(clone, Images(clone), Settings())

    refusals = _admit_many(gate, 10)

    assert all(refusal is not None for refusal in refusals)
    assert len({refusal.id for refusal in refusals}) == 1
    assert gate.raised == refusals[0]


def test_the_item_says_in_plain_words_which_check_failed(
    clone: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _without_credential(monkeypatch)
    gate = StartGate(clone, Images(clone), Settings())

    [refusal] = _admit_many(gate, 1)

    assert refusal.kind == "environment"
    assert "an agent credential is set" in [check.name for check in refusal.failed]
    assert "an agent credential is set" in refusal.reason
    assert "ANTHROPIC_API_KEY" in refusal.reason


def test_the_gate_reads_the_environment_again_before_every_start(
    clone: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _without_credential(monkeypatch)
    gate = StartGate(clone, Images(clone), Settings())
    [first] = _admit_many(gate, 1)

    monkeypatch.setenv(API_KEY, SECRET)
    [second] = _admit_many(gate, 1)

    # Still refused (this clone has no layer), but no longer for the credential,
    # and still the one item rather than a second.
    assert "an agent credential is set" in [check.name for check in first.failed]
    assert "an agent credential is set" not in [check.name for check in second.failed]
    assert second.id == first.id
    assert SECRET not in second.model_dump_json()


@pytest.mark.docker
def test_a_ready_clone_passes_all_six_checks(
    wayfarer: Launcher, clone: Path, launched: dict[str, str | None], built_tags: list[str]
) -> None:
    _identify(clone)
    url = wayfarer.start(env=launched).url()
    _, finished = build_layer(url, clone, "FROM wayfarer-base\nRUN echo gate-ready\n")
    built_tags.append(finished["tag"])

    gate = _gate(url)

    assert gate["passed"] is True, gate
    assert [check["name"] for check in gate["checks"] if check["passed"]] == CHECKS


@pytest.mark.docker
def test_an_image_that_failed_its_probe_is_named_as_the_reason(
    wayfarer: Launcher, clone: Path, launched: dict[str, str | None], built_tags: list[str]
) -> None:
    url = wayfarer.start(env=launched).url()
    _, finished = build_layer(url, clone, "FROM wayfarer-base\nUSER root\n")
    built_tags.append(finished["tag"])

    check = _checks(_gate(url))["the session image passed its probe"]

    assert check["passed"] is False
    assert "a non-root user owns the workspace" in check["detail"]


@pytest.mark.docker
def test_once_the_gate_passes_again_its_item_is_cleared(
    wayfarer: Launcher,
    clone: Path,
    launched: dict[str, str | None],
    built_tags: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _identify(clone)
    url = wayfarer.start(env=launched).url()
    _, finished = build_layer(url, clone, "FROM wayfarer-base\nRUN echo gate-clears\n")
    built_tags.append(finished["tag"])
    for variable, value in launched.items():
        if value is None:
            monkeypatch.delenv(variable, raising=False)
        else:
            monkeypatch.setenv(variable, value)
    monkeypatch.delenv(SESSION_GH_TOKEN)
    gate = StartGate(clone, Images(clone), Settings())
    [refused] = _admit_many(gate, 1)

    monkeypatch.setenv(SESSION_GH_TOKEN, "github_pat_not-a-real-token")
    [admitted] = _admit_many(gate, 1)

    assert refused is not None
    assert admitted is None
    assert gate.raised is None
