"""Two branches that each regenerated the browser's types merge without a conflict.

`web/src/api.gen.ts` is rebuilt from the models (ADR-0004), so a conflict in it
never needs a person: the merge keeps one side and `just types-drift` catches a
stale result. The repo's own `.gitattributes` and `justfile` are what is tested,
in a throwaway repo, so the test holds what a clone actually gets.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.git

ROOT = Path(__file__).resolve().parents[1]
TYPES = Path("web/src/api.gen.ts")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)


@pytest.fixture
def diverged(tmp_path: Path) -> Path:
    """A repo whose `left` and `right` branches each added a model to the types."""
    repo = tmp_path / "repo"
    (repo / TYPES.parent).mkdir(parents=True)
    shutil.copy(ROOT / ".gitattributes", repo / ".gitattributes")
    for args in (
        ("init", "--quiet", "--initial-branch=main"),
        ("config", "user.name", "Ada"),
        ("config", "user.email", "ada@example.com"),
    ):
        _git(repo, *args).check_returncode()

    def commit(content: str) -> None:
        (repo / TYPES).write_text(content)
        _git(repo, "add", ".").check_returncode()
        _git(repo, "commit", "--quiet", "-m", content.splitlines()[-1]).check_returncode()

    base = "export interface Ticket {}\n"
    commit(base)
    _git(repo, "switch", "--quiet", "-c", "left").check_returncode()
    commit(base + "export interface Left {}\n")
    _git(repo, "switch", "--quiet", "-c", "right", "main").check_returncode()
    commit(base + "export interface Right {}\n")
    return repo


def test_the_regenerated_types_merge_without_a_conflict_once_just_hooks_has_run(
    diverged: Path,
) -> None:
    subprocess.run(
        ["just", "--justfile", ROOT / "justfile", "--working-directory", diverged, "merge-driver"],
        check=True,
        capture_output=True,
    )

    merge = _git(diverged, "merge", "--no-edit", "left")

    assert merge.returncode == 0, merge.stdout + merge.stderr
    assert "<<<<<<<" not in (diverged / TYPES).read_text()
    assert _git(diverged, "status", "--porcelain").stdout == ""


def test_a_clone_without_the_driver_still_merges_with_the_old_conflict(diverged: Path) -> None:
    merge = _git(diverged, "merge", "--no-edit", "left")

    assert merge.returncode != 0
    assert "CONFLICT" in merge.stdout
    assert "<<<<<<<" in (diverged / TYPES).read_text()
