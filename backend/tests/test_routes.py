"""The HTTP API against docs/api.md, with the repository swapped for fixture data (no DB)."""

import csv
import logging
import time
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from app.config import Settings
from app.main import create_app
from app.repository import CONNECT_TIMEOUT_S, PublishedPlans, ranked_overlaps
from app.routes import get_repository
from app.schemas import ErrorDetail, Health, Overlap, Project, UploadedProject, Workspace
from pipeline.overlap import (
    TIER_ORDER,
    closest_approach_miles,
    coordination_tier,
    footprint,
    opportunity_score,
)
from pipeline.overlap import Overlap as EngineOverlap

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


def fixture_engine_overlaps() -> list[EngineOverlap]:
    """The sponsor's six pairs as project_overlaps stores them (unranked)."""
    return [
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


def fixture_overlaps(projects: list[Project] | None = None) -> list[Overlap]:
    """The sponsor's six pairs, ranked as the real repository ranks them.

    Built with the repository's own `ranked_overlaps`, so rank, closest_mi / tier and savings
    come from the real code path.
    """
    return ranked_overlaps(fixture_engine_overlaps(), projects or fixture_projects(), [])


# The sponsor's six pairs tier first, then by score: OVL_1 touches at Thurmond (crossing),
# OVL_2 / OVL_3 are site_logistics, the rest crews. Worked out from the fixture coordinates.
STARTER_TIER_FIRST_ORDER = ["OVL_1", "OVL_2", "OVL_3", "OVL_5", "OVL_6", "OVL_4"]
# The sponsor's reference distance and gap for each pair (tests/fixtures/starter_overlaps.csv).
REFERENCE_PAIRS = {
    row["overlap_id"]: (float(row["distance_mi"]), int(row["time_gap_days"]))
    for row in read_csv("starter_overlaps.csv")
}


def tier_first_key(overlap: Overlap) -> tuple:
    """The contract's ordering, written out independently of the engine's sort."""
    return (TIER_ORDER.index(overlap.tier), -overlap.score, overlap.distance_mi,
            overlap.overlap_id)


def expected_closest_mi(overlap: Overlap) -> float:
    """closest_mi recomputed from the two served projects with the engine's own functions."""
    shapes = [
        footprint(p.lat_a, p.lon_a, p.lat_b, p.lon_b, p.lat_center, p.lon_center)
        for p in (overlap.project_a, overlap.project_b)
    ]
    return closest_approach_miles(*shapes)


def assert_closest_and_tier_served(body: dict) -> None:
    """The raw JSON carries both fields, and they are what the engine computes for the pair."""
    assert "closest_mi" in body and "tier" in body, body["overlap_id"]
    overlap = Overlap.model_validate(body)
    assert overlap.closest_mi == expected_closest_mi(overlap), overlap.overlap_id
    assert overlap.tier == coordination_tier(overlap.closest_mi), overlap.overlap_id


class FixtureRepository:
    """Serves fixture data, deliberately NOT in rank order, so the route must sort."""

    def __init__(self, costs: dict[str, int] | None = None) -> None:
        self.projects = [
            p.model_copy(update={"est_cost_usd": (costs or {}).get(p.project_id)})
            for p in fixture_projects()
        ]
        self.overlaps = list(reversed(fixture_overlaps(self.projects)))

    def list_projects(self) -> list[Project]:
        return self.projects

    def list_overlaps(self) -> list[Overlap]:
        return self.overlaps

    def get_overlap(self, overlap_id: str) -> Overlap | None:
        return next((o for o in self.overlaps if o.overlap_id == overlap_id), None)

    def published_plans(self) -> PublishedPlans:
        return PublishedPlans(list(reversed(self.projects)), fixture_engine_overlaps())

    def sample_submissions(self) -> list[UploadedProject]:
        # None: these tests pin the sponsor's six pairs alone. The samples are tested with the
        # real repository code in test_sample_submissions.py.
        return []


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
    # Rank is tier first, then score (docs/api.md), so scores alone need not descend.
    assert overlaps == sorted(overlaps, key=tier_first_key)
    assert {o.overlap_id for o in overlaps} == {f"OVL_{n}" for n in range(1, 7)}


def test_overlaps_rank_one_is_the_contract_example(client):
    top = client.get("/overlaps").json()[0]

    # OVL_1 scores lowest of the top three, but Hooks-Thurmond and Evans-Thurmond Dam touch
    # at Thurmond, so the crossing tier puts it first.
    assert top["overlap_id"] == "OVL_1"
    assert top["project_a"]["project_id"] == "DESC_2"
    assert top["project_b"]["project_id"] == "GPC_1"
    assert (top["tier"], top["closest_mi"]) == ("crossing", 0.0)


def test_overlaps_serve_closest_mi_and_tier_on_every_pair(client):
    body = client.get("/overlaps").json()

    assert len(body) == 6
    for overlap in body:
        assert_closest_and_tier_served(overlap)
    served = {o["overlap_id"]: (o["closest_mi"], o["tier"]) for o in body}
    assert served["OVL_1"] == (0.0, "crossing")
    assert served["OVL_2"] == (2.99, "site_logistics")
    assert served["OVL_3"] == (3.39, "site_logistics")
    assert {served[i][1] for i in ("OVL_4", "OVL_5", "OVL_6")} == {"crews"}


def test_overlaps_are_ranked_tier_first_then_by_score(client):
    body = client.get("/overlaps").json()

    assert [o["overlap_id"] for o in body] == STARTER_TIER_FIRST_ORDER
    assert [o["tier"] for o in body] == [
        "crossing", "site_logistics", "site_logistics", "crews", "crews", "crews"
    ]
    # Within a tier, higher score first; across tiers the tier wins even over a higher score.
    by_id = {o["overlap_id"]: o for o in body}
    assert by_id["OVL_2"]["score"] > by_id["OVL_3"]["score"]
    assert by_id["OVL_5"]["score"] > by_id["OVL_6"]["score"] > by_id["OVL_4"]["score"]
    assert by_id["OVL_1"]["score"] < by_id["OVL_2"]["score"]
    assert by_id["OVL_1"]["rank"] == 1


def test_overlaps_keep_distance_score_and_savings_for_the_six_reference_pairs(costed_client):
    body = {o["overlap_id"]: o for o in costed_client.get("/overlaps").json()}

    assert set(body) == set(REFERENCE_PAIRS)
    for overlap_id, (distance_mi, gap_days) in REFERENCE_PAIRS.items():
        served = body[overlap_id]
        assert served["distance_mi"] == distance_mi, overlap_id
        assert served["time_gap_days"] == gap_days, overlap_id
        assert served["score"] == opportunity_score(distance_mi, gap_days), overlap_id
    # The estimator's figures from before tiers existed (see the savings tests below).
    assert body["OVL_2"]["est_savings_usd"] == 709_900
    assert body["OVL_3"]["est_savings_usd"] == 324_472
    assert all(body[i]["est_savings_usd"] is None for i in ("OVL_1", "OVL_4", "OVL_5", "OVL_6"))


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


@pytest.mark.parametrize("overlap_id", [f"OVL_{n}" for n in range(1, 7)])
def test_get_overlap_serves_closest_mi_tier_and_the_same_rank_as_the_list(client, overlap_id):
    listed = {o["overlap_id"]: o for o in client.get("/overlaps").json()}

    response = client.get(f"/overlaps/{overlap_id}")

    assert response.status_code == 200
    body = response.json()
    assert_closest_and_tier_served(body)
    assert (body["closest_mi"], body["tier"], body["rank"]) == (
        listed[overlap_id]["closest_mi"], listed[overlap_id]["tier"], listed[overlap_id]["rank"]
    )
    assert body["rank"] == STARTER_TIER_FIRST_ORDER.index(overlap_id) + 1


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


# --- POST /workspace ----------------------------------------------------------------------


def upload_row(**overrides) -> dict:
    """One upload as the browser keeps and sends it: on GPC_2's center and in-service date."""
    return {
        "project_id": "b1-1",
        "utility": "Tidewater Grid Co.",
        "state": "SC",
        "project_name": "Savannah River crossing",
        "lat_center": 32.352116,
        "lon_center": -81.175112,
        "in_service_date": "2026-06-01",
        "est_cost_usd": 2000000,
        **overrides,
    }


def post_workspace(client: TestClient, *rows: dict):
    return client.post("/workspace", json={"projects": list(rows)})


def test_an_empty_workspace_is_exactly_the_published_data(client):
    response = post_workspace(client)

    assert response.status_code == 200
    workspace = Workspace.model_validate(response.json())
    assert workspace.projects == TypeAdapter(list[Project]).validate_python(
        client.get("/projects").json()
    )
    assert workspace.overlaps == TypeAdapter(list[Overlap]).validate_python(
        client.get("/overlaps").json()
    )
    assert len(workspace.projects) == 10 and len(workspace.overlaps) == 6


def test_a_workspace_is_the_published_data_plus_the_uploads_with_their_pairs_ranked(client):
    second = upload_row(project_id="b1-2", project_name="Far line", lat_center=33.5186,
                        lon_center=-86.8104)  # Birmingham, AL: near nothing
    response = post_workspace(client, upload_row(), second)

    assert response.status_code == 200
    workspace = Workspace.model_validate(response.json())
    ids = [p.project_id for p in workspace.projects]
    assert ids[:10] == sorted(p.project_id for p in fixture_projects())
    assert ids[10:] == ["SUB-b1-1", "SUB-b1-2"]
    assert all(p.location_confidence == "low" for p in workspace.projects[10:])

    ranked = workspace.overlaps
    assert [o.rank for o in ranked] == list(range(1, len(ranked) + 1))
    assert ranked == sorted(ranked, key=tier_first_key)
    # Sitting on GPC_2's center (both without endpoints): a 0 mi, 0 day crossing pair, so it
    # takes rank 1 above every published pair, OVL_1's crossing included.
    top = ranked[0]
    assert top.overlap_id == "SUB:GPC_2|SUB-b1-1"
    assert (top.distance_mi, top.time_gap_days, top.score) == (0.0, 0, 1.0)
    assert (top.closest_mi, top.tier) == (0.0, "crossing")
    assert top.est_savings_usd == 100_000  # 5% of $2M, nothing discounted
    # DESC_3 is 5.65 mi from GPC_2, so also from the upload; still ranked among the rest.
    assert "SUB:DESC_3|SUB-b1-1" in {o.overlap_id for o in ranked}
    assert {f"OVL_{n}" for n in range(1, 7)} <= {o.overlap_id for o in ranked}
    assert not any("SUB-b1-2" in o.overlap_id for o in ranked)


def test_workspace_serves_closest_mi_and_tier_on_every_pair(client):
    response = post_workspace(client, upload_row())

    assert response.status_code == 200
    overlaps = response.json()["overlaps"]
    assert any(o["overlap_id"].startswith("SUB:") for o in overlaps)
    for overlap in overlaps:
        assert_closest_and_tier_served(overlap)


def test_an_upload_without_endpoints_gets_closest_mi_and_tier_and_is_ranked_tier_first(client):
    # 1.04 mi from GPC_2's center, no endpoints: the docs/api.md workspace example's upload.
    near = upload_row(lat_center=32.36, lon_center=-81.16, in_service_date="2026-09-01",
                      est_cost_usd=2_500_000)
    assert "lat_a" not in near and "lat_b" not in near

    ranked = Workspace.model_validate(post_workspace(client, near).json()).overlaps
    by_id = {o.overlap_id: o for o in ranked}

    pair = by_id["SUB:GPC_2|SUB-b1-1"]
    # Measured from the upload's center (the fallback), which here equals the center distance.
    assert (pair.closest_mi, pair.tier) == (1.04, "site_logistics")
    assert pair.closest_mi == pair.distance_mi
    # The best score of all, but a site_logistics pair: second, behind OVL_1's crossing.
    assert pair.score == max(o.score for o in ranked)
    assert [o.overlap_id for o in ranked[:2]] == ["OVL_1", "SUB:GPC_2|SUB-b1-1"]
    assert pair.rank == 2
    assert ranked == sorted(ranked, key=tier_first_key)
    assert [o.rank for o in ranked] == list(range(1, len(ranked) + 1))


def test_an_upload_whose_endpoints_sit_far_from_its_center_is_capped_not_a_500(client):
    # Center on GPC_2 (flagged at 0 mi), but its own A-B segment ~80 mi away: the segments
    # alone would give ~81 mi, past the 25 mi bound, which used to fail the whole response.
    far = upload_row(lat_a=33.0, lon_a=-80.0, lat_b=33.1, lon_b=-80.1)

    response = client.post("/workspace", json={"projects": [far]})

    assert response.status_code == 200
    pair = {o.overlap_id: o for o in Workspace.model_validate(response.json()).overlaps}[
        "SUB:GPC_2|SUB-b1-1"
    ]
    assert pair.distance_mi == 0.0
    assert (pair.closest_mi, pair.tier) == (0.0, "crossing")


def test_the_same_workspace_request_gets_the_same_ids_every_time(client):
    first = post_workspace(client, upload_row()).json()
    second = post_workspace(client, upload_row()).json()

    assert first == second
    assert [o["overlap_id"] for o in first["overlaps"]][0] == "SUB:GPC_2|SUB-b1-1"


def test_a_workspace_request_stores_nothing_for_anyone_else(client):
    """Uploads live in the uploader's browser: GET /projects and /overlaps never see them."""
    assert post_workspace(client, upload_row()).status_code == 200

    assert len(client.get("/projects").json()) == 10
    assert all(not p["project_id"].startswith("SUB-") for p in client.get("/projects").json())
    assert {o["overlap_id"] for o in client.get("/overlaps").json()} == {
        f"OVL_{n}" for n in range(1, 7)
    }
    assert client.get("/overlaps/SUB:GPC_2|SUB-b1-1").status_code == 404
    # ...and a second visitor with no uploads gets exactly the published data.
    assert len(post_workspace(client).json()["projects"]) == 10


def test_an_upload_matching_a_published_project_is_a_409(client, repository):
    duplicate = upload_row(
        project_id="b1-2", utility="georgia power", project_name=repository.projects[5].project_name
    )
    response = post_workspace(client, upload_row(), duplicate)

    assert response.status_code == 409
    assert "already exists" in ErrorDetail.model_validate(response.json()).detail


def test_the_same_project_twice_in_the_uploads_is_a_409(client):
    twin = upload_row(project_id="b2-1", project_name=" savannah RIVER crossing")
    response = post_workspace(client, upload_row(), twin)

    assert response.status_code == 409
    assert "appears twice" in ErrorDetail.model_validate(response.json()).detail


def test_the_same_client_id_twice_is_a_409(client):
    response = post_workspace(client, upload_row(), upload_row(project_name="Other line"))

    assert response.status_code == 409
    assert "reuses the id 'b1-1'" in ErrorDetail.model_validate(response.json()).detail


def test_a_utility_spelled_like_a_published_one_takes_its_spelling(client):
    far = upload_row(utility="  georgia POWER ", lat_center=33.5186, lon_center=-86.8104)
    [uploaded] = post_workspace(client, far).json()["projects"][10:]

    assert uploaded["utility"] == "Georgia Power"


@pytest.mark.parametrize(
    "body",
    [
        {"projects": [upload_row()] * 1001},
        {"projects": [upload_row(project_id="")]},
        {"projects": [upload_row(project_id="a|b")]},
        {"projects": [upload_row(project_id="b1:1")]},
        {"projects": [upload_row(project_id="has space")]},
        {"projects": [upload_row(project_id="x" * 65)]},
        {"projects": [upload_row(lat_center=91)]},
        {"projects": [upload_row(in_service_date="06/01/2026")]},
        {"projects": [upload_row(utility="")]},
        {"projects": [upload_row(est_cost_usd=-1)]},
        {},
        [upload_row()],
    ],
    ids=["over-1000", "empty-id", "pipe-id", "colon-id", "space-id", "id-over-64",
         "bad-latitude", "non-iso-date", "no-utility", "negative-cost", "no-projects-key",
         "bare-list"],
)
def test_an_invalid_workspace_request_is_a_422(client, body):
    assert client.post("/workspace", json=body).status_code == 422


def test_the_upload_limit_is_exactly_1000(client):
    rows = [
        upload_row(project_id=f"b-{n}", project_name=f"Line {n}", lat_center=33.5186,
                   lon_center=-86.8104)
        for n in range(1000)
    ]
    response = post_workspace(client, *rows)

    assert response.status_code == 200
    assert len(response.json()["projects"]) == 1010


def test_the_old_shared_upload_endpoint_is_gone(client):
    assert client.post("/submissions", json={"projects": [upload_row()]}).status_code == 404


# --- database unavailable -> 503 ----------------------------------------------------------

API_DOC = Path(__file__).parents[2] / "docs" / "api.md"
DB_UNAVAILABLE_BODY = {"detail": "database unavailable"}
DB_ERROR_MESSAGE = "connection to server at 10.0.0.9, port 5432 failed: password=hunter2"
DB_ROUTES = ["/projects", "/overlaps", "/overlaps/OVL_2"]


class RaisingRepository:
    """Every call fails the way the real repository does when the database is unreachable."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def list_projects(self) -> list[Project]:
        raise self.error

    def list_overlaps(self) -> list[Overlap]:
        raise self.error

    def get_overlap(self, overlap_id: str) -> Overlap | None:
        raise self.error

    def published_plans(self) -> PublishedPlans:
        raise self.error

    def sample_submissions(self) -> list[UploadedProject]:
        return []  # read from a file, not the database: never the failing part


def raising_client(error: Exception) -> TestClient:
    app = create_app(SETTINGS)
    app.dependency_overrides[get_repository] = lambda: RaisingRepository(error)
    # Let an unhandled error become the 500 a real server sends, instead of re-raising it.
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("path", DB_ROUTES)
def test_an_unreachable_database_is_a_503_with_a_clear_message(path):
    client = raising_client(psycopg.OperationalError(DB_ERROR_MESSAGE))

    response = client.get(path)

    assert response.status_code == 503
    assert response.json() == DB_UNAVAILABLE_BODY
    assert ErrorDetail.model_validate(response.json()).detail == "database unavailable"


def test_a_workspace_request_while_the_database_is_unreachable_is_a_503():
    client = raising_client(psycopg.OperationalError(DB_ERROR_MESSAGE))

    response = client.post("/workspace", json={"projects": [upload_row()]})

    assert response.status_code == 503
    assert response.json() == DB_UNAVAILABLE_BODY


def test_the_503_logs_the_cause_but_never_sends_it_to_the_client(caplog):
    client = raising_client(psycopg.OperationalError(DB_ERROR_MESSAGE))

    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = client.get("/overlaps")

    assert "hunter2" not in response.text and "10.0.0.9" not in response.text
    assert any(
        "database unavailable" in r.getMessage() and DB_ERROR_MESSAGE in r.getMessage()
        and "/overlaps" in r.getMessage()
        for r in caplog.records
    )


def test_health_stays_200_while_the_database_is_unreachable():
    client = raising_client(psycopg.OperationalError(DB_ERROR_MESSAGE))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "error",
    [RuntimeError("boom"), psycopg.errors.UndefinedTable('relation "projects" does not exist')],
    ids=["non-db-error", "query-error"],
)
@pytest.mark.parametrize("path", DB_ROUTES)
def test_other_errors_are_not_swallowed_and_stay_500(path, error):
    response = raising_client(error).get(path)

    assert response.status_code == 500
    assert "database unavailable" not in response.text


def test_other_errors_still_propagate_to_the_server():
    app = create_app(SETTINGS)
    app.dependency_overrides[get_repository] = lambda: RaisingRepository(RuntimeError("boom"))

    with pytest.raises(RuntimeError, match="boom"):
        TestClient(app).get("/overlaps")


def test_unknown_overlap_is_still_a_404_alongside_the_503_handler(client):
    response = client.get("/overlaps/OVL_99")

    assert response.status_code == 404
    assert response.json() == {"detail": "overlap OVL_99 not found"}


def test_real_repository_on_a_closed_port_is_a_503_within_the_connect_timeout():
    # Port 1 on loopback: nothing listens, and no traffic leaves the machine. On Windows a
    # refused loopback connect is retried until psycopg's connect_timeout, so this can take
    # the full CONNECT_TIMEOUT_S; the bound proves the request never hangs past it.
    settings = Settings(
        database_url="postgresql://gridwatch@127.0.0.1:1/never", frontend_origin=FRONTEND_ORIGIN
    )
    client = TestClient(create_app(settings))  # no override: the real PostgresRepository

    started = time.monotonic()
    response = client.get("/overlaps")
    elapsed = time.monotonic() - started

    assert response.status_code == 503
    assert response.json() == DB_UNAVAILABLE_BODY
    assert elapsed < CONNECT_TIMEOUT_S + 2


def test_docs_document_the_503_body_for_every_db_route():
    # The paragraph that promises the 503 (it opens with "Database unavailable").
    doc = API_DOC.read_text(encoding="utf-8")
    section = doc[doc.index("**Database unavailable.**"):doc.index("### `GET /health`")]

    assert "**503**" in section
    assert '{"detail": "database unavailable"}' in section
    for route in ("`GET /projects`", "`GET /overlaps`", "`GET /overlaps/{overlap_id}`"):
        assert route in section


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


def test_cors_preflight_allows_posting_the_workspace(client):
    response = client.options(
        "/workspace",
        headers={"Origin": FRONTEND_ORIGIN, "Access-Control-Request-Method": "POST"},
    )

    assert response.status_code == 200
    assert "POST" in response.headers["access-control-allow-methods"]
