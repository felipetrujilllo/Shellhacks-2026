"""PostgresRepository: connection settings, and (with TEST_DATABASE_URL) its real SQL."""

import csv
from pathlib import Path

import psycopg
import pytest
from test_load import TEST_DATABASE_URL, requires_postgres

from app import repository
from app.repository import CONNECT_TIMEOUT_S, PostgresRepository
from app.schemas import Project
from app.submissions import SubmissionConflict, prepare_submission
from pipeline.load import load, read_project_csv, to_engine_project
from pipeline.overlap import Overlap as EngineOverlap
from pipeline.overlap import detect_overlaps, opportunity_score, rank_by_score
from pipeline.savings import estimate_savings


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
# projects tables and DROP submitted_projects. See tests/test_load.py for the docker command.

STARTER_CSV = Path(__file__).parent / "fixtures" / "starter_projects.csv"


def reload_csv(csv_path: Path) -> None:
    """What `python -m pipeline.load` does: truncate the published tables and refill them."""
    rows = read_project_csv(csv_path)
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        load(conn, rows, detect_overlaps(to_engine_project(r) for r in rows))


def reload_starter() -> None:
    reload_csv(STARTER_CSV)


def upload(**overrides) -> Project:
    """A new utility's project sitting exactly on GPC_2's center and in-service date."""
    return Project.model_validate(
        {
            "project_id": "client-ref",
            "utility": "Tidewater Grid Co.",
            "state": "SC",
            "project_name": "Savannah River crossing",
            "lat_center": 32.352116,
            "lon_center": -81.175112,
            "in_service_date": "2026-06-01",
            "est_cost_usd": 2_000_000,
            **overrides,
        }
    )


def drop_submissions() -> None:
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        conn.execute("DROP TABLE IF EXISTS submitted_projects")


@pytest.fixture
def db():
    """Starter table loaded, no submissions table yet: exactly the live DB before this change.

    Dropped again afterwards, so no other DB test (e.g. test_demo_data's counts) sees them.
    """
    reload_starter()
    drop_submissions()
    yield PostgresRepository(TEST_DATABASE_URL)
    drop_submissions()


def submit(repository: PostgresRepository, *projects: Project) -> list[Project]:
    prepared = prepare_submission(projects, repository.list_projects())
    repository.add_submission(prepared)
    return prepared


def submissions_table_exists() -> bool:
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        return conn.execute("SELECT to_regclass('submitted_projects')").fetchone()[0] is not None


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
    assert not submissions_table_exists()


@requires_postgres
def test_the_first_upload_creates_the_submissions_table(db):
    submit(db, upload())
    assert submissions_table_exists()


@requires_postgres
def test_published_ranking_matches_the_old_sql_row_number_order(db):
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        sql_order = [
            row[0]
            for row in conn.execute(
                'SELECT overlap_id FROM project_overlaps ORDER BY score DESC, distance_mi, '
                'overlap_id COLLATE "C"'
            )
        ]
    assert [o.overlap_id for o in db.list_overlaps()] == sql_order


@requires_postgres
def test_a_submission_is_stored_and_served_by_a_fresh_repository(db):
    [stored] = submit(db, upload())

    # A new repository = another API instance, or the same one after a restart.
    other = PostgresRepository(TEST_DATABASE_URL)
    by_id = {p.project_id: p for p in other.list_projects()}
    assert len(by_id) == 11
    assert by_id[stored.project_id] == stored


@requires_postgres
def test_a_submission_adds_its_pairs_to_the_ranked_overlaps(db):
    [stored] = submit(db, upload())

    ranked = PostgresRepository(TEST_DATABASE_URL).list_overlaps()
    assert ranked[0].overlap_id == f"SUB:GPC_2|{stored.project_id}"
    assert (ranked[0].distance_mi, ranked[0].time_gap_days) == (0.0, 0)
    assert ranked[0].est_savings_usd == 100_000
    assert [o.rank for o in ranked] == list(range(1, len(ranked) + 1))
    assert {f"OVL_{n}" for n in range(1, 7)} <= {o.overlap_id for o in ranked}


@requires_postgres
def test_a_submitted_pair_can_be_fetched_by_id(db):
    [stored] = submit(db, upload())
    overlap = db.get_overlap(f"SUB:GPC_2|{stored.project_id}")
    assert overlap is not None and overlap.rank == 1
    assert db.get_overlap("SUB:nope") is None


@requires_postgres
def test_reloading_the_published_plans_keeps_every_submission(db):
    [stored] = submit(db, upload())
    reload_starter()
    assert stored.project_id in {p.project_id for p in db.list_projects()}
    assert db.list_overlaps()[0].overlap_id == f"SUB:GPC_2|{stored.project_id}"


@requires_postgres
def test_the_database_refuses_a_duplicate_that_slipped_past_the_api_check(db):
    submit(db, upload())
    # Prepared against a stale view (as if two uploads raced), so only the index can stop it.
    [racer] = prepare_submission([upload(utility="TIDEWATER GRID CO.")], [])
    with pytest.raises(SubmissionConflict):
        db.add_submission([racer])
    assert len(db.list_projects()) == 11


@requires_postgres
def test_a_refused_row_rolls_back_the_whole_upload(db):
    submit(db, upload())
    batch = prepare_submission(
        [upload(project_name="New line"), upload(project_name="savannah river crossing")], []
    )
    with pytest.raises(SubmissionConflict):
        db.add_submission(batch)
    assert "New line" not in {p.project_name for p in db.list_projects()}


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
    """projects_seed.csv loaded and no submitted projects, so the published pairs are all.

    A submission left by another test would add pairs and shift every rank, so the table is
    dropped first, checked gone, and dropped again afterwards.
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
def test_the_repository_rank_order_equals_rank_by_score(seed_db):
    served = seed_db.list_overlaps()

    assert [o.rank for o in served] == list(range(1, len(served) + 1))
    # The engine's own ranking of the same seed projects...
    assert [o.overlap_id for o in served] == [
        o.overlap_id for o in rank_by_score(SEED_ENGINE_OVERLAPS)
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
    assert [o.overlap_id for o in served] == [o.overlap_id for o in rank_by_score(as_engine)]
    # get_overlap reports the same rank as the list.
    assert [seed_db.get_overlap(o.overlap_id).rank for o in served] == [o.rank for o in served]
