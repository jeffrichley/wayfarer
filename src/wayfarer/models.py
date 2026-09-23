"""Every shape that crosses to the browser, defined once.

FastAPI publishes these as OpenAPI, and `web/src/api.gen.ts` is generated from
that schema (`pnpm gen:types`), so the browser's types never drift from these
(ADR-0004).

Everything the browser holds is an `Item`: a shape with a `kind` and an `id`
unique across every kind. It reaches the browser only as a `WireEvent` on the
page's one stream, which the browser applies by id without folding anything.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

__all__ = [
    "Actor",
    "Answered",
    "Armed",
    "Asked",
    "Beat",
    "BeatKind",
    "BuildFinished",
    "BuildOutput",
    "Checks",
    "ChronicleLine",
    "Closed",
    "Effort",
    "EffortUnreadable",
    "EnvironmentFailure",
    "GateCheck",
    "GateStatus",
    "Health",
    "Held",
    "ImageStatus",
    "Landed",
    "Mention",
    "ProbeCheck",
    "Published",
    "PullRequest",
    "ReadyToShip",
    "Removal",
    "Retried",
    "Shipped",
    "Snapshot",
    "Taken",
    "TestRun",
    "Ticket",
    "TicketState",
    "Upsert",
]


class Health(BaseModel):
    """That the process is up, and which Wayfarer it is."""

    version: str


class TicketState(StrEnum):
    """Where a ticket stands, derived from GitHub on every read and never stored.

    When a ticket matches more than one, it takes the first in this order.
    """

    LANDED = "landed"
    """Its PR merged, or it was closed as completed."""
    CLOSED = "closed"
    """Closed without landing: not planned, or a duplicate."""
    ASKED = "asked"
    """Labelled `wayfarer:asked`: its session ended to ask a person something."""
    HELD = "held"
    """Labelled `wayfarer:held`: kept back until a person decides."""
    LANDING = "landing"
    """Its PR is ready, its checks green or absent, and approved if auto-merge is off."""
    IN_REVIEW = "in_review"
    """It has an open PR that is not landing."""
    BUILDING = "building"
    """A session is running on it."""
    TAKEABLE = "takeable"
    """Open, every blocker closed, and nobody on it: on the frontier."""
    BLOCKED = "blocked"
    """Anything else: a blocker is still open, or someone has taken it by hand."""


class Checks(StrEnum):
    """A pull request's checks, rolled up. A PR with no checks has none of these."""

    PASSING = "passing"
    PENDING = "pending"
    FAILING = "failing"


class PullRequest(BaseModel):
    """The pull request carrying a ticket's work, from the ticket's own branch."""

    number: int
    branch: str
    """Its head: the ticket branch, `ticket/<n>-…`."""
    base: str
    """Where it merges: the effort branch."""
    head_commit: str
    """The commit at its head, which moves when work is pushed to it."""
    draft: bool
    merged: bool
    merge_commit: str | None
    """The commit its merge made on its base; None until it merges."""
    checks: Checks | None
    """None when the PR has no checks at all, which counts as green."""
    approved: bool


class Ticket(BaseModel):
    """One ticket in an effort, as GitHub has it now."""

    kind: Literal["ticket"]
    id: str
    number: int
    title: str
    state: TicketState
    open: bool
    """Whether its issue is open. A landed ticket stays open until Wayfarer closes it."""
    labels: list[str]
    assignees: list[str]
    blocked_by: list[int]
    """Every ticket blocking this one, open or closed, from GitHub's issue dependencies."""
    open_blockers: int
    pull_request: PullRequest | None


class Effort(BaseModel):
    """An effort's whole ticket graph: its spec issue, and every ticket under it."""

    kind: Literal["effort"]
    id: str
    number: int
    title: str
    trunk: str = Field(
        description="The repo's default branch, which the effort meets once, when it ships."
    )
    tickets: list[str] = Field(description="The ids of its tickets, each an item of its own.")


class EffortUnreadable(BaseModel):
    """An effort Wayfarer was asked to read and could not. It stands in the effort's place."""

    kind: Literal["effort_unreadable"]
    id: str
    number: int
    reason: str = Field(description="Why, in words for the person.")


