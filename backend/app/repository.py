"""Data access for the API: read projects and ranked overlaps out of Postgres, and store uploads.

Routes depend on the `Repository` protocol, never on psycopg, so tests can swap in fixtures.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import fields
from pathlib import Path
from typing import Protocol

import psycopg
from psycopg.rows import dict_row

from app.schemas import Overlap, Project
from app.submissions import SubmissionConflict, submitted_overlaps
from pipeline.overlap import Overlap as EngineOverlap
from pipeline.overlap import rank_by_score
from pipeline.savings import estimate_savings

SUBMISSIONS_SCHEMA_PATH = Path(__file__).parents[1] / "db" / "submissions.sql"

# Column names are the model's field names (schema.sql uses the same vocabulary).
PROJECT_COLUMNS = ", ".join(Project.model_fields)

# A project_overlaps row carries exactly the engine Overlap's fields.
OVERLAP_COLUMNS = ", ".join(f.name for f in fields(EngineOverlap))

INSERT_SUBMITTED_PROJECT = (
    f"INSERT INTO submitted_projects ({PROJECT_COLUMNS}) "
    f"VALUES ({', '.join(f'%({name})s' for name in Project.model_fields)})"
)

# Fail fast instead of hanging a request when the database is unreachable.
CONNECT_TIMEOUT_S = 5


class Repository(Protocol):
    def list_projects(self) -> list[Project]: ...  # published + submitted

    def list_overlaps(self) -> list[Overlap]: ...  # ranked, rank 1 first

    def get_overlap(self, overlap_id: str) -> Overlap | None: ...  # None -> 404

    # All or nothing; raises SubmissionConflict if a project already exists.
    def add_submission(self, projects: Sequence[Project]) -> None: ...


class PostgresRepository:
    """Reads the tables pipeline/load.py writes plus submitted_projects, which it owns.

    One short-lived connection per call.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(
            self._database_url, row_factory=dict_row, connect_timeout=CONNECT_TIMEOUT_S
        )

    def _published_and_submitted(
        self, conn: psycopg.Connection
    ) -> tuple[list[Project], list[Project]]:
        # Reads never create the table (smoke.py must stay read-only on the demo database):
        # until the first upload creates it, there are simply no submitted projects.
        has_submissions = conn.execute(
            "SELECT to_regclass('submitted_projects') IS NOT NULL AS present"
        ).fetchone()["present"]
        submitted = _select_projects(conn, "submitted_projects") if has_submissions else []
        return _select_projects(conn, "projects"), submitted

    def list_projects(self) -> list[Project]:
        with self._connect() as conn:
            published, submitted = self._published_and_submitted(conn)
        return sorted([*published, *submitted], key=lambda p: p.project_id)

    def list_overlaps(self) -> list[Overlap]:
        with self._connect() as conn:
            stored = [
                EngineOverlap(**row)
                for row in conn.execute(f"SELECT {OVERLAP_COLUMNS} FROM project_overlaps")
            ]
            published, submitted = self._published_and_submitted(conn)
        return ranked_overlaps(stored, published, submitted)

    def get_overlap(self, overlap_id: str) -> Overlap | None:
        # A rank is a position in the whole list, so there is no cheaper way to get one right.
        return next((o for o in self.list_overlaps() if o.overlap_id == overlap_id), None)

    def add_submission(self, projects: Sequence[Project]) -> None:
        # Leaving the `with` block commits; an exception rolls every row back.
        with self._connect() as conn:
            # The first upload creates the table; idempotent, so no migration step is needed.
            conn.execute(SUBMISSIONS_SCHEMA_PATH.read_text(encoding="utf-8"))
            try:
                with conn.cursor() as cur:
                    cur.executemany(INSERT_SUBMITTED_PROJECT, [p.model_dump() for p in projects])
            except psycopg.errors.UniqueViolation as err:
                # Two uploads raced past prepare_submission's check; the index caught it.
                raise SubmissionConflict("a project in this upload was just submitted") from err


def _select_projects(conn: psycopg.Connection, table: str) -> list[Project]:
    rows = conn.execute(f"SELECT {PROJECT_COLUMNS} FROM {table}").fetchall()
    return [Project.model_validate(row) for row in rows]


def ranked_overlaps(
    stored: Sequence[EngineOverlap],
    published: Sequence[Project],
    submitted: Sequence[Project],
) -> list[Overlap]:
    """Stored published pairs plus every pair involving a submitted project, ranked together.

    `rank` is not stored: it is the position by rank_by_score, so a submitted pair can take
    rank 1 and pushes the published pairs down.
    """
    projects = {p.project_id: p for p in [*published, *submitted]}
    ranked = rank_by_score([*stored, *submitted_overlaps(published, submitted)])
    return [build_overlap(o, rank, projects) for rank, o in enumerate(ranked, start=1)]


def build_overlap(overlap: EngineOverlap, rank: int, projects: dict[str, Project]) -> Overlap:
    """An engine overlap plus its rank and two projects, as the API serves it.

    The savings estimate is derived here from the projects' costs, never stored.
    """
    project_a = projects[overlap.project_id_a]
    project_b = projects[overlap.project_id_b]
    savings = estimate_savings(
        overlap,
        project_a.est_cost_usd,
        project_b.est_cost_usd,
        utility_a=project_a.utility,
        utility_b=project_b.utility,
    )
    return Overlap(
        overlap_id=overlap.overlap_id,
        rank=rank,
        score=overlap.score,
        distance_mi=overlap.distance_mi,
        time_gap_days=overlap.time_gap_days,
        project_a=project_a,
        project_b=project_b,
        est_savings_usd=savings.est_savings_usd,
        savings_basis=savings.savings_basis,
    )
