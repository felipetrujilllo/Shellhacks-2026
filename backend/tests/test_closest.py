"""Closest-approach tiers and tier-first ranking (Sperry's published distance tiers)."""

import csv
import math
from pathlib import Path

import pytest
from test_overlap import load_expected_overlaps, load_starter_projects

from pipeline.overlap import (
    Overlap,
    closest_approach_miles,
    coordination_tier,
    detect_overlaps,
    footprint,
    opportunity_score,
    rank_by_score,
    rank_opportunities,
)

FIXTURES = Path(__file__).parent / "fixtures"

# Spec numbers as literals, not imported from the engine (see test_overlap.py).
SPEC_EARTH_RADIUS_MI = 3958.8
MILES_PER_DEGREE = SPEC_EARTH_RADIUS_MI * math.pi / 180


def lon_offset(miles: float, lat: float) -> float:
    """Degrees of longitude spanning `miles` along the parallel at `lat`."""
    return miles / (MILES_PER_DEGREE * math.cos(math.radians(lat)))


def optional_float(value: str) -> float | None:
    return float(value) if value.strip() else None


def load_starter_footprints() -> dict[str, tuple]:
    """Each starter project's footprint, built from its endpoint columns (blank → center)."""
    with open(FIXTURES / "starter_projects.csv", newline="", encoding="utf-8") as f:
        return {
            row["project_id"]: footprint(
                optional_float(row["lat_a"]),
                optional_float(row["lon_a"]),
                optional_float(row["lat_b"]),
                optional_float(row["lon_b"]),
                float(row["lat_center"]),
                float(row["lon_center"]),
            )
            for row in csv.DictReader(f)
        }


def starter_tier_of():
    shapes = load_starter_footprints()

    def tier_of(o: Overlap) -> str:
        return coordination_tier(
            closest_approach_miles(shapes[o.project_id_a], shapes[o.project_id_b])
        )

    return tier_of


def overlap(overlap_id: str, distance_mi: float, gap_days: int) -> Overlap:
    return Overlap(
        overlap_id,
        "DESC_X",
        "GPC_X",
        distance_mi,
        gap_days,
        opportunity_score(distance_mi, gap_days),
    )


# --- closest approach ---------------------------------------------------------------


def test_crossing_segments_are_zero_apart_and_tier_crossing():
    a = ((33.0, -82.0), (33.1, -82.1))
    b = ((33.0, -82.1), (33.1, -82.0))

    closest = closest_approach_miles(a, b)

    assert closest == 0.0
    assert coordination_tier(closest) == "crossing"


def test_segments_sharing_an_endpoint_are_zero_apart_and_tier_crossing():
    a = ((33.0, -82.0), (33.1, -82.1))
    b = ((33.1, -82.1), (33.3, -82.0))

    closest = closest_approach_miles(a, b)

    assert closest == 0.0
    assert coordination_tier(closest) == "crossing"


def test_parallel_segments_half_a_mile_apart_are_tier_shared_land():
    a = ((33.0, -82.0), (33.2, -82.0))
    b = ((33.0, -82.0 + lon_offset(0.5, 33.1)), (33.2, -82.0 + lon_offset(0.5, 33.1)))

    closest = closest_approach_miles(a, b)

    assert 0.4 <= closest <= 0.6
    assert coordination_tier(closest) == "shared_land"


def test_point_three_miles_from_a_segments_middle_is_tier_site_logistics():
    segment = ((33.0, -82.0), (33.2, -82.0))
    point = ((33.1, -82.0 + lon_offset(3.0, 33.1)),)

    closest = closest_approach_miles(segment, point)

    assert closest == pytest.approx(3.0, abs=0.05)
    # Measured to the middle, not an end: each end is ~7.5 mi from the point.
    assert (
        closest
        < min(
            closest_approach_miles((segment[0],), point),
            closest_approach_miles((segment[1],), point),
        )
        - 4
    )
    assert coordination_tier(closest) == "site_logistics"


def test_closest_approach_is_symmetric():
    a = ((33.0, -82.0), (33.2, -82.0))
    b = ((33.1, -81.9), (33.3, -81.95))
    assert closest_approach_miles(a, b) == closest_approach_miles(b, a)


