"""Tests for the Georgia Power IRP Volume 3 parser and the CSV it produces.

Layout rules run against inlined page text; the committed `data/seed/gpc_projects.csv` is
checked against the sponsor's starter table, and the last test re-parses the committed PDF
(its table and sheet pages only) and requires the same rows back.
"""

import csv
import os
from datetime import date
from pathlib import Path

import pytest

from pipeline.parse_gpc import (
    CSV_COLUMNS,
    GpcParseError,
    Sheet,
    TableRow,
    join,
    parse_pdf,
    parse_sheet_page,
    parse_table_page,
    write_csv,
)

REPO_ROOT = Path(__file__).parents[2]
GPC_CSV = REPO_ROOT / "data" / "seed" / "gpc_projects.csv"
SPONSOR_SEED_CSV = REPO_ROOT / "data" / "seed" / "projects_seed.csv"
SOURCE_PDF = Path(
    os.environ.get(
        "GPC_PDF",
        str(
            REPO_ROOT
            / "data/source/Project Listings/Georgia Power"
            / "2025 IRP Volume 3 PUBLIC DISCLOSURE.pdf"
        ),
    )
)

EXPECTED_PROJECT_COUNT = 208

# The sponsor's five GPC projects, by name, with the Teams # and need date the filing gives.
SPONSOR_PROJECTS = {
    "EVANS PRIMARY - THURMOND DAM (USA) #5 115KV REBUILD": ("20793", "2033-06-01"),
    "SAV: MCINTOSH - PURRYSBURG 230KV REACTORS": ("20277", "2026-06-01"),
    "SAV: GOSHEN (SAV) - MCINTOSH 115KV LINE REBUILD": ("20065", "2027-06-01"),
    "MITCHELL - NORTH TIFTON 230KV RECONDUCTOR": ("18492", "2025-05-01"),
    "JESUP - LUDOWICI PRIMARY 115KV REBUILD": ("11821", "2025-06-01"),
}

NOTICE = """PUBLIC DISCLOSURE
CRITICAL ENERGY INFRASTRUCTURE INFORMATION - CONFIDENTIAL. This data is confidential CEII and is subject to Regulation by CFR Sec. 388.113. Recipient should
be aware that disclosure of this material and its contents shall be handled in accordance with CEII procedures. Any and all duplications of this data must contain this
notification. This document contains non-public transmission information and in accordance with FERC policy, should not be disclosed to Marketing Function
employees."""  # noqa: E501

# Excerpt of `extract_text()` for PDF p. 177 (Table 2), CRLF line endings as on Windows.
TABLE_PAGE = "\r\n".join(
    [
        "PUBLIC DISCLOSURE",
        "Table 2 Georgia ITS 10 Year Plan Project List",
        "TEAMS Need Date Project Estimated Cost - Estimated Cost -",
        "Zone Year Project Name Estimated Cost - GPC Estimated Cost - GTC Totals",
        "Number 2024 Sponsor MEAG DU",
        "219 2025 19523 SAV: CC - HYUNDAI MOTORS 1/1/2025 SAV REDACTED REDACTED REDACTED "
        "REDACTED REDACTED",
        "SAVANNAH AKA. PROJECT EA",
        "216 2025 18492 MITCHELL - NORTH TIFTON 5/1/2025 GPC REDACTED REDACTED REDACTED "
        "REDACTED REDACTED",
        "230KV RECONDUCTOR",
        "214 2025 20466 SMART VALVE INSTALLATION 6/1/2025 GPC REDACTED REDACTED REDACTED "
        "REDACTED REDACTED",
        "2024 GA ITS Ten-Year Plan (2025-2034) Page 7 of 304",
    ]
)

# Excerpt of `extract_text()` for PDF p. 233, the Mitchell sheet.
SHEET_PAGE = (
    NOTICE
    + """
MITCHELL - NORTH TIFTON 230KV RECONDUCTOR
Teams # 18492
Need Date 05/01/2025 Start Date 12/31/2021
Description
Rebuild 35.21 miles of the Mitchell - North Tifton 230kV line from 100C 795 ACSR to 100C 1351
ACSR.
Supporting Statement
REDACTED
Estimated Cost – GPC REDACTED
2024 GA ITS Ten-Year Plan (2025-2034) Page 63 of 304"""
)

SECTION_INTRO_PAGE = (
    NOTICE
    + """
B. Stability Project Details
The following group of projects are the result of the Stability studies conducted as needed.
2024 GA ITS Ten-Year Plan (2025-2034) Page 43 of 304"""
)


