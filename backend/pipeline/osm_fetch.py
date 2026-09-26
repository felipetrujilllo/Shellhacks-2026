"""Fetch each utility's OSM substations from Overpass once and cache them in the repo.

Follows the sponsor guide (`data/source/finding_real_projects_locations.pdf`): one query per
utility for every `power=substation` whose `operator` matches the utility, inside a bounding
box. The results are committed under `data/interim/` so the endpoint matcher and the demo never
depend on Overpass being reachable. Run manually, from `backend/`:

    python -m pipeline.osm_fetch

Only this CLI touches the network; the tests mock the HTTP session.

Query: the guide's filter unchanged (`nwr["power"="substation"]["operator"~REGEX,i](S,W,N,E)`)
but `out tags center;` instead of `out body; >; out skel qt;`, so ways and relations come back
with a single `center` point rather than their full node lists.

Operator values observed (fetched 2026-09-26, all `power=substation` in the two bboxes; most
substations — ~2,200 of ~2,800 in the SC box, ~2,400 of ~4,100 in the GA box — carry no
operator tag at all and so cannot be found by this query):
  - DESC and its predecessor: "Dominion Energy South Carolina" (19), "South Carolina Gas &
    Electric" (17, a mis-ordered SCE&G), "South Carolina Electric & Gas" (10), "Dominion
    Energy" (10, all in SC), "South Carolina Electric & Gas Company" (5), "SCE&G" (1).
    No "SCANA" tags were seen; it is in the regex in case one gets added.
  - GPC: "Georgia Power" (~1,300), "Georgia Power Company" (2), "Savannah Electric and Power
    Company" (1, merged into Georgia Power in 2006). "Southern Company" did not occur;
    "Southern Power" (Southern's generation arm, 1 unnamed site) is deliberately excluded.
  - Third parties excluded by construction: Santee Cooper, Duke Energy, Georgia Transmission
    Corporation/Cooperative, MEAG, EMCs/co-ops, municipals, "University of South Carolina".

Unnamed substations are dropped (they cannot be matched to a project endpoint by name) and the
count is printed; every cached entry therefore has a name. First run: DESC kept 53 (dropped 9),
GPC kept 763 (dropped 548).

Known gap for the matcher: DESC's tagging is thin. Of the starter-table DESC endpoints only
Bluffton is in the DESC cache; Jasper, Queensborough and Stevens Creek Dam exist in OSM but
with no operator tag (Hooks, Okatie and Ft Johnson were not found by name at all).

Third target, `UNTAGGED_SC`, exists to close that gap: every named substation in the DESC
(South Carolina) bbox with NO operator tag — filter `nwr["power"="substation"][!"operator"]
["name"](32.0,-83.4,35.25,-78.5)`, same `out tags center;` — cached as
`osm_substations_untagged_sc.json` with `operator: null`. Nothing ties these to DESC, so the
matcher must treat hits from this cache as lower-confidence. It is disjoint from the two
operator caches by construction. Kept as a third constant beside DESC/GPC so every bbox and
filter lives in one place.

Fetched 2026-09-26 from overpass.kumi.systems (overpass-api.de was returning 504): 366 named
untagged substations, 0 dropped. The script's own runs timed out on every mirror, so the
committed file was built by POSTing this same filter by hand (curl, same bbox and output) and
running the response through `parse_response` + `write_cache`. The query took ~165 s, hence
the 240 s timeout. Refresh just this cache with:

    python -m pipeline.osm_fetch --only untagged_sc --endpoint <mirror>

The bbox also covers the Georgia side of the Savannah River, so a few GA sites (e.g. McIntosh
Combined Cycle) are in it; "_sc" names the bbox, not a guarantee of the state.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import requests

OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
# Fallback when the main instance is overloaded: https://overpass.kumi.systems/api/interpreter
USER_AGENT = "GridWatch/0.1 (ShellHacks 2026 hackathon; one-off substation cache fetch)"
# The untagged-SC query takes ~165 s on a loaded public instance, so 90 was not enough.
QUERY_TIMEOUT_S = 240
# Client-side timeout is a little longer than the server-side one so Overpass reports first.
HTTP_TIMEOUT_S = QUERY_TIMEOUT_S + 30

REPO_ROOT = Path(__file__).resolve().parents[2]
INTERIM_DIR = REPO_ROOT / "data" / "interim"

# (south, west, north, east) — the order Overpass expects.
BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class FetchTarget:
    """One cache file: substations in `bbox` whose operator matches `operator_regex`.

    `operator_regex=None` selects the named substations that have no operator tag at all.
    """

    key: str
    operator_regex: str | None
    bbox: BBox

    @property
    def cache_path(self) -> Path:
        return INTERIM_DIR / f"osm_substations_{self.key}.json"


DESC = FetchTarget(
    key="desc",
    operator_regex=(
        "Dominion Energy|South Carolina (Electric|Gas) & (Gas|Electric)|SCE&G|SCANA"
    ),
    bbox=(32.0, -83.4, 35.25, -78.5),  # South Carolina
)
GPC = FetchTarget(
    key="gpc",
    operator_regex="Georgia Power|Savannah Electric",
    bbox=(30.35, -85.65, 35.0, -80.75),  # Georgia
)
UNTAGGED_SC = FetchTarget(key="untagged_sc", operator_regex=None, bbox=DESC.bbox)
# Operator-filtered caches only — each belongs to one utility.
UTILITIES = (DESC, GPC)
TARGETS = (DESC, GPC, UNTAGGED_SC)


class OverpassError(RuntimeError):
    """Overpass could not be reached or did not answer with a usable 200 response."""


def build_query(operator_regex: str | None, bbox: BBox) -> str:
    """Overpass QL for every substation in bbox whose operator matches, case-insensitively.

    With `operator_regex=None`, selects named substations that have no operator tag instead.
    """
    south, west, north, east = bbox
    if operator_regex is None:
        tag_filter = '[!"operator"]["name"]'
    else:
        tag_filter = f'["operator"~"{operator_regex}",i]'
    return (
        f"[out:json][timeout:{QUERY_TIMEOUT_S}];\n"
        "(\n"
        f'  nwr["power"="substation"]{tag_filter}\n'
        f"    ({south},{west},{north},{east});\n"
        ");\n"
        "out tags center;\n"
    )


def fetch(query: str, session: requests.Session, endpoint: str = OVERPASS_ENDPOINT) -> dict:
    """POST one query to Overpass and return the decoded JSON. Fails loud; never retries."""
    try:
        response = session.post(
            endpoint,
            data={"data": query},
            headers={"User-Agent": USER_AGENT},
            timeout=HTTP_TIMEOUT_S,
        )
    except requests.RequestException as exc:
        raise OverpassError(f"Overpass request to {endpoint} failed: {exc}") from exc
    if response.status_code != 200:
        raise OverpassError(
            f"Overpass returned HTTP {response.status_code} from {endpoint}: "
            f"{response.text[:300]}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise OverpassError(
            f"Overpass returned a non-JSON 200 body from {endpoint}: {response.text[:300]}"
        ) from exc
    # Overpass reports a server-side timeout inside a 200 response via `remark`.
    remark = payload.get("remark")
    if remark and "error" in remark.lower():
        raise OverpassError(f"Overpass reported an error: {remark}")
    return payload


def parse_response(payload: dict) -> tuple[list[dict], int]:
    """Turn an Overpass JSON response into substation records.

    Returns `(records, dropped)`: one `{osm_id, name, lat, lon, operator}` per named element
    with a location (nodes use their own lat/lon, ways and relations their `center`), sorted by
    osm_id; `dropped` counts the elements skipped for lacking a name or a location.
    """
    records = []
    dropped = 0
    for element in payload.get("elements", []):
        tags = element.get("tags") or {}
        point = element if "lat" in element else element.get("center") or {}
        name = (tags.get("name") or "").strip()
        if not name or "lat" not in point or "lon" not in point:
            dropped += 1
            continue
        records.append(
            {
                "osm_id": f"{element['type']}/{element['id']}",
                "name": name,
                "lat": float(point["lat"]),
                "lon": float(point["lon"]),
                "operator": tags.get("operator"),
            }
        )
    records.sort(key=lambda r: r["osm_id"])
    return records, dropped


def write_cache(records: Iterable[dict], path: Path) -> None:
    """Write records as stable, diff-friendly UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(list(records), ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")


def main(endpoint: str = OVERPASS_ENDPOINT, only: str | None = None) -> None:
    targets = [t for t in TARGETS if only is None or t.key == only]
    with requests.Session() as session:
        for target in targets:
            query = build_query(target.operator_regex, target.bbox)
            records, dropped = parse_response(fetch(query, session, endpoint))
            if not records:
                raise OverpassError(f"{target.key}: Overpass returned no named substations")
            write_cache(records, target.cache_path)
            print(
                f"{target.key}: kept {len(records)} named substations, "
                f"dropped {dropped} unnamed/unlocated -> {target.cache_path}"
            )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--endpoint", default=OVERPASS_ENDPOINT)
    parser.add_argument(
        "--only", choices=[t.key for t in TARGETS], help="refresh one cache instead of all"
    )
    args = parser.parse_args()
    main(args.endpoint, args.only)
