"""Issue #24: the demo database serves data/seed/projects.csv.

Three layers, so the shared demo DB is only loaded once everything else already agrees:

- Offline (always runs): the engine, run on projects.csv exactly as pipeline.load runs it and
  shaped the way the API serves overlaps, already contains the sponsor's 6 reference pairs by
  smoke.py's own matching. So smoke.py will pass after the load.
- scripts/check_demo_data.py's comparison logic, against a faked API (no network, no DB).
- A rehearsal on the throwaway PostGIS (opt-in, TEST_DATABASE_URL like test_load.py): run the
  real `python -m pipeline.load` on projects.csv, then query the real API over it.
"""

import csv
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from test_load import TEST_DATABASE_URL, requires_postgres

from app.config import Settings
from app.main import create_app
from app.repository import build_overlap
from app.schemas import Project
from pipeline.load import ENV_PATH, read_project_csv, to_engine_project
from pipeline.overlap import detect_overlaps, rank_by_score

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
PROJECTS_CSV = REPO_ROOT / "data" / "seed" / "projects.csv"
SPONSOR_SAMPLE_CSV = REPO_ROOT / "data" / "seed" / "projects_seed.csv"


def load_script(name: str):
    """scripts/<name>.py as a module (scripts/ is not a package)."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


smoke = load_script("smoke")
check_demo_data = load_script("check_demo_data")  # its `import smoke` finds the module above

REFERENCE = smoke.load_reference_pairs(REPO_ROOT)


def csv_row_count(path: Path) -> int:
    """Counted with the csv module, independently of the loader under test."""
    with open(path, newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.DictReader(f))


def engine_overlaps(path: Path):
    """What pipeline.load's main() computes before writing: read, narrow, detect."""
    rows = read_project_csv(path)
    return rows, detect_overlaps(to_engine_project(r) for r in rows)


def served_overlaps(path: Path) -> list[dict]:
    """The engine's overlaps as GET /overlaps serves them (repository.build_overlap, JSON)."""
    rows, overlaps = engine_overlaps(path)
    projects = {r.project_id: Project.model_validate(vars(r)) for r in rows}
    return [
        build_overlap(o, rank, projects).model_dump(mode="json")
        for rank, o in enumerate(rank_by_score(overlaps), start=1)
    ]


# --- Offline: smoke.py will pass on projects.csv ------------------------------------------------


def test_projects_csv_is_the_full_dataset_not_the_sponsor_sample():
    assert csv_row_count(PROJECTS_CSV) > csv_row_count(SPONSOR_SAMPLE_CSV)


def test_smoke_finds_all_six_sponsor_pairs_in_what_projects_csv_would_serve():
    """AC1 before any load: smoke's own reference loading and matching (0.5 mi tolerance)."""
    overlaps = served_overlaps(PROJECTS_CSV)

    assert len(REFERENCE) == 6
    assert smoke.find_missing_pairs(overlaps, REFERENCE) == []


def test_smoke_would_catch_a_missing_sponsor_pair():
    """The check above can fail: drop one reference pair and smoke reports exactly it."""
    overlaps = served_overlaps(PROJECTS_CSV)
    first = REFERENCE[0]
    kept = [o for o in overlaps if not smoke._matches(o, first)]

    assert smoke.find_missing_pairs(kept, REFERENCE) == [first]


# --- check_demo_data.py: comparison logic, no DB ------------------------------------------------


def project(pid: str) -> dict:
    return {"project_id": pid, "project_name": pid}


def overlap(id_a: str, id_b: str, rank: int = 1) -> dict:
    return {"overlap_id": f"OVL_{rank}", "rank": rank,
            "project_a": project(id_a), "project_b": project(id_b)}


EXPECTED = check_demo_data.ExpectedData(
    project_ids=frozenset({"A", "B", "C"}),
    overlap_pairs=frozenset({frozenset({"A", "B"}), frozenset({"B", "C"})}),
)
MATCHING_PROJECTS = [project("A"), project("B"), project("C")]
MATCHING_OVERLAPS = [overlap("A", "B", 1), overlap("C", "B", 2)]  # either order is the same pair


