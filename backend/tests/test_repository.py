"""PostgresRepository: connection settings, and (with TEST_DATABASE_URL) its real SQL."""

import csv
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from test_load import TEST_DATABASE_URL, requires_postgres

from app import repository
from app.config import Settings
from app.main import create_app
from app.repository import CONNECT_TIMEOUT_S, PROJECT_COLUMNS, PostgresRepository
from app.schemas import Project, Workspace
from pipeline.load import load, read_project_csv, to_engine_project
from pipeline.overlap import (
    TIER_ORDER,
    closest_approach_miles,
    coordination_tier,
    detect_overlaps,
    footprint,
    opportunity_score,
    rank_opportunities,
)
from pipeline.overlap import Overlap as EngineOverlap
from pipeline.savings import estimate_savings

# The sponsor's six pairs tier first, then by score: OVL_1 touches at Thurmond (crossing),
# OVL_2 / OVL_3 are site_logistics, the rest crews. The starter and seed tables are the same
# ten projects, so this holds for both.
TIER_FIRST_ORDER = ["OVL_1", "OVL_2", "OVL_3", "OVL_5", "OVL_6", "OVL_4"]


def engine_closest_mi(project_a: Project, project_b: Project) -> float:
    """closest_mi straight from the engine's functions, independently of the repository."""
    shapes = [
        footprint(p.lat_a, p.lon_a, p.lat_b, p.lon_b, p.lat_center, p.lon_center)
        for p in (project_a, project_b)
    ]
    return closest_approach_miles(*shapes)


def test_connect_uses_a_timeout_so_an_unreachable_db_fails_fast(monkeypatch):
    calls = []
    monkeypatch.setattr(
        repository.psycopg, "connect", lambda *args, **kwargs: calls.append((args, kwargs))
    )

    PostgresRepository("postgresql://localhost/never-connected")._connect()

    [(args, kwargs)] = calls
    assert args == ("postgresql://localhost/never-connected",)
    assert kwargs["connect_timeout"] == CONNECT_TIMEOUT_S
    assert 0 < CONNECT_TIMEOUT_S <= 10


# --- Against a real database ----------------------------------------------------------------
# These run only with TEST_DATABASE_URL pointing at a throwaway PostGIS: they reload the
# projects tables and create/DROP a legacy submitted_projects table. See tests/test_load.py
# for the docker command.

STARTER_CSV = Path(__file__).parent / "fixtures" / "starter_projects.csv"


def reload_csv(csv_path: Path) -> None:
    """What `python -m pipeline.load` does: truncate the published tables and refill them."""
    rows = read_project_csv(csv_path)
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        load(conn, rows, detect_overlaps(to_engine_project(r) for r in rows))


def reload_starter() -> None:
    reload_csv(STARTER_CSV)


def upload_row(**overrides) -> dict:
    """An upload as the browser sends it: a new utility's project exactly on GPC_2."""
    return {
        "project_id": "b1-1",
        "utility": "Tidewater Grid Co.",
        "state": "SC",
        "project_name": "Savannah River crossing",
        "lat_center": 32.352116,
        "lon_center": -81.175112,
        "in_service_date": "2026-06-01",
        "est_cost_usd": 2_000_000,
        **overrides,
    }


def drop_submissions() -> None:
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        conn.execute("DROP TABLE IF EXISTS submitted_projects")


def create_legacy_submissions() -> None:
    """The old shared-uploads table as it still sits in the demo database, with one row.

    Exactly the columns the old code read from it; the row is a new utility's project sitting
    on GPC_2, so the old code would have served it and ranked its pair first.
    """
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        conn.execute(
            f"CREATE TABLE submitted_projects AS SELECT {PROJECT_COLUMNS} FROM projects "
            "WHERE false"
        )
        conn.execute(
            f"INSERT INTO submitted_projects ({PROJECT_COLUMNS}) "
            f"SELECT 'SUB-legacy-1', 'Tallapoosa Grid Partners', state, 'Legacy upload', "
            "name_a, lat_a, lon_a, name_b, lat_b, lon_b, lat_center, lon_center, "
            "in_service_date, est_cost_usd, 'low' FROM projects WHERE project_id = 'GPC_2'"
        )


