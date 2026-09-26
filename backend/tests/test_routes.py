"""The HTTP API against docs/api.md, with the repository swapped for fixture data (no DB)."""

import csv
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from app.config import Settings
from app.main import create_app
from app.repository import build_overlap
from app.routes import get_repository
from app.schemas import ErrorDetail, Health, Overlap, Project
from pipeline.overlap import Overlap as EngineOverlap
from pipeline.overlap import opportunity_score, rank_by_score

FIXTURES = Path(__file__).parent / "fixtures"
FRONTEND_ORIGIN = "http://localhost:5173"
SETTINGS = Settings(
    database_url="postgresql://localhost/never-connected", frontend_origin=FRONTEND_ORIGIN
)


def read_csv(name: str) -> list[dict]:
    with open(FIXTURES / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fixture_projects() -> list[Project]:
    return [Project.model_validate(row) for row in read_csv("starter_projects.csv")]


def fixture_overlaps(projects: list[Project] | None = None) -> list[Overlap]:
    """The sponsor's six pairs, ranked by the engine's rule — as the real repository would.

    Built with the repository's own `build_overlap`, so savings come from the real estimator.
    """
    by_id = {p.project_id: p for p in (projects or fixture_projects())}
    engine_rows = [
        EngineOverlap(
            overlap_id=row["overlap_id"],
            project_id_a=row["project_id_a"],
            project_id_b=row["project_id_b"],
            distance_mi=float(row["distance_mi"]),
            time_gap_days=int(row["time_gap_days"]),
            score=opportunity_score(float(row["distance_mi"]), int(row["time_gap_days"])),
        )
        for row in read_csv("starter_overlaps.csv")
    ]
    return [
        build_overlap(o, rank, by_id)
        for rank, o in enumerate(rank_by_score(engine_rows), start=1)
    ]


class FixtureRepository:
    """Serves fixture data, deliberately NOT in rank order, so the route must sort."""

    def __init__(self, costs: dict[str, int] | None = None) -> None:
        self.projects = [
            p.model_copy(update={"est_cost_usd": (costs or {}).get(p.project_id)})
            for p in fixture_projects()
        ]
        self.overlaps = list(reversed(fixture_overlaps(self.projects)))
        self.submitted: list[Project] = []

    def list_projects(self) -> list[Project]:
        return [*self.projects, *self.submitted]

    def list_overlaps(self) -> list[Overlap]:
        return self.overlaps

    def get_overlap(self, overlap_id: str) -> Overlap | None:
        return next((o for o in self.overlaps if o.overlap_id == overlap_id), None)

    def add_submission(self, projects: list[Project]) -> None:
        self.submitted.extend(projects)


@pytest.fixture
def repository() -> FixtureRepository:
    return FixtureRepository()


@pytest.fixture
def client(repository) -> TestClient:
    app = create_app(SETTINGS)
    app.dependency_overrides[get_repository] = lambda: repository
    return TestClient(app)


# --- /health ------------------------------------------------------------------------------


def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert Health.model_validate(response.json()) == Health(status="ok")


# --- /projects ----------------------------------------------------------------------------


def test_projects_returns_every_project_as_valid_project(client, repository):
    response = client.get("/projects")

    assert response.status_code == 200
    projects = TypeAdapter(list[Project]).validate_python(response.json())
    assert projects == repository.projects
    assert len(projects) == 10


def test_projects_serializes_nulls_and_iso_dates(client):
    body = client.get("/projects").json()
    desc_1 = next(p for p in body if p["project_id"] == "DESC_1")

    assert desc_1["lat_b"] is None and desc_1["lon_b"] is None
    assert desc_1["in_service_date"] == "2024-12-31"
    assert desc_1["est_cost_usd"] is None
    assert desc_1["location_confidence"] == "confirmed"


# --- /overlaps ----------------------------------------------------------------------------


def test_overlaps_sorted_by_rank_even_when_repository_is_not(client, repository):
    # Guard the premise: the fixture repository really serves them out of order.
    assert [o.rank for o in repository.list_overlaps()] != sorted(
        o.rank for o in repository.list_overlaps()
    )

    response = client.get("/overlaps")

    assert response.status_code == 200
    overlaps = TypeAdapter(list[Overlap]).validate_python(response.json())
    assert [o.rank for o in overlaps] == list(range(1, 7))
    assert [o.score for o in overlaps] == sorted((o.score for o in overlaps), reverse=True)
    assert {o.overlap_id for o in overlaps} == {f"OVL_{n}" for n in range(1, 7)}


def test_overlaps_rank_one_is_the_contract_example(client):
    top = client.get("/overlaps").json()[0]

    assert top["overlap_id"] == "OVL_2"
    assert top["project_a"]["project_id"] == "DESC_3"
    assert top["project_b"]["project_id"] == "GPC_2"


# --- /overlaps/{overlap_id} ---------------------------------------------------------------


def test_get_known_overlap_returns_it(client):
    response = client.get("/overlaps/OVL_3")

    assert response.status_code == 200
    overlap = Overlap.model_validate(response.json())
    assert overlap.overlap_id == "OVL_3"
    assert overlap.project_a.project_id == "DESC_3"
    assert overlap.project_b.project_id == "GPC_3"
    assert overlap.distance_mi == 7.55
    assert overlap.time_gap_days == 517


def test_get_unknown_overlap_is_404_with_contract_error_body(client):
    response = client.get("/overlaps/OVL_99")

    assert response.status_code == 404
    assert ErrorDetail.model_validate(response.json()) == ErrorDetail(
        detail="overlap OVL_99 not found"
    )


# --- savings estimate on /overlaps and /overlaps/{overlap_id} -----------------------------

DESC_3_COST = 23_787_423  # the docs/api.md example's DESC_3 cost


@pytest.fixture
def costed_client() -> TestClient:
    """Starter data with DESC_3's public cost filled in (the starter CSV has no costs)."""
    repository = FixtureRepository(costs={"DESC_3": DESC_3_COST})
    app = create_app(SETTINGS)
    app.dependency_overrides[get_repository] = lambda: repository
    return TestClient(app)


def test_overlaps_without_any_known_cost_are_null_with_the_redaction_reason(client):
    body = client.get("/overlaps").json()

    assert len(body) == 6
    for overlap in body:
        assert "est_savings_usd" in overlap and overlap["est_savings_usd"] is None
        # Every starter pair has a Georgia Power side, whose cost is redacted.
        assert "cost redacted in Georgia Power IRP" in overlap["savings_basis"]


def test_get_overlap_without_known_cost_is_null_with_the_redaction_reason(client):
    body = client.get("/overlaps/OVL_3").json()

    assert body["est_savings_usd"] is None
    assert body["savings_basis"] == (
        "No estimate: neither project has a known cost "
        "(the Dominion Energy South Carolina project: no published cost; "
        "the Georgia Power project: cost redacted in Georgia Power IRP)."
    )


def test_overlaps_with_a_known_cost_carry_the_estimate(costed_client):
    by_id = {o["overlap_id"]: o for o in costed_client.get("/overlaps").json()}

    # DESC_3's pairs get a number; the closer, sooner OVL_2 beats OVL_3.
    assert by_id["OVL_2"]["est_savings_usd"] == 709_900
    assert by_id["OVL_3"]["est_savings_usd"] == 324_472
    assert "$23,787,423" in by_id["OVL_2"]["savings_basis"]
    # Pairs without DESC_3 still have no known cost.
    for overlap_id in ("OVL_1", "OVL_4", "OVL_5", "OVL_6"):
        assert by_id[overlap_id]["est_savings_usd"] is None
        assert "cost redacted in Georgia Power IRP" in by_id[overlap_id]["savings_basis"]


def test_get_overlap_with_a_known_cost_carries_the_estimate(costed_client):
    response = costed_client.get("/overlaps/OVL_2")

    assert response.status_code == 200
    overlap = Overlap.model_validate(response.json())
    assert overlap.est_savings_usd == 709_900
    assert overlap.savings_basis == (
        "Assumed shared mobilization of 5% of the Dominion Energy South Carolina project's "
        "$23,787,423 cost, x0.80 for 5.65 mi apart and x0.75 for 152 days between in-service "
        "dates. No figure for the Georgia Power project (cost redacted in Georgia Power IRP)."
    )


# --- POST /submissions --------------------------------------------------------------------


def upload_row(**overrides) -> dict:
    """One row as the frontend's upload dialog sends it (docs/api.md)."""
    return {
        "project_id": "client-ref-1",
        "utility": "Tidewater Grid Co.",
        "state": "SC",
        "project_name": "Savannah River crossing",
        "lat_center": 32.352116,
        "lon_center": -81.175112,
        "in_service_date": "2026-06-01",
        "est_cost_usd": 2500000,
        **overrides,
    }


def test_a_submission_is_stored_and_returned_with_server_ids(client, repository):
    rows = [upload_row(), upload_row(project_id="client-ref-2", project_name="Second line")]
    response = client.post("/submissions", json={"projects": rows})

    assert response.status_code == 201
    stored = TypeAdapter(list[Project]).validate_python(response.json())
    assert [p.project_name for p in stored] == ["Savannah River crossing", "Second line"]
    assert all(p.project_id.startswith("SUB-") for p in stored)
    assert all(p.location_confidence == "low" for p in stored)
    assert repository.submitted == stored


def test_submitted_projects_are_served_to_everyone_by_get_projects(client):
    [stored] = client.post("/submissions", json={"projects": [upload_row()]}).json()

    ids = [p["project_id"] for p in client.get("/projects").json()]
    assert stored["project_id"] in ids
    assert len(ids) == 11


def test_a_project_that_already_exists_is_a_409_and_nothing_is_stored(client, repository):
    duplicate = upload_row(
        project_id="client-ref-2",
        utility="georgia power",
        project_name=repository.projects[5].project_name,
    )
    response = client.post("/submissions", json={"projects": [upload_row(), duplicate]})

    assert response.status_code == 409
    assert "already exists" in ErrorDetail.model_validate(response.json()).detail
    assert repository.submitted == []


def test_submitting_the_same_upload_twice_is_a_409_the_second_time(client, repository):
    assert client.post("/submissions", json={"projects": [upload_row()]}).status_code == 201
    assert client.post("/submissions", json={"projects": [upload_row()]}).status_code == 409
    assert len(repository.submitted) == 1


@pytest.mark.parametrize(
    "body",
    [
        {"projects": []},
        {"projects": [upload_row()] * 1001},
        {"projects": [upload_row(lat_center=91)]},
        {"projects": [upload_row(in_service_date="06/01/2026")]},
        {"projects": [upload_row(utility="")]},
        {"projects": [upload_row(est_cost_usd=-1)]},
        [upload_row()],
    ],
    ids=["empty", "over-1000", "bad-latitude", "non-iso-date", "no-utility", "negative-cost",
         "bare-list"],
)
def test_an_invalid_submission_is_a_422_and_nothing_is_stored(client, repository, body):
    assert client.post("/submissions", json=body).status_code == 422
    assert repository.submitted == []


# --- CORS ---------------------------------------------------------------------------------


def test_cors_allows_the_configured_frontend_origin(client):
    response = client.get("/health", headers={"Origin": FRONTEND_ORIGIN})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN


def test_cors_preflight_from_frontend_origin_is_allowed(client):
    response = client.options(
        "/overlaps",
        headers={"Origin": FRONTEND_ORIGIN, "Access-Control-Request-Method": "GET"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN


@pytest.mark.parametrize("origin", ["http://evil.example", "http://localhost:3000"])
def test_cors_rejects_any_other_origin(client, origin):
    response = client.get("/health", headers={"Origin": origin})
    assert "access-control-allow-origin" not in response.headers

    preflight = client.options(
        "/overlaps", headers={"Origin": origin, "Access-Control-Request-Method": "GET"}
    )
    assert preflight.status_code == 400
    assert "access-control-allow-origin" not in preflight.headers


def test_cors_origin_comes_from_settings(repository):
    other = "https://gridwatch.example"
    app = create_app(Settings(database_url=SETTINGS.database_url, frontend_origin=other))
    app.dependency_overrides[get_repository] = lambda: repository
    client = TestClient(app)

    assert client.get("/health", headers={"Origin": other}).headers[
        "access-control-allow-origin"
    ] == other
    assert "access-control-allow-origin" not in client.get(
        "/health", headers={"Origin": FRONTEND_ORIGIN}
    ).headers


def test_cors_preflight_allows_posting_a_submission(client):
    response = client.options(
        "/submissions",
        headers={"Origin": FRONTEND_ORIGIN, "Access-Control-Request-Method": "POST"},
    )

    assert response.status_code == 200
    assert "POST" in response.headers["access-control-allow-methods"]