class ImageStatus(BaseModel):
    """The image this repo's sessions run in: Wayfarer's base plus the repo's layer (ADR-0005)."""

    kind: Literal["image"]
    id: Literal["image"]
    layer: str = Field(description="Where the repo's layer lives, relative to the clone.")
    refusal: str | None = Field(
        description="Why no image can be built for this repo, in words for the person; "
        "null when one can."
    )
    tag: str | None = Field(
        description="The tag an image of the current inputs has; null when refused."
    )
    ready: bool = Field(description="That tag exists, so it was built and passed its probe.")
    building: bool


class ProbeCheck(BaseModel):
    """One thing the probe proved, or failed to prove, about a newly built image."""

    name: str
    passed: bool
    detail: str


class BuildOutput(BaseModel):
    """One line of the last build's output, as Docker printed it."""

    kind: Literal["build_output"]
    id: str
    number: int = Field(description="Where the line falls in the output, counting from 0.")
    line: str


class BuildFinished(BaseModel):
    """How the last build ended."""

    kind: Literal["build_finished"]
    id: Literal["build_finished"]
    tag: str
    ready: bool = Field(description="Built and passed its probe, so sessions may use it.")
    error: str | None = Field(description="Why the build itself failed; null when it built.")
    checks: list[ProbeCheck] = Field(description="The probe's checks; empty when it never built.")


class GateCheck(BaseModel):
    """One of the start gate's six checks, and what it found."""

    name: str = Field(description="What must hold, in plain words.")
    passed: bool
    detail: str = Field(
        description="What was found, in plain words, saying how to fix it when it failed. "
        "Names a credential's variable, never its value."
    )


class EnvironmentFailure(BaseModel):
    """The one Needs you item a failed start gate raises, however many starts it refused."""

    kind: Literal["environment"]
    id: str = Field(description="Stays the same while the gate keeps failing, so it is one item.")
    reason: str = Field(description="Which checks failed and why, in plain words.")
    failed: list[GateCheck]


class GateStatus(BaseModel):
    """The start gate as it stands now: all six checks, run afresh."""

    kind: Literal["gate"]
    id: Literal["gate"]
    checks: list[GateCheck]
    passed: bool = Field(description="Every check passed, so a session may start.")
    raised: EnvironmentFailure | None = Field(
        description="The item the gate raised when it last refused a start; null when it has "
        "not refused one, or has admitted one since."
    )


class BeatKind(StrEnum):
    """What kind of moment a beat is."""

    READ = "read"
    """Consecutive reads and searches, folded into one."""
    REMARK = "remark"
    """The agent's own narration."""
    RED = "red"
    """A test run through `wf-test` that failed, by its exit status."""
    GREEN = "green"
    """A test run through `wf-test` that passed, by its exit status."""
    REFACTOR = "refactor"
    """Edits after a green, confirmed by the next run staying green."""
    OUTCOME = "outcome"
    """The one beat that closes a session: the Outcome it reported, or how it ended without."""
    WORKING = "working"
    """A call with no result yet, which its beat replaces, or which goes when it has none."""


class TestRun(BaseModel):
    """One test run, as `wf-test` reported it on its own line."""

    # Not a test class, though its name says so.
    __test__ = False

    exit: int = Field(description="The tests' real exit status: 0 is green, anything else red.")
    passed: int | None = Field(description="Null when the runner wrote no JUnit report.")
    failed: int | None = Field(description="Null when the runner wrote no JUnit report.")
    failing: list[str] = Field(description="The failing tests' names, when the runner wrote them.")


class Beat(BaseModel):
    """One meaningful moment in a session, derived from its events and never stored.

    Folding the session's events again gives the same beats with the same ids, so a
    replay tells exactly the story that was watched live.
    """

    kind: Literal["beat"]
    id: str = Field(description="`beat:<session>:<seq>`, where `seq` is its first event's.")
    session: str = Field(description="The session's run id.")
    seq: int = Field(description="Its first event's place in the session; beats sort by it.")
    beat: BeatKind
    at: datetime = Field(description="When its first event arrived.")
    chapter: int = Field(description="0 for Orient, before the first red; then cycle 1, 2, ….")
    text: str = Field(description="One sentence.")
    run: TestRun | None = Field(description="The test run a red, green or refactor rests on.")
    output: str | None = Field(description="What a red run printed; null for every other beat.")


class Actor(StrEnum):
    """Who moved a ticket, read from the kind of event rather than the timeline's
    actor, since Wayfarer writes with the person's own token (#22)."""

    WAYFARER = "wayfarer"
    """Wayfarer or a session did it, and the line reads passively."""
    YOU = "you"
    """The person running Wayfarer did it, and the line reads "You"."""
    SOMEONE = "someone"
    """Anyone else did it, and the line names their login."""


