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

Two more ways an endpoint the name matcher cannot place still gets a coordinate, both `low`:
- a manual coordinate in `data/seed/location_overrides.csv` (`LocationOverride`), for a
  substation OSM does not have at all (DESC's Okatie). Every row must cite its `source`.
- the candidate nearest the line's other end, when the name fits several far-apart OSM
  substations and one is clearly the right one (`nearest_to_other_end`; Georgia Power's
  Savannah-area GOSHEN, whose namesake near Augusta is 80+ mi from McIntosh).
A name OSM spells differently (THURMOND DAM vs "Thurmond Substation") is not handled here but
in `endpoints.ENDPOINT_OVERRIDES`, like any other irregular project name.

`build_dataset` is pure (rows, cache records and overrides in, rows out); only `main` touches
files. `summarize` turns a built dataset into the `Coverage` the CLI both prints and renders to
`docs/coverage.md`, so the report can never disagree with the printed summary.
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
from pipeline.load import optional_coordinate, parse_project_row
from pipeline.locate import Location, SubstationCache, locate_endpoint, normalize_name
from pipeline.osm_fetch import TARGETS
from pipeline.overlap import EARTH_RADIUS_MI, haversine_miles

SEED_DIR = Path(__file__).parents[2] / "data" / "seed"
DESC_CSV = SEED_DIR / "desc_projects.csv"
GPC_CSV = SEED_DIR / "gpc_projects.csv"
LOCATION_OVERRIDES_CSV = SEED_DIR / "location_overrides.csv"
OUT_CSV = SEED_DIR / "projects.csv"
COVERAGE_MD = Path(__file__).parents[2] / "docs" / "coverage.md"

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

# location_overrides.csv: one hand-placed endpoint per row. `utility` is the utility whose
# project names use `endpoint` (so DESC's Okatie never places a same-named Georgia station),
# `endpoint` is compared after locate.normalize_name, and `source` says where lat/lon come from.
OVERRIDE_COLUMNS = ("utility", "endpoint", "lat", "lon", "source")

# When an endpoint's exact name fits several far-apart OSM substations, the one nearest the
# line's other (located) end is used only if it is clearly the line's end:
# - it lies within NEAREST_MAX_MILES of the other end. Lines in this dataset with both ends
#   located run 10.7 mi at the median and 34.7 mi at the 90th percentile; a "nearest" namesake
#   farther away than that is likelier a stand-in for a station OSM lacks than the real end;
# - every other candidate is at least NEAREST_MIN_RATIO times as far from the other end.
# Real cases: GOSHEN-MCINTOSH 7.4 vs 82.1 mi and GOSHEN-KRAFT 7.9 vs 94.8 mi (>10x) resolve;
# the two Savannah-area COLEMANs, 6.7 mi apart, stay ambiguous from DEAN FOREST (2.8 vs 4.4 mi)
# and from MELDRIM (8.9 vs 15.3 mi), both under 2x.
NEAREST_MAX_MILES = 35.0
NEAREST_MIN_RATIO = 3.0

ProjectConfidence = Literal["confirmed", "low"]
ExclusionReason = Literal["no_endpoints", "ambiguous", "unlocated", "wrong_state"]

# One line per ExclusionReason, for readers of docs/coverage.md. The order is the report's.
REASON_MEANINGS: dict[str, str] = {
    "no_endpoints": "the project name holds no station name to look up at all",
    "ambiguous": "an endpoint's name fits several far-apart OSM substations, so none can be picked",
    "unlocated": "no OSM substation (and no manual override) matches any endpoint of the project",
    "wrong_state": "the only match lands more than "
                   f"{BORDER_MARGIN_MI:g} mi inside the other utility's state",
}


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


@dataclass(frozen=True)
class LocationOverride:
    """A hand-placed endpoint, one row of location_overrides.csv (see OVERRIDE_COLUMNS)."""

    utility: str
    endpoint: str
    lat: float
    lon: float
    source: str

    @property
    def key(self) -> tuple[str, str]:
        return self.utility, normalize_name(self.endpoint)

    def location(self, endpoint: str) -> Location:
        """Always `low`: a hand-entered point, however well sourced, is not an OSM match."""
        return Location(endpoint, self.lat, self.lon, "low")


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


def parse_location_overrides(rows: Iterable[Mapping[str, str]]) -> tuple[LocationOverride, ...]:
    """Validate location_overrides.csv rows; any bad row fails loud, naming the row.

    Every column is required and non-blank (a coordinate without a `source` is not
    reviewable), the utility must be one of UTILITIES, lat/lon must be real coordinates, one
    endpoint may be overridden once per utility, and the point may not land where the border
    rule would drop it (a typo, or a station of the other utility's that OSM should place).
    """
    overrides: list[LocationOverride] = []
    seen: set[tuple[str, str]] = set()
    for number, row in enumerate(rows, start=1):
        where = f"location override row {number}"
        missing = [c for c in OVERRIDE_COLUMNS if row.get(c) is None]
        if missing:
            raise DatasetError(f"{where}: missing column(s) {', '.join(missing)}")
        values = {c: row[c].strip() for c in OVERRIDE_COLUMNS}
        blank = [c for c, value in values.items() if not value]
        if blank:
            raise DatasetError(f"{where}: blank {', '.join(blank)}")
        where = f"{where} ({values['endpoint']!r})"
        if values["utility"] not in UTILITIES:
            raise DatasetError(f"{where}: unknown utility {values['utility']!r}")
        if not normalize_name(values["endpoint"]):
            raise DatasetError(f"{where}: endpoint has no station name in it")
        override = LocationOverride(
            utility=values["utility"],
            endpoint=values["endpoint"],
            lat=optional_coordinate(values, "lat", where),
            lon=optional_coordinate(values, "lon", where),
            source=values["source"],
        )
        if wrong_side_of_border(override.location(override.endpoint), override.utility):
            raise DatasetError(
                f"{where}: {override.lat}, {override.lon} is more than {BORDER_MARGIN_MI:g} mi "
                "inside the other utility's state"
            )
        if override.key in seen:
            raise DatasetError(f"{where}: a second override for the same endpoint")
        seen.add(override.key)
        overrides.append(override)
    return tuple(overrides)


def unused_location_overrides(
    rows: Iterable[Mapping[str, str]], overrides: Iterable[LocationOverride]
) -> list[LocationOverride]:
    """Overrides that placed no endpoint in these output rows: a typo or a renamed endpoint.

    An override always places its endpoint, so it was used exactly when some row has a located
    endpoint under its (utility, name).
    """
    placed = {
        (row["utility"], normalize_name(row[f"name_{end}"]))
        for row in rows
        for end in ("a", "b")
        if row[f"lat_{end}"]
    }
    return [override for override in overrides if override.key not in placed]


def _distance(a: Location, lat: float, lon: float) -> float:
    return haversine_miles(a.lat, a.lon, lat, lon)


def nearest_to_other_end(location: Location, other: Location) -> Location:
    """Place an endpoint with several far-apart same-named candidates by its line's other end.

    Only when `location` has no coordinate because of those candidates, every candidate is an
    exact (normalized) name match — the nearest of several fuzzy matches would stack two
    guesses — `other` is located, and the nearest candidate is clearly the one
    (NEAREST_MAX_MILES, NEAREST_MIN_RATIO). The result is `low`, nearest candidate first.
    Otherwise `location` comes back unchanged, still without a coordinate.
    """
    if location.lat is not None or len(location.candidates) < 2 or other.lat is None:
        return location
    name = normalize_name(location.endpoint)
    if any(normalize_name(c.name) != name for c in location.candidates):
        return location
    ranked = sorted(location.candidates, key=lambda c: _distance(other, c.lat, c.lon))
    nearest, runner_up = (_distance(other, c.lat, c.lon) for c in ranked[:2])
    if nearest > NEAREST_MAX_MILES or runner_up < NEAREST_MIN_RATIO * nearest:
        return location
    return replace(location, lat=ranked[0].lat, lon=ranked[0].lon, location_confidence="low",
                   candidates=tuple(ranked))


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


def _unplaced(location: Location) -> Location:
    """The endpoint stays named, with blank coordinates."""
    return replace(location, lat=None, lon=None, location_confidence="unlocated")


def _locate(
    name: str,
    utility: str,
    caches: Sequence[SubstationCache],
    overrides: Sequence[LocationOverride],
) -> Location:
    """The endpoint's manual coordinate if location_overrides.csv has one, else its OSM match."""
    key = (utility, normalize_name(name))
    for override in overrides:
        if override.key == key:
            return override.location(name)
    return locate_endpoint(name, caches)


def build_project(
    row: Mapping[str, str],
    caches: Sequence[SubstationCache],
    location_overrides: Sequence[LocationOverride] = (),
) -> dict[str, str] | ExcludedProject:
    """One located output row, or why the project cannot be placed."""
    project_id = row["project_id"].strip()
    utility = row["utility"]
    try:
        name_a, name_b = endpoints_for(project_id, row["project_name"])
    except ValueError as exc:  # split_endpoints found no station name at all
        return ExcludedProject(project_id, row["project_name"], "no_endpoints", str(exc))
    _check_stored_endpoints(row, (name_a, name_b))

    found = [
        _locate(name, utility, caches, location_overrides) for name in (name_a, name_b) if name
    ]
    if len(found) == 2:
        # An end the border rule drops cannot vouch for the other end either.
        anchors = [_unplaced(loc) if wrong_side_of_border(loc, utility) else loc for loc in found]
        found = [nearest_to_other_end(found[0], anchors[1]),
                 nearest_to_other_end(found[1], anchors[0])]
    # A nearest-candidate pick is `low`, so the border rule applies to it like any other match.
    wrong_state = [loc for loc in found if wrong_side_of_border(loc, utility)]
    # A wrong-state match places nothing.
    locations = [_unplaced(loc) if loc in wrong_state else loc for loc in found]
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
    project_rows: Iterable[Mapping[str, str]],
    caches: Iterable[SubstationCache],
    location_overrides: Iterable[LocationOverride] = (),
) -> Dataset:
    """Locate every project; keep the placeable ones (input order), list the rest."""
    rows = list(project_rows)
    caches = [list(cache) for cache in caches]
    overrides = tuple(location_overrides)
    _check_inputs(rows)

    included: list[dict[str, str]] = []
    excluded: list[ExcludedProject] = []
    for row in rows:
        result = build_project(row, caches, overrides)
        if isinstance(result, ExcludedProject):
            excluded.append(result)
        else:
            included.append(result)
    return Dataset(included, excluded)


