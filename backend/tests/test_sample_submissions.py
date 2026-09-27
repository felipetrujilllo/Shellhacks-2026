# ruff: noqa: E501  (SOURCE below is the user's CSV verbatim; its rows cannot be wrapped)
"""Issue #62: the standing sample submissions ("Tallapoosa Grid Partners"), served to every
visitor as if someone had already uploaded them.

No database: the API runs over the real repository code with only published_plans read from
data/seed/projects.csv instead of Postgres (test_demo_data.CsvRepository), so the samples are
merged exactly as in production. The DB-backed checks are in test_repository.py and the
rehearsal in test_demo_data.py.
"""

import csv
import io
import re
import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from test_demo_data import (
    PROJECTS_CSV,
    REFERENCE,
    SPONSOR_SAMPLE_CSV,
    CsvRepository,
    served_overlaps,
    smoke,
)
from test_routes import SETTINGS, tier_first_key

from app.main import create_app
from app.routes import get_repository
from app.samples import (
    SAMPLE_SUBMISSIONS_CSV,
    SampleDataError,
    load_sample_submissions,
    prepare_samples,
)
from app.schemas import UPLOAD_ID_PATTERN, Overlap, Project, UploadedProject, Workspace
from app.submissions import SubmissionConflict, prepare_submission

REPO_ROOT = Path(__file__).resolve().parents[2]
UTILITY = "Tallapoosa Grid Partners"

