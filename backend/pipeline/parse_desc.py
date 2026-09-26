"""Parse Dominion Energy South Carolina's planned-transmission PDF into one CSV row per project.

Source: `2024-2028-2million-and-above-project-descriptions.pdf` (SCRTP), 44 one-page project
sheets with an identical field layout. Run as a script to regenerate `data/seed/desc_projects.csv`:

    python -m pipeline.parse_desc --pdf <path to the PDF> --out ../data/seed/desc_projects.csv

Extraction only — locating each project's substations against OSM is a separate step, so there
are no coordinates here.
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

UTILITY = "Dominion Energy South Carolina"
STATE = "SC"

NAME_STARTS_AFTER = "5 Year Budget"
FIELD_LABELS = (
    "Project ID",
    "Project Description",
    "Project Need",
    "Project Status",
    "Planned In-Service Date",
    "Estimated Project Cost",
)

DATE_PATTERN = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2,4})")
MONEY_PATTERN = re.compile(r"\$([\d,]+)")

CSV_COLUMNS = [
    "project_id",
    "utility",
    "state",
    "project_name",
    "project_status",
    "in_service_date",
    "in_service_date_raw",
    "est_cost_usd",
    "project_description",
    "project_need",
    "source_page",
]


class DescParseError(ValueError):
    """A project sheet did not have the layout every other sheet has."""


@dataclass(frozen=True)
class DescProject:
    project_id: str
    utility: str
    state: str
    project_name: str
    project_status: str
    in_service_date: date | None
    in_service_date_raw: str
    est_cost_usd: int
    project_description: str
    project_need: str
    source_page: int


def parse_in_service_date(raw: str) -> date | None:
    """Earliest date in the field, or None if it holds no date at all.

    One sheet is phased ("10/1/2025 (phase 1) and 10/1/2026 (phase 2)"); the earliest date is
    when crews first show up, which is what matters for coordinating with a neighbour. The
    original text is kept alongside in `in_service_date_raw` so nothing is silently dropped.
    """
    found = []
    for month, day, year in DATE_PATTERN.findall(raw):
        year_number = int(year)
        if year_number < 100:
            year_number += 2000
        found.append(date(year_number, int(month), int(day)))
    return min(found) if found else None


def parse_cost_usd(cost_block: str) -> int:
    """Total estimated cost — the last dollar figure in the per-year cost table."""
    amounts = MONEY_PATTERN.findall(cost_block)
    if not amounts:
        raise DescParseError("no dollar amounts in the estimated cost table")
    return int(amounts[-1].replace(",", ""))


def parse_page(text: str, source_page: int) -> DescProject:
    """Turn one project sheet's extracted text into a record."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    positions = {}
    for label in (NAME_STARTS_AFTER, *FIELD_LABELS):
        if label not in lines:
            raise DescParseError(f"page {source_page}: missing the {label!r} label")
        positions[label] = lines.index(label)

    def field(label: str) -> str:
        """Everything between this label and the next one, joined into a single line."""
        start = positions[label] + 1
        later = [p for p in positions.values() if p > positions[label]]
        return " ".join(lines[start : min(later)]) if later else " ".join(lines[start:])

    name = " ".join(lines[positions[NAME_STARTS_AFTER] + 1 : positions["Project ID"]])
    if not name:
        raise DescParseError(f"page {source_page}: no project name")

    raw_date = field("Planned In-Service Date")

    return DescProject(
        project_id=field("Project ID"),
        utility=UTILITY,
        state=STATE,
        project_name=name,
        project_status=field("Project Status"),
        in_service_date=parse_in_service_date(raw_date),
        in_service_date_raw=raw_date,
        est_cost_usd=parse_cost_usd(" ".join(lines[positions["Estimated Project Cost"] + 1 :])),
        project_description=field("Project Description"),
        project_need=field("Project Need"),
        source_page=source_page,
    )


def parse_pdf(pdf_path: Path | str) -> list[DescProject]:
    """Every project sheet in the PDF, in page order."""
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        return [
            parse_page(page.extract_text() or "", source_page=number)
            for number, page in enumerate(pdf.pages, start=1)
        ]


def write_csv(projects: list[DescProject], out_path: Path | str) -> None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for project in projects:
            row = asdict(project)
            parsed_date = project.in_service_date
            row["in_service_date"] = parsed_date.isoformat() if parsed_date else ""
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, help="path to the DESC project-descriptions PDF")
    parser.add_argument("--out", required=True, help="CSV to write")
    args = parser.parse_args()

    projects = parse_pdf(args.pdf)
    write_csv(projects, args.out)
    print(f"wrote {len(projects)} projects to {args.out}")


if __name__ == "__main__":
    main()