@pytest.mark.parametrize(
    "lat_a, lon_a, lat_b, lon_b",
    [(None, None, 33.5, -82.5), (33.5, -82.5, None, None), (33.5, None, 33.6, -82.6)],
)
def test_a_project_with_a_missing_endpoint_is_its_center(lat_a, lon_a, lat_b, lon_b):
    shape = footprint(lat_a, lon_a, lat_b, lon_b, 33.0, -82.0)

    assert shape == ((33.0, -82.0),)
    # And the distance really is measured from the center, not the known endpoint.
    other = ((33.0, -82.0 + lon_offset(2.0, 33.0)),)
    assert closest_approach_miles(shape, other) == pytest.approx(2.0, abs=0.01)


def test_a_project_with_both_endpoints_is_its_segment():
    assert footprint(33.5, -82.5, 33.6, -82.6, 33.55, -82.55) == ((33.5, -82.5), (33.6, -82.6))


def test_footprints_must_have_one_or_two_points():
    with pytest.raises(ValueError):
        closest_approach_miles((), ((33.0, -82.0),))


# --- tiers --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "closest_mi, tier",
    [
        (0.0, "crossing"),
        (0.01, "shared_land"),
        (0.99, "shared_land"),
        (1.0, "site_logistics"),
        (4.99, "site_logistics"),
        (5.0, "crews"),
        (24.0, "crews"),
    ],
)
def test_coordination_tier_boundaries(closest_mi, tier):
    assert coordination_tier(closest_mi) == tier


def test_negative_closest_approach_fails_loud():
    with pytest.raises(ValueError):
        coordination_tier(-0.1)


# --- tier-first ranking -------------------------------------------------------------


def test_a_higher_scoring_crews_pair_ranks_below_a_site_logistics_pair():
    crews = overlap("OVL_1", 2.0, 0)
    site_logistics = overlap("OVL_2", 20.0, 1800)
    assert crews.score > site_logistics.score
    tiers = {"OVL_1": "crews", "OVL_2": "site_logistics"}

    ranked = rank_opportunities([crews, site_logistics], lambda o: tiers[o.overlap_id])

    assert [o.overlap_id for o in ranked] == ["OVL_2", "OVL_1"]


def test_within_one_tier_the_order_equals_rank_by_score():
    overlaps = [
        overlap("OVL_1", 4.09, 3074),
        overlap("OVL_2", 5.65, 152),
        overlap("OVL_3", 7.55, 517),
        overlap("OVL_4", 8.01, 3074),
        overlap("OVL_5", 3.0, 3074),
    ]

    assert rank_opportunities(overlaps, lambda o: "crews") == rank_by_score(overlaps)


def test_ranking_follows_the_full_tier_order():
    tiers = {
        "OVL_1": "crews",
        "OVL_2": "site_logistics",
        "OVL_3": "shared_land",
        "OVL_4": "crossing",
    }
    overlaps = [overlap(i, 10.0, 100) for i in tiers]

    ranked = rank_opportunities(overlaps, lambda o: tiers[o.overlap_id])

    assert [o.overlap_id for o in ranked] == ["OVL_4", "OVL_3", "OVL_2", "OVL_1"]


def test_an_unknown_tier_fails_loud():
    with pytest.raises(ValueError):
        rank_opportunities([overlap("OVL_1", 1.0, 1), overlap("OVL_2", 2.0, 2)], lambda o: "nearby")


# --- the sponsor's starter table ----------------------------------------------------


def test_every_reference_pair_is_no_farther_apart_at_its_closest_than_at_its_centers():
    shapes = load_starter_footprints()
    expected = load_expected_overlaps()
    assert len(expected) == 6

    for row in expected:
        closest = closest_approach_miles(shapes[row["project_id_a"]], shapes[row["project_id_b"]])
        assert closest <= float(row["distance_mi"]) + 0.05, row["overlap_id"]


def test_hooks_thurmond_and_evans_thurmond_dam_touch_at_thurmond():
    shapes = load_starter_footprints()
    assert closest_approach_miles(shapes["DESC_2"], shapes["GPC_1"]) == 0.0


def test_tier_first_ranking_puts_ovl_1_first_on_the_starter_table():
    overlaps = detect_overlaps(load_starter_projects())

    ranked = rank_opportunities(overlaps, starter_tier_of())

    assert ranked[0].overlap_id == "OVL_1"
    # Score-only ranking had OVL_2 first; the tier is what moves OVL_1 up.
    assert rank_by_score(overlaps)[0].overlap_id == "OVL_2"
    assert sorted(o.overlap_id for o in ranked) == sorted(o.overlap_id for o in overlaps)
