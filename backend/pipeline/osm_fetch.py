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
QUERY_TIMEOUT_S = 90
# Client-side timeout is a little longer than the server-side one so Overpass reports first.
HTTP_TIMEOUT_S = QUERY_TIMEOUT_S + 30

REPO_ROOT = Path(__file__).resolve().parents[2]
INTERIM_DIR = REPO_ROOT / "data" / "interim"

# (south, west, north, east) — the order Overpass expects.
BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class UtilitySource:
    key: str
    operator_regex: str
    bbox: BBox

    @property
    def cache_path(self) -> Path:
        return INTERIM_DIR / f"osm_substations_{self.key}.json"


DESC = UtilitySource(
    key="desc",
    operator_regex=(
        "Dominion Energy|South Carolina (Electric|Gas) & (Gas|Electric)|SCE&G|SCANA"
    ),
    bbox=(32.0, -83.4, 35.25, -78.5),  # South Carolina
)
GPC = UtilitySource(
    key="gpc",
    operator_regex="Georgia Power|Savannah Electric",
    bbox=(30.35, -85.65, 35.0, -80.75),  # Georgia
)
UTILITIES = (DESC, GPC)


class OverpassError(RuntimeError):
    """Overpass could not be reached or did not answer with a usable 200 response."""


def build_query(operator_regex: str, bbox: BBox) -> str:
    """Overpass QL for every substation whose operator matches, case-insensitively, in bbox."""
    south, west, north, east = bbox
    return (
        f"[out:json][timeout:{QUERY_TIMEOUT_S}];\n"
        "(\n"
        f'  nwr["power"="substation"]["operator"~"{operator_regex}",i]\n'
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
    payload = response.json()
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


def main(endpoint: str = OVERPASS_ENDPOINT) -> None:
    with requests.Session() as session:
        for utility in UTILITIES:
            query = build_query(utility.operator_regex, utility.bbox)
            records, dropped = parse_response(fetch(query, session, endpoint))
            if not records:
                raise OverpassError(f"{utility.key}: Overpass returned no named substations")
            write_cache(records, utility.cache_path)
            print(
                f"{utility.key}: kept {len(records)} named substations, "
                f"dropped {dropped} unnamed/unlocated -> {utility.cache_path}"
            )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--endpoint", default=OVERPASS_ENDPOINT)
    main(parser.parse_args().endpoint)
