"""Parse Georgia Power's planned transmission projects out of the 2025 IRP Volume 3 into a CSV.

Source: `2025 IRP Volume 3 PUBLIC DISCLOSURE.pdf` (668 pages). Two parts of it are read:

- **Table 2**, "Georgia ITS 10 Year Plan Project List" (PDF pp. 177-190): one row per project
  with its TEAMS number, need date and sponsor (GPC, GTC, SAV, MEAG, DU). Project names wrap
  over several lines there. p. 191 is Table 3, cancelled projects, and is not read.
- **Per-project sheets** (PDF pp. 214-425): the full name on one line, "Teams #" and
  "Need Date". Pages in that range without a "Teams #" line are section intros or a sheet's
  overflow, and are skipped.

The two are joined on the TEAMS number, which must pair every Table-2 row with exactly one
sheet and the other way round. The sheet wins for `project_name` and `in_service_date`: its
name is printed on one line, while Table 2 breaks names at hyphens ("230-" / "115KV"), so
the original spacing can't be recovered. The two sources disagree on 4 names (e.g. Table 2's
typo "TALLBOT") and 3 dates (e.g. TEAMS 19523: 1/1/2025 in the table, 04/25/2025 on the
sheet). `owner` is Table 2's "Project Sponsor" column; rows are in Table-2 order and
`source_page` is the page of the project's sheet. Every cost in the filing is REDACTED, so
`est_cost_usd` is blank. Run as a script to regenerate `data/seed/gpc_projects.csv`:

    python -m pipeline.parse_gpc --pdf <path to the PDF> --out ../data/seed/gpc_projects.csv

Extraction only: splitting names into substation endpoints happens when the dataset is built.
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

UTILITY = "Georgia Power"
STATE = "GA"

# 1-based PDF pages, inclusive.
TABLE_PAGES = range(177, 191)
SHEET_PAGES = range(214, 426)

# "216 2025 18492 MITCHELL - NORTH TIFTON 5/1/2025 GPC REDACTED REDACTED ..."
# zone, need year, TEAMS number, first line of the name, need date, sponsor, redacted costs.
TABLE_ROW = re.compile(
    r"^\d{3} \d{4} (?P<teams>\d+) (?P<name>.+?) (?P<date>\d{1,2}/\d{1,2}/\d{4}) "
    r"(?P<sponsor>[A-Z]+)(?: REDACTED)+$"
)
TABLE_ROW_START = re.compile(r"^\d{3} \d{4} ")
TABLE_HEADER_END = re.compile(r"^Number \d{4} Sponsor\b")
TABLE_TOTAL = re.compile(r"^Total(?: REDACTED)+$")
PAGE_FOOTER = re.compile(r"^\d{4} GA ITS Ten-Year Plan \(\d{4}-\d{4}\) Page \d+ of \d+$")
DATE_TEXT = re.compile(r"\d{1,2}/\d{1,2}/\d{4}")

# The CEII notice at the top of every sheet ends with this line; the project name follows it.
NOTICE_LAST_LINE = "employees."
SHEET_TEAMS = re.compile(r"^Teams # ?(?P<teams>.*)$")
SHEET_NEED_DATE = re.compile(
    r"^Need Date (?P<date>\d{2}/\d{2}/\d{4}) Start Date \d{2}/\d{2}/\d{4}$"
)

CSV_COLUMNS = [
    "project_id",
    "utility",
    "state",
    "project_name",
    "in_service_date",
    "owner",
    "est_cost_usd",
    "source_page",
]


class GpcParseError(ValueError):
    """A Table-2 row or project sheet did not have the layout every other one has."""


@dataclass(frozen=True)
class TableRow:
    """One project as listed in Table 2."""

    teams_id: str
    name: str
    need_date: date
    sponsor: str
    page: int


@dataclass(frozen=True)
class Sheet:
    """One per-project detail sheet."""

    teams_id: str
    name: str
    need_date: date
    page: int


@dataclass(frozen=True)
class GpcProject:
    project_id: str
    utility: str
    state: str
    project_name: str
    in_service_date: date
    owner: str
    est_cost_usd: int | None
    source_page: int


def parse_us_date(raw: str, page: int) -> date:
    try:
        return datetime.strptime(raw, "%m/%d/%Y").date()
    except ValueError as exc:
        raise GpcParseError(f"page {page}: not a M/D/YYYY date: {raw!r}") from exc


def parse_table_page(text: str, page: int) -> list[TableRow]:
    """Every Table-2 row on one page, with wrapped name lines joined back on with a space."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    header_ends = [i for i, line in enumerate(lines) if TABLE_HEADER_END.match(line)]
    if len(header_ends) != 1:
        raise GpcParseError(f"page {page}: expected one Table 2 header, found {len(header_ends)}")

    rows: list[dict] = []
    for line in lines[header_ends[0] + 1 :]:
        if PAGE_FOOTER.match(line) or TABLE_TOTAL.match(line):
            continue
        match = TABLE_ROW.match(line)
        if match:
            rows.append({**match.groupdict(), "name": match["name"].strip()})
            continue
        if TABLE_ROW_START.match(line) or "REDACTED" in line or DATE_TEXT.search(line):
            raise GpcParseError(f"page {page}: Table 2 row does not fit the layout: {line!r}")
        if not rows:
            raise GpcParseError(f"page {page}: name continuation before any row: {line!r}")
        rows[-1]["name"] += " " + line

    if not rows:
        raise GpcParseError(f"page {page}: no Table 2 rows")
    return [
        TableRow(
            teams_id=row["teams"],
            name=row["name"],
            need_date=parse_us_date(row["date"], page),
            sponsor=row["sponsor"],
            page=page,
        )
        for row in rows
    ]


