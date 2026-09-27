"""Data access for the API: read the published projects and ranked overlaps out of Postgres.

Read-only: nothing here writes. Uploads never reach the database (they live in each visitor's
browser, see app/submissions.py). The legacy `submitted_projects` table from the old shared
uploads may still exist in the demo database; it is deliberately never read.

Routes depend on the `Repository` protocol, never on psycopg, so tests can swap in fixtures.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import fields
from typing import NamedTuple, Protocol

import psycopg
from psycopg.rows import dict_row

from app.schemas import Overlap, Project
from app.submissions import submitted_overlaps
from pipeline.overlap import (
    LatLon,
    closest_approach_miles,
    coordination_tier,
    footprint,
    rank_opportunities,
)
from pipeline.overlap import Overlap as EngineOverlap
from pipeline.savings import estimate_savings

# Column names are the model's field names (schema.sql uses the same vocabulary).
PROJECT_COLUMNS = ", ".join(Project.model_fields)

# A project_overlaps row carries exactly the engine Overlap's fields.
OVERLAP_COLUMNS = ", ".join(f.name for f in fields(EngineOverlap))

# Fail fast instead of hanging a request when the database is unreachable.
CONNECT_TIMEOUT_S = 5


class PublishedPlans(NamedTuple):
    """The published projects and their stored pairs, read together (one snapshot)."""

    projects: list[Project]
    overlaps: list[EngineOverlap]  # unranked, as pipeline/load.py stored them


class Repository(Protocol):
    def list_projects(self) -> list[Project]: ...  # published only

    def list_overlaps(self) -> list[Overlap]: ...  # published pairs, ranked, rank 1 first

    def get_overlap(self, overlap_id: str) -> Overlap | None: ...  # None -> 404

    def published_plans(self) -> PublishedPlans: ...  # what POST /workspace scores uploads on


class PostgresRepository:
    """Reads the tables pipeline/load.py writes. One short-lived connection per call."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(
            self._database_url, row_factory=dict_row, connect_timeout=CONNECT_TIMEOUT_S
        )

    def published_plans(self) -> PublishedPlans:
        with self._connect() as conn:
            projects = _select_projects(conn)
            overlaps = [
                EngineOverlap(**row)
                for row in conn.execute(f"SELECT {OVERLAP_COLUMNS} FROM project_overlaps")
            ]
        return PublishedPlans(projects, overlaps)

    def list_projects(self) -> list[Project]:
        with self._connect() as conn:
            return sorted(_select_projects(conn), key=lambda p: p.project_id)

    def list_overlaps(self) -> list[Overlap]:
        projects, stored = self.published_plans()
        return ranked_overlaps(stored, projects, [])

    def get_overlap(self, overlap_id: str) -> Overlap | None:
        # A rank is a position in the whole list, so there is no cheaper way to get one right.
        return next((o for o in self.list_overlaps() if o.overlap_id == overlap_id), None)


def _select_projects(conn: psycopg.Connection) -> list[Project]:
    rows = conn.execute(f"SELECT {PROJECT_COLUMNS} FROM projects").fetchall()
    return [Project.model_validate(row) for row in rows]


def ranked_overlaps(
    stored: Sequence[EngineOverlap],
    published: Sequence[Project],
    submitted: Sequence[Project],
) -> list[Overlap]:
    """Stored published pairs plus every pair involving an uploaded project, ranked together.

    `rank` is not stored: it is the position by rank_opportunities (tier first, then score),
    so an uploaded pair can take rank 1 and pushes the published pairs down. Each pair's
    closest approach is computed once here and used both to rank it and to serve it.

    The closest approach is capped at the center distance: the centers are two points of
    the pair that are already that close. Published centers lie on their own segments, so
    the cap only bites when an upload's endpoints sit far from its own center, which would
    otherwise push closest_mi past the 25 mi bound and fail the whole response.
    """
    projects = {p.project_id: p for p in [*published, *submitted]}
    pairs = [*stored, *submitted_overlaps(published, submitted)]
    closest = {
        o.overlap_id: min(
            closest_mi(projects[o.project_id_a], projects[o.project_id_b]), o.distance_mi
        )
        for o in pairs
    }
    ranked = rank_opportunities(pairs, lambda o: coordination_tier(closest[o.overlap_id]))
    return [
        build_overlap(o, rank, projects, closest[o.overlap_id])
        for rank, o in enumerate(ranked, start=1)
    ]


def closest_mi(project_a: Project, project_b: Project) -> float:
    """Miles between the closest points of two projects' footprints (segment, else center)."""
    return closest_approach_miles(_footprint(project_a), _footprint(project_b))


def _footprint(p: Project) -> tuple[LatLon, ...]:
    return footprint(p.lat_a, p.lon_a, p.lat_b, p.lon_b, p.lat_center, p.lon_center)


def build_overlap(
    overlap: EngineOverlap, rank: int, projects: dict[str, Project], closest: float
) -> Overlap:
    """An engine overlap plus its rank, two projects and closest approach, as the API serves it.

    The tier follows from `closest` (see ranked_overlaps); the savings estimate is derived
    here from the projects' costs. Neither is stored.
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
        closest_mi=closest,
        tier=coordination_tier(closest),
        time_gap_days=overlap.time_gap_days,
        project_a=project_a,
        project_b=project_b,
        est_savings_usd=savings.est_savings_usd,
        savings_basis=savings.savings_basis,
    )
