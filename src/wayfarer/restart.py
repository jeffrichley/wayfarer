"""Restart: a Wayfarer back after a crash or a quit makes the same next move as one
that never stopped (ADR-0002).

It reads what it recorded, then GitHub, then the containers still running, in that
order (docs/design/data-and-commands.md). The store gives the cascades that were
armed, which come back paused so a restart never spends anything unasked, and the
sessions it started and never saw end. Each of those is an orphan, raised in Needs
you by its ticket and offered a reap. GitHub gives every ticket's state, as it always
does: nothing the store remembers says where a ticket stands. Docker gives the
containers Waystation labelled with a run id, and one whose run the store never
recorded is shown as unknown and never reaped, because the label carries no repo
and it may be another Wayfarer's.

A ticket claimed on GitHub whose session never started is left alone. Its claim
reads exactly as a person taking the ticket as themselves, which the cascade must
leave to them, and guessing otherwise could start it twice.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Protocol

from waystation import DockerSandbox, StageError

from wayfarer.cascade import Cascades
from wayfarer.github import GitHub, GitHubError, NoSuchIssue, NotConnected
from wayfarer.models import Mention, Orphan, UnknownContainer
from wayfarer.read_model import HELD, Efforts
from wayfarer.settings import Settings
from wayfarer.store import SessionRow
from wayfarer.stream import Store as Stream

__all__ = ["Containers", "ContainersError", "DockerContainers", "Restart"]

_log = logging.getLogger(__name__)

# The label Waystation puts on every sandbox it makes, naming the run (its ADR-0014).
# It exports no name for it.
_RUN_ID = "waystation.run-id"

_TICKET = """
query Orphan($owner: String!, $name: String!, $ticket: Int!) {
  repository(owner: $owner, name: $name) {
    issue(number: $ticket) { title parent { number title } }
  }
}
"""


class ContainersError(Exception):
    """Docker could not be asked, or refused."""


class Containers(Protocol):
    """The sandboxes Waystation's runs left on this host (`DockerContainers`)."""

    async def run_ids(self) -> set[str]:
        """The run id on every one, running or stopped."""
        ...

    async def reap(self, run_id: str) -> None:
        """Remove `run_id`'s, if any are left."""
        ...


class DockerContainers:
    """The containers on the Docker host the environment names, as sessions run there."""

    def __init__(self, settings: Settings) -> None:
        self._timeout = settings.docker_timeout

    async def run_ids(self) -> set[str]:
        listing = ["docker", "ps", "--all", "--filter", f"label={_RUN_ID}"]
        try:
            process = await asyncio.create_subprocess_exec(
                *listing,
                "--format",
                f'{{{{.Label "{_RUN_ID}"}}}}',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as error:
            raise ContainersError(f"Docker could not be run: {error}") from error
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), self._timeout)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise ContainersError(
                f"Docker did not answer within {self._timeout:g} seconds"
            ) from None
        if process.returncode != 0:
            raise ContainersError(stderr.decode(errors="replace").strip())
        return set(stdout.decode().split())

    async def reap(self, run_id: str) -> None:
        try:
            await DockerSandbox.reap(run_id)
        except StageError as error:
            raise ContainersError(str(error)) from error


class Restart:
    """What a Wayfarer before this one left: read as the app starts, and reaped on asking."""

    def __init__(
        self,
        stream: Stream,
        github: GitHub,
        cascades: Cascades,
        efforts: Efforts,
        containers: Containers,
    ) -> None:
        self._stream = stream
        self._github = github
        self._cascades = cascades
        self._efforts = efforts
        self._containers = containers
        self._armed: list[int] = []
        self._orphans: list[SessionRow] = []

    def recall(self) -> None:
        """Read the store, before anything is served: no session has started here yet,
        so every one it has with no end was the last Wayfarer's."""
        if self._github.repo is None:
            return  # No repo, so no store, and nothing was ever started.
        # Opening it brings every armed cascade back paused.
        store = self._cascades.record()
        self._armed = sorted(store.cascades())
        self._orphans = [row for row in store.sessions() if row.ended is None]

    async def recover(self) -> None:
        """Then GitHub, and then Docker: read every effort it was working, raise each
        orphan, and show every container no session here accounts for."""
        orphans = [await self._orphan(row) for row in self._orphans]
        efforts = set(self._armed) | {o.effort.number for o in orphans if o.effort is not None}
        for number in sorted(efforts):
            await self._efforts.read(number)
        for orphan in orphans:
            self._stream.upsert(orphan)
        try:
            running = await self._containers.run_ids()
        except ContainersError as error:
            _log.warning("Could not ask Docker what containers were left running: %s", error)
            return
        # Read now, not at recall: a session started since then is this Wayfarer's.
        known = {row.run_id for row in self._cascades.record().sessions()}
        for run_id in sorted(running - known):
            self._stream.upsert(
                UnknownContainer(kind="unknown_container", id=f"container:{run_id}", run_id=run_id)
            )

    async def reap(self, run_id: str) -> None:
        """Remove what orphan `run_id` left running, and hold its ticket. An unknown
        container is never reaped, however asked."""
        orphan = self._stream.get(f"orphan:{run_id}")
        if not isinstance(orphan, Orphan):
            return
        try:
            await self._containers.reap(run_id)
            # As stopping a ticket does (`Cascades.stop`): its session ended with no
            # Outcome and the claim stays, so it waits on a person, not on nobody.
            await self._github.write("POST", f"/issues/{orphan.ticket}/labels", {"labels": [HELD]})
        except (ContainersError, GitHubError, NotConnected) as error:
            # Each half is safe to repeat, so the orphan stays offered.
            _log.warning("Could not reap the session on #%s: %s", orphan.ticket, error)
            return
        self._cascades.record().session_ended(run_id, datetime.now(UTC), None)
        self._stream.remove(orphan.id)

    async def _orphan(self, row: SessionRow) -> Orphan:
        """The orphan `row` is, named by its ticket and its effort as GitHub has them."""
        title: str | None = None
        effort: Mention | None = None
        try:
            data = await self._github.query(_TICKET, ticket=row.ticket)
        except (NotConnected, NoSuchIssue, GitHubError) as error:
            _log.warning("Could not read #%s, which a session was left on: %s", row.ticket, error)
        else:
            if (issue := data["repository"]["issue"]) is not None:
                title = issue["title"]
                if (parent := issue["parent"]) is not None:
                    effort = Mention(number=parent["number"], title=parent["title"])
        return Orphan(
            kind="orphan",
            id=f"orphan:{row.run_id}",
            run_id=row.run_id,
            ticket=row.ticket,
            title=title,
            effort=effort,
            started=row.started,
        )
