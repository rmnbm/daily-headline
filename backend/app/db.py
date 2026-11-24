"""SQLite persistence for pipeline runs and their steps.

A run goes through these states:

    preparing -> draft -> publishing -> published
         |         |           |
         v         v           v
       failed   rejected     failed

Each call opens its own short-lived connection, so the repository is safe to
use from FastAPI's worker threads.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from app.pipeline import Draft, Publication, Step, StepStatus

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT NOT NULL,
    status       TEXT NOT NULL,
    headline     TEXT,
    prompt       TEXT,
    image        BLOB,
    image_uri    TEXT,
    metadata_uri TEXT,
    tx_hash      TEXT,
    error        TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS steps (
    run_id     INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    step       TEXT NOT NULL,
    status     TEXT NOT NULL,
    error      TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (run_id, step)
);
"""


class RunStatus(StrEnum):
    PREPARING = "preparing"
    DRAFT = "draft"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True)
class StepRecord:
    step: Step
    status: StepStatus
    error: str | None
    updated_at: str


@dataclass(frozen=True)
class RunRecord:
    id: int
    date: str
    status: RunStatus
    headline: str | None
    prompt: str | None
    has_image: bool
    image_uri: str | None
    metadata_uri: str | None
    tx_hash: str | None
    error: str | None
    created_at: str
    updated_at: str
    steps: list[StepRecord] = field(default_factory=list)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class RunRepository:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open a connection and commit on success, roll back on error."""
        with closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            with conn:
                yield conn

    # --- Writes ----------------------------------------------------------------

    def create_run(self, date: str) -> int:
        now = _now()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO runs (date, status, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (date, RunStatus.PREPARING, now, now),
            )
            run_id = cursor.lastrowid
            conn.executemany(
                "INSERT INTO steps (run_id, step, status, updated_at) VALUES (?, ?, ?, ?)",
                [(run_id, step, StepStatus.PENDING, now) for step in Step],
            )
        return run_id

    def record_step(self, run_id: int, step: Step, status: StepStatus, error: str | None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE steps SET status = ?, error = ?, updated_at = ? "
                "WHERE run_id = ? AND step = ?",
                (status, error, _now(), run_id, step),
            )

    def save_draft(self, run_id: int, draft: Draft) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET status = ?, headline = ?, prompt = ?, image = ?, updated_at = ? "
                "WHERE id = ?",
                (RunStatus.DRAFT, draft.headline, draft.prompt, draft.image, _now(), run_id),
            )

    def save_publication(self, run_id: int, publication: Publication) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET status = ?, image_uri = ?, metadata_uri = ?, tx_hash = ?, "
                "updated_at = ? WHERE id = ?",
                (
                    RunStatus.PUBLISHED,
                    publication.image_uri,
                    publication.metadata_uri,
                    publication.tx_hash,
                    _now(),
                    run_id,
                ),
            )

    def mark_failed(self, run_id: int, error: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET status = ?, error = ?, updated_at = ? WHERE id = ?",
                (RunStatus.FAILED, error, _now(), run_id),
            )

    def transition(self, run_id: int, expected: RunStatus, new: RunStatus) -> bool:
        """Atomically move a run from `expected` to `new`.

        Returns False if the run is not in the `expected` state, so two
        concurrent requests can never both publish the same draft.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE id = ? AND status = ?",
                (new, _now(), run_id, expected),
            )
        return cursor.rowcount == 1

    # --- Reads -----------------------------------------------------------------

    def get_run(self, run_id: int) -> RunRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT *, image IS NOT NULL AS has_image FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
            if row is None:
                return None
            steps = conn.execute(
                "SELECT step, status, error, updated_at FROM steps WHERE run_id = ?", (run_id,)
            ).fetchall()
        order = {step: index for index, step in enumerate(Step)}
        records = sorted(
            (
                StepRecord(Step(s["step"]), StepStatus(s["status"]), s["error"], s["updated_at"])
                for s in steps
            ),
            key=lambda record: order[record.step],
        )
        return _to_record(row, records)

    def list_runs(self, limit: int = 50) -> list[RunRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT *, image IS NOT NULL AS has_image FROM runs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_to_record(row, []) for row in rows]

    def get_draft(self, run_id: int) -> Draft | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT date, headline, prompt, image FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None or row["image"] is None:
            return None
        return Draft(
            date=row["date"], headline=row["headline"], prompt=row["prompt"], image=row["image"]
        )


def _to_record(row: sqlite3.Row, steps: list[StepRecord]) -> RunRecord:
    return RunRecord(
        id=row["id"],
        date=row["date"],
        status=RunStatus(row["status"]),
        headline=row["headline"],
        prompt=row["prompt"],
        has_image=bool(row["has_image"]),
        image_uri=row["image_uri"],
        metadata_uri=row["metadata_uri"],
        tx_hash=row["tx_hash"],
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        steps=steps,
    )
