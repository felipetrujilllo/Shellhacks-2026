"""The API contract (app/schemas.py) against the seed CSV shape and docs/api.md examples."""

import csv
import json
import re
from datetime import date
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas import ErrorDetail, Health, Overlap, Project
from pipeline.load import REQUIRED_COLUMNS
from pipeline.overlap import haversine_miles, opportunity_score, time_gap_days
from pipeline.savings import estimate_savings

FIXTURES = Path(__file__).parent / "fixtures"
API_DOC = Path(__file__).parents[2] / "docs" / "api.md"

# Every docs/api.md example is tagged with one of these, mapped to the model it must satisfy.
EXAMPLE_MODELS = {
    "health": Health,
    "projects": list[Project],
    "overlaps": list[Overlap],
    "overlap": Overlap,
    "not_found": ErrorDetail,
}

EXAMPLE_BLOCK = re.compile(r"<!-- example: (\w+) -->\s*```json\n(.*?)```", re.DOTALL)


def seed_rows() -> list[dict]:
    """Raw rows exactly as csv.DictReader yields them — blanks are empty strings."""
    with open(FIXTURES / "starter_projects.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def seed_columns() -> list[str]:
    with open(FIXTURES / "starter_projects.csv", newline="", encoding="utf-8") as f:
        return next(csv.reader(f))


def doc_examples() -> dict[str, object]:
    doc = API_DOC.read_text(encoding="utf-8")
    return {tag: json.loads(body) for tag, body in EXAMPLE_BLOCK.findall(doc)}


# --- Project ------------------------------------------------------------------------------


def test_project_has_every_seed_column_plus_cost_and_confidence():
    expected = set(seed_columns()) | {"est_cost_usd", "location_confidence"}
    assert set(Project.model_fields) == expected


def test_project_requires_exactly_what_the_loader_requires():
    # Coordinates are optional except the center, matching pipeline/load.py and schema.sql.
    required = {name for name, field in Project.model_fields.items() if field.is_required()}
    assert required == set(REQUIRED_COLUMNS)
    for optional in ("lat_a", "lon_a", "lat_b", "lon_b", "name_a", "name_b", "est_cost_usd"):
        assert optional not in required


@pytest.mark.parametrize("raw", seed_rows(), ids=lambda r: r["project_id"])
def test_seed_csv_row_validates_as_project(raw):
    project = Project.model_validate(raw)

    assert project.project_id == raw["project_id"]
    assert project.lat_center == float(raw["lat_center"])
    assert project.lon_center == float(raw["lon_center"])
    assert project.in_service_date == date.fromisoformat(raw["in_service_date"])
    assert project.est_cost_usd is None
    assert project.location_confidence == "confirmed"


def test_blank_endpoint_in_seed_row_becomes_null():
    desc_1 = next(r for r in seed_rows() if r["project_id"] == "DESC_1")
    assert desc_1["lat_b"] == ""  # the fixture really has an unlocated b-side

    project = Project.model_validate(desc_1)
    assert project.name_b == "Hooks Sub"
    assert project.lat_b is None and project.lon_b is None


def test_est_cost_usd_is_optional_and_accepts_whole_dollars():
    raw = seed_rows()[0]
    assert Project.model_validate({**raw, "est_cost_usd": ""}).est_cost_usd is None
    assert Project.model_validate({**raw, "est_cost_usd": "23787423"}).est_cost_usd == 23787423


@pytest.mark.parametrize("column", ["lat_center", "lon_center"])
def test_row_missing_center_is_rejected(column):
    raw = seed_rows()[0]
    without = {k: v for k, v in raw.items() if k != column}

    with pytest.raises(ValidationError, match=column):
        Project.model_validate(without)
    with pytest.raises(ValidationError, match=column):
        Project.model_validate({**raw, column: ""})


@pytest.mark.parametrize(
    "bad_date", ["12/31/24", "2024/12/31", "Dec 31 2024", "1735603200", 1735603200, ""]
)
def test_row_with_non_iso_date_is_rejected(bad_date):
    raw = seed_rows()[0]
    with pytest.raises(ValidationError, match="in_service_date"):
        Project.model_validate({**raw, "in_service_date": bad_date})


def test_unknown_location_confidence_is_rejected():
    with pytest.raises(ValidationError, match="location_confidence"):
        Project.model_validate({**seed_rows()[0], "location_confidence": "maybe"})


# --- Overlap ------------------------------------------------------------------------------


def test_overlap_has_exactly_the_contract_fields():
    assert list(Overlap.model_fields) == [
        "overlap_id",
        "rank",
        "score",
        "distance_mi",
        "time_gap_days",
        "project_a",
        "project_b",
        "est_savings_usd",
        "savings_basis",
    ]
    assert Overlap.model_fields["project_a"].annotation is Project
    assert Overlap.model_fields["project_b"].annotation is Project


@pytest.mark.parametrize(
    ("field", "value"),
    [("rank", 0), ("score", 1.2), ("distance_mi", 25.5), ("time_gap_days", -1)],
)
def test_overlap_rejects_values_the_engine_cannot_produce(field, value):
    example = doc_examples()["overlap"]
    with pytest.raises(ValidationError, match=field):
        Overlap.model_validate({**example, field: value})


# --- docs/api.md examples -----------------------------------------------------------------


def test_doc_has_one_example_per_response():
    tags = [tag for tag, _ in EXAMPLE_BLOCK.findall(API_DOC.read_text(encoding="utf-8"))]
    assert sorted(tags) == sorted(EXAMPLE_MODELS)  # none missing, none duplicated


@pytest.mark.parametrize("tag", sorted(EXAMPLE_MODELS))
def test_doc_example_validates_against_its_model(tag):
    TypeAdapter(EXAMPLE_MODELS[tag]).validate_python(doc_examples()[tag])


def test_overlaps_example_is_ranked_rank_one_first():
    overlaps = TypeAdapter(list[Overlap]).validate_python(doc_examples()["overlaps"])

    assert [o.rank for o in overlaps] == list(range(1, len(overlaps) + 1))
    assert [o.score for o in overlaps] == sorted((o.score for o in overlaps), reverse=True)


@pytest.mark.parametrize("tag", ["overlaps", "overlap"])
def test_overlap_examples_agree_with_the_engine(tag):
    examples = doc_examples()[tag]
    for overlap in TypeAdapter(list[Overlap]).validate_python(
        examples if isinstance(examples, list) else [examples]
    ):
        a, b = overlap.project_a, overlap.project_b
        assert a.utility != b.utility
        distance = haversine_miles(a.lat_center, a.lon_center, b.lat_center, b.lon_center)
        assert round(distance, 2) == overlap.distance_mi
        assert time_gap_days(a.in_service_date, b.in_service_date) == overlap.time_gap_days
        assert opportunity_score(overlap.distance_mi, overlap.time_gap_days) == overlap.score


@pytest.mark.parametrize("tag", ["overlaps", "overlap"])
def test_overlap_example_savings_agree_with_the_estimator(tag):
    examples = doc_examples()[tag]
    for overlap in TypeAdapter(list[Overlap]).validate_python(
        examples if isinstance(examples, list) else [examples]
    ):
        a, b = overlap.project_a, overlap.project_b
        expected = estimate_savings(
            overlap, a.est_cost_usd, b.est_cost_usd, utility_a=a.utility, utility_b=b.utility
        )
        assert overlap.est_savings_usd == expected.est_savings_usd
        assert overlap.savings_basis == expected.savings_basis


@pytest.mark.parametrize(
    "text",
    [
        "GET /health",
        "GET /projects",
        "GET /overlaps",
        "GET /overlaps/{overlap_id}",
        "404",
        "def list_projects() -> list[Project]",
        "def list_overlaps() -> list[Overlap]",
        "def get_overlap(overlap_id: str) -> Overlap | None",
    ],
)
def test_doc_covers_every_endpoint_and_repository_signature(text):
    assert text in API_DOC.read_text(encoding="utf-8")
