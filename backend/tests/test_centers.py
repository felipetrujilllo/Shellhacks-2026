"""Tests for pipeline/centers.py: a project's center from its endpoints (docs/prompt.md step 3)."""

import csv
from pathlib import Path

import pytest

from pipeline.centers import HalfLocatedEndpointError, project_center

STARTER_CSV = Path(__file__).parent / "fixtures" / "starter_projects.csv"
SEED_CSV = Path(__file__).resolve().parents[2] / "data" / "seed" / "projects_seed.csv"


def coordinate(value: str) -> float | None:
    return float(value) if value.strip() else None


def seed_rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_both_endpoints_give_the_arithmetic_midpoint():
    assert project_center(32.0, -81.0, 33.0, -82.0) == (32.5, -81.5)


def test_only_endpoint_a_gives_that_point():
    assert project_center(33.562599, -82.051362, None, None) == (33.562599, -82.051362)


def test_only_endpoint_b_gives_that_point():
    assert project_center(None, None, 33.660127, -82.195931) == (33.660127, -82.195931)


def test_no_located_endpoint_gives_none():
    assert project_center(None, None, None, None) is None


@pytest.mark.parametrize(
    "endpoints",
    [
        (33.0, None, 32.0, -81.0),
        (None, -82.0, 32.0, -81.0),
        (33.0, -82.0, 32.0, None),
        (33.0, -82.0, None, -81.0),
        (33.0, None, None, None),
    ],
)
def test_a_half_located_endpoint_fails_loud_rather_than_being_dropped(endpoints):
    """Half a coordinate pair is bad data, not an unlocated substation."""
    with pytest.raises(HalfLocatedEndpointError):
        project_center(*endpoints)


def test_zero_is_a_located_coordinate_not_a_blank():
    assert project_center(0.0, 0.0, 2.0, 2.0) == (1.0, 1.0)


@pytest.mark.parametrize("path", [STARTER_CSV, SEED_CSV], ids=["fixture", "seed"])
def test_recomputing_every_seed_center_reproduces_the_sponsors_to_six_decimals(path):
    rows = seed_rows(path)
    assert len(rows) == 10

    for row in rows:
        center = project_center(
            *(coordinate(row[c]) for c in ("lat_a", "lon_a", "lat_b", "lon_b"))
        )
        assert center is not None, row["project_id"]
        assert round(center[0], 6) == round(float(row["lat_center"]), 6), row["project_id"]
        assert round(center[1], 6) == round(float(row["lon_center"]), 6), row["project_id"]