# The 31 projects exactly as the user provided them (ids still with their spaces).
SOURCE = """\
project_id,utility,project_name,lat_center,lon_center,in_service_date,est_cost_usd,name_a,lat_a,lon_a,name_b,lat_b,lon_b
7302,Tallapoosa Grid Partners,Roanoke - Wedowee 115 kV Reconductor,33.23,-85.4285,2027-06-01,8900000,Roanoke,33.151,-85.372,Wedowee,33.309,-85.485
5512 A,Tallapoosa Grid Partners,Anniston - Oxford 115 kV Line Upgrade,33.637,-85.833,2026-08-31,5250000,Anniston,33.66,-85.831,Oxford,33.614,-85.835
7215 A,Tallapoosa Grid Partners,Lanett - Valley 115 kV Line Rebuild,32.844,-85.1845,2026-09-30,7900000,Lanett,32.869,-85.19,Valley,32.819,-85.179
7390,Tallapoosa Grid Partners,Fredonia - Five Points 115 kV Line Rebuild,33.0,-85.3225,2026-10-31,4600000,Fredonia,32.98,-85.29,Five Points,33.02,-85.355
6781,Tallapoosa Grid Partners,Auburn - Opelika 115 kV Reconductor,32.6275,-85.4295,2026-05-31,5250000,Auburn,32.61,-85.481,Opelika,32.645,-85.378
6620,Tallapoosa Grid Partners,Phenix City - Smiths Station 115 kV Line Rebuild,32.5055,-85.05,2025-11-30,7200000,Phenix City,32.471,-85.001,Smiths Station,32.54,-85.099
6390,Tallapoosa Grid Partners,Tuskegee 115 kV Sub: Capacitor Bank Addition,32.424,-85.691,2026-04-30,2300000,Tuskegee,32.424,-85.691,,,
6033,Tallapoosa Grid Partners,Alexander City - Dadeville 115 kV Rebuild,32.8875,-85.859,2028-06-30,5400000,Alexander City,32.944,-85.954,Dadeville,32.831,-85.764
5720,Tallapoosa Grid Partners,Wetumpka - Tallassee 115 kV Reconductor,32.54,-86.0525,2026-07-31,4600000,Wetumpka,32.544,-86.212,Tallassee,32.536,-85.893
5904 C,Tallapoosa Grid Partners,Montgomery - Prattville 230 kV Line Upgrade,32.4155,-86.3795,2027-12-31,20500000,Montgomery,32.367,-86.3,Prattville,32.464,-86.459
6244,Tallapoosa Grid Partners,Troy - Union Springs 115 kV Line Rebuild,31.9765,-85.8425,2028-12-31,15600000,Troy,31.809,-85.97,Union Springs,32.144,-85.715
6955,Tallapoosa Grid Partners,Eufaula 115-12.47 kV Sub: Rebuild,31.891,-85.145,2027-04-30,4650000,Eufaula,31.891,-85.145,,,
8215,Tallapoosa Grid Partners,Shorterville 115 kV Switching Station,31.56,-85.1,2029-09-30,6000000,Shorterville,31.56,-85.1,,,
7488,Tallapoosa Grid Partners,Dothan - Headland 115 kV Line Rebuild,31.287,-85.366,2028-10-31,7550000,Dothan,31.223,-85.39,Headland,31.351,-85.342
7602,Tallapoosa Grid Partners,Enterprise - Ozark 115 kV Line Rebuild,31.387,-85.7475,2027-09-30,8050000,Enterprise,31.315,-85.855,Ozark,31.459,-85.64
3988,Tallapoosa Grid Partners,Andalusia - Opp 115 kV Reconductor,31.2955,-86.3685,2027-10-31,5350000,Andalusia,31.308,-86.482,Opp,31.283,-86.255
3655,Tallapoosa Grid Partners,Bay Minette 230-115 kV Sub: New Autotransformer,30.883,-87.773,2027-12-31,16900000,Bay Minette,30.883,-87.773,,,
3740,Tallapoosa Grid Partners,Foley - Gulf Shores 115 kV Line Rebuild,30.3265,-87.6925,2027-04-30,8400000,Foley,30.407,-87.684,Gulf Shores,30.246,-87.701
3701 A,Tallapoosa Grid Partners,Mobile - Saraland 115 kV Line Upgrade,30.758,-88.0555,2026-09-30,9000000,Mobile,30.695,-88.04,Saraland,30.821,-88.071
7220,Tallapoosa Grid Partners,Lanett - LaGrange Primary 115 kV Tie Line,32.9466,-85.1028,2026-06-01,11500000,Lanett,32.869,-85.19,LaGrange Primary,33.024106,-85.01568
7410,Tallapoosa Grid Partners,Ranburne - Bowdon 115 kV Tie Line,33.531,-85.298,2027-08-31,8600000,Ranburne,33.524,-85.343,Bowdon,33.538,-85.253
5530,Tallapoosa Grid Partners,Heflin 115-12.47 kV Sub: Rebuild,33.649,-85.587,2027-04-30,3000000,Heflin,33.649,-85.587,,,
8150,Tallapoosa Grid Partners,Columbia - Blakely West 115 kV Interconnection,31.3323,-85.015,2029-03-31,14400000,Columbia,31.293,-85.112,Blakely West,31.3716,-84.918
8162,Tallapoosa Grid Partners,Gordon - Early County 115 kV Tie Line,31.2365,-85.0235,2028-12-31,16800000,Gordon,31.143,-85.097,Early County Tie,31.33,-84.95
8305,Tallapoosa Grid Partners,Cottonwood 115-12.47 kV Sub: Rebuild,31.049,-85.305,2027-10-31,3500000,Cottonwood,31.049,-85.305,,,
8321,Tallapoosa Grid Partners,Hartford - Slocomb 115 kV Line Rebuild,31.1055,-85.6455,2028-06-30,5600000,Hartford,31.103,-85.697,Slocomb,31.108,-85.594
8340,Tallapoosa Grid Partners,Geneva - Samson 115 kV Reconductor,31.073,-85.955,2027-03-31,3850000,Geneva,31.033,-85.864,Samson,31.113,-86.046
3990,Tallapoosa Grid Partners,Florala 115-12.47 kV Sub: Expansion,31.004,-86.328,2026-11-30,2600000,Florala,31.004,-86.328,,,
3622,Tallapoosa Grid Partners,Brewton - Flomaton 115 kV Line Rebuild,31.0525,-87.1665,2028-06-30,9200000,Brewton,31.105,-87.072,Flomaton,31.0,-87.261
3641,Tallapoosa Grid Partners,Atmore 115 kV Breaker Station,31.024,-87.494,2027-12-31,4800000,Atmore,31.024,-87.494,,,
3760,Tallapoosa Grid Partners,Lillian 115-12.47 kV Sub: New Substation,30.411,-87.438,2028-05-31,5050000,Lillian,30.411,-87.438,,,
"""
SOURCE_ROWS = list(csv.DictReader(io.StringIO(SOURCE)))
MAPPED_IDS = {"5512 A": "5512-A", "7215 A": "7215-A", "5904 C": "5904-C", "3701 A": "3701-A"}
# Substations: one endpoint only.
ONE_ENDPOINT = {"6390", "6955", "8215", "3655", "5530", "8305", "3990", "3641", "3760"}

