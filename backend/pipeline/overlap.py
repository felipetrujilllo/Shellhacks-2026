"""Cross-utility overlap detection — the deterministic core of GridWatch.

Pure functions over Project records: no LLM, no database, no web framework, so the
sponsor's reference table can be reproduced exactly and the job re-run on demand.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterable, Sequence
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

# Sperry's distance tiers, measured between the closest points of two projects (1.6 km
# and 8 km in the published spec). They only order pairs — the 25-mile center gate above
# still decides what is flagged.
SHARED_LAND_UNDER_MI = 1.0
SITE_LOGISTICS_UNDER_MI = 5.0
TIER_ORDER = ("crossing", "shared_land", "site_logistics", "crews")

# A (lat, lon) point; a project's footprint is its A→B segment (two points) or its center
# (one point).
LatLon = tuple[float, float]
# The same point projected to the local flat grid, as (x, y) in miles.
XY = tuple[float, float]


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
    """One flagged cross-utility pair, shaped like a row of the `project_overlaps` table.

    The SQL table is `project_overlaps` (OVERLAPS is a reserved word in Postgres); the API
    endpoint is still `GET /overlaps`.
    """

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


def footprint(
    lat_a: float | None,
    lon_a: float | None,
    lat_b: float | None,
    lon_b: float | None,
    lat_center: float,
    lon_center: float,
) -> tuple[LatLon, ...]:
    """A project's shape for `closest_approach_miles`, built from its nullable endpoints.

    The A→B segment when both endpoints are known, otherwise just the center point.
    """
    if None in (lat_a, lon_a, lat_b, lon_b):
        return ((lat_center, lon_center),)
    return ((lat_a, lon_a), (lat_b, lon_b))


def _cross(o: XY, p: XY, q: XY) -> float:
    """z of (p - o) × (q - o): > 0 left turn, < 0 right turn, 0 collinear."""
    return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])


def _within_box(p: XY, q: XY, r: XY) -> bool:
    """For r collinear with p–q: does r lie on that segment?"""
    return min(p[0], q[0]) <= r[0] <= max(p[0], q[0]) and min(p[1], q[1]) <= r[1] <= max(p[1], q[1])


def _segments_touch(p1: XY, q1: XY, p2: XY, q2: XY) -> bool:
    """Do segments p1–q1 and p2–q2 cross or touch (including collinear overlap)?

    A single point is the degenerate segment (p, p), which this handles as is.
    """
    d1, d2 = _cross(p2, q2, p1), _cross(p2, q2, q1)
    d3, d4 = _cross(p1, q1, p2), _cross(p1, q1, q2)
    if ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4)):
        return True
    return (
        (d1 == 0 and _within_box(p2, q2, p1))
        or (d2 == 0 and _within_box(p2, q2, q1))
        or (d3 == 0 and _within_box(p1, q1, p2))
        or (d4 == 0 and _within_box(p1, q1, q2))
    )


def _point_to_segment(r: XY, p: XY, q: XY) -> float:
    """Distance from point r to segment p–q on the flat grid."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    length_sq = dx * dx + dy * dy
    t = 0.0 if length_sq == 0 else ((r[0] - p[0]) * dx + (r[1] - p[1]) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    return sqrt((r[0] - p[0] - t * dx) ** 2 + (r[1] - p[1] - t * dy) ** 2)


def closest_approach_miles(a: Sequence[LatLon], b: Sequence[LatLon]) -> float:
    """Distance in miles between the closest points of two project footprints.

    Each footprint is 1 (center) or 2 (A→B segment) (lat, lon) points — see `footprint`.
    Points are projected to a local flat grid in miles centered on their mean latitude,
    which is accurate well within a percent at the < 25-mile scale of flagged pairs.
    0.0 when the footprints cross or touch; rounded to 2 decimals like `distance_mi`.
    """
    for shape in (a, b):
        if len(shape) not in (1, 2):
            raise ValueError(f"a footprint has 1 or 2 points, got {len(shape)}")
    points = [*a, *b]
    x_scale = EARTH_RADIUS_MI * cos(radians(sum(lat for lat, _ in points) / len(points)))

    def flat(point: LatLon) -> XY:
        lat, lon = point
        return (x_scale * radians(lon), EARTH_RADIUS_MI * radians(lat))

    p1, q1 = flat(a[0]), flat(a[-1])
    p2, q2 = flat(b[0]), flat(b[-1])
    if _segments_touch(p1, q1, p2, q2):
        return 0.0
    closest = min(
        _point_to_segment(p1, p2, q2),
        _point_to_segment(q1, p2, q2),
        _point_to_segment(p2, p1, q1),
        _point_to_segment(q2, p1, q1),
    )
    return round(closest, 2)


def coordination_tier(closest_mi: float) -> str:
    """Sperry's distance tier for a pair's closest approach — one of `TIER_ORDER`."""
    if closest_mi < 0:
        raise ValueError(f"closest approach cannot be negative, got {closest_mi}")
    if closest_mi == 0:
        return "crossing"
    if closest_mi < SHARED_LAND_UNDER_MI:
        return "shared_land"
    if closest_mi < SITE_LOGISTICS_UNDER_MI:
        return "site_logistics"
    return "crews"


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


def rank_opportunities(
    overlaps: Sequence[Overlap], tier_of: Callable[[Overlap], str]
) -> list[Overlap]:
    """Order flagged pairs tier-first (`TIER_ORDER`), then as `rank_by_score` does.

    `tier_of` maps an overlap to its `coordination_tier`; the caller owns the endpoint
    data, so the engine never needs it. An unknown tier raises instead of sorting last.
    """

    def key(o: Overlap) -> tuple:
        tier = tier_of(o)
        if tier not in TIER_ORDER:
            raise ValueError(f"unknown coordination tier {tier!r} for {o.overlap_id}")
        return (TIER_ORDER.index(tier), -o.score, o.distance_mi, o.overlap_id)

    return sorted(overlaps, key=key)
