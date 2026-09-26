"""Endpoint -> OSM substation matching (#15).

Unit tests use small record lists in the exact shape `pipeline.osm_fetch` caches
(`{osm_id, name, lat, lon, operator}`). The sponsor regression runs the matcher over the real
committed caches in `data/interim/` and fails, rather than skips, if they are missing. Never
synthesize OSM records from the sponsor's coordinates: that would test the oracle against itself.
"""

import csv
import json
from copy import deepcopy
from difflib import SequenceMatcher
from pathlib import Path

import pytest

from pipeline.locate import (
    DEFAULT_FUZZY_THRESHOLD,
    locate_endpoint,
    locate_endpoints,
    normalize_name,
)
from pipeline.osm_fetch import TARGETS
from pipeline.overlap import haversine_miles

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "data" / "seed" / "projects_seed.csv"
MATCH_TOLERANCE_MI = 2.0

# Sponsor-located seed endpoints the matcher does not place within 2 miles, observed by running
# it over the real caches. The regression asserts each one still misses, so this can't go stale.
KNOWN_MISSES = {
    "Okatie Sub": "no substation named anything like Okatie in any of the three OSM caches",
    "THURMOND DAM #5": "OSM calls it 'Thurmond Substation' (GPC cache); 'thurmond dam 5' is "
    "below the fuzzy threshold and no alias is added",
    "GOSHEN": "two GPC 'Goshen Substation' features ~87 mi apart -> ambiguous, low, no coordinate",
}

DESC_OP = "Dominion Energy South Carolina"
GPC_OP = "Georgia Power"


def sub(name="Okatie Substation", *, osm_id="node/1", lat=32.33, lon=-81.03, operator=DESC_OP):
    """One cache record, shaped like `osm_fetch.parse_response` output."""
    return {"osm_id": osm_id, "name": name, "lat": lat, "lon": lon, "operator": operator}


# --- Exact normalized match -> confirmed ------------------------------------------------------

@pytest.mark.parametrize("name", [" OKATIE sub ", "Okatie", "Okatie Substation"])
@pytest.mark.parametrize("osm_id", ["node/1", "way/1", "relation/1"])
def test_unique_exact_normalized_match_is_confirmed(name, osm_id):
    result = locate_endpoint(name, [[sub(osm_id=osm_id)], []])
    assert result.location_confidence == "confirmed"
    assert (result.lat, result.lon) == (32.33, -81.03)
    assert [c.osm_id for c in result.candidates] == [osm_id]


def test_normalization_retains_geographic_qualifiers():
    assert normalize_name("NORTH-TIFTON Substation") == "north tifton"
    assert normalize_name("Thurmond Dam #5") == "thurmond dam 5"
    assert normalize_name("LUDOWICI PRIMARY") == "ludowici primary"
    assert normalize_name("West McIntosh Substation") == "west mcintosh"


def test_normalization_drops_voltage_labels():
    assert normalize_name("Mitchell Substation (115kV)") == "mitchell"
    assert normalize_name("North Tifton Substation (500 kV)") == "north tifton"
    assert normalize_name("Plant 1.5kV Sub") == "plant"


def test_exact_match_without_operator_is_only_low():
    # untagged_sc records have operator null: nothing ties them to a utility.
    result = locate_endpoint("Jasper Sub", [[sub("Jasper Substation", operator=None)]])
    assert result.location_confidence == "low"
    assert (result.lat, result.lon) == (32.33, -81.03)


# --- Fuzzy-only or multiple candidates -> low -------------------------------------------------

def test_fuzzy_only_is_low_with_coordinates():
    result = locate_endpoint("Okatiee", [[sub()], []])
    assert result.location_confidence == "low"
    assert (result.lat, result.lon) == (32.33, -81.03)


def test_exact_precedes_fuzzy():
    result = locate_endpoint("Okatie", [[sub()], [sub("Okatiee", osm_id="node/2", lat=34.5)]])
    assert result.location_confidence == "confirmed"
    assert len(result.candidates) == 1


def test_multiple_fuzzy_candidates_far_apart_do_not_choose_highest_score():
    cache = [sub(), sub("Okatieee", osm_id="node/2", lat=34.5, lon=-83.0)]
    result = locate_endpoint("Okatiee", [cache])
    assert result.location_confidence == "low"
    assert len(result.candidates) == 2
    assert result.lat is result.lon is None


