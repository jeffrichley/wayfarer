"""The pull request's diff, read from GitHub when a review opens (#109).

Driven as the browser does: the desk asks for a pull request's diff, and it
arrives on the page's stream in the shape the diff view takes (#53). It is read
from GitHub each time and never stored (ADR-0003).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from conftest import Launcher, Stream, post, quick
from github_stand_in import GitHub, Issue

pytestmark = pytest.mark.git

# Two hunks, as GitHub gives a file's patch: no file header, and a context line
# that is empty in the code is a lone space; a note on the file, such as a missing
# newline, is no line of it.
_PATCH = "\n".join(
    [
        "@@ -1,4 +1,5 @@",
        " def loudness(samples):",
        "-    return max(samples)",
        "+    peak = max(samples)",
        "+    return 20 * log10(peak)",
        " ",
        " ",
        "@@ -20,2 +21,2 @@ def meter():",
        "-    pass",
        "+    return 0",
        "\\ No newline at end of file",
    ]
)


def _read(url: str, page: Stream, effort: Issue) -> None:
    """The effort read, as the screens that show it ask."""
    assert post(f"{url}api/efforts/{effort.number}/read").status_code == 202
    page.until(lambda items: f"effort:{effort.number}" in items)


def _open(url: str, pull: int) -> None:
    """The review opened on the desk, which asks for its pull request's diff."""
    assert post(f"{url}api/pulls/{pull}/read").status_code == 202


def _lines(file: dict[str, Any]) -> list[tuple[int | None, int | None, str]]:
    return [(line["old"], line["new"], line["code"]) for line in file["lines"]]


def test_opening_a_review_sends_its_changed_files_line_by_line(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    _, (ticket,) = github.effort("Widgets", tickets=1)
    files: dict[str, str | None] = {"src/loud.py": _PATCH, "README.md": "@@ -0,0 +1 @@\n+Loud"}
    pull = github.pull_request(ticket, files=files)
    url = wayfarer.start(env=quick(tmp_path)).url()

    with Stream(url, patience=30) as page:
        _open(url, pull.number)
        diff = page.item(f"diff:{pull.number}")

    assert diff["pull"] == pull.number
    assert diff["head_commit"] == pull.head_commit
    assert [f["path"] for f in diff["files"]] == ["src/loud.py", "README.md"]
    # Each line has its old number, its new one, or both, and the numbers pick up
    # again at each hunk.
    assert _lines(diff["files"][0]) == [
        (1, 1, "def loudness(samples):"),
        (2, None, "    return max(samples)"),
        (None, 2, "    peak = max(samples)"),
        (None, 3, "    return 20 * log10(peak)"),
        (3, 4, ""),
        (4, 5, ""),
        (20, None, "    pass"),
        (None, 21, "    return 0"),
    ]
    assert _lines(diff["files"][1]) == [(None, 1, "Loud")]
    assert diff["left_out"] == []
    assert diff["unread"] == 0


def test_a_push_to_the_pull_request_sends_the_new_diff(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    spec, (ticket,) = github.effort("Widgets", tickets=1)
    pull = github.pull_request(ticket, files={"a.py": "@@ -0,0 +1 @@\n+one"})
    url = wayfarer.start(env=quick(tmp_path)).url()

    with Stream(url, patience=30) as page:
        _read(url, page, spec)
        _open(url, pull.number)
        page.item(f"diff:{pull.number}", head_commit=pull.head_commit)

        github.push(pull, {"a.py": "@@ -0,0 +1,2 @@\n+one\n+two", "b.py": "@@ -0,0 +1 @@\n+three"})
        # The stand-in's issue listing carries no pull requests, as GitHub's does, so
        # the push is seen when the page asks for a read.
        _read(url, page, spec)
        diff = page.item(f"diff:{pull.number}", head_commit=pull.head_commit)

    assert [f["path"] for f in diff["files"]] == ["a.py", "b.py"]
    assert _lines(diff["files"][0]) == [(None, 1, "one"), (None, 2, "two")]


def test_a_pull_request_past_the_bound_says_what_it_left_out(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    _, (ticket,) = github.effort("Widgets", tickets=1)
    three = "@@ -0,0 +1,3 @@\n+a\n+b\n+c"
    files: dict[str, str | None] = {"logo.png": None}
    # More files than GitHub sends on one page, so leaving them out stops the paging.
    files |= {f"f{i:03}.py": three for i in range(150)}
    pull = github.pull_request(ticket, files=files)
    url = wayfarer.start(env=quick(tmp_path) | {"WAYFARER_DIFF_LINES": "7"}).url()

    with Stream(url, patience=30) as page:
        _open(url, pull.number)
        diff = page.item(f"diff:{pull.number}")

    # Two files' lines fit in seven; the third would not, so it and every file after
    # it are left out, and the files never read are counted rather than named.
    assert [f["path"] for f in diff["files"]] == ["f000.py", "f001.py"]
    assert diff["left_out"][:3] == [
        {"path": "logo.png", "added": 0, "removed": 0, "why": "no_patch"},
        {"path": "f002.py", "added": 3, "removed": 0, "why": "bound"},
        {"path": "f003.py", "added": 3, "removed": 0, "why": "bound"},
    ]
    assert len(diff["left_out"]) == 98
    assert diff["unread"] == 51
    assert len(github.polls("/files")) == 1


def test_files_github_never_lists_are_counted_as_unread(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    _, (ticket,) = github.effort("Widgets", tickets=1)
    # Past the 3000 files GitHub lists, with no patch among them to reach the bound.
    files: dict[str, str | None] = {f"art/{i:04}.png": None for i in range(3002)}
    pull = github.pull_request(ticket, files=files)
    url = wayfarer.start(env=quick(tmp_path)).url()

    with Stream(url, patience=30) as page:
        _open(url, pull.number)
        diff = page.item(f"diff:{pull.number}")

    assert diff["files"] == []
    assert len(diff["left_out"]) == 3000
    assert diff["unread"] == 2


def test_a_pull_request_github_cannot_find_says_so(
    wayfarer: Launcher, github: GitHub, tmp_path: Path
) -> None:
    url = wayfarer.start(env=quick(tmp_path)).url()

    with Stream(url, patience=30) as page:
        _open(url, 404)
        unreadable = page.item("diff:404")

    assert unreadable["kind"] == "pull_diff_unreadable"
    assert "404" in unreadable["reason"]
