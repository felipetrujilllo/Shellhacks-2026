"""Rough cost/impact estimate for a flagged overlap: what coordinating the two jobs might save.

Pure functions only — no I/O, no database, no clock — so the number behind every flagged pair
is reproducible and explainable in one sentence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pipeline.overlap import OVERLAP_RADIUS_MI

# ASSUMPTION, not a sourced figure: mobilization/demobilization (moving crews, equipment and
# temporary facilities on and off site) is commonly quoted at roughly 3-10% of a construction
# contract. We take a conservative 5% of the known project cost as the share two coordinated
# jobs could split instead of paying twice.
SHARED_MOBILIZATION_SHARE = 0.05

# At the edge of the overlap radius the jobs share far less (separate staging yards, longer
# crew moves), so the estimate falls linearly with distance to 10% of its full value at
# OVERLAP_RADIUS_MI. It never reaches zero because every flagged pair is inside the radius.
DISTANCE_DISCOUNT_AT_RADIUS = 0.9

# Crews and equipment can only be shared if the jobs happen near the same time. The estimate
# halves for every year between the two in-service dates: strictly positive, strictly falling.
TIME_HALF_LIFE_DAYS = 365

# Georgia Power publishes its project list in its IRP but redacts every project cost.
REDACTED_COST_UTILITY = "Georgia Power"
REDACTED_COST_REASON = "cost redacted in Georgia Power IRP"
MISSING_COST_REASON = "no published cost"


class OverlapGeometry(Protocol):
    """Anything with the engine's distance and time gap (pipeline or API Overlap)."""

    distance_mi: float
    time_gap_days: int


@dataclass(frozen=True)
class SavingsEstimate:
    """Whole-dollar estimate (None when no cost is known) and the plain-English reason."""

    est_savings_usd: int | None
    savings_basis: str


def distance_factor(distance_mi: float) -> float:
    """1.0 at 0 mi, falling linearly to 1 - DISTANCE_DISCOUNT_AT_RADIUS at the radius."""
    return 1.0 - DISTANCE_DISCOUNT_AT_RADIUS * distance_mi / OVERLAP_RADIUS_MI


def time_factor(time_gap_days: int) -> float:
    """1.0 at a zero gap, halving every TIME_HALF_LIFE_DAYS."""
    return 0.5 ** (time_gap_days / TIME_HALF_LIFE_DAYS)


def estimate_savings(
    overlap: OverlapGeometry,
    cost_a: int | None,
    cost_b: int | None,
    *,
    utility_a: str | None = None,
    utility_b: str | None = None,
) -> SavingsEstimate:
    """Estimate shared mobilization/crew savings for one flagged pair.

    Formula (whole dollars, rounded to the nearest dollar):

        est_savings_usd = SHARED_MOBILIZATION_SHARE * known_cost
                          * (1 - DISTANCE_DISCOUNT_AT_RADIUS * distance_mi / OVERLAP_RADIUS_MI)
                          * 0.5 ** (time_gap_days / TIME_HALF_LIFE_DAYS)

    - SHARED_MOBILIZATION_SHARE = 0.05: an assumed 5% of the known project cost is
      mobilization/crew overhead the two jobs could share. It is an assumption, not a sourced
      figure (industry rules of thumb put mobilization at roughly 3-10%).
    - DISTANCE_DISCOUNT_AT_RADIUS = 0.9: the estimate falls linearly with distance to 10% of
      its full value at OVERLAP_RADIUS_MI (25 mi, the engine's gate), so it stays positive for
      every flagged pair.
    - TIME_HALF_LIFE_DAYS = 365: the estimate halves for every year between the in-service
      dates; it keeps falling with the gap but never reaches zero.

    known_cost: whichever of cost_a / cost_b is known. When both are known, the smaller one —
    only as much mobilization can be shared as the smaller job actually needs.

    When neither cost is known, est_savings_usd is None rather than an invented number, and
    savings_basis says why ("cost redacted in Georgia Power IRP" for a Georgia Power project).
    utility_a / utility_b are optional and only shape that wording.

    Raises ValueError for a negative cost or time gap, or a distance outside 0..radius.
    """
    _validate(overlap, cost_a, cost_b)
    reason_a = _missing_reason(cost_a, utility_a)
    reason_b = _missing_reason(cost_b, utility_b)

    if cost_a is None and cost_b is None:
        return SavingsEstimate(
            None,
            "No estimate: neither project has a known cost "
            f"({_side('A', utility_a)}: {reason_a}; {_side('B', utility_b)}: {reason_b}).",
        )

    if cost_b is None or (cost_a is not None and cost_a <= cost_b):
        known_cost, known_side, other_side, other_reason = cost_a, "A", "B", reason_b
        known_utility, other_utility = utility_a, utility_b
    else:
        known_cost, known_side, other_side, other_reason = cost_b, "B", "A", reason_a
        known_utility, other_utility = utility_b, utility_a

    d_factor = distance_factor(overlap.distance_mi)
    t_factor = time_factor(overlap.time_gap_days)
    estimate = round(SHARED_MOBILIZATION_SHARE * known_cost * d_factor * t_factor)

    if other_reason is None:
        cost_note = "Both costs are known; the smaller one bounds what can be shared."
    else:
        cost_note = f"No figure for {_side(other_side, other_utility)} ({other_reason})."
    basis = (
        f"Assumed shared mobilization of {SHARED_MOBILIZATION_SHARE:.0%} of "
        f"{_side(known_side, known_utility)}'s ${known_cost:,} cost, "
        f"x{d_factor:.2f} for {overlap.distance_mi:g} mi apart "
        f"and x{t_factor:.2f} for {overlap.time_gap_days} days between in-service dates. "
        f"{cost_note}"
    )
    return SavingsEstimate(estimate, basis)


def _validate(overlap: OverlapGeometry, cost_a: int | None, cost_b: int | None) -> None:
    for name, cost in (("cost_a", cost_a), ("cost_b", cost_b)):
        if cost is not None and cost < 0:
            raise ValueError(f"{name} must be >= 0, got {cost}")
    if not 0 <= overlap.distance_mi <= OVERLAP_RADIUS_MI:
        raise ValueError(
            f"distance_mi must be between 0 and {OVERLAP_RADIUS_MI}, got {overlap.distance_mi}"
        )
    if overlap.time_gap_days < 0:
        raise ValueError(f"time_gap_days must be >= 0, got {overlap.time_gap_days}")


def _missing_reason(cost: int | None, utility: str | None) -> str | None:
    if cost is not None:
        return None
    return REDACTED_COST_REASON if utility == REDACTED_COST_UTILITY else MISSING_COST_REASON


def _side(side: str, utility: str | None) -> str:
    return f"the {utility} project" if utility else f"project {side}"