def submissions_table_exists() -> bool:
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        return conn.execute("SELECT to_regclass('submitted_projects')").fetchone()[0] is not None


# Every table the API could conceivably write to, and how to count its rows.
COUNTED_TABLES = ("projects", "project_overlaps", "submitted_projects")


def database_snapshot() -> tuple[dict[str, int], list[str]]:
    """Row count of each counted table, and every table name in the public schema."""
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        counts = {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                  for t in COUNTED_TABLES}
        tables = [row[0] for row in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )]
    return counts, tables


@pytest.fixture
def db():
    """Starter table loaded and no submitted_projects table.

    Dropped again afterwards, so no other DB test (e.g. test_demo_data's counts) sees it.
    """
    reload_starter()
    drop_submissions()
    yield PostgresRepository(TEST_DATABASE_URL)
    drop_submissions()


@pytest.fixture
def legacy_db(db):
    """The starter table plus the old shared-uploads table holding one teammate's upload."""
    create_legacy_submissions()
    return db


@pytest.fixture
def api():
    """The real API (real PostgresRepository) over the throwaway database."""
    app = create_app(Settings(database_url=TEST_DATABASE_URL,
                              frontend_origin="http://localhost:5173"))
    with TestClient(app) as client:
        yield client


@requires_postgres
def test_reads_work_on_a_database_that_has_never_seen_a_submission(db):
    assert len(db.list_projects()) == 10
    assert [o.rank for o in db.list_overlaps()] == [1, 2, 3, 4, 5, 6]
    assert db.get_overlap("OVL_1") is not None


@requires_postgres
def test_reads_never_create_the_submissions_table(db):
    """smoke.py runs against the shared demo DB and promises to be read-only."""
    db.list_projects()
    db.list_overlaps()
    db.published_plans()
    assert not submissions_table_exists()


@requires_postgres
def test_legacy_shared_uploads_are_never_served(legacy_db, api):
    """Other people's old uploads stay in the table but no endpoint shows them any more."""
    ids = [p.project_id for p in legacy_db.list_projects()]
    assert len(ids) == 10 and "SUB-legacy-1" not in ids
    # Exactly the starter table's six pairs, in the published (tier-first) order.
    assert [o.overlap_id for o in legacy_db.list_overlaps()] == TIER_FIRST_ORDER
    assert legacy_db.get_overlap("SUB:GPC_2|SUB-legacy-1") is None
    assert "SUB-legacy-1" not in {p.project_id for p in legacy_db.published_plans().projects}

    served = api.get("/projects").json()
    assert len(served) == 10
    assert not any(p["project_id"].startswith("SUB-") for p in served)
    assert not any(o["overlap_id"].startswith("SUB:") for o in api.get("/overlaps").json())
    assert api.get("/overlaps/SUB:GPC_2|SUB-legacy-1").status_code == 404
    empty = Workspace.model_validate(api.post("/workspace", json={"projects": []}).json())
    assert "SUB-legacy-1" not in {p.project_id for p in empty.projects}
    assert "Tallapoosa Grid Partners" not in {p.utility for p in empty.projects}


@requires_postgres
def test_legacy_rows_are_left_in_place(legacy_db, api):
    """Hidden, not deleted: the API never touches the old table."""
    api.get("/projects")
    api.get("/overlaps")
    api.post("/workspace", json={"projects": [upload_row()]})
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        rows = conn.execute("SELECT project_id FROM submitted_projects").fetchall()
    assert rows == [("SUB-legacy-1",)]


