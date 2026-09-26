"""Tests for the seed loader and the SQL schema.

Most of these cover row validation, the values bound to each insert, and the order of
statements the loader issues — against a recording stub rather than a live connection. The
tests at the bottom execute the real SQL against Postgres+PostGIS and run only when
TEST_DATABASE_URL points at a throwaway database; see the comment on that constant.
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
    apply_schema,
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
STARTER_OVERLAPS_CSV = Path(__file__).parent / "fixtures" / "starter_overlaps.csv"


def expected_overlap_rows() -> list[dict]:
    """The sponsor's six reference pairs (docs/prompt.md), shared with test_overlap.py."""
    with open(STARTER_OVERLAPS_CSV, newline="") as f:
        return list(csv.DictReader(f))


# These tests TRUNCATE, so they deliberately do NOT read $DATABASE_URL - once #7 provisions
# the shared instance, everyone will have that set and a stray pytest run must not empty the
# demo database. Point TEST_DATABASE_URL at a throwaway instead:
#
#   docker run -d --name gridwatch-pg -e POSTGRES_HOST_AUTH_METHOD=trust \
#       -e POSTGRES_DB=gridwatch_test -p 55432:5432 postgis/postgis:16-3.4
#   TEST_DATABASE_URL=postgresql://postgres@localhost:55432/gridwatch_test \
#       .venv/bin/python -m pytest tests/test_load.py
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
requires_postgres = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="no TEST_DATABASE_URL; see the comment above for a throwaway"
)


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


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("lat_center", "91.5"),
        ("lat_center", "-91"),
        ("lon_center", "-200"),
        ("lon_center", "180.5"),
        ("lat_a", "999"),
        ("lon_b", "1e9"),
    ],
)
def test_a_coordinate_outside_its_real_world_bound_is_rejected(column, value):
    """A swapped lat/lon or a bad substation match is finite, so it loads silently and
    quietly changes which pairs get flagged. The sponsor guide calls mis-located
    substations the top data risk, and this is where they enter."""
    with pytest.raises(LoadError, match=column):
        parse_project_row(raw_row(**{column: value}))


@pytest.mark.parametrize("value", ["nan", "-nan", "inf", "-inf", "1e400"])
def test_a_non_finite_coordinate_is_rejected(value):
    """float() accepts all of these. nan is the dangerous one: the engine's gate
    (distance >= 25) is False for nan, so the pair is flagged carrying a nan distance,
    which then trips the schema CHECK and aborts the entire single-transaction load with
    an error naming no project. parse_cost already rejects nan; coordinates now match."""
    with pytest.raises(LoadError, match="lat_center"):
        parse_project_row(raw_row(lat_center=value))


def test_a_nan_center_never_reaches_the_overlap_engine():
    """The failure this closes, stated as behavior: a nan center used to produce an
    overlap with distance_mi=nan and score=nan."""
    rows = read_project_csv(STARTER_CSV)
    poisoned = [raw_row(project_id=r.project_id) for r in rows[:1]]
    poisoned[0]["lat_center"] = "nan"

    with pytest.raises(LoadError):
        parse_project_row(poisoned[0])

    # Sanity check that clean seed data still produces clean distances.
    clean = [to_engine_project(r) for r in rows]
    assert all(not math.isnan(o.distance_mi) for o in detect_overlaps(clean))


def test_longitude_is_bounded_at_180_not_90():
    """Using 90 for both would reject legitimate western longitudes."""
    row = parse_project_row(raw_row(lon_center="-100.5", lon_a="-179.9"))

    assert row.lon_center == -100.5
    assert row.lon_a == -179.9


def test_the_exact_coordinate_limits_are_still_valid_places():
    row = parse_project_row(raw_row(lat_center="90", lon_center="-180"))

    assert (row.lat_center, row.lon_center) == (90.0, -180.0)


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


