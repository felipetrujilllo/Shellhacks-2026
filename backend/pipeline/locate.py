"""Match project endpoint names to cached OSM substations, with a location confidence.

Pure functions over the substation caches written by `pipeline.osm_fetch` (#14): each cache is
a list of `{"osm_id": "node/1" | "way/1" | "relation/1", "name", "lat", "lon", "operator"}`
records, every one already a named `power=substation`. No file access or network happens here;
the caller loads the JSON and passes every cache it wants searched — in practice all three of
`osm_fetch.TARGETS` (DESC, GPC and the operator-less `untagged_sc`), because border projects
end at the other utility's substations and many DESC substations carry no operator tag in OSM.

Rules, in order:
  1. Names are compared after `normalize_name`. Exact normalized matches win; only if there are
     none do fuzzy matches (similarity >= `fuzzy_threshold`) count.
  2. The same OSM feature appearing in more than one cache counts once (keyed by `osm_id`).
  3. One candidate from an exact match whose record names an operator -> `confirmed`.
     An exact match on a record with no operator (the `untagged_sc` cache) is only `low`:
     nothing ties that substation to a utility, so the name alone is weaker evidence.
     A fuzzy-only match is `low`.
  4. Several candidates -> `low`. If they all sit within `SAME_SITE_MILES` of each other they
     are one site (e.g. OSM maps "Mitchell Substation (115kV)" and "(230kV)" as two yards) and
     their mean point is used; otherwise the names collide across areas — the sponsor guide's
     "similarly named substation in the wrong area" trap — and no coordinate is chosen.
  5. No candidate -> `unlocated` with blank coordinates. `locate_endpoints` keeps those in the
     output so the caller can list them rather than guess.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import combinations
from typing import Any, Literal

from pipeline.overlap import haversine_miles

Confidence = Literal["confirmed", "low", "unlocated"]
SubstationCache = Sequence[Mapping[str, Any]]

DEFAULT_FUZZY_THRESHOLD = 0.85
# Candidates this close together are one physical site, not a name collision. Far below both the
# 25-mile overlap radius and the 2-mile tolerance the sponsor's locations are checked against.
SAME_SITE_MILES = 1.0

_STATION_SUFFIXES = {"sub", "substation"}
_VOLTAGE_LABEL = re.compile(r"\b\d+(?:\.\d+)?\s*kv\b")


@dataclass(frozen=True)
class Candidate:
    osm_id: str
    name: str
    lat: float
    lon: float
    operator: str | None
    score: float


@dataclass(frozen=True)
class Location:
    endpoint: str
    lat: float | None
    lon: float | None
    location_confidence: Confidence
    candidates: tuple[Candidate, ...] = ()


def normalize_name(name: str) -> str:
    """Ignore case, accents, punctuation, voltage labels and a trailing "Sub"/"Substation".

    Geographic qualifiers stay: North/South/West, numbers, "Primary", "Dam", town names. Those
    are what tell apart similarly named substations in different areas. Voltage labels such as
    "(115kV)" only name a yard within a site, so they are dropped.
    """
    name = unicodedata.normalize("NFKD", name.casefold())
    name = "".join(char for char in name if not unicodedata.combining(char))
    words = re.findall(r"[^\W_]+", _VOLTAGE_LABEL.sub(" ", name))
    while words and words[-1] in _STATION_SUFFIXES:
        words.pop()
    return " ".join(words)


def _valid_point(record: Mapping[str, Any]) -> tuple[float, float] | None:
    try:
        lat, lon = float(record["lat"]), float(record["lon"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if math.isfinite(lat) and math.isfinite(lon) and abs(lat) <= 90 and abs(lon) <= 180:
        return lat, lon
    return None


def _same_site(candidates: Sequence[Candidate]) -> bool:
    return all(
        haversine_miles(a.lat, a.lon, b.lat, b.lon) <= SAME_SITE_MILES
        for a, b in combinations(candidates, 2)
    )


def locate_endpoint(
    endpoint: str | None,
    caches: Iterable[SubstationCache],
    *,
    fuzzy_threshold: float = DEFAULT_FUZZY_THRESHOLD,
) -> Location:
    """Find `endpoint` in every cache and return its location and confidence (see module doc)."""
    if not math.isfinite(fuzzy_threshold) or not 0 < fuzzy_threshold <= 1:
        raise ValueError("fuzzy_threshold must be in (0, 1]")
    endpoint = endpoint or ""
    target = normalize_name(endpoint)
    if not target:
        return Location(endpoint, None, None, "unlocated")

    exact: dict[tuple, Candidate] = {}
    fuzzy: dict[tuple, Candidate] = {}
    for cache in caches:
        for record in cache:
            name = record.get("name")
            normalized = normalize_name(name) if isinstance(name, str) else ""
            point = _valid_point(record)
            if not normalized or point is None:
                continue
            score = SequenceMatcher(None, target, normalized, autojunk=False).ratio()
            if normalized == target:
                pool = exact
            elif score >= fuzzy_threshold:
                pool = fuzzy
            else:
                continue
            osm_id = str(record.get("osm_id") or "")
            # Coordinates are part of the key, so one feature cached at two different points
            # (inconsistent snapshots) is treated as two candidates rather than silently merged.
            key = (osm_id, *point) if osm_id else (osm_id, *point, normalized)
            pool.setdefault(key, Candidate(osm_id, name, *point, record.get("operator"), score))

    candidates = tuple(sorted(
        (exact or fuzzy).values(),
        key=lambda c: (-c.score, c.name, c.osm_id, c.lat, c.lon),
    ))
    if not candidates:
        return Location(endpoint, None, None, "unlocated")
    if not _same_site(candidates):
        return Location(endpoint, None, None, "low", candidates)
    lat = sum(c.lat for c in candidates) / len(candidates)
    lon = sum(c.lon for c in candidates) / len(candidates)
    only = candidates[0]
    confirmed = bool(exact) and len(candidates) == 1 and only.operator is not None
    return Location(endpoint, lat, lon, "confirmed" if confirmed else "low", candidates)


def locate_endpoints(
    endpoints: Iterable[str | None],
    caches: Iterable[SubstationCache],
    *,
    fuzzy_threshold: float = DEFAULT_FUZZY_THRESHOLD,
) -> list[Location]:
    """Locate each endpoint in input order; unlocated ones stay in the list for reporting."""
    caches = [list(cache) for cache in caches]  # Reused for every endpoint.
    return [
        locate_endpoint(name, caches, fuzzy_threshold=fuzzy_threshold) for name in endpoints
    ]
