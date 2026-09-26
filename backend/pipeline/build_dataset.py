"""Build the full located dataset: every DESC and Georgia Power project that can be placed.

    python -m pipeline.build_dataset            # from backend/, writes data/seed/projects.csv

Per project: split the name into its end substations (`endpoints.endpoints_for`), locate each
one in the committed OSM caches (`locate.locate_endpoint`), and take the center
(`centers.project_center`). A project with no located endpoint cannot go on the map, so it is
left out and listed with the reason instead of being guessed at.

The output has the sponsor's `projects_seed.csv` columns plus `est_cost_usd` and
`location_confidence`, so `pipeline.load` loads it unchanged. `projects_seed.csv` stays the
golden-test fixture; this file is what the demo database serves.

A match that isn't `confirmed` is also dropped when it lands well inside the other utility's
state (see `wrong_side_of_border`): the sponsor guide's "similarly named substation in the wrong
area" trap. Georgia Power's Atlanta-area BUZZARD ROOST otherwise lands on "Buzzard Roost Dam
Substation" on Lake Greenwood, SC, and pairs four Atlanta projects with a DESC line 23 mi away.

`build_dataset` is pure (rows and cache records in, rows out); only `main` touches files.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from itertools import pairwise
from pathlib import Path
from typing import Literal

from pipeline import parse_desc, parse_gpc
from pipeline.centers import project_center
from pipeline.endpoints import endpoints_for
from pipeline.load import parse_project_row
from pipeline.locate import Location, SubstationCache, locate_endpoint
from pipeline.osm_fetch import TARGETS
from pipeline.overlap import EARTH_RADIUS_MI

SEED_DIR = Path(__file__).parents[2] / "data" / "seed"
DESC_CSV = SEED_DIR / "desc_projects.csv"
GPC_CSV = SEED_DIR / "gpc_projects.csv"
OUT_CSV = SEED_DIR / "projects.csv"

UTILITIES = (parse_desc.UTILITY, parse_gpc.UTILITY)

# Columns every parser CSV must have. name_a/name_b are optional: when present (DESC) they are
# checked against endpoints_for rather than trusted, so the two can never silently diverge.
INPUT_COLUMNS = (
    "project_id",
    "utility",
    "state",
    "project_name",
    "in_service_date",
    "est_cost_usd",
)

# projects_seed.csv's columns, then the two the loader, DB and API add.
OUTPUT_COLUMNS = (
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
    "est_cost_usd",
    "location_confidence",
)

# The Georgia–South Carolina line: the Savannah River from the coast, then the Tugaloo and
# Chattooga up to the North Carolina corner. Rough (lat, lon) points along it, south to north.
# It only has to tell a point well inside one state from one well inside the other, so the
# check allows BORDER_MARGIN_MI either way and a few miles of error here cannot matter.
GA_SC_BORDER = (
    (32.03, -80.85),  # river mouth, Tybee
    (32.08, -81.09),  # Savannah
    (32.36, -81.16),  # McIntosh (GA bank) / Jasper (SC)
    (32.70, -81.42),
    (33.00, -81.50),
    (33.20, -81.73),
    (33.47, -81.97),  # Augusta
    (33.66, -82.20),  # Thurmond (Clarks Hill) dam
    (34.03, -82.59),  # Russell dam
    (34.36, -82.82),  # Hartwell dam
    (34.60, -83.25),  # Tugaloo
    (35.00, -83.11),  # NC corner
)
BORDER_MARGIN_MI = 10.0
MILES_PER_DEGREE = EARTH_RADIUS_MI * math.pi / 180
# Which side of the line each utility's own substations are on: +1 east (SC), -1 west (GA).
HOME_SIDE = {parse_desc.UTILITY: 1, parse_gpc.UTILITY: -1}

ProjectConfidence = Literal["confirmed", "low"]
ExclusionReason = Literal["no_endpoints", "ambiguous", "unlocated", "wrong_state"]


class DatasetError(ValueError):
    """The parser CSVs are not in a state the dataset can be built from."""


@dataclass(frozen=True)
class ExcludedProject:
    project_id: str
    project_name: str
    reason: ExclusionReason
    detail: str


@dataclass(frozen=True)
class Dataset:
    rows: list[dict[str, str]]  # OUTPUT_COLUMNS, as written to projects.csv
    excluded: list[ExcludedProject]


def project_confidence(locations: Sequence[Location]) -> ProjectConfidence | None:
    """Project-level confidence from its endpoints' (the DB only stores confirmed|low).

    - confirmed: every endpoint the name yields (one for a single-site job, two for a line)
      is `confirmed`, so the center rests only on unique, operator-tagged exact matches;
    - low: at least one endpoint has coordinates, but not all are confirmed — one end
      missing or ambiguous, or a fuzzy / untagged / multi-yard match;
    - None: no endpoint has coordinates, so the project cannot be placed and is excluded.
    """
    if not any(loc.lat is not None for loc in locations):
        return None
    if all(loc.location_confidence == "confirmed" for loc in locations):
        return "confirmed"
    return "low"


def miles_east_of_ga_sc_border(lat: float, lon: float) -> float | None:
    """East-west distance from the GA-SC line at this latitude: positive in SC, negative in GA.

    None outside the latitudes the line spans, where there is no GA/SC question to answer.
    """
    for (lat1, lon1), (lat2, lon2) in pairwise(GA_SC_BORDER):
        if lat1 <= lat <= lat2:
            border_lon = lon1 + (lon2 - lon1) * (lat - lat1) / (lat2 - lat1)
            return (lon - border_lon) * MILES_PER_DEGREE * math.cos(math.radians(lat))
    return None


def wrong_side_of_border(location: Location, utility: str) -> bool:
    """A match that isn't `confirmed` and lands more than BORDER_MARGIN_MI into the other state.

    `confirmed` (a unique exact name on an operator-tagged record) is trusted across the line:
    DESC's "Thurmond Sub" really is Georgia Power's Thurmond substation on the GA bank.
    """
    if location.lat is None or location.lon is None or location.location_confidence == "confirmed":
        return False
    east = miles_east_of_ga_sc_border(location.lat, location.lon)
    return east is not None and east * HOME_SIDE[utility] < -BORDER_MARGIN_MI


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


def _coordinate(value: float | None, places: int) -> str:
    return "" if value is None else repr(round(value, places))


def _check_inputs(rows: Sequence[Mapping[str, str]]) -> None:
    for row in rows:
        project_id = (row.get("project_id") or "").strip() or "<no project_id>"
        missing = [c for c in INPUT_COLUMNS if c not in row]
        if missing:
            raise DatasetError(f"{project_id}: missing column(s) {', '.join(missing)}")
        if row["utility"] not in UTILITIES:
            raise DatasetError(f"{project_id}: unknown utility {row['utility']!r}")
    counts = Counter(row["project_id"].strip() for row in rows)
    duplicates = sorted(pid for pid, count in counts.items() if count > 1)
    if duplicates:
        raise DatasetError(f"duplicate project_id(s): {', '.join(duplicates)}")


def _check_stored_endpoints(row: Mapping[str, str], names: tuple[str, str | None]) -> None:
    """A CSV that already carries name_a/name_b (DESC) must agree with endpoints_for."""
    if "name_a" not in row and "name_b" not in row:
        return
    stored = ((row.get("name_a") or "").strip(), (row.get("name_b") or "").strip() or None)
    if stored != names:
        raise DatasetError(
            f"{row['project_id'].strip()}: CSV endpoints {stored} differ from endpoints_for "
            f"{names}; re-run the parser so the CSV matches pipeline.endpoints"
        )


def _exclusion(
    row: Mapping[str, str], locations: Sequence[Location], wrong_state: Sequence[Location]
) -> ExcludedProject:
    def why(loc: Location) -> str:
        if loc in wrong_state:
            return f"{loc.endpoint!r}: only match {loc.candidates[0].name!r} is in the other state"
        if loc.candidates:
            return f"{loc.endpoint!r}: {len(loc.candidates)} far-apart candidates"
        return f"{loc.endpoint!r}: no OSM substation"

    reason: ExclusionReason = (
        "wrong_state" if wrong_state
        else "ambiguous" if any(loc.candidates for loc in locations)
        else "unlocated"
    )
    detail = "; ".join(why(loc) for loc in locations)
    return ExcludedProject(row["project_id"].strip(), row["project_name"], reason, detail)


def build_project(
    row: Mapping[str, str], caches: Sequence[SubstationCache]
) -> dict[str, str] | ExcludedProject:
    """One located output row, or why the project cannot be placed."""
    project_id = row["project_id"].strip()
    try:
        name_a, name_b = endpoints_for(project_id, row["project_name"])
    except ValueError as exc:  # split_endpoints found no station name at all
        return ExcludedProject(project_id, row["project_name"], "no_endpoints", str(exc))
    _check_stored_endpoints(row, (name_a, name_b))

    found = [locate_endpoint(name, caches) for name in (name_a, name_b) if name]
    wrong_state = [loc for loc in found if wrong_side_of_border(loc, row["utility"])]
    # A wrong-state match places nothing; the endpoint stays named, with blank coordinates.
    locations = [
        replace(loc, lat=None, lon=None, location_confidence="unlocated") if loc in wrong_state
        else loc
        for loc in found
    ]
    confidence = project_confidence(locations)
    if confidence is None:
        return _exclusion(row, found, wrong_state)

    # Six decimals (~0.1 m), as in the sponsor's table; the center is computed from the
    # rounded endpoints so the CSV's center is exactly their average.
    points = [(_round(loc.lat), _round(loc.lon)) for loc in locations]
    (lat_a, lon_a), (lat_b, lon_b) = points[0], (points[1] if name_b else (None, None))
    lat_center, lon_center = project_center(lat_a, lon_a, lat_b, lon_b)

    out = {
        "project_id": project_id,
        "utility": row["utility"],
        "state": row["state"].strip(),
        "project_name": row["project_name"].strip(),
        "name_a": name_a,
        "lat_a": _coordinate(lat_a, 6),
        "lon_a": _coordinate(lon_a, 6),
        "name_b": name_b or "",
        "lat_b": _coordinate(lat_b, 6),
        "lon_b": _coordinate(lon_b, 6),
        "lat_center": _coordinate(lat_center, 7),
        "lon_center": _coordinate(lon_center, 7),
        "in_service_date": row["in_service_date"].strip(),
        "est_cost_usd": (row["est_cost_usd"] or "").strip(),
        "location_confidence": confidence,
    }
    parse_project_row(out)  # Fail here, not at load time, on anything the loader rejects.
    return out


def build_dataset(
    project_rows: Iterable[Mapping[str, str]], caches: Iterable[SubstationCache]
) -> Dataset:
    """Locate every project; keep the placeable ones (input order), list the rest."""
    rows = list(project_rows)
    caches = [list(cache) for cache in caches]
    _check_inputs(rows)

    included: list[dict[str, str]] = []
    excluded: list[ExcludedProject] = []
    for row in rows:
        result = build_project(row, caches)
        if isinstance(result, ExcludedProject):
            excluded.append(result)
        else:
            included.append(result)
    return Dataset(included, excluded)


# --- CLI: the only part that touches files ------------------------------------------------------


def read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_caches() -> list[list[dict]]:
    missing = [str(t.cache_path) for t in TARGETS if not t.cache_path.is_file()]
    if missing:
        raise DatasetError(f"OSM caches missing (run python -m pipeline.osm_fetch): {missing}")
    return [json.loads(t.cache_path.read_text(encoding="utf-8")) for t in TARGETS]


def write_csv(rows: Sequence[Mapping[str, str]], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build data/seed/projects.csv.")
    parser.add_argument("--desc", type=Path, default=DESC_CSV, help="parse_desc output CSV")
    parser.add_argument("--gpc", type=Path, default=GPC_CSV, help="parse_gpc output CSV")
    parser.add_argument("--out", type=Path, default=OUT_CSV, help="projects CSV to write")
    args = parser.parse_args()

    dataset = build_dataset(read_csv(args.desc) + read_csv(args.gpc), read_caches())
    write_csv(dataset.rows, args.out)

    total = len(dataset.rows) + len(dataset.excluded)
    print(f"wrote {len(dataset.rows)} of {total} projects to {args.out}")
    by_utility = Counter(row["utility"] for row in dataset.rows)
    by_confidence = Counter(row["location_confidence"] for row in dataset.rows)
    print(f"  included by utility: {dict(sorted(by_utility.items()))}")
    print(f"  included by confidence: {dict(sorted(by_confidence.items()))}")
    reasons = Counter(project.reason for project in dataset.excluded)
    print(f"excluded {len(dataset.excluded)} unlocated projects: {dict(sorted(reasons.items()))}")
    for project in dataset.excluded:
        print(f"  {project.project_id} [{project.reason}] {project.project_name} -- "
              f"{project.detail}")


if __name__ == "__main__":
    main()