@requires_postgres
def test_published_ranking_is_the_old_sql_score_order_regrouped_tier_first(db):
    """Within a tier the order is still the old SQL row_number order (score, distance, id)."""
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        sql_order = [
            row[0]
            for row in conn.execute(
                'SELECT overlap_id FROM project_overlaps ORDER BY score DESC, distance_mi, '
                'overlap_id COLLATE "C"'
            )
        ]
    served = db.list_overlaps()
    tier = {o.overlap_id: o.tier for o in served}
    # sorted() is stable: regrouping by tier keeps the SQL order inside each tier.
    assert [o.overlap_id for o in served] == sorted(
        sql_order, key=lambda i: TIER_ORDER.index(tier[i])
    )
    assert [o.overlap_id for o in served] == TIER_FIRST_ORDER
    # The regrouping really moves something: the score order alone had OVL_2 first.
    assert sql_order[0] == "OVL_2"


@requires_postgres
def test_published_plans_are_the_loaded_projects_and_their_stored_pairs(db):
    projects, overlaps = db.published_plans()
    assert sorted(projects, key=lambda p: p.project_id) == db.list_projects()
    assert sorted(o.overlap_id for o in overlaps) == [f"OVL_{n}" for n in range(1, 7)]


@requires_postgres
def test_an_empty_workspace_is_exactly_the_published_data(db, api):
    response = api.post("/workspace", json={"projects": []})

    assert response.status_code == 200
    workspace = Workspace.model_validate(response.json())
    assert workspace.projects == db.list_projects()
    assert workspace.overlaps == db.list_overlaps()


@requires_postgres
def test_a_workspace_upload_adds_its_pairs_to_the_ranking(db, api):
    response = api.post("/workspace", json={"projects": [upload_row()]})

    assert response.status_code == 200
    workspace = Workspace.model_validate(response.json())
    assert [p.project_id for p in workspace.projects][-1] == "SUB-b1-1"
    ranked = workspace.overlaps
    assert ranked[0].overlap_id == "SUB:GPC_2|SUB-b1-1"
    assert (ranked[0].distance_mi, ranked[0].time_gap_days) == (0.0, 0)
    assert ranked[0].est_savings_usd == 100_000
    # On GPC_2's center, neither with endpoints: a crossing that outscores OVL_1's.
    assert (ranked[0].closest_mi, ranked[0].tier) == (0.0, "crossing")
    assert ranked[1].overlap_id == "OVL_1"
    assert [o.rank for o in ranked] == list(range(1, len(ranked) + 1))
    assert {f"OVL_{n}" for n in range(1, 7)} <= {o.overlap_id for o in ranked}
    # Deterministic: the same uploads give the same ids and ranks next time.
    assert api.post("/workspace", json={"projects": [upload_row()]}).json() == response.json()


@requires_postgres
def test_a_workspace_request_writes_nothing_to_the_database(legacy_db, api):
    before = database_snapshot()

    ok = api.post("/workspace", json={"projects": [upload_row(), upload_row(
        project_id="b1-2", project_name="Second line")]})
    conflict = api.post("/workspace", json={"projects": [upload_row(
        utility="georgia power", project_name=legacy_db.list_projects()[5].project_name)]})

    assert (ok.status_code, conflict.status_code) == (200, 409)
    assert database_snapshot() == before
    # A fresh repository (another API instance) still serves only the published plans.
    assert len(PostgresRepository(TEST_DATABASE_URL).list_projects()) == 10


@requires_postgres
def test_a_workspace_request_never_creates_the_submissions_table(db, api):
    assert api.post("/workspace", json={"projects": [upload_row()]}).status_code == 200
    assert not submissions_table_exists()


# --- Issue #34: the sponsor seed's 6 known overlaps, round-tripped through Postgres ----------
# Expectations come from the CSVs and the pipeline's pure functions, never from the repository.

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_CSV = REPO_ROOT / "data" / "seed" / "projects_seed.csv"
EXPECTED_OVERLAPS_CSV = REPO_ROOT / "data" / "seed" / "expected_overlaps.csv"

