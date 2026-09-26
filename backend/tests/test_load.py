"""Tests for the seed loader and the SQL schema.

Tiger Data is not provisioned yet (issue #7), so these cover row validation, the values
bound to each insert, and the order of statements the loader issues — against a recording
stub rather than a live connection. The one real-database test runs only when DATABASE_URL
is set, which is what will exercise it once the instance exists.
"""

import csv
import math
import os
import re
from datetime import date
from pathlib import Path

import pytest

from pipeline.load import (
    INSERT_OVERLAP,
    INSERT_PROJECT,
    SCHEMA_PATH,
    LoadError,
    load,
    parse_project_row,
    project_params,
    read_project_csv,
    to_engine_project,
)
from pipeline.overlap import Project, detect_overlaps

# Spec numbers as literals, so these tests do not derive expectations from the code
# they are checking. From docs/prompt.md.
SPEC_EARTH_RADIUS_MI = 3958.8
MILES_PER_DEGREE = SPEC_EARTH_RADIUS_MI * math.pi / 180

STARTER_CSV = Path(__file__).parent / "fixtures" / "starter_projects.csv"
DATABASE_URL = os.environ.get("DATABASE_URL")


def raw_row(**overrides) -> dict:
    """A well-formed seed row; override one field to test that field."""
    return {
        "project_id": "DESC_1",
        "utility": "Dominion Energy South Carolina",
        "state": "SC",
        "project_name": "Stevens Creek - Hooks 115 kV",
        "name_a": "Stevens Creek Sub",
        "lat_a": "33.562599",
        "lon_a": "-82.051362",
        "name_b": "Hooks Sub",
        "lat_b": "",
        "lon_b": "",
        "lat_center": "33.562599",
        "lon_center": "-82.051362",
        "in_service_date": "2024-12-31",
        **overrides,
    }


class RecordingConnection:
    """Stands in for a psycopg connection and remembers what it was asked to run."""

    def __init__(self):
        self.calls: list[tuple[str, dict | None]] = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    @property
    def statements(self) -> list[str]:
        return [sql for sql, _ in self.calls]

    def params_for(self, table: str) -> list[dict]:
        return [params for sql, params in self.calls if f"INSERT INTO {table}" in sql]


def loaded_starter() -> RecordingConnection:
    rows = read_project_csv(STARTER_CSV)
    overlaps = detect_overlaps(to_engine_project(r) for r in rows)
    connection = RecordingConnection()
    load(connection, rows, overlaps)
    return connection


# --- row validation -----------------------------------------------------------------


def test_a_well_formed_row_parses():
    row = parse_project_row(raw_row())

    assert row.project_id == "DESC_1"
    assert row.lat_center == 33.562599
    assert row.in_service_date == date(2024, 12, 31)


def test_a_missing_endpoint_coordinate_is_none_not_zero():
    """0.0 is a real place off the coast of Africa; blank must not become it."""
    row = parse_project_row(raw_row())

    assert row.lat_b is None
    assert row.lon_b is None
    assert row.name_b == "Hooks Sub"


@pytest.mark.parametrize(
    "column", ["project_id", "utility", "state", "project_name", "lat_center", "lon_center"]
)
def test_a_row_missing_a_required_column_is_rejected(column):
    with pytest.raises(LoadError):
        parse_project_row(raw_row(**{column: ""}))


def test_a_row_with_no_in_service_date_is_rejected():
    with pytest.raises(LoadError, match="in_service_date"):
        parse_project_row(raw_row(in_service_date=""))


def test_a_non_iso_date_is_rejected_rather_than_guessed():
    with pytest.raises(LoadError, match="ISO"):
        parse_project_row(raw_row(in_service_date="12/31/2024"))


def test_an_unparseable_coordinate_is_rejected():
    with pytest.raises(LoadError, match="lat_a"):
        parse_project_row(raw_row(lat_a="about 33"))


def test_confidence_defaults_to_confirmed_when_the_column_is_absent():
    assert parse_project_row(raw_row()).location_confidence == "confirmed"


def test_confidence_can_be_marked_low():
    assert parse_project_row(raw_row(location_confidence="low")).location_confidence == "low"


def test_an_unknown_confidence_value_is_rejected():
    with pytest.raises(LoadError, match="location_confidence"):
        parse_project_row(raw_row(location_confidence="probably"))


def test_cost_is_absent_when_the_utility_redacts_it():
    """Georgia Power redacts every cost, so NULL has to be a first-class value."""
    assert parse_project_row(raw_row()).est_cost_usd is None