def test_matching_data_has_no_differences():
    assert check_demo_data.find_differences(EXPECTED, MATCHING_PROJECTS, MATCHING_OVERLAPS) == []


def test_a_project_count_mismatch_is_reported_with_the_missing_id():
    problems = check_demo_data.find_differences(EXPECTED, MATCHING_PROJECTS[:2], MATCHING_OVERLAPS)

    assert any("2 projects, but the CSV has 3" in p for p in problems)
    assert any("missing 1 from the CSV: C" in p for p in problems)


def test_a_leftover_project_from_an_older_load_is_reported():
    projects = [project("A"), project("B"), project("DESC_1")]
    problems = check_demo_data.find_differences(EXPECTED, projects, MATCHING_OVERLAPS)

    assert any("not in the CSV: DESC_1" in p for p in problems)


def test_an_overlap_count_mismatch_is_reported():
    problems = check_demo_data.find_differences(EXPECTED, MATCHING_PROJECTS, MATCHING_OVERLAPS[:1])

    assert any("1 overlaps, but the engine flags 2" in p for p in problems)
    assert any("missing 1 engine pairs: B x C" in p for p in problems)


def test_same_count_but_a_wrong_pair_is_still_reported():
    """Counts alone would pass on the wrong pairs."""
    overlaps = [overlap("A", "B", 1), overlap("A", "C", 2)]
    problems = check_demo_data.find_differences(EXPECTED, MATCHING_PROJECTS, overlaps)

    assert not any("overlaps, but" in p for p in problems)
    assert any("missing 1 engine pairs: B x C" in p for p in problems)
    assert any("pairs the engine does not flag: A x C" in p for p in problems)


def test_expected_data_is_the_csv_rows_and_the_engine_pairs():
    rows, overlaps = engine_overlaps(PROJECTS_CSV)
    expected = check_demo_data.expected_from_csv(PROJECTS_CSV)

    assert len(expected.project_ids) == csv_row_count(PROJECTS_CSV)
    assert len(expected.overlap_pairs) == len(overlaps) > 6
    assert expected.project_ids == {r.project_id for r in rows}


def fake_api(projects: list[dict], overlaps: list[dict], prefix: str = "/api"):
    def handler(request: httpx.Request) -> httpx.Response:
        routes = {f"{prefix}/projects": projects, f"{prefix}/overlaps": overlaps}
        if request.url.path in routes:
            return httpx.Response(200, json=routes[request.url.path])
        return httpx.Response(404, json={"detail": "not found"})

    return httpx.MockTransport(handler)


def run_main(transport, capsys, csv_path: Path = SPONSOR_SAMPLE_CSV) -> tuple[int, str, str]:
    code = check_demo_data.main(
        ["--csv", str(csv_path)],
        environ={"BASE_URL": "https://gridwatch.example/api/"},
        transport=transport,
    )
    out, err = capsys.readouterr()
    return code, out, err


def test_main_passes_when_the_api_serves_the_csv(capsys):
    overlaps = served_overlaps(SPONSOR_SAMPLE_CSV)
    projects = [{"project_id": r.project_id} for r in read_project_csv(SPONSOR_SAMPLE_CSV)]

    code, out, err = run_main(fake_api(projects, overlaps), capsys)

    assert code == 0, err
    assert "demo data OK: 10 projects and 6 overlaps" in out


def test_main_ignores_uploaded_projects_and_their_pairs_but_says_so(capsys):
    """A deployed API on the old shared-uploads code serves them; the check is about the CSV."""
    overlaps = served_overlaps(SPONSOR_SAMPLE_CSV)
    projects = [{"project_id": r.project_id} for r in read_project_csv(SPONSOR_SAMPLE_CSV)]
    uploaded = project("SUB-abc-1")
    projects.append(uploaded)
    overlaps.append({"overlap_id": "SUB:GPC_2|SUB-abc-1", "rank": 1,
                     "project_a": project("GPC_2"), "project_b": uploaded})

    code, out, err = run_main(fake_api(projects, overlaps), capsys)

    assert code == 0, err
    assert "demo data OK: 10 projects and 6 overlaps" in out
    assert "ignored 1 uploaded project(s) and 1 of their pair(s)" in out