# Floats that went into the database as Python floats come back as the same float8; this only
# absorbs a representation wobble, far below the 4 decimals opportunity_score rounds to.
FLOAT_TOLERANCE = 1e-9


def read_expected_overlaps() -> dict[str, dict]:
    with open(EXPECTED_OVERLAPS_CSV, newline="", encoding="utf-8") as f:
        return {row["overlap_id"]: row for row in csv.DictReader(f)}


EXPECTED_OVERLAPS = read_expected_overlaps()
SEED_ROWS = read_project_csv(SEED_CSV)
# Each seed row exactly as the API should serve it: every column, straight from the CSV.
SEED_PROJECTS = {r.project_id: Project.model_validate(vars(r)) for r in SEED_ROWS}
SEED_ENGINE_OVERLAPS = detect_overlaps(to_engine_project(r) for r in SEED_ROWS)


@pytest.fixture
def seed_db():
    """projects_seed.csv loaded and no legacy submitted_projects table.

    The API no longer reads that table, but it is dropped first, checked gone, and dropped
    again afterwards, so these tests start from exactly the published load.
    """
    reload_csv(SEED_CSV)
    drop_submissions()
    assert not submissions_table_exists()
    yield PostgresRepository(TEST_DATABASE_URL)
    drop_submissions()


def test_the_seed_engine_numbers_its_pairs_like_expected_overlaps_csv():
    """Offline: OVL_n from detect_overlaps is the same pair as OVL_n in the reference CSV,
    so the DB tests below may look the known overlaps up by id."""
    assert len(EXPECTED_OVERLAPS) == 6
    assert {
        o.overlap_id: (o.project_id_a, o.project_id_b) for o in SEED_ENGINE_OVERLAPS
    } == {
        oid: (row["project_id_a"], row["project_id_b"]) for oid, row in EXPECTED_OVERLAPS.items()
    }


@requires_postgres
def test_seed_db_serves_only_the_published_seed(seed_db):
    assert [p.project_id for p in seed_db.list_projects()] == sorted(SEED_PROJECTS)
    assert {o.overlap_id for o in seed_db.list_overlaps()} == set(EXPECTED_OVERLAPS)


@requires_postgres
@pytest.mark.parametrize("overlap_id", sorted(EXPECTED_OVERLAPS))
def test_a_known_overlap_is_fetched_by_id_with_both_projects_fully_populated(
    seed_db, overlap_id
):
    expected = EXPECTED_OVERLAPS[overlap_id]

    overlap = seed_db.get_overlap(overlap_id)

    assert overlap is not None
    assert overlap.overlap_id == overlap_id
    assert overlap.project_a.project_id == expected["project_id_a"]
    assert overlap.project_b.project_id == expected["project_id_b"]
    for served in (overlap.project_a, overlap.project_b):
        # Every column (names, utility, endpoints, center, date, cost, confidence) as loaded.
        assert served == SEED_PROJECTS[served.project_id]
        assert served.project_name and served.utility and served.state
        assert served.lat_center is not None and served.lon_center is not None
    assert overlap.project_a.utility != overlap.project_b.utility


@requires_postgres
def test_known_overlaps_round_trip_distance_gap_and_score(seed_db):
    served = seed_db.list_overlaps()

    assert len(served) == len(EXPECTED_OVERLAPS)
    for overlap in served:
        expected = EXPECTED_OVERLAPS[overlap.overlap_id]
        assert round(overlap.distance_mi, 2) == float(expected["distance_mi"]), overlap.overlap_id
        assert overlap.time_gap_days == int(expected["time_gap_days"]), overlap.overlap_id
        assert overlap.score == pytest.approx(
            opportunity_score(float(expected["distance_mi"]), int(expected["time_gap_days"])),
            abs=FLOAT_TOLERANCE,
        ), overlap.overlap_id