def table_row(teams_id: str, page: int = 177) -> TableRow:
    return TableRow(teams_id, f"TABLE NAME {teams_id}", date(2025, 1, 1), "GPC", page)


def sheet(teams_id: str, page: int = 233) -> Sheet:
    return Sheet(teams_id, f"SHEET NAME {teams_id}", date(2025, 4, 25), page)


@pytest.fixture(scope="module")
def gpc_rows() -> list[dict]:
    with open(GPC_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# --- Table 2 --------------------------------------------------------------------------


def test_table_rows_carry_teams_number_date_and_sponsor():
    rows = parse_table_page(TABLE_PAGE, page=177)

    assert [r.teams_id for r in rows] == ["19523", "18492", "20466"]
    assert [r.sponsor for r in rows] == ["SAV", "GPC", "GPC"]
    assert rows[1].need_date == date(2025, 5, 1)
    assert {r.page for r in rows} == {177}


def test_wrapped_table_names_are_rejoined():
    rows = parse_table_page(TABLE_PAGE, page=177)

    assert rows[0].name == "SAV: CC - HYUNDAI MOTORS SAVANNAH AKA. PROJECT EA"
    assert rows[1].name == "MITCHELL - NORTH TIFTON 230KV RECONDUCTOR"
    assert rows[2].name == "SMART VALVE INSTALLATION"


def test_a_table_row_that_does_not_fit_fails_naming_the_page():
    broken = TABLE_PAGE.replace("5/1/2025 GPC", "GPC")  # need date missing

    with pytest.raises(GpcParseError, match="page 180"):
        parse_table_page(broken, page=180)


def test_a_table_row_with_a_real_cost_fails_rather_than_being_misread():
    broken = TABLE_PAGE.replace("6/1/2025 GPC REDACTED", "6/1/2025 GPC $1,000")

    with pytest.raises(GpcParseError, match="page 177"):
        parse_table_page(broken, page=177)


def test_a_table_page_without_its_header_fails_naming_the_page():
    with pytest.raises(GpcParseError, match="page 185.*header"):
        parse_table_page(TABLE_PAGE.replace("Number 2024 Sponsor MEAG DU", ""), page=185)


def test_a_name_fragment_before_any_row_fails_naming_the_page():
    orphan = TABLE_PAGE.replace("MEAG DU", "MEAG DU\r\nORPHANED 115KV LINE")

    with pytest.raises(GpcParseError, match="page 178"):
        parse_table_page(orphan, page=178)


# --- project sheets -------------------------------------------------------------------


def test_a_sheet_gives_full_name_teams_number_and_need_date():
    parsed = parse_sheet_page(SHEET_PAGE, page=233)

    assert parsed == Sheet(
        "18492", "MITCHELL - NORTH TIFTON 230KV RECONDUCTOR", date(2025, 5, 1), 233
    )


def test_a_page_with_no_teams_number_is_not_a_sheet():
    assert parse_sheet_page(SECTION_INTRO_PAGE, page=213) is None


def test_a_sheet_without_its_need_date_fails_naming_the_page():
    broken = SHEET_PAGE.replace("Need Date 05/01/2025 Start Date 12/31/2021\n", "")

    with pytest.raises(GpcParseError, match="page 233.*Need Date"):
        parse_sheet_page(broken, page=233)


def test_a_sheet_with_a_non_numeric_teams_number_fails_naming_the_page():
    with pytest.raises(GpcParseError, match="page 240"):
        parse_sheet_page(SHEET_PAGE.replace("Teams # 18492", "Teams # TBD"), page=240)


def test_a_sheet_without_a_name_fails_naming_the_page():
    nameless = SHEET_PAGE.replace("MITCHELL - NORTH TIFTON 230KV RECONDUCTOR\n", "")

    with pytest.raises(GpcParseError, match="page 233.*name"):
        parse_sheet_page(nameless, page=233)


# --- joining Table 2 to the sheets ----------------------------------------------------


def test_the_sheet_wins_for_name_and_date_and_the_table_for_owner():
    [project] = join([table_row("19523")], [sheet("19523", page=231)])

    assert project.project_id == "19523"
    assert project.project_name == "SHEET NAME 19523"
    assert project.in_service_date == date(2025, 4, 25)
    assert project.owner == "GPC"
    assert project.source_page == 231
    assert project.est_cost_usd is None


def test_a_table_row_without_a_sheet_fails_naming_its_table_page():
    with pytest.raises(GpcParseError, match="page 183.*20001"):
        join([table_row("1"), table_row("20001", page=183)], [sheet("1")])


def test_a_sheet_missing_from_table_2_fails_naming_its_page():
    with pytest.raises(GpcParseError, match="page 302.*20002"):
        join([table_row("1")], [sheet("1"), sheet("20002", page=302)])


def test_two_sheets_for_one_teams_number_fail_naming_the_page():
    with pytest.raises(GpcParseError, match="page 250"):
        join([table_row("1")], [sheet("1", page=249), sheet("1", page=250)])


def test_a_project_listed_twice_in_table_2_fails_naming_the_page():
    with pytest.raises(GpcParseError, match="page 181"):
        join([table_row("1"), table_row("1", page=181)], [sheet("1")])


# --- the committed CSV ----------------------------------------------------------------


def test_csv_has_the_ticket_columns(gpc_rows):
    with open(GPC_CSV, newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))

    assert header == [
        "project_id",
        "utility",
        "state",
        "project_name",
        "in_service_date",
        "owner",
        "est_cost_usd",
        "source_page",
    ]
    assert header == CSV_COLUMNS


