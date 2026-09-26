"""The HTTP API against docs/api.md, with the repository swapped for fixture data (no DB)."""

import csv
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from app.config import Settings
from app.main import create_app
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


def fixture_overlaps() -> list[Overlap]:
    """The sponsor's six pairs, ranked by the engine's rule — as the real repository would."""
    projects = {p.project_id: p for p in fixture_projects()}
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
        Overlap(
            overlap_id=o.overlap_id,
            rank=rank,
            score=o.score,
            distance_mi=o.distance_mi,
            time_gap_days=o.time_gap_days,
            project_a=projects[o.project_id_a],
            project_b=projects[o.project_id_b],
        )
        for rank, o in enumerate(rank_by_score(engine_rows), start=1)
    ]


class FixtureRepository:
    """Serves fixture data, deliberately NOT in rank order, so the route must sort."""

    def __init__(self) -> None:
        self.projects = fixture_projects()
        self.overlaps = list(reversed(fixture_overlaps()))

    def list_projects(self) -> list[Project]:
        return self.projects

    def list_overlaps(self) -> list[Overlap]:
        return self.overlaps

    def get_overlap(self, overlap_id: str) -> Overlap | None:
        return next((o for o in self.overlaps if o.overlap_id == overlap_id), None)


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