# The pairs the samples add to data/seed/projects.csv, worked out once with the engine and
# checked by hand against the live test-branch-1 API (docs/demo.md "Figures").
SAMPLE_PAIRS = {
    "SUB:19598|SUB-7220": "crossing",
    "SUB:10222|SUB-8150": "shared_land",
    "SUB:10222|SUB-8162": "site_logistics",
    "SUB:19598|SUB-7215-A": "crews",
    "SUB:10222|SUB-8215": "crews",
    "SUB:19598|SUB-7390": "crews",
    "SUB:15879|SUB-7410": "crews",
}


def file_rows(path: Path = SAMPLE_SUBMISSIONS_CSV) -> tuple[list[str], list[dict]]:
    """The file's leading '#' note lines and its data rows as raw strings (csv module only)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    note = [line for line in lines if line.startswith("#")]
    return note, list(csv.DictReader(line for line in lines if not line.startswith("#")))


def client_over(repository) -> TestClient:
    app = create_app(SETTINGS)
    app.dependency_overrides[get_repository] = lambda: repository
    return TestClient(app)


@pytest.fixture(scope="module")
def client() -> TestClient:
    """The API over the demo dataset (projects.csv) plus the real sample submissions."""
    return client_over(CsvRepository(PROJECTS_CSV))


@pytest.fixture(scope="module")
def listed(client) -> list[Overlap]:
    return TypeAdapter(list[Overlap]).validate_python(client.get("/overlaps").json())


def upload_row(**overrides) -> dict:
    """A visitor's upload: another utility's project on sample 7302's center and date."""
    return {
        "project_id": "c0ffee-1",
        "utility": "Chattahoochee Water",
        "state": "AL",
        "project_name": "Roanoke water main",
        "lat_center": 33.23,
        "lon_center": -85.4285,
        "in_service_date": "2027-06-01",
        "est_cost_usd": 1_000_000,
        **overrides,
    }


# --- the CSV --------------------------------------------------------------------------------


def test_the_csv_holds_the_31_given_projects_exactly_with_mapped_ids_and_state_al():
    _, rows = file_rows()

    assert len(SOURCE_ROWS) == len(rows) == 31
    for source, row in zip(SOURCE_ROWS, rows, strict=True):
        expected = {**source, "project_id": MAPPED_IDS.get(source["project_id"],
                                                           source["project_id"]), "state": "AL"}
        # Every value byte for byte: coordinates, dates, costs and names untouched.
        assert row == expected, source["project_id"]


def test_ids_with_a_space_are_mapped_to_a_hyphen_and_every_id_fits_the_upload_pattern():
    _, rows = file_rows()
    ids = [r["project_id"] for r in rows]

    assert set(MAPPED_IDS.values()) <= set(ids)
    assert not set(MAPPED_IDS) & set(ids)
    assert all(re.fullmatch(UPLOAD_ID_PATTERN, i) for i in ids)
    assert len(set(ids)) == 31


def test_the_csv_says_plainly_that_it_is_sample_data_not_a_real_filing():
    note, _ = file_rows()

    assert note, "the sample-data note at the top of the file is gone"
    assert note[0].startswith("# SAMPLE DATA - NOT A REAL UTILITY'S PUBLIC FILING.")
    assert "Never loaded into the database" in " ".join(note)


def test_the_samples_are_not_in_the_seed_data_the_database_is_loaded_from():
    names = {r["project_name"] for r in SOURCE_ROWS}
    for seed in (PROJECTS_CSV, SPONSOR_SAMPLE_CSV):
        text = seed.read_text(encoding="utf-8")
        assert UTILITY not in text, seed.name
        assert not any(name in text for name in names), seed.name


