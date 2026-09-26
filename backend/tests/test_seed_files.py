"""Seed data tests: the sponsor's starter table (Projects_Overlaps.xlsx) as two CSVs.

`data/seed/projects_seed.csv` is the slice's 10-project dataset and
`data/seed/expected_overlaps.csv` is the golden answer the overlap engine is held to.
The sponsor's source package lives under `data/source/`.
"""

import csv
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED = REPO_ROOT / "data" / "seed"
SOURCE = REPO_ROOT / "data" / "source"
FIXTURES = Path(__file__).parent / "fixtures"

PROJECTS_CSV = SEED / "projects_seed.csv"
OVERLAPS_CSV = SEED / "expected_overlaps.csv"

PROJECT_COLUMNS = [
    "project_id",
    "utility",
    "state",
    "project_name",
    "name_a",
    "lat_a",
    "lon_a",
    "name_b",
    "lat_b",
    "lon_b",
    "lat_center",
    "lon_center",
    "in_service_date",
]
OVERLAP_COLUMNS = ["overlap_id", "project_id_a", "project_id_b", "distance_mi", "time_gap_days"]
COORD_COLUMNS = ["lat_a", "lon_a", "lat_b", "lon_b", "lat_center", "lon_center"]

# Sponsor reference table (docs/prompt.md), written out as literals on purpose.
SPONSOR_OVERLAPS = [
    ("OVL_1", "DESC_2", "GPC_1", 4.09, 3074),
    ("OVL_2", "DESC_3", "GPC_2", 5.65, 152),
    ("OVL_3", "DESC_3", "GPC_3", 7.55, 517),
    ("OVL_4", "DESC_1", "GPC_1", 8.01, 3074),
    ("OVL_5", "DESC_5", "GPC_2", 14.34, 365),
    ("OVL_6", "DESC_5", "GPC_3", 14.81, 730),
]

# Plausible bounding box for SC/GA substations.
LAT_RANGE = (30.0, 36.0)
LON_RANGE = (-86.0, -78.0)


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


@pytest.fixture(scope="module")
def projects() -> list[dict[str, str]]:
    return read_csv(PROJECTS_CSV)[1]


@pytest.fixture(scope="module")
def overlaps() -> list[dict[str, str]]:
    return read_csv(OVERLAPS_CSV)[1]


# --- projects_seed.csv -------------------------------------------------------


def test_projects_seed_has_exactly_ten_rows(projects):
    assert len(projects) == 10


def test_projects_seed_header_is_the_13_columns_in_order():
    header, _ = read_csv(PROJECTS_CSV)
    assert header == PROJECT_COLUMNS


def test_projects_seed_dates_are_iso(projects):
    for row in projects:
        parsed = date.fromisoformat(row["in_service_date"])
        assert parsed.isoformat() == row["in_service_date"], row["project_id"]


def test_projects_seed_coords_are_blank_or_in_sc_ga_range(projects):
    for row in projects:
        for col in COORD_COLUMNS:
            raw = row[col]
            if raw == "":
                continue
            value = float(raw)
            lo, hi = LAT_RANGE if col.startswith("lat") else LON_RANGE
            assert lo <= value <= hi, f"{row['project_id']}.{col}={value}"


def test_projects_seed_keeps_blank_coords_blank(projects):
    by_id = {row["project_id"]: row for row in projects}
    # Sponsor sheet leaves one endpoint unlocated for these projects.
    assert by_id["DESC_1"]["lat_b"] == "" and by_id["DESC_1"]["lon_b"] == ""
    assert by_id["DESC_2"]["lat_a"] == "" and by_id["DESC_2"]["lon_a"] == ""
    assert by_id["DESC_4"]["lat_b"] == "" and by_id["DESC_4"]["lon_b"] == ""
    assert by_id["GPC_2"]["lat_b"] == "" and by_id["GPC_2"]["lon_b"] == ""


def test_projects_seed_every_row_has_a_center(projects):
    for row in projects:
        assert row["lat_center"] != "", row["project_id"]
        assert row["lon_center"] != "", row["project_id"]


def test_projects_seed_ids_are_unique(projects):
    ids = [row["project_id"] for row in projects]
    assert len(ids) == len(set(ids))


def test_projects_seed_utilities(projects):
    assert {row["utility"] for row in projects} == {
        "Dominion Energy South Carolina",
        "Georgia Power",
    }


# --- expected_overlaps.csv ---------------------------------------------------


def test_expected_overlaps_has_exactly_six_rows(overlaps):
    assert len(overlaps) == 6


def test_expected_overlaps_header_is_the_5_columns_in_order():
    header, _ = read_csv(OVERLAPS_CSV)
    assert header == OVERLAP_COLUMNS


def test_expected_overlaps_match_sponsor_reference(overlaps):
    parsed = [
        (
            row["overlap_id"],
            row["project_id_a"],
            row["project_id_b"],
            float(row["distance_mi"]),
            int(row["time_gap_days"]),
        )
        for row in overlaps
    ]
    assert parsed == SPONSOR_OVERLAPS


# --- referential integrity ---------------------------------------------------


def test_every_overlap_project_exists_in_projects_seed(projects, overlaps):
    ids = {row["project_id"] for row in projects}
    for row in overlaps:
        assert row["project_id_a"] in ids, row["overlap_id"]
        assert row["project_id_b"] in ids, row["overlap_id"]


def test_every_overlap_is_cross_utility(overlaps):
    for row in overlaps:
        assert row["project_id_a"].startswith("DESC_"), row["overlap_id"]
        assert row["project_id_b"].startswith("GPC_"), row["overlap_id"]


# --- drift guard vs. the engine's test fixtures -------------------------------


@pytest.mark.parametrize(
    ("seed", "fixture"),
    [
        (PROJECTS_CSV, FIXTURES / "starter_projects.csv"),
        (OVERLAPS_CSV, FIXTURES / "starter_overlaps.csv"),
    ],
    ids=["projects", "overlaps"],
)
def test_seed_matches_test_fixture(seed, fixture):
    assert read_csv(seed) == read_csv(fixture)


# --- sponsor source package --------------------------------------------------


@pytest.mark.parametrize(
    "relpath",
    [
        "Projects_Overlaps.xlsx",
        "Projects_Overlaps.pdf",
        "ShellHacks_Challenge_Gridlock.docx",
        "finding_real_projects_locations.pdf",
        "Project Listings/Dominion Energy/2024-2028-2million-and-above-project-descriptions.pdf",
        "Project Listings/Georgia Power/2025 IRP Volume 3 PUBLIC DISCLOSURE.pdf",
    ],
)
def test_sponsor_source_file_present(relpath):
    path = SOURCE / relpath
    assert path.is_file(), path
    assert path.stat().st_size > 0, path
