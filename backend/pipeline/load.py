"""Load the seed CSV into Tiger Data and rebuild the project_overlaps table.

This is the batch job from the plan: read projects, run the overlap engine over them, and
write both tables inside one transaction so the database is never half-loaded. Re-running it
is the supported way to refresh — it truncates first rather than trying to merge.

    python -m pipeline.load --csv ../data/seed/projects_seed.csv

That seed CSV is issue #2's deliverable and does not exist yet. Until it lands, the ten-row
sponsor starter table at tests/fixtures/starter_projects.csv is the only CSV that loads end
to end.

Reads the connection string from --database-url, else $DATABASE_URL, else DATABASE_URL in
the repo-root .env (a real environment variable always wins, so deploys need no file).
"""

from __future__ import annotations

import argparse
import csv
import math
import os
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from pipeline.overlap import Overlap, Project, detect_overlaps

SCHEMA_PATH = Path(__file__).parents[1] / "db" / "schema.sql"
ENV_PATH = Path(__file__).parents[2] / ".env"

# Degrees. A value outside these bounds is a swapped lat/lon or a bad substation match,
# not a location, and it must not reach the database.
COORDINATE_LIMITS = {"lat": 90.0, "lon": 180.0}

VALID_CONFIDENCE = ("confirmed", "low")
DEFAULT_CONFIDENCE = "confirmed"

# Georgia Power's filings redact every project cost; these all mean "no figure published".
REDACTED_MARKERS = ("redacted", "n/a", "tbd", "-")

REQUIRED_COLUMNS = (
    "project_id",
    "utility",
    "state",
    "project_name",
    "lat_center",
    "lon_center",
    "in_service_date",
)

INSERT_PROJECT = """
INSERT INTO projects (
    project_id, utility, state, project_name,
    name_a, lat_a, lon_a, name_b, lat_b, lon_b,
    lat_center, lon_center, in_service_date, est_cost_usd, location_confidence,
    geom_center, geom_line
) VALUES (
    %(project_id)s, %(utility)s, %(state)s, %(project_name)s,
    %(name_a)s, %(lat_a)s, %(lon_a)s, %(name_b)s, %(lat_b)s, %(lon_b)s,
    %(lat_center)s, %(lon_center)s, %(in_service_date)s, %(est_cost_usd)s,
    %(location_confidence)s,
    ST_SetSRID(ST_MakePoint(%(lon_center)s, %(lat_center)s), 4326),
    CASE WHEN %(draw_line)s
         THEN ST_SetSRID(
             ST_MakeLine(
                 ST_MakePoint(%(lon_a)s, %(lat_a)s),
                 ST_MakePoint(%(lon_b)s, %(lat_b)s)
             ), 4326)
    END
)
"""

INSERT_OVERLAP = """
INSERT INTO project_overlaps (
    overlap_id, project_id_a, project_id_b, distance_mi, time_gap_days, score
) VALUES (
    %(overlap_id)s, %(project_id_a)s, %(project_id_b)s,
    %(distance_mi)s, %(time_gap_days)s, %(score)s
)
"""


class LoadError(ValueError):
    """A seed row cannot be loaded, and guessing at what it meant would be worse."""


@dataclass(frozen=True)
class ProjectRow:
    """A full seed row — everything the `projects` table stores."""

    project_id: str
    utility: str
    state: str
    project_name: str
    name_a: str | None
    lat_a: float | None
    lon_a: float | None
    name_b: str | None
    lat_b: float | None
    lon_b: float | None
    lat_center: float
    lon_center: float
    in_service_date: date
    est_cost_usd: int | None
    location_confidence: str

    @property
    def has_both_endpoints(self) -> bool:
        """Only then can the map draw a line rather than a single point."""
        return None not in (self.lat_a, self.lon_a, self.lat_b, self.lon_b)


def optional_text(raw: dict, column: str) -> str | None:
    value = (raw.get(column) or "").strip()
    return value or None


def optional_coordinate(raw: dict, column: str, project_id: str) -> float | None:
    """One latitude or longitude, checked against its real-world bound.

    float() accepts "nan" and "inf", and the engine's distance gate (`distance >= 25`) is
    False for nan — so an unchecked coordinate is flagged as an overlap carrying a nan
    distance, which then trips the schema's CHECK and aborts the whole transaction. A
    finite-but-impossible value is worse: it loads silently and changes which pairs get
    flagged. Reject both here, at the boundary.
    """
    value = (raw.get(column) or "").strip()
    if not value:
        return None
    try:
        degrees = float(value)
    except ValueError as exc:
        raise LoadError(f"{project_id}: {column} is not a number: {value!r}") from exc

    limit = COORDINATE_LIMITS[column.split("_")[0]]
    if not math.isfinite(degrees) or abs(degrees) > limit:
        raise LoadError(
            f"{project_id}: {column} must be a number between -{limit:g} and {limit:g}, "
            f"got {value!r}"
        )
    return degrees


def required_coordinate(raw: dict, column: str, project_id: str) -> float:
    value = optional_coordinate(raw, column, project_id)
    if value is None:
        raise LoadError(f"{project_id}: {column} is required")
    return value


