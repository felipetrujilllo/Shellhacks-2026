"""PostgresRepository: connection settings, and (with TEST_DATABASE_URL) its real SQL."""

from pathlib import Path

import psycopg
import pytest
from test_load import TEST_DATABASE_URL, requires_postgres

from app import repository
from app.repository import CONNECT_TIMEOUT_S, PostgresRepository
from app.schemas import Project
from app.submissions import SubmissionConflict, prepare_submission
from pipeline.load import load, read_project_csv, to_engine_project
from pipeline.overlap import detect_overlaps


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


def reload_starter() -> None:
    """What `python -m pipeline.load` does: truncate the published tables and refill them."""
    rows = read_project_csv(STARTER_CSV)
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        load(conn, rows, detect_overlaps(to_engine_project(r) for r in rows))


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
