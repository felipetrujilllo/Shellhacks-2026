"""Overlap engine tests, anchored on the sponsor's 10-project / 6-overlap reference table."""

import csv
import math
from datetime import date
from pathlib import Path

import pytest

from pipeline.overlap import (
    Overlap,
    Project,
    detect_overlaps,
    haversine_miles,
    opportunity_score,
    rank_by_score,
    time_gap_days,
)

FIXTURES = Path(__file__).parent / "fixtures"

# Spec numbers written out as literals, deliberately NOT imported from the engine:
# a test that derives its expectation from the constant under test cannot catch that
# constant being wrong. These come from docs/prompt.md.
SPEC_EARTH_RADIUS_MI = 3958.8
SPEC_OVERLAP_RADIUS_MI = 25.0

# On a sphere, a degree along a meridian is R * pi / 180 miles at any latitude.
MILES_PER_DEGREE = SPEC_EARTH_RADIUS_MI * math.pi / 180


def load_starter_projects() -> list[Project]:
    with open(FIXTURES / "starter_projects.csv", newline="") as f:
        return [
            Project(
                project_id=row["project_id"],
                utility=row["utility"],
                lat_center=float(row["lat_center"]),
                lon_center=float(row["lon_center"]),
                in_service_date=date.fromisoformat(row["in_service_date"]),
            )
            for row in csv.DictReader(f)
        ]


def load_expected_overlaps() -> list[dict]:
    with open(FIXTURES / "starter_overlaps.csv", newline="") as f:
        return list(csv.DictReader(f))


def project(project_id, utility, lat, lon, day="2025-01-01") -> Project:
    return Project(project_id, utility, lat, lon, date.fromisoformat(day))


# --- golden test: the sponsor's reference table -------------------------------------


def test_starter_table_yields_exactly_six_overlaps():
    assert len(detect_overlaps(load_starter_projects())) == 6


def test_starter_table_reproduces_the_reference_table_exactly():
    found = detect_overlaps(load_starter_projects())
    expected = load_expected_overlaps()

    assert [o.overlap_id for o in found] == [e["overlap_id"] for e in expected]
    assert [(o.project_id_a, o.project_id_b) for o in found] == [
        (e["project_id_a"], e["project_id_b"]) for e in expected
    ]
    assert [o.distance_mi for o in found] == [float(e["distance_mi"]) for e in expected]
    assert [o.time_gap_days for o in found] == [int(e["time_gap_days"]) for e in expected]


def test_projects_with_no_nearby_counterpart_are_never_flagged():
    flagged = {
        project_id
        for overlap in detect_overlaps(load_starter_projects())
        for project_id in (overlap.project_id_a, overlap.project_id_b)
    }
    # Charleston and south-Georgia projects sit far from the Savannah River border.
    assert flagged.isdisjoint({"DESC_4", "GPC_4", "GPC_5"})


# --- haversine ----------------------------------------------------------------------


def test_haversine_matches_a_known_equator_degree():
    assert haversine_miles(0.0, 0.0, 0.0, 1.0) == pytest.approx(MILES_PER_DEGREE, abs=1e-6)


def test_haversine_is_zero_for_the_same_point():
    assert haversine_miles(33.5, -82.1, 33.5, -82.1) == pytest.approx(0.0, abs=1e-9)


def test_haversine_is_symmetric():
    there = haversine_miles(33.660127, -82.195931, 33.6020605, -82.1822895)
    back = haversine_miles(33.6020605, -82.1822895, 33.660127, -82.195931)
    assert there == pytest.approx(back, abs=1e-12)


# --- the 25-mile gate ---------------------------------------------------------------


def pair_separated_by(miles: float) -> list[Project]:
    """Two cross-utility projects exactly `miles` apart along a meridian."""
    return [
        project("DESC_X", "DESC", 33.0, -82.0),
        project("GPC_X", "GPC", 33.0 + miles / MILES_PER_DEGREE, -82.0),
    ]


def test_pair_inside_the_radius_is_flagged():
    overlaps = detect_overlaps(pair_separated_by(20.0))

    assert len(overlaps) == 1
    assert overlaps[0].distance_mi == pytest.approx(20.0, abs=0.01)


def test_pair_outside_the_radius_is_ignored():
    assert detect_overlaps(pair_separated_by(30.0)) == []


def test_pair_just_inside_twenty_five_miles_is_flagged():
    """Pins the spec's actual threshold — a wrong radius constant must fail here."""
    overlaps = detect_overlaps(pair_separated_by(SPEC_OVERLAP_RADIUS_MI - 0.001))

    assert len(overlaps) == 1
    assert overlaps[0].distance_mi == pytest.approx(24.999, abs=0.01)


def test_pair_just_outside_twenty_five_miles_is_ignored():
    # Approached from just outside rather than at exactly 25.0: the boundary is a float
    # coin-flip that lands differently across libm builds, the threshold is not.
    assert detect_overlaps(pair_separated_by(SPEC_OVERLAP_RADIUS_MI + 0.001)) == []