def parse_cost(raw: dict, project_id: str) -> int | None:
    """Whole dollars, or None where the utility withholds the figure.

    Georgia Power redacts every cost, so an explicit marker has to mean "unknown" rather
    than blowing up the load.
    """
    value = (raw.get("est_cost_usd") or "").strip()
    if not value or value.lower() in REDACTED_MARKERS:
        return None
    try:
        return round(float(value.lstrip("$").replace(",", "")))
    except (ValueError, OverflowError) as exc:
        raise LoadError(f"{project_id}: est_cost_usd is not an amount: {value!r}") from exc


def parse_project_row(raw: dict) -> ProjectRow:
    """Validate one CSV row at the boundary, before anything reaches the database."""
    project_id = (raw.get("project_id") or "").strip()
    if not project_id:
        raise LoadError("a row has no project_id")

    missing = [c for c in REQUIRED_COLUMNS if not (raw.get(c) or "").strip()]
    if missing:
        raise LoadError(f"{project_id}: missing required column(s) {', '.join(missing)}")

    confidence = (raw.get("location_confidence") or "").strip() or DEFAULT_CONFIDENCE
    if confidence not in VALID_CONFIDENCE:
        raise LoadError(
            f"{project_id}: location_confidence must be one of "
            f"{', '.join(VALID_CONFIDENCE)}, got {confidence!r}"
        )

    try:
        in_service = date.fromisoformat(raw["in_service_date"].strip())
    except ValueError as exc:
        raise LoadError(
            f"{project_id}: in_service_date must be ISO (YYYY-MM-DD), "
            f"got {raw['in_service_date']!r}"
        ) from exc

    return ProjectRow(
        project_id=project_id,
        utility=raw["utility"].strip(),
        state=raw["state"].strip(),
        project_name=raw["project_name"].strip(),
        name_a=optional_text(raw, "name_a"),
        lat_a=optional_coordinate(raw, "lat_a", project_id),
        lon_a=optional_coordinate(raw, "lon_a", project_id),
        name_b=optional_text(raw, "name_b"),
        lat_b=optional_coordinate(raw, "lat_b", project_id),
        lon_b=optional_coordinate(raw, "lon_b", project_id),
        lat_center=required_coordinate(raw, "lat_center", project_id),
        lon_center=required_coordinate(raw, "lon_center", project_id),
        in_service_date=in_service,
        est_cost_usd=parse_cost(raw, project_id),
        location_confidence=confidence,
    )


def read_project_csv(csv_path: Path | str) -> list[ProjectRow]:
    # utf-8-sig, not utf-8: exporting a CSV from the sponsor's xlsx in Excel prepends a BOM,
    # which would otherwise land in the first header name and read as a row with no project_id.
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = [parse_project_row(raw) for raw in csv.DictReader(f)]

    if not rows:
        raise LoadError(
            f"{csv_path} has no project rows - refusing to truncate the tables for an "
            "empty load"
        )

    seen = Counter(r.project_id for r in rows)
    duplicates = sorted(pid for pid, count in seen.items() if count > 1)
    if duplicates:
        raise LoadError(f"duplicate project_id(s) in {csv_path}: {', '.join(duplicates)}")
    return rows


def project_params(row: ProjectRow) -> dict:
    """Bind values for one `projects` insert.

    Endpoint coordinates are stored even when only one endpoint is located — losing the
    one known substation would be worse than having no line. `draw_line` is what decides
    whether a LINESTRING is built.
    """
    return {**asdict(row), "draw_line": row.has_both_endpoints}


def to_engine_project(row: ProjectRow) -> Project:
    """Narrow a seed row to what the overlap engine needs."""
    return Project(
        project_id=row.project_id,
        utility=row.utility,
        lat_center=row.lat_center,
        lon_center=row.lon_center,
        in_service_date=row.in_service_date,
    )


def apply_schema(connection) -> None:
    connection.execute(SCHEMA_PATH.read_text())


def load(connection, rows: list[ProjectRow], overlaps: list[Overlap]) -> tuple[int, int]:
    """Replace both tables. Caller owns the transaction."""
    apply_schema(connection)
    connection.execute("TRUNCATE projects CASCADE")

    for row in rows:
        connection.execute(INSERT_PROJECT, project_params(row))

    for overlap in overlaps:
        connection.execute(INSERT_OVERLAP, asdict(overlap))

    return len(rows), len(overlaps)


def main() -> None:
    # Before the parser, so $DATABASE_URL's default picks .env up. override=False keeps a
    # real exported variable authoritative - DigitalOcean sets one and ships no .env.
    load_dotenv(ENV_PATH, override=False)

    parser = argparse.ArgumentParser(description="Load seed projects and rebuild overlaps.")
    parser.add_argument("--csv", required=True, help="seed projects CSV")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="Postgres connection string (defaults to $DATABASE_URL)",
    )
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("no database URL: pass --database-url or set DATABASE_URL")

    import psycopg

    rows = read_project_csv(args.csv)
    overlaps = detect_overlaps(to_engine_project(r) for r in rows)

    with psycopg.connect(args.database_url) as connection:
        loaded, flagged = load(connection, rows, overlaps)

    print(f"loaded {loaded} projects and {flagged} overlaps")


if __name__ == "__main__":
    main()
