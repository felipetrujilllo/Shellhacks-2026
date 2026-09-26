"""Tests for the DESC PDF parser and the CSV it produces.

The PDF itself is not in the repo, so these run against inlined page text and the committed
`data/seed/desc_projects.csv`. The strongest check is cross-source: the five projects that also
appear in the sponsor's starter spreadsheet must carry the same in-service dates.
"""

import csv
import os
import re
from datetime import date
from pathlib import Path

import pytest

from pipeline.parse_desc import (
    DescParseError,
    parse_cost_usd,
    parse_in_service_date,
    parse_page,
    parse_pdf,
)

REPO_ROOT = Path(__file__).parents[2]
DESC_CSV = REPO_ROOT / "data" / "seed" / "desc_projects.csv"
STARTER_CSV = Path(__file__).parent / "fixtures" / "starter_projects.csv"
# #2 committed the sponsor folder, so the default is the repo copy and this test now runs
# for everyone rather than only for whoever had the PDF in their Downloads. DESC_PDF still
# overrides it.
SOURCE_PDF = Path(
    os.environ.get(
        "DESC_PDF",
        str(
            REPO_ROOT
            / "data/source/Project Listings/Dominion Energy"
            / "2024-2028-2million-and-above-project-descriptions.pdf"
        ),
    )
)

EXPECTED_PROJECT_COUNT = 44

# Verbatim `extract_text()` output for sheet 1, including its en dash and two-line title.
PAGE_ONE = """Project 1 of 44
Dominion Energy South Carolina
Planned Transmission Projects $2M and above Total
5 Year Budget
Queensboro - Ft Johnson 115 kV & Queensboro-Bayfront 115kV
(Queensboro-James Island Sect)
Project ID
6807 B
Project Description
Replace the Queensboro – Ft Johnson 115 kV Line and structures as they have reached the end of life.
Project Need
This project is required due to address end of life issues.
Project Status
In Progress
Planned In-Service Date
12/31/23
Estimated Project Cost
Previous 2024 2025 2026 2027 2028 Total*
$4,604,301 $800,000 $0 $0 $0 $0 $5,404,301
*Total Estimated Amount applied to 2024 Rate Base Calculation"""