def test_cost_parses_with_currency_formatting():
    assert parse_project_row(raw_row(est_cost_usd="$11,745,543")).est_cost_usd == 11_745_543


def test_an_explicitly_redacted_cost_loads_as_unknown():
    """Georgia Power prints REDACTED; that must mean NULL, not abort the load."""
    assert parse_project_row(raw_row(est_cost_usd="REDACTED")).est_cost_usd is None


@pytest.mark.parametrize("value", ["a few million", "nan", "inf"])
def test_a_nonsense_cost_is_rejected_rather_than_zeroed(value):
    with pytest.raises(LoadError, match="est_cost_usd"):
        parse_project_row(raw_row(est_cost_usd=value))


def test_a_bad_center_coordinate_names_the_project_it_came_from():
    with pytest.raises(LoadError, match="DESC_1"):
        parse_project_row(raw_row(lat_center="about 33"))


# --- reading the seed file ----------------------------------------------------------


def test_the_starter_seed_reads_cleanly():
    rows = read_project_csv(STARTER_CSV)

    assert len(rows) == 10
    assert {r.utility for r in rows} == {"Dominion Energy South Carolina", "Georgia Power"}


def test_a_duplicate_project_id_is_rejected(tmp_path):
    with open(STARTER_CSV, newline="") as f:
        original = list(csv.DictReader(f))
    doubled = tmp_path / "doubled.csv"
    with open(doubled, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=original[0].keys())
        writer.writeheader()
        writer.writerows(original + original[:1])

    with pytest.raises(LoadError, match="duplicate"):
        read_project_csv(doubled)


def test_seed_rows_narrow_cleanly_to_engine_projects():
    rows = read_project_csv(STARTER_CSV)

    projects = [to_engine_project(r) for r in rows]

    assert len(detect_overlaps(projects)) == 6


# --- insert parameters --------------------------------------------------------------


def test_a_project_with_both_endpoints_draws_a_line():
    row = parse_project_row(raw_row(lat_b="33.660127", lon_b="-82.195931"))

    assert row.has_both_endpoints
    assert project_params(row)["draw_line"] is True


def test_a_project_with_one_endpoint_draws_no_line():
    assert project_params(parse_project_row(raw_row()))["draw_line"] is False


def test_the_one_known_endpoint_is_still_stored_when_there_is_no_line():
    """No line to draw is not a reason to throw away the substation we did locate."""
    params = project_params(parse_project_row(raw_row()))

    assert params["draw_line"] is False
    assert params["lat_a"] == 33.562599
    assert params["lon_a"] == -82.051362


def test_every_placeholder_in_the_insert_gets_a_value():
    """A renamed column would otherwise only surface as a psycopg error at load time."""
    placeholders = set(re.findall(r"%\((\w+)\)s", INSERT_PROJECT))

    assert placeholders == set(project_params(parse_project_row(raw_row())))


def test_every_placeholder_in_the_overlap_insert_gets_a_value():
    rows = read_project_csv(STARTER_CSV)
    overlaps = detect_overlaps(to_engine_project(r) for r in rows)
    placeholders = set(re.findall(r"%\((\w+)\)s", INSERT_OVERLAP))

    assert placeholders == set(loaded_starter().params_for("overlaps")[0])
    assert placeholders == {
        "overlap_id",
        "project_id_a",
        "project_id_b",
        "distance_mi",
        "time_gap_days",
        "score",
    }
    assert len(overlaps) == 6


def test_every_point_is_built_longitude_first():
    """ST_MakePoint takes (x, y) = (lon, lat). Swapping them silently moves SC to Asia."""
    point_args = re.findall(r"ST_MakePoint\(%\((\w+)\)s,\s*%\((\w+)\)s\)", INSERT_PROJECT)

    assert point_args == [
        ("lon_center", "lat_center"),
        ("lon_a", "lat_a"),
        ("lon_b", "lat_b"),
    ]


def test_stored_coordinates_match_the_seed_file():
    stored = {p["project_id"]: p for p in loaded_starter().params_for("projects")}

    assert stored["DESC_2"]["lat_center"] == 33.660127
    assert stored["DESC_2"]["lon_center"] == -82.195931
    assert stored["DESC_2"]["draw_line"] is False
    assert stored["GPC_1"]["draw_line"] is True


# --- the load sequence --------------------------------------------------------------


def test_load_applies_the_schema_then_clears_before_inserting():
    rows = read_project_csv(STARTER_CSV)
    overlaps = detect_overlaps(to_engine_project(r) for r in rows)
    connection = RecordingConnection()

    load(connection, rows, overlaps)

    statements = connection.statements
    assert "CREATE TABLE IF NOT EXISTS projects" in statements[0]
    assert statements[1].startswith("TRUNCATE projects")
    assert all("INSERT INTO projects" in s for s in statements[2:12])