# --- Coverage: the one summary of a build, printed and written to docs/coverage.md ---------------


@dataclass(frozen=True)
class UtilityCoverage:
    """How one utility's parsed projects came out: located (by confidence), or excluded."""

    utility: str
    parsed: int  # rows in that utility's parser CSV
    confirmed: int
    low: int
    excluded: tuple[ExcludedProject, ...]  # input (source document) order

    @property
    def located(self) -> int:
        return self.confirmed + self.low


@dataclass(frozen=True)
class Coverage:
    """A built dataset plus its per-utility split: the CLI's printed summary and the report."""

    dataset: Dataset
    utilities: tuple[UtilityCoverage, ...]  # by utility name

    @property
    def parsed(self) -> int:
        return len(self.dataset.rows) + len(self.dataset.excluded)

    @property
    def located(self) -> int:
        return len(self.dataset.rows)

    def summary_lines(self, out: Path) -> list[str]:
        """The summary the CLI prints, one line per element. Wording is load-bearing: teammates
        read it after every build, so it stays as it is."""
        dataset = self.dataset
        by_utility = Counter(row["utility"] for row in dataset.rows)
        by_confidence = Counter(row["location_confidence"] for row in dataset.rows)
        reasons = Counter(project.reason for project in dataset.excluded)
        return [
            f"wrote {len(dataset.rows)} of {self.parsed} projects to {out}",
            f"  included by utility: {dict(sorted(by_utility.items()))}",
            f"  included by confidence: {dict(sorted(by_confidence.items()))}",
            f"excluded {len(dataset.excluded)} unlocated projects: {dict(sorted(reasons.items()))}",
            *(
                f"  {project.project_id} [{project.reason}] {project.project_name} -- "
                f"{project.detail}"
                for project in dataset.excluded
            ),
        ]

    def markdown(self) -> str:
        """docs/coverage.md: the same counts as a report a judge can read, plus every exclusion.

        Deterministic by construction — no timestamps, utilities by name, reasons in
        REASON_MEANINGS order, projects in source-document order — so the committed file only
        changes when the data does.
        """
        reasons = Counter(project.reason for project in self.dataset.excluded)
        lines = [
            "# Coverage and confidence",
            "",
            "Which projects from the two utilities' published plans are on the map, and how well",
            "each one is located. Generated from the committed sources by",
            "`python -m pipeline.build_dataset`, which writes both this report and",
            "`data/seed/projects.csv`, so the two cannot disagree.",
            "",
            f"**{self.located} of {self.parsed} parsed projects are located** and load into the",
            f"database. The other {len(self.dataset.excluded)} are listed in full below, each with",
            "the endpoint that could not be placed — a project with no located endpoint has no",
            "center, so it is left out rather than guessed at.",
            "",
            "## Per utility",
            "",
            "| Utility | Parsed | Located | Confirmed | Low | Excluded |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for utility in self.utilities:
            lines.append(
                f"| {_cell(utility.utility)} | {utility.parsed} | {utility.located} | "
                f"{utility.confirmed} | {utility.low} | {len(utility.excluded)} |"
            )
        lines += [
            f"| **Total** | **{self.parsed}** | **{self.located}** | "
            f"**{sum(u.confirmed for u in self.utilities)}** | "
            f"**{sum(u.low for u in self.utilities)}** | "
            f"**{len(self.dataset.excluded)}** |",
            "",
            "- **Parsed** — projects read out of the utility's own plan document into",
            "  `data/seed/desc_projects.csv` / `gpc_projects.csv`.",
            "- **Located** — projects with a center, written to `data/seed/projects.csv`:",
            "  Parsed = Located + Excluded, per utility and overall.",
            "- **Confirmed** — every endpoint in the project's name is a unique, exact-name match",
            "  on an operator-tagged OpenStreetMap substation.",
            "- **Low** — the project has a center, but at least one endpoint is placed less",
            "  certainly: an OSM record with no `operator` tag, a hand-entered coordinate from",
            "  `data/seed/location_overrides.csv`, the same-named candidate nearest the line's",
            "  other end, or an endpoint that could not be placed at all (the center then rests",
            "  on the other end). `low` does not mean the project is in the wrong place; it means",
            "  the match is not self-evident.",
            "- **Excluded** — no endpoint could be placed, so there is nothing to map.",
            "",
            "## Why projects are excluded",
            "",
            "| Reason | Count | What it means |",
            "| --- | --- | --- |",
        ]
        for reason, meaning in REASON_MEANINGS.items():
            if reasons[reason]:
                lines.append(f"| `{reason}` | {reasons[reason]} | {_cell(meaning)} |")
        lines += ["", "## Excluded projects"]
        for utility in self.utilities:
            lines += [
                "",
                f"### {utility.utility} — {len(utility.excluded)} of {utility.parsed}",
                "",
                "| Project ID | Reason | Project | Endpoints tried |",
                "| --- | --- | --- | --- |",
            ]
            for project in utility.excluded:
                lines.append(
                    f"| `{_cell(project.project_id)}` | `{project.reason}` | "
                    f"{_cell(project.project_name)} | {_cell(project.detail)} |"
                )
        return "\n".join(lines) + "\n"


def _cell(text: str) -> str:
    """One markdown table cell: a pipe or newline in a project name must not break the row."""
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def summarize(project_rows: Iterable[Mapping[str, str]], dataset: Dataset) -> Coverage:
    """Split a built dataset by utility. `project_rows` are the same rows `build_dataset` got:
    the parsed counts come from them, not from the located output.
    """
    rows = list(project_rows)
    utility_of = {row["project_id"].strip(): row["utility"] for row in rows}
    parsed = Counter(row["utility"] for row in rows)
    confirmed: Counter[str] = Counter()
    low: Counter[str] = Counter()
    excluded: dict[str, list[ExcludedProject]] = {utility: [] for utility in parsed}
    for row in dataset.rows:
        (confirmed if row["location_confidence"] == "confirmed" else low)[row["utility"]] += 1
    for project in dataset.excluded:
        utility = utility_of.get(project.project_id)
        if utility is None:  # a dataset built from other rows: the report would be a fiction
            raise DatasetError(
                f"{project.project_id}: excluded project is not in the given project rows"
            )
        excluded[utility].append(project)
    return Coverage(
        dataset=dataset,
        utilities=tuple(
            UtilityCoverage(
                utility=utility,
                parsed=parsed[utility],
                confirmed=confirmed[utility],
                low=low[utility],
                excluded=tuple(excluded[utility]),
            )
            for utility in sorted(parsed)
        ),
    )


# --- CLI: the only part that touches files ------------------------------------------------------


def read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_caches() -> list[list[dict]]:
    missing = [str(t.cache_path) for t in TARGETS if not t.cache_path.is_file()]
    if missing:
        raise DatasetError(f"OSM caches missing (run python -m pipeline.osm_fetch): {missing}")
    return [json.loads(t.cache_path.read_text(encoding="utf-8")) for t in TARGETS]


def read_location_overrides(path: Path) -> tuple[LocationOverride, ...]:
    return parse_location_overrides(read_csv(path))


def write_csv(rows: Sequence[Mapping[str, str]], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build projects.csv and its coverage report.")
    parser.add_argument("--desc", type=Path, default=DESC_CSV, help="parse_desc output CSV")
    parser.add_argument("--gpc", type=Path, default=GPC_CSV, help="parse_gpc output CSV")
    parser.add_argument("--overrides", type=Path, default=LOCATION_OVERRIDES_CSV,
                        help="manual endpoint coordinates CSV")
    parser.add_argument("--out", type=Path, default=OUT_CSV, help="projects CSV to write")
    parser.add_argument("--coverage-out", type=Path, default=COVERAGE_MD,
                        help="coverage markdown to write")
    args = parser.parse_args()

    overrides = read_location_overrides(args.overrides)
    project_rows = read_csv(args.desc) + read_csv(args.gpc)
    dataset = build_dataset(project_rows, read_caches(), overrides)
    unused = unused_location_overrides(dataset.rows, overrides)
    if unused:
        names = ", ".join(f"{o.endpoint!r} ({o.utility})" for o in unused)
        raise DatasetError(f"{args.overrides}: override(s) match no project endpoint: {names}")
    coverage = summarize(project_rows, dataset)
    write_csv(dataset.rows, args.out)
    args.coverage_out.write_text(coverage.markdown(), encoding="utf-8")
    for line in coverage.summary_lines(args.out):
        print(line)


if __name__ == "__main__":
    main()