class Mention(BaseModel):
    """A ticket or an effort as a line names it: by its title, its number riding after."""

    number: int
    title: str


class Taken(BaseModel):
    """A ticket was taken: by a session the cascade started, or by a person's hand."""

    kind: Literal["taken"]
    ticket: Mention
    by: Actor
    login: str | None = Field(description="Who took it, when it was someone else; else null.")


class Asked(BaseModel):
    """A ticket's session ended to ask a person something."""

    kind: Literal["asked"]
    ticket: Mention
    gist: str = Field(description="The question's gist, quoted as the session wrote it.")


class Answered(BaseModel):
    """A person answered a ticket's question, and its session resumed."""

    kind: Literal["answered"]
    ticket: Mention
    by: Literal[Actor.YOU, Actor.SOMEONE]
    login: str | None = Field(description="Who answered, when it was someone else; else null.")


class Held(BaseModel):
    """A ticket was kept back until a person decides."""

    kind: Literal["held"]
    ticket: Mention
    reason: str = Field(description="The plain-words Held reason, quoted, as a sentence.")


class Retried(BaseModel):
    """You retried a Held ticket (#20)."""

    kind: Literal["retried"]
    ticket: Mention
    over: bool = Field(
        description="Started over on the effort branch's head, rather than continuing "
        "where its session stopped."
    )


class Landed(BaseModel):
    """A ticket landed on its effort branch, with what that directly caused (#22)."""

    kind: Literal["landed"]
    ticket: Mention
    by: Actor = Field(
        description="Wayfarer for a landing through the merge queue; a person for a "
        "merge by hand on GitHub, which was not re-tested."
    )
    login: str | None = Field(description="Who merged it, when it was someone else; else null.")
    freed: list[Mention] = Field(description="The tickets its landing made takeable.")
    started: list[Mention] = Field(description="Those of them the cascade started a session on.")


class Closed(BaseModel):
    """A person closed a ticket without landing it."""

    kind: Literal["closed"]
    ticket: Mention
    by: Literal[Actor.YOU, Actor.SOMEONE]
    login: str | None = Field(description="Who closed it, when it was someone else; else null.")


class Armed(BaseModel):
    """You armed the effort's cascade, with the sessions it started straight away."""

    kind: Literal["armed"]
    started: list[Mention]


class Published(BaseModel):
    """`/to-tickets` published the effort's tickets, with what that directly caused."""

    kind: Literal["published"]
    tickets: int = Field(description="How many tickets it published.")
    freed: list[Mention] = Field(description="Those of them takeable from the start.")
    started: list[Mention] = Field(description="Those the cascade started a session on.")


class ReadyToShip(BaseModel):
    """The effort's last ticket landed, so the effort can ship."""

    kind: Literal["ready_to_ship"]


class Shipped(BaseModel):
    """The effort's branch landed on the trunk."""

    kind: Literal["shipped"]


class ChronicleLine(BaseModel):
    """One line of the chronicle: one thing that moved a ticket, with what it directly
    caused, derived from GitHub and never stored (#22). The browser writes its
    sentence from one template per kind of movement, so a rebuilt chronicle reads
    the same and no line can misname a ticket."""

    kind: Literal["chronicle_line"]
    id: str
    at: datetime
    effort: Mention = Field(description="The effort it moved, named on the right of the line.")
    moved: Annotated[
        Taken
        | Asked
        | Answered
        | Held
        | Retried
        | Landed
        | Closed
        | Armed
        | Published
        | ReadyToShip
        | Shipped,
        Field(discriminator="kind"),
    ]


Item = Annotated[
    ImageStatus
    | BuildOutput
    | BuildFinished
    | Effort
    | EffortUnreadable
    | Ticket
    | GateStatus
    | Beat
    | ChronicleLine,
    Field(discriminator="kind"),
]
"""Anything the browser holds, keyed by its `id`."""


class Snapshot(BaseModel):
    """Everything there is, replacing whatever the browser held."""

    kind: Literal["snapshot"]
    items: list[Item]


class Upsert(BaseModel):
    """One item, new or replacing the one with its id."""

    kind: Literal["upsert"]
    item: Item


class Removal(BaseModel):
    """The item with this id is gone."""

    kind: Literal["removal"]
    id: str


WireEvent = Annotated[Snapshot | Upsert | Removal, Field(discriminator="kind")]
"""Every event on the page's stream (ADR-0004)."""