@requires_postgres
def test_every_overlap_carries_the_savings_estimate_for_its_two_projects(seed_db):
    engine = {o.overlap_id: o for o in SEED_ENGINE_OVERLAPS}

    for listed in seed_db.list_overlaps():
        fetched = seed_db.get_overlap(listed.overlap_id)
        a = SEED_PROJECTS[engine[listed.overlap_id].project_id_a]
        b = SEED_PROJECTS[engine[listed.overlap_id].project_id_b]
        expected = estimate_savings(
            engine[listed.overlap_id],
            a.est_cost_usd,
            b.est_cost_usd,
            utility_a=a.utility,
            utility_b=b.utility,
        )
        for overlap in (listed, fetched):
            assert overlap.savings_basis, overlap.overlap_id
            assert (overlap.est_savings_usd, overlap.savings_basis) == (
                expected.est_savings_usd,
                expected.savings_basis,
            ), overlap.overlap_id


@requires_postgres
def test_the_repository_rank_order_is_the_engines_tier_first_order(seed_db):
    served = seed_db.list_overlaps()

    assert [o.rank for o in served] == list(range(1, len(served) + 1))
    assert [o.overlap_id for o in served] == TIER_FIRST_ORDER
    # The engine's own tier-first ranking of the same seed projects...
    def seed_tier(o: EngineOverlap) -> str:
        a, b = SEED_PROJECTS[o.project_id_a], SEED_PROJECTS[o.project_id_b]
        return coordination_tier(engine_closest_mi(a, b))

    assert [o.overlap_id for o in served] == [
        o.overlap_id for o in rank_opportunities(SEED_ENGINE_OVERLAPS, seed_tier)
    ]
    # ...and of the values the repository itself served (the order is not just the input's).
    as_engine = [
        EngineOverlap(
            overlap_id=o.overlap_id,
            project_id_a=o.project_a.project_id,
            project_id_b=o.project_b.project_id,
            distance_mi=o.distance_mi,
            time_gap_days=o.time_gap_days,
            score=o.score,
        )
        for o in reversed(served)
    ]
    served_tier = {o.overlap_id: o.tier for o in served}
    assert [o.overlap_id for o in served] == [
        o.overlap_id for o in rank_opportunities(as_engine, lambda o: served_tier[o.overlap_id])
    ]
    # get_overlap reports the same rank as the list.
    assert [seed_db.get_overlap(o.overlap_id).rank for o in served] == [o.rank for o in served]


@requires_postgres
def test_every_served_pair_carries_closest_mi_and_tier_from_its_two_projects(seed_db):
    for listed in seed_db.list_overlaps():
        fetched = seed_db.get_overlap(listed.overlap_id)
        a = SEED_PROJECTS[listed.project_a.project_id]
        b = SEED_PROJECTS[listed.project_b.project_id]
        expected_closest = engine_closest_mi(a, b)
        for overlap in (listed, fetched):
            assert overlap.closest_mi == expected_closest, overlap.overlap_id
            assert overlap.tier == coordination_tier(expected_closest), overlap.overlap_id
    top = seed_db.get_overlap("OVL_1")
    assert (top.rank, top.tier, top.closest_mi) == (1, "crossing", 0.0)


@requires_postgres
def test_the_real_api_serves_closest_mi_and_tier_everywhere(db, api):
    listed = api.get("/overlaps").json()
    fetched = api.get("/overlaps/OVL_1").json()
    workspace = api.post("/workspace", json={"projects": [upload_row()]}).json()["overlaps"]

    assert listed[0]["overlap_id"] == "OVL_1"
    for body in [*listed, fetched, *workspace]:
        assert isinstance(body["closest_mi"], float), body["overlap_id"]
        assert body["tier"] in TIER_ORDER, body["overlap_id"]
    assert (fetched["rank"], fetched["tier"], fetched["closest_mi"]) == (1, "crossing", 0.0)
    assert any(o["overlap_id"].startswith("SUB:") for o in workspace)
