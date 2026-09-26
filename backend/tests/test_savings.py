"""The savings estimate (pipeline/savings.py): pure, positive, decaying, and honest about nulls."""

import inspect
from itertools import pairwise

import pytest

from pipeline import savings
from pipeline.overlap import OVERLAP_RADIUS_MI, Overlap
from pipeline.savings import (
    DISTANCE_DISCOUNT_AT_RADIUS,
    SHARED_MOBILIZATION_SHARE,
    TIME_HALF_LIFE_DAYS,
    SavingsEstimate,
    estimate_savings,
)

DESC = "Dominion Energy South Carolina"
GPC = "Georgia Power"
DESC_3_COST = 23_787_423  # the docs/api.md example's DESC_3 cost


def pair(distance_mi: float, time_gap_days: int) -> Overlap:
    return Overlap("OVL_1", "DESC_3", "GPC_2", distance_mi, time_gap_days, 0.5)


def desc_vs_gpc(distance_mi: float, time_gap_days: int, cost: int = DESC_3_COST):
    return estimate_savings(
        pair(distance_mi, time_gap_days), cost, None, utility_a=DESC, utility_b=GPC
    )


# --- known cost ---------------------------------------------------------------------------


def test_known_cost_gives_the_documented_formula_in_whole_dollars():
    result = desc_vs_gpc(5.65, 152)

    expected = (
        SHARED_MOBILIZATION_SHARE
        * DESC_3_COST
        * (1 - DISTANCE_DISCOUNT_AT_RADIUS * 5.65 / OVERLAP_RADIUS_MI)
        * 0.5 ** (152 / TIME_HALF_LIFE_DAYS)
    )
    assert result.est_savings_usd == round(expected) == 709_900
    assert isinstance(result.est_savings_usd, int)


def test_same_place_same_day_is_the_full_mobilization_share():
    assert desc_vs_gpc(0, 0).est_savings_usd == round(SHARED_MOBILIZATION_SHARE * DESC_3_COST)


@pytest.mark.parametrize(
    ("distance_mi", "time_gap_days"),
    [(0, 0), (5.65, 152), (14.81, 730), (OVERLAP_RADIUS_MI, 0), (24.99, 3074), (25.0, 3650)],
)
def test_known_cost_is_strictly_positive_anywhere_inside_the_radius(distance_mi, time_gap_days):
    assert desc_vs_gpc(distance_mi, time_gap_days).est_savings_usd > 0


def test_estimate_strictly_decreases_as_distance_grows():
    distances = [0, 4.09, 5.65, 7.55, 14.34, 20.0, OVERLAP_RADIUS_MI]
    estimates = [desc_vs_gpc(d, 152).est_savings_usd for d in distances]

    assert all(near > far for near, far in pairwise(estimates)), estimates


def test_estimate_strictly_decreases_as_time_gap_grows():
    gaps = [0, 152, 365, 517, 730, 1825, 3074]
    estimates = [desc_vs_gpc(5.65, g).est_savings_usd for g in gaps]

    assert all(sooner > later for sooner, later in pairwise(estimates)), estimates


def test_time_gap_halves_the_estimate_every_half_life():
    one_year = desc_vs_gpc(0, TIME_HALF_LIFE_DAYS).est_savings_usd
    assert one_year == round(SHARED_MOBILIZATION_SHARE * DESC_3_COST / 2)


def test_cost_on_either_side_is_used():
    overlap = pair(7.55, 517)
    a_side = estimate_savings(overlap, DESC_3_COST, None, utility_a=DESC, utility_b=GPC)
    b_side = estimate_savings(overlap, None, DESC_3_COST, utility_a=GPC, utility_b=DESC)

    assert a_side.est_savings_usd == b_side.est_savings_usd > 0


def test_both_costs_known_uses_the_smaller():
    overlap = pair(7.55, 517)
    both = estimate_savings(overlap, 50_000_000, 2_000_000)

    assert both.est_savings_usd == estimate_savings(overlap, 2_000_000, None).est_savings_usd
    assert both.est_savings_usd == estimate_savings(overlap, None, 2_000_000).est_savings_usd
    assert "smaller" in both.savings_basis


def test_known_cost_basis_explains_the_number():
    basis = desc_vs_gpc(5.65, 152).savings_basis

    assert "5%" in basis
    assert "$23,787,423" in basis
    assert DESC in basis
    assert "5.65 mi" in basis and "152 days" in basis
    # The other side's missing figure is still explained.
    assert "cost redacted in Georgia Power IRP" in basis


# --- no known cost ------------------------------------------------------------------------


def test_no_known_cost_is_null_with_the_georgia_power_reason():
    result = estimate_savings(pair(5.65, 152), None, None, utility_a=DESC, utility_b=GPC)

    assert result.est_savings_usd is None
    assert "cost redacted in Georgia Power IRP" in result.savings_basis
    assert "no published cost" in result.savings_basis  # the DESC side's reason


def test_no_known_cost_without_utilities_still_gives_a_reason():
    result = estimate_savings(pair(5.65, 152), None, None)

    assert result == SavingsEstimate(
        None,
        "No estimate: neither project has a known cost "
        "(project A: no published cost; project B: no published cost).",
    )


# --- boundary validation ------------------------------------------------------------------


@pytest.mark.parametrize(("cost_a", "cost_b"), [(-1, None), (None, -5), (-1, 100)])
def test_negative_cost_is_rejected(cost_a, cost_b):
    with pytest.raises(ValueError, match="cost_"):
        estimate_savings(pair(5.65, 152), cost_a, cost_b)


@pytest.mark.parametrize("distance_mi", [-0.01, OVERLAP_RADIUS_MI + 0.01])
def test_distance_outside_the_radius_is_rejected(distance_mi):
    with pytest.raises(ValueError, match="distance_mi"):
        estimate_savings(pair(distance_mi, 152), DESC_3_COST, None)


def test_negative_time_gap_is_rejected():
    with pytest.raises(ValueError, match="time_gap_days"):
        estimate_savings(pair(5.65, -1), DESC_3_COST, None)


# --- purity and documentation -------------------------------------------------------------


def test_estimate_is_deterministic_and_does_not_mutate_its_input():
    overlap = pair(7.55, 517)
    first = estimate_savings(overlap, DESC_3_COST, None, utility_a=DESC, utility_b=GPC)
    second = estimate_savings(overlap, DESC_3_COST, None, utility_a=DESC, utility_b=GPC)

    assert first == second
    assert overlap == pair(7.55, 517)


def test_module_does_no_io_and_reuses_the_engine_radius():
    source = inspect.getsource(savings)
    for forbidden in ("open(", "psycopg", "datetime", "requests", "os.environ"):
        assert forbidden not in source
    assert "OVERLAP_RADIUS_MI = " not in source  # imported from the engine, not redefined


@pytest.mark.parametrize(
    "constant",
    ["SHARED_MOBILIZATION_SHARE", "DISTANCE_DISCOUNT_AT_RADIUS", "TIME_HALF_LIFE_DAYS"],
)
def test_docstring_documents_each_constant_and_its_value(constant):
    doc = estimate_savings.__doc__
    assert f"{constant} = {getattr(savings, constant)}" in doc


def test_docstring_admits_the_percentage_is_an_assumption():
    assert "assumption" in estimate_savings.__doc__