def test_load_writes_every_project_and_every_overlap():
    rows = read_project_csv(STARTER_CSV)
    overlaps = detect_overlaps(to_engine_project(r) for r in rows)
    connection = RecordingConnection()

    loaded, flagged = load(connection, rows, overlaps)

    assert (loaded, flagged) == (10, 6)
    assert sum("INSERT INTO projects" in s for s in connection.statements) == 10
    assert sum("INSERT INTO overlaps" in s for s in connection.statements) == 6


def test_overlaps_are_inserted_after_the_projects_they_reference():
    """The foreign key means the order is not cosmetic."""
    rows = read_project_csv(STARTER_CSV)
    overlaps = detect_overlaps(to_engine_project(r) for r in rows)
    connection = RecordingConnection()

    load(connection, rows, overlaps)

    last_project = max(i for i, s in enumerate(connection.statements) if "INTO projects" in s)
    first_overlap = min(i for i, s in enumerate(connection.statements) if "INTO overlaps" in s)
    assert last_project < first_overlap


def test_reloading_truncates_rather_than_accumulating():
    rows = read_project_csv(STARTER_CSV)
    connection = RecordingConnection()

    load(connection, rows, [])
    load(connection, rows, [])

    assert sum(s.startswith("TRUNCATE projects") for s in connection.statements) == 2


# --- the schema ---------------------------------------------------------------------


def test_schema_creates_both_tables_and_postgis():
    sql = SCHEMA_PATH.read_text()

    assert "CREATE EXTENSION IF NOT EXISTS postgis" in sql
    assert "CREATE TABLE IF NOT EXISTS projects" in sql
    assert "CREATE TABLE IF NOT EXISTS overlaps" in sql


def schema_distance_bound() -> tuple[str, float]:
    """The upper bound the `overlaps` CHECK constraint puts on distance_mi."""
    match = re.search(r"distance_mi\s*(<=?)\s*([\d.]+)", SCHEMA_PATH.read_text())
    return match.group(1), float(match.group(2))


def test_the_schema_bounds_distance_at_the_spec_distance():
    _, bound = schema_distance_bound()

    assert bound == 25.0


def test_the_schema_accepts_every_distance_the_engine_can_produce():
    """A pair just inside the gate stores as exactly 25.0 once rounded to 2 dp.

    The gate is on the full-precision distance, the column holds the rounded one, so an
    exclusive CHECK would reject a legitimately flagged pair and abort the whole load.
    """
    offset = (25.0 - 0.001) / MILES_PER_DEGREE
    worst_case = [
        Project("DESC_X", "DESC", 33.0, -82.0, date(2025, 1, 1)),
        Project("GPC_X", "GPC", 33.0 + offset, -82.0, date(2025, 1, 1)),
    ]

    flagged = detect_overlaps(worst_case)
    assert len(flagged) == 1
    assert flagged[0].distance_mi == 25.0

    operator, bound = schema_distance_bound()
    stored = flagged[0].distance_mi
    satisfied = stored < bound if operator == "<" else stored <= bound
    assert satisfied, f"engine emitted {stored} but the CHECK is {operator} {bound}"


def test_schema_allows_redacted_costs_but_not_missing_centers():
    sql = SCHEMA_PATH.read_text()

    assert "est_cost_usd        BIGINT," in sql
    assert "lat_center          DOUBLE PRECISION NOT NULL" in sql


# --- against a real database, once there is one -------------------------------------


@pytest.mark.skipif(not DATABASE_URL, reason="no DATABASE_URL; Tiger Data not provisioned yet")
def test_loading_into_a_real_database_produces_the_golden_six():
    import psycopg

    rows = read_project_csv(STARTER_CSV)
    overlaps = detect_overlaps(to_engine_project(r) for r in rows)

    with psycopg.connect(DATABASE_URL) as connection:
        load(connection, rows, overlaps)
        stored_projects = connection.execute("SELECT count(*) FROM projects").fetchone()[0]
        stored_overlaps = connection.execute(
            "SELECT count(*) FROM overlaps"
        ).fetchone()[0]
        lines = connection.execute(
            "SELECT count(*) FROM projects WHERE geom_line IS NOT NULL"
        ).fetchone()[0]
        connection.rollback()

    assert stored_projects == 10
    assert stored_overlaps == 6
    # Six of the ten starter projects have both substations located.
    assert lines == 6
