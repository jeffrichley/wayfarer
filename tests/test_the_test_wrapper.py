"""`wf-test`: the wrapper every test run in a session goes through.

It runs the tests, exits with their real status, and prints one line last in a
format Wayfarer owns, which is the only text of a session Wayfarer parses. It
runs here on the host's Python exactly as it runs in the image.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from wayfarer.image import BASE

pytestmark = pytest.mark.unit

_WRAPPER = BASE.files / "wf-test"
_SENTINEL = "::wf-test "

_JUNIT = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="4" failures="1" errors="1" skipped="1">
  <testcase classname="tests.test_widgets" name="test_a_widget_folds"/>
  <testcase classname="tests.test_widgets" name="test_the_limit_is_ten">
    <failure message="assert 11 == 10"/>
  </testcase>
  <testcase classname="tests.test_widgets" name="test_the_fixture_loads">
    <error message="no such file"/>
  </testcase>
  <testcase classname="tests.test_widgets" name="test_someday"><skipped/></testcase>
</testsuite></testsuites>
"""


def _wf_test(
    *command: str, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    environment = {
        name: value for name, value in os.environ.items() if not name.startswith("WF_TEST_")
    }
    return subprocess.run(
        [sys.executable, str(_WRAPPER), *command],
        cwd=cwd,
        env=environment | (env or {}),
        capture_output=True,
        text=True,
        timeout=60,
    )


def _report(printed: str) -> dict[str, Any]:
    """The one line of the wrapper's own, which must be the last it prints."""
    lines = printed.splitlines()
    assert [line for line in lines if line.startswith(_SENTINEL)] == [lines[-1]]
    report: dict[str, Any] = json.loads(lines[-1].removeprefix(_SENTINEL))
    return report


def _script(tmp_path: Path, body: str) -> str:
    script = tmp_path / "tests.py"
    script.write_text(body)
    return str(script)


@pytest.mark.parametrize("status", [0, 1, 5])
def test_the_wrapper_exits_with_the_tests_real_status_and_says_so_last(
    tmp_path: Path, status: int
) -> None:
    tests = _script(tmp_path, f"print('running'); raise SystemExit({status})")

    ran = _wf_test(sys.executable, tests, cwd=tmp_path)

    assert ran.returncode == status
    assert ran.stdout.startswith("running\n")
    assert _report(ran.stdout) == {"exit": status, "passed": None, "failed": None, "failing": []}


def test_the_tests_output_passes_through_untouched(tmp_path: Path) -> None:
    tests = _script(
        tmp_path, "import sys; print('out'); print('err', file=sys.stderr); sys.exit(1)"
    )

    ran = _wf_test(sys.executable, tests, cwd=tmp_path)

    assert ran.stdout.splitlines()[0] == "out"
    assert ran.stderr == "err\n"


def test_the_runners_junit_report_gives_the_counts_and_the_failing_names(
    tmp_path: Path,
) -> None:
    tests = _script(tmp_path, f"import pathlib; pathlib.Path('junit.xml').write_text({_JUNIT!r})")

    ran = _wf_test(sys.executable, tests, cwd=tmp_path, env={"WF_TEST_JUNIT": "junit.xml"})

    assert _report(ran.stdout) == {
        "exit": 0,
        "passed": 1,
        "failed": 2,
        "failing": ["test_the_limit_is_ten", "test_the_fixture_loads"],
    }


def test_a_junit_report_left_from_an_earlier_run_is_never_read(tmp_path: Path) -> None:
    (tmp_path / "junit.xml").write_text(_JUNIT)
    tests = _script(tmp_path, "raise SystemExit(1)")

    ran = _wf_test(sys.executable, tests, cwd=tmp_path, env={"WF_TEST_JUNIT": "junit.xml"})

    assert _report(ran.stdout) == {"exit": 1, "passed": None, "failed": None, "failing": []}


def test_a_junit_report_that_is_not_xml_leaves_the_counts_unknown(tmp_path: Path) -> None:
    tests = _script(tmp_path, "import pathlib; pathlib.Path('junit.xml').write_text('<oops')")

    ran = _wf_test(sys.executable, tests, cwd=tmp_path, env={"WF_TEST_JUNIT": "junit.xml"})

    assert _report(ran.stdout) == {"exit": 0, "passed": None, "failed": None, "failing": []}


def test_with_no_command_given_it_runs_the_repos_configured_one(tmp_path: Path) -> None:
    tests = _script(tmp_path, "print('the suite'); raise SystemExit(3)")

    ran = _wf_test(cwd=tmp_path, env={"WF_TEST_COMMAND": f"{sys.executable} {tests}"})

    assert ran.returncode == 3
    assert ran.stdout.startswith("the suite\n")
    assert _report(ran.stdout)["exit"] == 3


def test_with_nothing_to_run_it_fails_saying_why(tmp_path: Path) -> None:
    ran = _wf_test(cwd=tmp_path)

    assert ran.returncode == 2
    assert "WF_TEST_COMMAND" in ran.stderr
    assert _report(ran.stdout)["exit"] == 2


def test_a_command_that_does_not_exist_fails_as_a_shell_would(tmp_path: Path) -> None:
    ran = _wf_test("no-such-test-runner", cwd=tmp_path)

    assert ran.returncode == 127
    assert _report(ran.stdout)["exit"] == 127
