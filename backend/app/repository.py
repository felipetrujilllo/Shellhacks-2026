"""Data access for the API: read projects and ranked overlaps out of Postgres.

Routes depend on the `Repository` protocol, never on psycopg, so tests can swap in fixtures.
"""

from __future__ import annotations

from typing import Protocol

import psycopg
from psycopg.rows import dict_row

from app.schemas import Overlap, Project

# Column names are the model's field names (schema.sql uses the same vocabulary).
PROJECT_COLUMNS = ", ".join(Project.model_fields)

# Fail fast instead of hanging a request when the database is unreachable.
CONNECT_TIMEOUT_S = 5

# `rank` is not stored: it is the position by descending score, with the same tie-breaks
# as pipeline.overlap.rank_by_score. COLLATE "C" makes the id tie-break byte order, like
# Python's string sort, instead of depending on the database's locale.
RANKED_OVERLAPS = """
SELECT overlap_id, project_id_a, project_id_b, distance_mi, time_gap_days, score,
       ROW_NUMBER() OVER (ORDER BY score DESC, distance_mi, overlap_id COLLATE "C") AS rank
FROM project_overlaps
"""


class Repository(Protocol):
    def list_projects(self) -> list[Project]: ...

    def list_overlaps(self) -> list[Overlap]: ...  # ranked, rank 1 first

    def get_overlap(self, overlap_id: str) -> Overlap | None: ...  # None -> 404


class PostgresRepository:
    """Reads the tables pipeline/load.py writes. One short-lived connection per call."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(
            self._database_url, row_factory=dict_row, connect_timeout=CONNECT_TIMEOUT_S
        )

    def list_projects(self) -> list[Project]:
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT {PROJECT_COLUMNS} FROM projects ORDER BY project_id"
            ).fetchall()
        return [Project.model_validate(row) for row in rows]

    def list_overlaps(self) -> list[Overlap]:
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM ({RANKED_OVERLAPS}) r ORDER BY rank").fetchall()
            projects = _projects_by_id(conn)
        return [_to_overlap(row, projects) for row in rows]

    def get_overlap(self, overlap_id: str) -> Overlap | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT * FROM ({RANKED_OVERLAPS}) r WHERE overlap_id = %s", (overlap_id,)
            ).fetchone()
            if row is None:
                return None
            projects = _projects_by_id(conn, [row["project_id_a"], row["project_id_b"]])
        return _to_overlap(row, projects)


def _projects_by_id(conn: psycopg.Connection, ids: list[str] | None = None) -> dict[str, Project]:
    if ids is None:
        rows = conn.execute(f"SELECT {PROJECT_COLUMNS} FROM projects").fetchall()
    else:
        rows = conn.execute(
            f"SELECT {PROJECT_COLUMNS} FROM projects WHERE project_id = ANY(%s)", (ids,)
        ).fetchall()
    return {row["project_id"]: Project.model_validate(row) for row in rows}


def _to_overlap(row: dict, projects: dict[str, Project]) -> Overlap:
    return Overlap(
        overlap_id=row["overlap_id"],
        rank=row["rank"],
        score=row["score"],
        distance_mi=row["distance_mi"],
        time_gap_days=row["time_gap_days"],
        project_a=projects[row["project_id_a"]],
        project_b=projects[row["project_id_b"]],
    )