def test_main_fails_naming_the_difference_when_the_api_serves_something_else(capsys):
    """E.g. the demo still serves the 10-row sample after a projects.csv load was meant."""
    overlaps = served_overlaps(SPONSOR_SAMPLE_CSV)
    projects = [{"project_id": r.project_id} for r in read_project_csv(SPONSOR_SAMPLE_CSV)]

    code, _, err = run_main(fake_api(projects, overlaps), capsys, csv_path=PROJECTS_CSV)

    assert code == 1
    rows, engine = engine_overlaps(PROJECTS_CSV)
    assert f"10 projects, but the CSV has {len(rows)}" in err
    assert f"6 overlaps, but the engine flags {len(engine)}" in err


def test_main_fails_loud_on_an_http_error(capsys):
    code, _, err = run_main(fake_api([], [], prefix="/elsewhere"), capsys)

    assert code == 1
    assert "GET /projects: expected 200, got 404" in err


# --- Rehearsal on the throwaway PostGIS ---------------------------------------------------------


def refuse_the_shared_database() -> None:
    """These tests replace both tables; never let TEST_DATABASE_URL be the demo database."""
    shared = {os.environ.get("DATABASE_URL"), dotenv_values(ENV_PATH).get("DATABASE_URL")}
    # pytest.fail, not assert: a failing assert prints both operands, i.e. the demo URL and
    # its password, into the test output.
    if TEST_DATABASE_URL in shared:
        pytest.fail("TEST_DATABASE_URL is the shared demo DATABASE_URL", pytrace=False)


@pytest.fixture(scope="module")
def loaded_api():
    """projects.csv loaded by the real CLI into the throwaway DB, and the real API over it."""
    refuse_the_shared_database()
    result = subprocess.run(
        [sys.executable, "-m", "pipeline.load", "--csv", str(PROJECTS_CSV),
         "--database-url", TEST_DATABASE_URL],
        cwd=BACKEND_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    assert result.returncode == 0, result.stderr
    app = create_app(Settings(database_url=TEST_DATABASE_URL,
                              frontend_origin="http://localhost:5173"))
    with TestClient(app) as client:
        yield client, result.stdout


@requires_postgres
def test_rehearsal_load_reports_the_csv_rows_and_the_engine_overlaps(loaded_api):
    _, stdout = loaded_api
    _, overlaps = engine_overlaps(PROJECTS_CSV)

    assert f"loaded {csv_row_count(PROJECTS_CSV)} projects and {len(overlaps)} overlaps" in stdout


@requires_postgres
def test_rehearsal_api_counts_match_the_csv_and_the_engine(loaded_api):
    """AC2: GET /projects == projects.csv rows; GET /overlaps == the engine's count on it."""
    client, _ = loaded_api
    _, overlaps = engine_overlaps(PROJECTS_CSV)

    projects = client.get("/projects")
    served = client.get("/overlaps")

    assert projects.status_code == served.status_code == 200
    assert len(projects.json()) == csv_row_count(PROJECTS_CSV)
    assert len(served.json()) == len(overlaps)


@requires_postgres
def test_rehearsal_passes_check_demo_data(loaded_api):
    """The post-load command's own check, run through the real API."""
    client, _ = loaded_api
    expected = check_demo_data.expected_from_csv(PROJECTS_CSV)

    assert check_demo_data.check_api(client, expected).startswith("demo data OK")


@requires_postgres
def test_rehearsal_passes_smoke_with_all_six_sponsor_pairs(loaded_api):
    """AC1 end to end: smoke.py's own checks against the real API over the loaded DB."""
    client, _ = loaded_api

    assert smoke.find_missing_pairs(client.get("/overlaps").json(), REFERENCE) == []
    assert smoke.check_api(client, REFERENCE).startswith("smoke OK")
