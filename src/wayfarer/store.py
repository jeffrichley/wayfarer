"""The store: what a restarted Wayfarer needs and GitHub cannot hold.

One SQLite file per repo, outside the checkout, beside the sessions' event
files. It never holds a ticket's state, which is GitHub's (ADR-0002).

A session is recorded the moment it starts, because Waystation mints the run's
id and writes it down nowhere else: a session that never ended is then still
known by the row with no end.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from wayfarer.github import Repo
from wayfarer.outcome import Outcome

__all__ = ["Purpose", "SessionRow", "Store"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    run_id TEXT PRIMARY KEY,
    ticket INTEGER NOT NULL,
    purpose TEXT NOT NULL,
    started TEXT NOT NULL,
    ended TEXT,
    event_file TEXT NOT NULL,
    outcome TEXT
)
"""


class Purpose(StrEnum):
    """Why a session ran. A ticket may have several over its life."""

    BUILD = "build"
    """`/implement` on the ticket."""
    RESOLVE = "resolve"
    """A resolver session, replaying the ticket's preserved commits onto the effort
    branch (#40). It is landing, so it never earns a chronicle line."""


@dataclass(frozen=True)
class SessionRow:
    """One session, as the store has it."""

    run_id: str
    ticket: int
    purpose: Purpose
    started: datetime
    ended: datetime | None
    """None while it runs, or when it never finished."""
    event_file: Path
    outcome: Outcome | None
    """None until it ends, and after it when it reported none that validated."""


class Store:
    """One repo's store."""

    def __init__(self, connection: sqlite3.Connection, directory: Path) -> None:
        self._db = connection
        self.directory = directory

    @classmethod
    def open(cls, directory: Path) -> Store:
        """The store in `directory`, made there if it is not yet."""
        directory.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(directory / "wayfarer.sqlite3", isolation_level=None)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(_SCHEMA)
        return cls(connection, directory)

    @classmethod
    def for_repo(cls, data_dir: Path, repo: Repo) -> Store:
        """The store for `repo`, keyed by its owner and name under `data_dir`."""
        return cls.open(data_dir / repo.owner / repo.name)

    def event_file(self, run_id: str) -> Path:
        """Where session `run_id` writes its events, beside the store."""
        sessions = self.directory / "sessions"
        sessions.mkdir(exist_ok=True)
        return sessions / f"{run_id}.jsonl"

    def close(self) -> None:
        self._db.close()

    def session_started(
        self, run_id: str, ticket: int, purpose: Purpose, started: datetime, event_file: Path
    ) -> None:
        self._db.execute(
            "INSERT INTO sessions (run_id, ticket, purpose, started, event_file) "
            "VALUES (?, ?, ?, ?, ?)",
            (run_id, ticket, purpose.value, started.isoformat(), str(event_file)),
        )

    def session_ended(self, run_id: str, ended: datetime, outcome: Outcome | None) -> None:
        self._db.execute(
            "UPDATE sessions SET ended = ?, outcome = ? WHERE run_id = ?",
            (ended.isoformat(), outcome.model_dump_json() if outcome else None, run_id),
        )

    def sessions(self) -> list[SessionRow]:
        """Every session recorded, in the order they started."""
        rows = self._db.execute(
            "SELECT run_id, ticket, purpose, started, ended, event_file, outcome "
            "FROM sessions ORDER BY started, rowid"
        )
        return [
            SessionRow(
                run_id=run_id,
                ticket=ticket,
                purpose=Purpose(purpose),
                started=datetime.fromisoformat(started),
                ended=datetime.fromisoformat(ended) if ended else None,
                event_file=Path(event_file),
                outcome=Outcome.model_validate_json(outcome) if outcome else None,
            )
            for run_id, ticket, purpose, started, ended, event_file, outcome in rows
        ]