def test_the_csv_ships_with_the_deployed_api():
    """The api component is built from backend/ alone (.do/app.yaml source_dir)."""
    assert SAMPLE_SUBMISSIONS_CSV.is_relative_to(REPO_ROOT / "backend")
    pyproject = tomllib.loads((REPO_ROOT / "backend" / "pyproject.toml").read_text(
        encoding="utf-8"))
    assert SAMPLE_SUBMISSIONS_CSV.name in pyproject["tool"]["setuptools"]["package-data"]["app"]


# --- loading ----------------------------------------------------------------------------------


def test_the_samples_load_as_uploads_with_typed_values():
    samples = load_sample_submissions()

    assert len(samples) == 31
    assert all(isinstance(s, UploadedProject) for s in samples)
    assert {s.utility for s in samples} == {UTILITY} and {s.state for s in samples} == {"AL"}
    tie = next(s for s in samples if s.project_id == "7220")
    assert (tie.lat_b, tie.lon_b, tie.name_b) == (33.024106, -85.01568, "LaGrange Primary")
    assert (str(tie.in_service_date), tie.est_cost_usd) == ("2026-06-01", 11_500_000)


def test_substations_have_one_endpoint_and_no_b_side():
    samples = {s.project_id: s for s in load_sample_submissions()}

    for pid in ONE_ENDPOINT:
        assert (samples[pid].name_b, samples[pid].lat_b, samples[pid].lon_b) == (None,) * 3, pid
        assert samples[pid].lat_a is not None, pid
    assert all(s.lat_b is not None for pid, s in samples.items() if pid not in ONE_ENDPOINT)


def write_sample_csv(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "samples.csv"
    path.write_text(text, encoding="utf-8")
    return path


HEADER = "# a note\nproject_id,utility,state,project_name,lat_center,lon_center,in_service_date\n"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (HEADER + "a-1,U,AL,Line,95,-85,2027-01-01\n", "data row 1"),
        (HEADER + "a-1,U,AL,Line,33,-85,2027-01-01\n5512 A,U,AL,Other,33,-85,2027-01-01\n",
         "data row 2"),
        (HEADER + "a-1,U,AL,Line,33,-85,01/01/2027\n", "data row 1"),
        (HEADER.replace("state", "state,color") + "a-1,U,AL,red,Line,33,-85,2027-01-01\n",
         "unknown column(s) ['color']"),
        (HEADER + "a-1,U,AL,Line,33,-85,2027-01-01\na-2,U,AL,line ,33,-85,2027-01-01\n",
         "appears twice"),
        (HEADER + "a-1,U,AL,Line,33,-85,2027-01-01\na-1,U,AL,Other,33,-85,2027-01-01\n",
         "reuses the id"),
        (HEADER, "has no rows"),
    ],
    ids=["bad-latitude", "id-with-space", "non-iso-date", "unknown-column", "duplicate-name",
         "duplicate-id", "empty"],
)
def test_a_broken_sample_file_fails_loud(tmp_path, text, message):
    with pytest.raises(SampleDataError, match=re.escape(message)):
        load_sample_submissions(write_sample_csv(tmp_path, text))


def test_a_sample_clashing_with_a_published_project_is_our_error_not_a_409():
    published = Project.model_validate({**upload_row(), "project_id": "PUB_1",
                                        "utility": UTILITY,
                                        "project_name": "Heflin 115-12.47 kV Sub: Rebuild"})
    with pytest.raises(SampleDataError, match="already exists"):
        prepare_samples(load_sample_submissions(), [published])

    class ClashingRepository(CsvRepository):
        def published_plans(self):
            plans = super().published_plans()
            return plans._replace(projects=[*plans.projects, published])

    app = create_app(SETTINGS)
    app.dependency_overrides[get_repository] = lambda: ClashingRepository(PROJECTS_CSV)
    broken = TestClient(app, raise_server_exceptions=False)
    assert broken.get("/overlaps").status_code == 500
    assert broken.post("/workspace", json={"projects": []}).status_code == 500


