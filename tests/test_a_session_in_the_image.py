"""What a real session is handed: the image, a read-only token, and its time caps.

Nothing runs here: the run spec is Waystation's own public description of the
run, so it can be read without starting one, and without spending anything.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest
from waystation import ClaudeCode, DockerSandbox, Timeouts

from wayfarer import stream
from wayfarer.gate import SESSION_GH_TOKEN
from wayfarer.github import Repo
from wayfarer.sessions import Sessions
from wayfarer.settings import Settings
from wayfarer.store import Store

pytestmark = pytest.mark.unit

_TAG = "wayfarer-session:0123456789abcdef"


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    with closing(Store.open(tmp_path / "data")) as opened:
        yield opened


def _in_image(store: Store, settings: Settings) -> Sessions:
    return Sessions.in_image(
        Path("clone"), store, Repo("octo", "widgets"), _TAG, settings, stream.Store(1000)
    )


def test_a_session_runs_claude_code_in_the_session_image(store: Store) -> None:
    spec = _in_image(store, Settings()).spec(7)

    assert spec.backend == DockerSandbox(_TAG)
    assert isinstance(spec.provider, ClaudeCode)
    assert spec.prompt == "/mattpocock-skills:implement 7"


def test_a_session_reads_github_with_the_read_only_token_not_the_persons(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GH_TOKEN", "the-persons-token")
    monkeypatch.setenv(SESSION_GH_TOKEN, "the-read-only-token")

    spec = _in_image(store, Settings()).spec(7)

    assert dict(spec.environment) == {"GH_TOKEN": "the-read-only-token", "GH_REPO": "octo/widgets"}
    assert "GH_TOKEN" not in spec.pass_through


def test_a_session_runs_under_the_time_caps_in_the_settings(store: Store) -> None:
    settings = Settings(session_silence=60.0, session_wall=600.0, stage_timeout=30.0)

    spec = _in_image(store, settings).spec(7)

    assert spec.bounds == Timeouts(
        workspace=30.0,
        sandbox=30.0,
        agent_silence=60.0,
        agent_wall=600.0,
        collect=30.0,
        integrate=30.0,
        teardown=30.0,
    )


def test_a_session_can_ask_because_it_is_named_the_images_permission_prompt_tool(
    store: Store,
) -> None:
    spec = _in_image(store, Settings()).spec(7)

    assert isinstance(spec.provider, ClaudeCode)
    args = list(spec.provider.args)
    tool = args[args.index("--permission-prompt-tool") + 1]
    config = json.loads(args[args.index("--mcp-config") + 1])
    # The tool the image carries, under the name the flag gives it (`base/wf-ask-tool`).
    assert tool == "mcp__wayfarer__ask"
    assert config == {"mcpServers": {"wayfarer": {"command": "/usr/local/bin/wf-ask-tool"}}}