@pytest.mark.parametrize("write_header", [True, False])
def test_a_seed_with_no_rows_is_refused_rather_than_wiping_the_tables(tmp_path, write_header):
    """This used to TRUNCATE both tables, insert nothing, and print "loaded 0 projects and
    0 overlaps" with exit 0 - so pointing the loader at a truncated or wrong file emptied
    the demo database and reported success."""
    with open(STARTER_CSV, newline="") as f:
        fieldnames = csv.DictReader(f).fieldnames
    empty = tmp_path / "empty.csv"
    with open(empty, "w", newline="") as f:
        if write_header:
            csv.DictWriter(f, fieldnames=fieldnames).writeheader()

    with pytest.raises(LoadError, match="no project rows"):
        read_project_csv(empty)


def test_a_csv_exported_from_excel_with_a_bom_still_reads(tmp_path):
    """Saving the sponsor's xlsx as CSV in Excel prepends a UTF-8 BOM. Without utf-8-sig it
    lands in the first header name, so every row looks like it has no project_id - a loud
    failure, but one that names the wrong problem. #2 will produce the seed exactly this way."""
    with_bom = tmp_path / "bom.csv"
    with_bom.write_bytes(b"\xef\xbb\xbf" + STARTER_CSV.read_bytes())

    rows = read_project_csv(with_bom)

    assert len(rows) == 10
    assert rows[0].project_id == read_project_csv(STARTER_CSV)[0].project_id


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

    assert placeholders == set(loaded_starter().params_for("project_overlaps")[0])
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
    assert sum("INSERT INTO project_overlaps" in s for s in connection.statements) == 6


def test_overlaps_are_inserted_after_the_projects_they_reference():
    """The foreign key means the order is not cosmetic."""
    rows = read_project_csv(STARTER_CSV)
    overlaps = detect_overlaps(to_engine_project(r) for r in rows)
    connection = RecordingConnection()

    load(connection, rows, overlaps)

    last_project = max(i for i, s in enumerate(connection.statements) if "INTO projects" in s)
    first_overlap = min(
        i for i, s in enumerate(connection.statements) if "INTO project_overlaps" in s
    )
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
    assert "CREATE TABLE IF NOT EXISTS project_overlaps" in sql


def schema_distance_bound() -> tuple[str, float]:
    """The upper bound the `project_overlaps` CHECK constraint puts on distance_mi."""
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


# --- against a real database ---------------------------------------------------------
#
# Everything above this line runs against a recording stub, which cannot tell valid SQL from
# invalid: the schema greps passed for days while `CREATE TABLE overlaps` was a syntax error
# (OVERLAPS is a reserved word in Postgres). These are the tests that actually execute it.


@requires_postgres
def test_the_schema_applies_to_a_real_postgis_database():
    """The DDL parses and runs. No string grep can tell you this."""
    import psycopg

    with psycopg.connect(TEST_DATABASE_URL) as connection:
        apply_schema(connection)
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            ).fetchall()
        }
        connection.rollback()

    assert {"projects", "project_overlaps"} <= tables


@requires_postgres
def test_loading_into_a_real_database_produces_the_golden_six():
    import psycopg

    rows = read_project_csv(STARTER_CSV)
    overlaps = detect_overlaps(to_engine_project(r) for r in rows)

    with psycopg.connect(TEST_DATABASE_URL) as connection:
        load(connection, rows, overlaps)
        stored_projects = connection.execute("SELECT count(*) FROM projects").fetchone()[0]
        stored_overlaps = connection.execute(
            "SELECT count(*) FROM project_overlaps"
        ).fetchone()[0]
        lines = connection.execute(
            "SELECT count(*) FROM projects WHERE geom_line IS NOT NULL"
        ).fetchone()[0]
        connection.rollback()

    assert stored_projects == 10
    assert stored_overlaps == 6
    # Six of the ten starter projects have both substations located.
    assert lines == 6


