"""Cross-utility overlap detection — the deterministic core of GridWatch.

Pure functions over Project records: no LLM, no database, no web framework, so the
sponsor's reference table can be reproduced exactly and the job re-run on demand.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from math import asin, cos, radians, sin, sqrt

# The sponsor's reference table was computed with this radius; using the WGS84
# spheroid instead shifts distances in the second decimal and breaks the golden test.
EARTH_RADIUS_MI = 3958.8

OVERLAP_RADIUS_MI = 25.0

# Distance is the gate, so it carries more weight; the time gap only orders pairs
# that already qualify. Gaps saturate at five years — beyond that two projects are
# equally uncoordinatable, and without a cap one far-future date would dominate.
SCORE_TIME_HORIZON_DAYS = 1825
DISTANCE_WEIGHT = 0.6
TIME_WEIGHT = 0.4


@dataclass(frozen=True)
class Project:
    """One utility's planned project, reduced to what overlap detection needs."""

    project_id: str
    utility: str
    lat_center: float
    lon_center: float
    in_service_date: date


@dataclass(frozen=True)
class Overlap:
    """One flagged cross-utility pair, shaped like a row of the `overlaps` table."""

    overlap_id: str
    project_id_a: str
    project_id_b: str
    distance_mi: float
    time_gap_days: int
    score: float


def haversine_miles(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Great-circle distance between two points in miles."""
    phi_a, phi_b = radians(lat_a), radians(lat_b)
    delta_phi = phi_b - phi_a
    delta_lambda = radians(lon_b) - radians(lon_a)
    h = sin(delta_phi / 2) ** 2 + cos(phi_a) * cos(phi_b) * sin(delta_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_MI * asin(sqrt(h))


def time_gap_days(date_a: date, date_b: date) -> int:
    """Absolute gap in days between two in-service dates."""
    return abs((date_a - date_b).days)


def opportunity_score(distance_mi: float, gap_days: int) -> float:
    """Rank a flagged pair from 0 to 1 — closer and closer-in-time scores higher."""
    distance_part = 1.0 - min(distance_mi, OVERLAP_RADIUS_MI) / OVERLAP_RADIUS_MI
    time_part = 1.0 - min(gap_days, SCORE_TIME_HORIZON_DAYS) / SCORE_TIME_HORIZON_DAYS
    return round(DISTANCE_WEIGHT * distance_part + TIME_WEIGHT * time_part, 4)


def detect_overlaps(projects: Iterable[Project]) -> list[Overlap]:
    """Flag every cross-utility pair whose centers are less than 25 miles apart.

    Returned in ascending distance order and numbered OVL_1..OVL_N to line up with
    the sponsor's reference table. Ranking for the UI is a separate concern —
    see `rank_by_score`.
    """
    flagged: list[tuple[float, str, str, int]] = []

    # Sorting by id first makes the a/b side of each pair deterministic.
    for a, b in itertools.combinations(sorted(projects, key=lambda p: p.project_id), 2):
        if a.utility == b.utility:
            continue
        distance = haversine_miles(a.lat_center, a.lon_center, b.lat_center, b.lon_center)
        if distance >= OVERLAP_RADIUS_MI:
            continue
        gap = time_gap_days(a.in_service_date, b.in_service_date)
        flagged.append((round(distance, 2), a.project_id, b.project_id, gap))

    flagged.sort()
    return [
        Overlap(
            overlap_id=f"OVL_{position}",
            project_id_a=project_id_a,
            project_id_b=project_id_b,
            distance_mi=distance,
            time_gap_days=gap,
            score=opportunity_score(distance, gap),
        )
        for position, (distance, project_id_a, project_id_b, gap) in enumerate(flagged, start=1)
    ]


def rank_by_score(overlaps: Sequence[Overlap]) -> list[Overlap]:
    """Order flagged pairs for the 'top coordination opportunities' list."""
    return sorted(overlaps, key=lambda o: (-o.score, o.distance_mi, o.overlap_id))