def parse_sheet_page(text: str, page: int) -> Sheet | None:
    """The project sheet on this page, or None if the page is not a sheet (no "Teams #" line)."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    teams_at = [i for i, line in enumerate(lines) if SHEET_TEAMS.match(line)]
    if not teams_at:
        return None
    if len(teams_at) > 1:
        raise GpcParseError(f"page {page}: more than one 'Teams #' line")
    at = teams_at[0]

    teams_id = SHEET_TEAMS.match(lines[at])["teams"].strip()
    if not teams_id.isdigit():
        raise GpcParseError(f"page {page}: 'Teams #' is not a number: {teams_id!r}")

    if NOTICE_LAST_LINE not in lines[:at]:
        raise GpcParseError(f"page {page}: no CEII notice above the project name")
    name = " ".join(lines[lines.index(NOTICE_LAST_LINE) + 1 : at])
    if not name:
        raise GpcParseError(f"page {page}: no project name above 'Teams #'")

    need = SHEET_NEED_DATE.match(lines[at + 1]) if at + 1 < len(lines) else None
    if not need:
        raise GpcParseError(f"page {page}: no 'Need Date' line under 'Teams #'")

    return Sheet(
        teams_id=teams_id, name=name, need_date=parse_us_date(need["date"], page), page=page
    )


def join(rows: list[TableRow], sheets: list[Sheet]) -> list[GpcProject]:
    """One project per Table-2 row, taking name and date from its sheet. Unpaired = error."""
    by_teams: dict[str, Sheet] = {}
    for sheet in sheets:
        if sheet.teams_id in by_teams:
            raise GpcParseError(
                f"page {sheet.page}: Teams # {sheet.teams_id} already has a sheet on "
                f"page {by_teams[sheet.teams_id].page}"
            )
        by_teams[sheet.teams_id] = sheet

    listed: set[str] = set()
    projects = []
    for row in rows:
        if row.teams_id in listed:
            raise GpcParseError(f"page {row.page}: TEAMS {row.teams_id} is listed twice")
        listed.add(row.teams_id)
        sheet = by_teams.get(row.teams_id)
        if sheet is None:
            raise GpcParseError(
                f"page {row.page}: no project sheet for TEAMS {row.teams_id} ({row.name})"
            )
        projects.append(
            GpcProject(
                project_id=row.teams_id,
                utility=UTILITY,
                state=STATE,
                project_name=sheet.name,
                in_service_date=sheet.need_date,
                owner=row.sponsor,
                est_cost_usd=None,  # REDACTED throughout the public filing
                source_page=sheet.page,
            )
        )

    for sheet in sheets:
        if sheet.teams_id not in listed:
            raise GpcParseError(
                f"page {sheet.page}: sheet for Teams # {sheet.teams_id} is not in Table 2"
            )
    return projects


def parse_pdf(pdf_path: Path | str) -> list[GpcProject]:
    """Every Table-2 project, in Table-2 order. Reads only the table and sheet pages."""
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:

        def text(number: int) -> str:
            return pdf.pages[number - 1].extract_text() or ""

        rows = [row for number in TABLE_PAGES for row in parse_table_page(text(number), number)]
        sheets = [parse_sheet_page(text(number), number) for number in SHEET_PAGES]
    return join(rows, [sheet for sheet in sheets if sheet is not None])


def write_csv(projects: list[GpcProject], out_path: Path | str) -> None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for project in projects:
            row = asdict(project)  # csv writes the None cost as an empty cell
            row["in_service_date"] = project.in_service_date.isoformat()
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, help="path to the 2025 IRP Volume 3 PDF")
    parser.add_argument("--out", required=True, help="CSV to write")
    args = parser.parse_args()

    projects = parse_pdf(args.pdf)
    write_csv(projects, args.out)
    print(f"wrote {len(projects)} projects to {args.out}")


if __name__ == "__main__":
    main()