def test_every_row_is_georgia_power_in_georgia(gpc_rows):
    assert {r["utility"] for r in gpc_rows} == {"Georgia Power"}
    assert {r["state"] for r in gpc_rows} == {"GA"}


def test_csv_has_every_table_2_project_once(gpc_rows):
    ids = [r["project_id"] for r in gpc_rows]

    assert len(ids) == EXPECTED_PROJECT_COUNT
    assert len(set(ids)) == len(ids)
    assert all(i.isdigit() for i in ids)  # Teams numbers


def test_every_row_has_a_name_an_iso_date_and_a_sheet_page(gpc_rows):
    for row in gpc_rows:
        assert row["project_name"]
        assert date.fromisoformat(row["in_service_date"])
        assert 214 <= int(row["source_page"]) <= 425


def test_est_cost_is_blank_on_every_row(gpc_rows):
    """Every cost in the public filing is REDACTED."""
    assert {r["est_cost_usd"] for r in gpc_rows} == {""}


def test_other_sponsors_projects_are_kept_and_tagged_by_owner(gpc_rows):
    owners = {r["owner"] for r in gpc_rows}

    assert {"GPC", "SAV", "GTC"} <= owners
    assert owners <= {"GPC", "SAV", "GTC", "MEAG", "DU"}
    for row in gpc_rows:
        if row["project_name"].startswith(("GTC: ", "SAV: ", "MEAG: ")):
            assert row["project_name"].startswith(row["owner"] + ": "), row["project_id"]


def test_the_sponsors_gpc_projects_match_by_name_teams_number_and_date(gpc_rows):
    by_name = {r["project_name"]: r for r in gpc_rows}
    for name, (teams_id, in_service) in SPONSOR_PROJECTS.items():
        assert name in by_name, name
        assert by_name[name]["project_id"] == teams_id, name
        assert by_name[name]["in_service_date"] == in_service, name


def test_the_sponsor_seed_names_and_dates_are_the_ones_checked(gpc_rows):
    """Guard against SPONSOR_PROJECTS drifting from `projects_seed.csv` (GPC_1..GPC_5)."""
    with open(SPONSOR_SEED_CSV, newline="", encoding="utf-8") as f:
        seed = {
            r["project_name"]: r["in_service_date"]
            for r in csv.DictReader(f)
            if r["project_id"].startswith("GPC_")
        }

    assert seed == {name: in_service for name, (_, in_service) in SPONSOR_PROJECTS.items()}


def test_the_wrapped_mitchell_name_is_whole_in_the_csv(gpc_rows):
    [mitchell] = [r for r in gpc_rows if r["project_id"] == "18492"]

    assert mitchell["project_name"] == "MITCHELL - NORTH TIFTON 230KV RECONDUCTOR"


# --- the real PDF ---------------------------------------------------------------------


def test_parsing_the_real_pdf_reproduces_the_committed_csv(gpc_rows, tmp_path):
    """Reads only the Table 2 and sheet pages (177-425) of the committed PDF."""
    out = tmp_path / "gpc_projects.csv"
    write_csv(parse_pdf(SOURCE_PDF), out)

    with open(out, newline="", encoding="utf-8") as f:
        assert list(csv.DictReader(f)) == gpc_rows