def squashed(name: str) -> str:
    """Compare project names across sources that disagree about spaces and dash characters."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


@pytest.fixture(scope="module")
def desc_rows() -> list[dict]:
    with open(DESC_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# --- parsing one sheet --------------------------------------------------------------


def test_parses_every_field_off_a_real_sheet():
    project = parse_page(PAGE_ONE, source_page=1)

    assert project.project_id == "6807 B"
    assert project.utility == "Dominion Energy South Carolina"
    assert project.state == "SC"
    assert project.project_status == "In Progress"
    assert project.in_service_date == date(2023, 12, 31)
    assert project.est_cost_usd == 5_404_301
    assert project.source_page == 1


def test_a_title_split_across_lines_is_rejoined():
    assert parse_page(PAGE_ONE, source_page=1).project_name == (
        "Queensboro - Ft Johnson 115 kV & Queensboro-Bayfront 115kV "
        "(Queensboro-James Island Sect)"
    )


def test_description_and_need_are_captured_separately():
    project = parse_page(PAGE_ONE, source_page=1)

    assert project.project_description.startswith("Replace the Queensboro")
    assert project.project_description.endswith("end of life.")
    assert project.project_need == "This project is required due to address end of life issues."


def test_a_sheet_missing_a_label_fails_loudly():
    broken = PAGE_ONE.replace("Project Status\n", "")

    with pytest.raises(DescParseError, match="Project Status"):
        parse_page(broken, source_page=1)


# --- in-service dates ---------------------------------------------------------------


def test_two_digit_years_are_read_as_this_century():
    assert parse_in_service_date("12/31/23") == date(2023, 12, 31)


def test_four_digit_years_are_read_as_written():
    assert parse_in_service_date("12/31/2024") == date(2024, 12, 31)


def test_single_digit_months_and_days_parse():
    assert parse_in_service_date("6/1/2026") == date(2026, 6, 1)


def test_a_phased_project_takes_its_earliest_date():
    """Sheet 34 lists two phases; crews arrive for the first one."""
    raw = "10/1/2025 (phase 1) and 10/1/2026 (phase 2)"

    assert parse_in_service_date(raw) == date(2025, 10, 1)


def test_the_parser_keeps_the_phase_text_it_did_not_use():
    raw = "10/1/2025 (phase 1) and 10/1/2026 (phase 2)"
    sheet = PAGE_ONE.replace("12/31/23", raw)

    project = parse_page(sheet, source_page=34)

    assert project.in_service_date == date(2025, 10, 1)
    assert project.in_service_date_raw == raw


def test_a_field_with_no_date_is_none_rather_than_a_guess():
    assert parse_in_service_date("TBD") is None


# --- costs --------------------------------------------------------------------------


def test_cost_is_the_total_column_not_the_first_year():
    block = "Previous 2024 2025 2026 2027 2028 Total*\n$4,604,301 $800,000 $0 $0 $0 $0 $5,404,301"

    assert parse_cost_usd(block) == 5_404_301


def test_cost_table_without_the_asterisk_still_parses():
    """Sheets 14, 15 and 25 head the column 'Total' instead of 'Total*'."""
    block = "Previous 2024 2025 2026 2027 2028 Total\n$0 $1,000 $0 $0 $0 $0 $7,800,000"

    assert parse_cost_usd(block) == 7_800_000


def test_a_cost_table_with_no_figures_fails_loudly():
    with pytest.raises(DescParseError):
        parse_cost_usd("Previous 2024 2025 2026 2027 2028 Total*")


# --- the committed CSV --------------------------------------------------------------


def test_csv_has_every_project_sheet(desc_rows):
    assert len(desc_rows) == EXPECTED_PROJECT_COUNT


def test_every_row_has_an_id_name_and_cost(desc_rows):
    for row in desc_rows:
        assert row["project_id"]
        assert row["project_name"]
        assert int(row["est_cost_usd"]) > 0


def test_every_row_has_a_usable_in_service_date(desc_rows):
    for row in desc_rows:
        assert date.fromisoformat(row["in_service_date"])


def test_the_raw_date_text_is_kept_alongside_the_parsed_one(desc_rows):
    phased = [r for r in desc_rows if "phase" in r["in_service_date_raw"]]

    assert len(phased) == 1
    assert phased[0]["in_service_date"] == "2025-10-01"
    assert "10/1/2026" in phased[0]["in_service_date_raw"]


def test_every_row_is_attributed_to_dominion(desc_rows):
    assert {r["utility"] for r in desc_rows} == {"Dominion Energy South Carolina"}
    assert {r["state"] for r in desc_rows} == {"SC"}


def test_rows_stay_in_page_order(desc_rows):
    assert [int(r["source_page"]) for r in desc_rows] == list(
        range(1, EXPECTED_PROJECT_COUNT + 1)
    )


# --- cross-source validation --------------------------------------------------------


def test_dates_agree_with_the_sponsors_starter_table(desc_rows):
    """Five sheets also appear in Projects_Overlaps.xlsx — the two sources must not disagree."""
    with open(STARTER_CSV, newline="", encoding="utf-8") as f:
        starter = [r for r in csv.DictReader(f) if r["project_id"].startswith("DESC_")]
    assert len(starter) == 5

    by_name = {squashed(r["project_name"]): r for r in desc_rows}
    for expected in starter:
        match = by_name.get(squashed(expected["project_name"]))
        assert match is not None, f"{expected['project_id']} not found in the parsed PDF"
        assert match["in_service_date"] == expected["in_service_date"], expected["project_id"]


def test_starter_table_names_are_unambiguous_in_the_pdf(desc_rows):
    """Two sheets share the Stevens Creek - Hooks stem, so matching must not be fuzzy."""
    names = [squashed(r["project_name"]) for r in desc_rows]

    assert len(names) == len(set(names))


# --- the real PDF, when it is on this machine ---------------------------------------


@pytest.mark.skipif(not SOURCE_PDF.exists(), reason="sponsor PDF is not in the repo")
def test_parsing_the_real_pdf_reproduces_the_committed_csv(desc_rows):
    parsed = parse_pdf(SOURCE_PDF)

    assert len(parsed) == EXPECTED_PROJECT_COUNT
    assert [p.project_id for p in parsed] == [r["project_id"] for r in desc_rows]
    assert [p.project_name for p in parsed] == [r["project_name"] for r in desc_rows]
    assert [p.in_service_date.isoformat() for p in parsed] == [
        r["in_service_date"] for r in desc_rows
    ]
    assert [p.in_service_date_raw for p in parsed] == [r["in_service_date_raw"] for r in desc_rows]
    assert [p.est_cost_usd for p in parsed] == [int(r["est_cost_usd"]) for r in desc_rows]