@pytest.mark.parametrize("endpoint,osm_name", [
    ("GRADY", "Gray Substation"),
    ("LICK CREEK", "Black Creek Substation"),
    ("WEST VALDOSTA", "East Valdosta Substation"),
])
def test_fuzzy_match_with_a_different_first_word_is_another_station(endpoint, osm_name):
    # Real Georgia Power endpoints that used to land on these wrong-area stations.
    similarity = SequenceMatcher(None, normalize_name(endpoint), normalize_name(osm_name)).ratio()
    assert similarity >= DEFAULT_FUZZY_THRESHOLD  # so it is the first-word rule rejecting it
    result = locate_endpoint(endpoint, [[sub(osm_name)]])
    assert result.location_confidence == "unlocated"
    assert result.lat is result.lon is None


@pytest.mark.parametrize("endpoint,osm_name", [
    ("Queensboro", "Queensborough Substation"),
    ("JEFFERSON ROAD", "Jefferson Rd Substation"),
    ("Stevens Creek", "Stevens Creek Dam Substation"),
])
def test_fuzzy_match_with_the_same_first_word_still_locates(endpoint, osm_name):
    result = locate_endpoint(endpoint, [[sub(osm_name)]])
    assert result.location_confidence == "low"
    assert (result.lat, result.lon) == (32.33, -81.03)


def test_colocated_candidates_are_one_site_but_still_low():
    # OSM maps some stations as one feature per voltage yard, a few hundred yards apart.
    cache = [
        sub("Mitchell Substation (115kV)", osm_id="way/1", lat=31.44391, lon=-84.13509),
        sub("Mitchell Substation (230kV)", osm_id="way/2", lat=31.44712, lon=-84.13384),
    ]
    result = locate_endpoint("Mitchell Substation", [cache])
    assert result.location_confidence == "low"
    assert len(result.candidates) == 2
    assert result.lat == pytest.approx((31.44391 + 31.44712) / 2)
    assert result.lon == pytest.approx((-84.13509 + -84.13384) / 2)


def test_same_numeric_id_on_different_osm_types_is_two_features():
    result = locate_endpoint("Okatie", [[sub()], [sub(osm_id="way/1")]])
    assert result.location_confidence == "low"
    assert len(result.candidates) == 2


# --- Two same-named substations far apart -> low, never confirmed ----------------------------

def test_far_apart_same_names_are_ambiguous_and_order_independent():
    first = [sub(operator=GPC_OP)]
    second = [sub(osm_id="way/2", lat=33.32, lon=-81.99, operator=GPC_OP)]
    result = locate_endpoint("Okatie", [first, second])
    assert result == locate_endpoint("Okatie", [second, first])
    assert result.location_confidence == "low"
    assert result.lat is result.lon is None
    assert len(result.candidates) == 2


def test_far_apart_same_names_within_one_cache_are_ambiguous():
    cache = [sub(operator=GPC_OP), sub(osm_id="way/2", lat=33.32, lon=-81.99, operator=GPC_OP)]
    result = locate_endpoint("OKATIE", [cache])
    assert result.location_confidence == "low"
    assert result.lat is result.lon is None


def test_same_feature_cached_at_inconsistent_points_is_ambiguous():
    result = locate_endpoint("Okatie", [[sub()], [sub(lat=34.5, lon=-83.0)]])
    assert result.location_confidence == "low"
    assert result.lat is result.lon is None


def test_same_osm_feature_in_two_caches_counts_once():
    cache = [sub()]
    result = locate_endpoint("Okatie", [cache, deepcopy(cache)])
    assert result.location_confidence == "confirmed"
    assert len(result.candidates) == 1


# --- Matching searches every cache -----------------------------------------------------------

def test_desc_endpoint_found_only_in_gpc_cache_and_inputs_untouched():
    desc = [sub("Bluffton Substation", osm_id="way/9", lat=32.235, lon=-80.853)]
    gpc = [sub("Thurmond Substation", osm_id="way/5", lat=33.66, lon=-82.196, operator=GPC_OP)]
    original = deepcopy((desc, gpc))
    result = locate_endpoint("Thurmond Sub", [desc, gpc])
    assert result.location_confidence == "confirmed"
    assert (result.lat, result.lon) == (33.66, -82.196)
    assert result.candidates[0].operator == GPC_OP
    assert (desc, gpc) == original