# --- pairing rules ------------------------------------------------------------------


def test_same_utility_projects_are_never_paired():
    same_utility = [
        project("DESC_X", "DESC", 33.0, -82.0),
        project("DESC_Y", "DESC", 33.01, -82.01),
    ]

    assert detect_overlaps(same_utility) == []


def test_each_cross_utility_pair_is_reported_once():
    trio = [
        project("DESC_X", "DESC", 33.0, -82.0),
        project("GPC_X", "GPC", 33.01, -82.0),
        project("GPC_Y", "GPC", 33.02, -82.0),
    ]

    overlaps = detect_overlaps(trio)

    pairs = [(o.project_id_a, o.project_id_b) for o in overlaps]
    assert sorted(pairs) == [("DESC_X", "GPC_X"), ("DESC_X", "GPC_Y")]
    assert len(pairs) == len(set(pairs))


def test_overlaps_are_numbered_by_ascending_distance():
    projects = [
        project("DESC_X", "DESC", 33.0, -82.0),
        project("GPC_FAR", "GPC", 33.2, -82.0),
        project("GPC_NEAR", "GPC", 33.01, -82.0),
    ]

    overlaps = detect_overlaps(projects)

    assert [o.overlap_id for o in overlaps] == ["OVL_1", "OVL_2"]
    assert overlaps[0].project_id_b == "GPC_NEAR"
    assert overlaps[0].distance_mi < overlaps[1].distance_mi


# --- time gap -----------------------------------------------------------------------


def test_time_gap_counts_days_between_in_service_dates():
    assert time_gap_days(date(2025, 1, 1), date(2025, 3, 2)) == 60


def test_time_gap_is_absolute_regardless_of_order():
    earlier, later = date(2024, 12, 31), date(2033, 6, 1)
    assert time_gap_days(earlier, later) == time_gap_days(later, earlier)


def test_time_gap_is_recorded_on_a_flagged_pair():
    pair = [
        project("DESC_X", "DESC", 33.0, -82.0, day="2025-01-01"),
        project("GPC_X", "GPC", 33.01, -82.0, day="2025-01-31"),
    ]

    assert detect_overlaps(pair)[0].time_gap_days == 30


def test_time_gap_alone_never_flags_a_distant_pair():
    """The spec makes distance the gate; a same-day pair 200 miles apart is not an overlap."""
    pair = [
        project("DESC_X", "DESC", 33.0, -82.0, day="2025-01-01"),
        project("GPC_X", "GPC", 36.0, -82.0, day="2025-01-01"),
    ]

    assert detect_overlaps(pair) == []


# --- scoring and ranking ------------------------------------------------------------


def test_score_stays_between_zero_and_one():
    for distance, gap in [(0.0, 0), (25.0, 100000), (12.5, 900), (24.99, 1)]:
        assert 0.0 <= opportunity_score(distance, gap) <= 1.0


def test_closer_projects_score_higher_at_the_same_time_gap():
    assert opportunity_score(2.0, 100) > opportunity_score(20.0, 100)


def test_smaller_time_gaps_score_higher_at_the_same_distance():
    assert opportunity_score(10.0, 30) > opportunity_score(10.0, 900)


def test_distance_outweighs_time_gap():
    """Distance is the primary signal, so it must win a head-to-head against the gap."""
    very_close_but_far_apart_in_time = opportunity_score(1.0, 1825)
    barely_inside_but_simultaneous = opportunity_score(24.0, 0)
    assert very_close_but_far_apart_in_time > barely_inside_but_simultaneous


def test_time_gaps_past_the_horizon_stop_mattering():
    assert opportunity_score(5.0, 1825) == opportunity_score(5.0, 5000)


def test_ranking_puts_the_best_opportunity_first():
    overlaps = [
        Overlap("OVL_1", "DESC_1", "GPC_1", 4.09, 3074, opportunity_score(4.09, 3074)),
        Overlap("OVL_2", "DESC_3", "GPC_2", 5.65, 152, opportunity_score(5.65, 152)),
    ]

    ranked = rank_by_score(overlaps)

    # Near-simultaneous beats slightly-closer-but-eight-years-apart.
    assert [o.overlap_id for o in ranked] == ["OVL_2", "OVL_1"]


def test_ranking_orders_the_starter_table_by_descending_score():
    ranked = rank_by_score(detect_overlaps(load_starter_projects()))

    scores = [o.score for o in ranked]
    assert scores == sorted(scores, reverse=True)
    assert ranked[0].overlap_id == "OVL_2"


def test_ranking_keeps_every_overlap():
    overlaps = detect_overlaps(load_starter_projects())
    assert sorted(o.overlap_id for o in rank_by_score(overlaps)) == sorted(
        o.overlap_id for o in overlaps
    )


# --- degenerate input ---------------------------------------------------------------


def test_empty_input_produces_no_overlaps():
    assert detect_overlaps([]) == []


def test_single_project_produces_no_overlaps():
    assert detect_overlaps([project("DESC_X", "DESC", 33.0, -82.0)]) == []
