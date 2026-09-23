"""The pull request gate: how a finished session's work reaches the effort branch.

When a session ends, Wayfarer opens its pull request against the effort branch
and decides, from the Outcome and exactly once, whether it opens ready or as a
draft. A draft holds its ticket. From then on only GitHub is read: the gate never
looks at the Outcome again, so a restarted Wayfarer reaches the same answer
(ADR-0002).

A ticket whose pull request is ready, green and unheld reads as Landing, which
is how it joins the merge queue (`merge_queue.py`).
"""

from __future__ import annotations

from wayfarer.github import GitHub
from wayfarer.outcome import Axis, Finding, Outcome
from wayfarer.read_model import HELD

__all__ = ["PullRequestGate", "body", "opens_ready"]


def opens_ready(outcome: Outcome) -> bool:
    """Finished with nothing blocking. Everything else, every `not_done` too, is a draft."""
    return outcome.status == "done" and not any(f.blocks for f in outcome.open_findings)


def body(ticket: int, outcome: Outcome) -> str:
    """The pull request's body: the summary, the findings by axis with what they cite,
    then the assumptions under "Assumed". A section with nothing in it is left out."""
    parts = [f"For #{ticket}.", outcome.summary.strip()]
    if outcome.open_findings:
        parts.append("## Findings")
        for axis, heading in ((Axis.SPEC, "Spec"), (Axis.STANDARDS, "Standards")):
            found = [f for f in outcome.open_findings if f.axis is axis]
            if found:
                parts += [f"### {heading}", "\n".join(_finding(f) for f in found)]
    if outcome.assumptions:
        parts += [
            "## Assumed",
            "\n".join(f"- **{a.what}** {a.why}" for a in outcome.assumptions),
        ]
    return "\n\n".join(parts) + "\n"


def _finding(finding: Finding) -> str:
    kind = "Blocking" if finding.blocks else "Judgement call"
    where = ""
    if finding.file is not None:
        at = finding.file if finding.line is None else f"{finding.file}:{finding.line}"
        where = f" (`{at}`)"
    return f"- **{kind}:** {finding.what}{where}\n  > {finding.cites}"


class PullRequestGate:
    """Opens each finished session's pull request, ready or as a draft."""

    def __init__(self, github: GitHub) -> None:
        self._github = github

    async def open(
        self, *, ticket: int, title: str, branch: str, effort_branch: str, outcome: Outcome
    ) -> int:
        """Open the pull request from `branch` into `effort_branch`, ready or as a draft,
        holding the ticket when it is a draft. Returns its number."""
        ready = opens_ready(outcome)
        opened = await self._github.write(
            "POST",
            "/pulls",
            {
                "title": title,
                "head": branch,
                "base": effort_branch,
                "body": body(ticket, outcome),
                "draft": not ready,
            },
        )
        if not ready:
            await self._github.write("POST", f"/issues/{ticket}/labels", {"labels": [HELD]})
        number: int = opened["number"]
        return number