def test_a_repository_reads_the_samples_once_when_it_is_created(monkeypatch):
    """So a broken sample file stops the app at startup, not on some later request."""
    import app.repository as repository_module

    def broken():
        raise SampleDataError("boom")

    monkeypatch.setattr(repository_module, "load_sample_submissions", broken)
    with pytest.raises(SampleDataError, match="boom"):
        create_app(SETTINGS)


# --- GET /overlaps, GET /overlaps/{id} ------------------------------------------------------


def test_overlaps_include_the_sample_pairs_with_sub_ids_and_low_confidence(listed):
    samples = {o.overlap_id: o for o in listed if o.overlap_id.startswith("SUB:")}

    assert {i: o.tier for i, o in samples.items()} == SAMPLE_PAIRS
    for overlap in samples.values():
        project = overlap.project_b
        assert project.project_id.startswith("SUB-") and project.utility == UTILITY
        assert project.location_confidence == "low"
        assert overlap.project_a.utility == "Georgia Power"
        assert overlap.est_savings_usd is not None  # every sample has a cost


def test_overlaps_rank_the_sample_pairs_in_with_the_published_ones_tier_first(listed):
    assert [o.rank for o in listed] == list(range(1, len(listed) + 1))
    assert listed == sorted(listed, key=tier_first_key)
    assert len(listed) == 46
    # A sample crossing takes #1; the sponsor's Thurmond crossings follow it.
    assert [o.overlap_id for o in listed[:4]] == [
        "SUB:19598|SUB-7220", "OVL_1", "OVL_2", "SUB:10222|SUB-8150"
    ]


def test_the_published_pairs_are_unchanged_by_the_samples_except_their_rank(listed):
    alone = {o.overlap_id: o for o in CsvRepository(PROJECTS_CSV, samples=[]).list_overlaps()}
    published = [o for o in listed if not o.overlap_id.startswith("SUB:")]

    assert [o.overlap_id for o in published] == list(alone)  # same relative order
    for o in published:
        assert o.model_dump(exclude={"rank"}) == alone[o.overlap_id].model_dump(exclude={"rank"})


@pytest.mark.parametrize("overlap_id", sorted(SAMPLE_PAIRS))
def test_a_sample_pair_is_found_by_id_with_the_same_rank_as_the_list(client, listed, overlap_id):
    response = client.get(f"/overlaps/{overlap_id}")

    assert response.status_code == 200
    assert Overlap.model_validate(response.json()) == next(
        o for o in listed if o.overlap_id == overlap_id
    )


def test_a_visitors_own_upload_pair_is_still_not_found_by_id(client):
    assert client.get("/overlaps/SUB:SUB-7302|SUB-c0ffee-1").status_code == 404


# --- GET /projects ------------------------------------------------------------------------------


def test_projects_stays_published_only(client):
    """The map is fed from POST /workspace, which carries the samples; /projects stays honest."""
    served = client.get("/projects").json()

    assert len(served) == sum(1 for _ in csv.DictReader(
        io.StringIO(PROJECTS_CSV.read_text(encoding="utf-8"))))
    assert not any(p["project_id"].startswith("SUB-") for p in served)
    assert UTILITY not in {p["utility"] for p in served}


# --- POST /workspace ------------------------------------------------------------------------------


def test_an_empty_workspace_is_the_published_plans_plus_the_samples(client, listed):
    workspace = Workspace.model_validate(client.post("/workspace", json={"projects": []}).json())
    published = TypeAdapter(list[Project]).validate_python(client.get("/projects").json())

    assert workspace.projects[:len(published)] == published
    samples = workspace.projects[len(published):]
    assert [p.project_id for p in samples] == [
        f"SUB-{MAPPED_IDS.get(r['project_id'], r['project_id'])}" for r in SOURCE_ROWS
    ]
    assert all(p.location_confidence == "low" and p.state == "AL" for p in samples)
    assert workspace.overlaps == listed