def test_third_cache_is_searched():
    untagged = [sub("Jasper Substation", osm_id="way/7", operator=None)]
    result = locate_endpoint("Jasper Sub", [[], [], untagged])
    assert result.location_confidence == "low"
    assert result.candidates[0].osm_id == "way/7"


# --- No match -> unlocated with blank coordinates --------------------------------------------

@pytest.mark.parametrize("name", ["Thurmond Dam", "", None, "Substation", "Unrelated Place"])
def test_no_match_has_blank_coordinates(name):
    result = locate_endpoint(name, [[sub()], []])
    assert result.location_confidence == "unlocated"
    assert result.lat is result.lon is None
    assert result.candidates == ()


@pytest.mark.parametrize("lat,lon", [(None, -81), (91, -81), (32, -181), ("nan", -81),
                                     (32, "inf"), ("bad", -81)])
def test_invalid_coordinates_do_not_match(lat, lon):
    result = locate_endpoint("Okatie", [[sub(lat=lat, lon=lon)]])
    assert result.location_confidence == "unlocated"


@pytest.mark.parametrize("name", [None, "", "  ", 42])
def test_records_without_a_usable_name_do_not_match(name):
    assert locate_endpoint("Okatie", [[sub(name=name)]]).location_confidence == "unlocated"


def test_unlocated_endpoints_are_retained_for_reporting():
    caches = iter([[sub()], [sub("Jesup", osm_id="way/3", lat=31.6, operator=GPC_OP)]])
    results = locate_endpoints(["Okatie", "Thurmond Dam", "Jesup"], caches)
    assert [r.endpoint for r in results] == ["Okatie", "Thurmond Dam", "Jesup"]
    assert [r.location_confidence for r in results] == ["confirmed", "unlocated", "confirmed"]


@pytest.mark.parametrize("threshold", [0, -1, 1.1, float("nan")])
def test_invalid_fuzzy_threshold(threshold):
    with pytest.raises(ValueError, match="fuzzy_threshold"):
        locate_endpoint("Okatie", [[]], fuzzy_threshold=threshold)


# --- Sponsor regression over the real committed caches ---------------------------------------

@pytest.fixture(scope="module")
def real_caches():
    missing = [str(t.cache_path) for t in TARGETS if not t.cache_path.is_file()]
    assert not missing, f"#14 OSM caches missing (run python -m pipeline.osm_fetch): {missing}"
    return {t.key: json.loads(t.cache_path.read_text(encoding="utf-8")) for t in TARGETS}


def sponsor_located_endpoints():
    with SEED.open(encoding="utf-8", newline="") as source:
        projects = list(csv.DictReader(source))
    assert len(projects) == 10
    return [
        (project["project_id"], project[f"name_{s}"],
         float(project[f"lat_{s}"]), float(project[f"lon_{s}"]))
        for project in projects
        for s in ("a", "b")
        if project[f"lat_{s}"] and project[f"lon_{s}"]  # blank = the sponsor didn't locate it
    ]


def test_ten_seed_projects_match_sponsor_within_two_miles(real_caches):
    caches = list(real_caches.values())
    seen_misses = set()
    for project_id, name, lat, lon in sponsor_located_endpoints():
        result = locate_endpoint(name, caches)
        within = result.lat is not None and haversine_miles(
            result.lat, result.lon, lat, lon) <= MATCH_TOLERANCE_MI
        if name in KNOWN_MISSES:
            seen_misses.add(name)
            assert not within, f"{project_id} {name} now matches; drop it from KNOWN_MISSES"
        else:
            assert within, (project_id, name, result)
    assert seen_misses == set(KNOWN_MISSES)


def test_real_caches_cross_utility_and_ambiguity(real_caches):
    caches = list(real_caches.values())
    # DESC_2's "Thurmond Sub" exists only in the Georgia Power cache.
    thurmond = locate_endpoint("Thurmond Sub", caches)
    assert thurmond.location_confidence == "confirmed"
    assert thurmond.candidates[0].osm_id in {r["osm_id"] for r in real_caches["gpc"]}
    assert not any(normalize_name(r["name"]) == "thurmond" for r in real_caches["desc"])
    # Two real, far-apart "Goshen Substation"s: low, no coordinate picked.
    goshen = locate_endpoint("GOSHEN", caches)
    assert goshen.location_confidence == "low"
    assert goshen.lat is goshen.lon is None
    assert len(goshen.candidates) == 2