@requires_postgres
def test_the_stored_pairs_are_the_sponsors_six_not_just_six_rows():
    """Counts alone would pass on six wrong pairs. Read them back out of SQL."""
    import psycopg

    rows = read_project_csv(STARTER_CSV)
    overlaps = detect_overlaps(to_engine_project(r) for r in rows)

    with psycopg.connect(TEST_DATABASE_URL) as connection:
        load(connection, rows, overlaps)
        stored = connection.execute(
            "SELECT project_id_a, project_id_b, distance_mi, time_gap_days "
            "FROM project_overlaps ORDER BY distance_mi"
        ).fetchall()
        connection.rollback()

    assert stored == [
        (
            row["project_id_a"],
            row["project_id_b"],
            float(row["distance_mi"]),
            int(row["time_gap_days"]),
        )
        for row in expected_overlap_rows()
    ]


@requires_postgres
def test_every_center_lands_where_the_seed_put_it():
    """Proves ST_MakePoint got (lon, lat) in that order - swapped, these land in Asia."""
    import psycopg

    rows = read_project_csv(STARTER_CSV)
    overlaps = detect_overlaps(to_engine_project(r) for r in rows)

    with psycopg.connect(TEST_DATABASE_URL) as connection:
        load(connection, rows, overlaps)
        stored = dict(
            (pid, (round(y, 6), round(x, 6)))
            for pid, x, y in connection.execute(
                "SELECT project_id, ST_X(geom_center), ST_Y(geom_center) FROM projects"
            ).fetchall()
        )
        srid = connection.execute(
            "SELECT DISTINCT ST_SRID(geom_center) FROM projects"
        ).fetchone()[0]
        connection.rollback()

    assert srid == 4326
    assert stored == {r.project_id: (round(r.lat_center, 6), round(r.lon_center, 6)) for r in rows}


@requires_postgres
def test_loading_twice_replaces_rather_than_accumulates():
    """The batch job's whole contract: re-running it is safe."""
    import psycopg

    rows = read_project_csv(STARTER_CSV)
    overlaps = detect_overlaps(to_engine_project(r) for r in rows)

    with psycopg.connect(TEST_DATABASE_URL) as connection:
        load(connection, rows, overlaps)
        first = connection.execute("SELECT count(*) FROM project_overlaps").fetchone()[0]
        load(connection, rows, overlaps)
        second = connection.execute("SELECT count(*) FROM project_overlaps").fetchone()[0]
        projects = connection.execute("SELECT count(*) FROM projects").fetchone()[0]
        connection.rollback()

    assert (first, second, projects) == (6, 6, 10)


@requires_postgres
def test_the_database_rejects_a_pair_beyond_the_twenty_five_mile_bound():
    """The CHECK is real, not just text in schema.sql."""
    import psycopg

    rows = read_project_csv(STARTER_CSV)
    overlaps = detect_overlaps(to_engine_project(r) for r in rows)

    with psycopg.connect(TEST_DATABASE_URL) as connection:
        load(connection, rows, overlaps)
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                "INSERT INTO project_overlaps (overlap_id, project_id_a, project_id_b, "
                "distance_mi, time_gap_days, score) "
                "VALUES ('BAD', %s, %s, 25.01, 10, 0.5)",
                (rows[0].project_id, rows[-1].project_id),
            )
        connection.rollback()


@requires_postgres
def test_the_database_rejects_an_overlap_for_a_project_that_was_never_loaded():
    """The foreign keys are real, so the map can trust every pair resolves."""
    import psycopg

    rows = read_project_csv(STARTER_CSV)
    overlaps = detect_overlaps(to_engine_project(r) for r in rows)

    with psycopg.connect(TEST_DATABASE_URL) as connection:
        load(connection, rows, overlaps)
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            connection.execute(
                "INSERT INTO project_overlaps (overlap_id, project_id_a, project_id_b, "
                "distance_mi, time_gap_days, score) "
                "VALUES ('BAD', %s, 'NOT_A_PROJECT', 5.0, 10, 0.5)",
                (rows[0].project_id,),
            )
        connection.rollback()