def test_a_visitors_upload_is_scored_together_with_the_samples(client, listed):
    response = client.post("/workspace", json={"projects": [upload_row()]})

    assert response.status_code == 200
    workspace = Workspace.model_validate(response.json())
    assert workspace.projects[-1].project_id == "SUB-c0ffee-1"
    by_id = {o.overlap_id: o for o in workspace.overlaps}
    # Sitting on sample 7302: a 0 mi, 0 day pair between the upload and the sample.
    [pair] = [o for o in workspace.overlaps
              if {o.project_a.project_id, o.project_b.project_id} == {"SUB-7302", "SUB-c0ffee-1"}]
    assert (pair.distance_mi, pair.time_gap_days, pair.tier) == (0.0, 0, "crossing")
    assert pair.overlap_id.startswith("SUB:")
    # Everything served without the upload is still there, ranked in one list with it.
    assert {o.overlap_id for o in listed} <= set(by_id)
    assert workspace.overlaps == sorted(workspace.overlaps, key=tier_first_key)
    assert [o.rank for o in workspace.overlaps] == list(range(1, len(workspace.overlaps) + 1))


def test_an_upload_spelling_the_sample_utility_differently_takes_its_spelling(client):
    far = upload_row(utility="  tallapoosa GRID partners ", project_name="New line",
                     lat_center=34.7, lon_center=-86.6)  # Huntsville: near no one

    [uploaded] = client.post("/workspace", json={"projects": [far]}).json()["projects"][-1:]

    assert uploaded["utility"] == UTILITY


def test_an_upload_repeating_a_sample_name_is_the_usual_readable_409(client):
    duplicate = upload_row(utility="tallapoosa grid partners",
                           project_name="  ROANOKE - Wedowee 115 kV Reconductor")

    response = client.post("/workspace", json={"projects": [upload_row(project_id="c0ffee-0",
                                                                       project_name="Other"),
                                                            duplicate]})

    assert response.status_code == 409
    assert response.json() == {"detail": "project 2 ('ROANOKE - Wedowee 115 kV Reconductor' by "
                                         "'tallapoosa grid partners') already exists"}


def test_an_upload_reusing_a_sample_id_is_the_usual_readable_409(client):
    response = client.post("/workspace", json={"projects": [upload_row(project_id="7302")]})

    assert response.status_code == 409
    assert response.json() == {"detail": "project 1 ('Roanoke water main' by "
                                         "'Chattahoochee Water') reuses the id '7302'"}


# --- the golden test and the reference pairs --------------------------------------------------


def test_the_samples_add_no_pair_to_the_sponsors_ten_projects():
    """The golden test's table still yields exactly its six pairs, samples merged in."""
    ids = [o.overlap_id for o in CsvRepository(SPONSOR_SAMPLE_CSV).list_overlaps()]
    assert sorted(ids) == [f"OVL_{n}" for n in range(1, 7)]


def test_smoke_still_finds_the_six_reference_pairs_with_the_samples_served():
    served = served_overlaps(PROJECTS_CSV)
    assert any(o["overlap_id"].startswith("SUB:") for o in served)
    assert smoke.find_missing_pairs(served, REFERENCE) == []


# --- docs/api.md --------------------------------------------------------------------------------


def test_api_doc_documents_the_standing_sample_submissions():
    doc = (REPO_ROOT / "docs" / "api.md").read_text(encoding="utf-8")
    section = " ".join(doc[doc.index("### Standing sample submissions"):
                           doc.index("## Repository functions")].split())
    projects = " ".join(doc[doc.index("### `GET /projects`"):
                            doc.index("<!-- example: projects -->")].split())

    assert "**Sample data, not a real utility's public filing.**" in section
    assert "`backend/app/sample_submissions.csv`" in section
    assert "never loaded into the database" in section
    assert "not in `GET /projects`" in section
    assert "`5512 A` → `5512-A`" in section
    assert "Neither are the [standing sample submissions]" in projects


# --- prepare_submission: ids already served --------------------------------------------------


def test_prepare_submission_refuses_a_client_id_already_served_by_an_existing_upload():
    samples = prepare_samples(load_sample_submissions(), [])
    [project] = [UploadedProject.model_validate(upload_row(project_id="5512-A"))]
    with pytest.raises(SubmissionConflict, match="reuses the id '5512-A'"):
        prepare_submission([project], samples)
