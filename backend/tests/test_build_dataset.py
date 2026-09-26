"""Tests for the full located dataset (data/seed/projects.csv).

Everything runs over committed files: the two parser CSVs, the three OSM caches in
data/interim/ and the generated projects.csv. No network, no database. The end-to-end check
resolves the sponsor's starter table (projects_seed.csv + expected_overlaps.csv) to the real
project IDs by name and runs the overlap engine over projects.csv.
"""

import builtins
import csv
import socket
import sys
from pathlib import Path

import pytest
from test_locate import KNOWN_MISSES  # endpoints the matcher is known not to place (#15)
from test_parse_desc import squashed  # names compared on lowercase letters and digits only

from pipeline import build_dataset as bd
from pipeline.build_dataset import (
    BORDER_MARGIN_MI,
    DatasetError,
    ExcludedProject,
    build_dataset,
    build_project,
    miles_east_of_ga_sc_border,
    project_confidence,
    wrong_side_of_border,
)
from pipeline.centers import project_center
from pipeline.load import VALID_CONFIDENCE, read_project_csv, to_engine_project
from pipeline.locate import Candidate, Location
from pipeline.overlap import detect_overlaps, haversine_miles

SEED_DIR = Path(__file__).resolve().parents[2] / "data" / "seed"
PROJECTS_CSV = SEED_DIR / "projects.csv"
STARTER_CSV = SEED_DIR / "projects_seed.csv"
EXPECTED_OVERLAPS_CSV = SEED_DIR / "expected_overlaps.csv"

DESC = "Dominion Energy South Carolina"
GPC = "Georgia Power"
DISTANCE_TOLERANCE_MI = 0.5

# Reference pairs whose distance is not within 0.5 mi of the sponsor's, each caused by an
# endpoint in test_locate.KNOWN_MISSES that the sponsor located and the matcher does not, so
# the project's center falls back to its other endpoint. Measured on projects.csv. The test
# asserts each one still misses, so this cannot go stale. (All six are still flagged < 25 mi.)
KNOWN_PAIR_MISSES = {
    ("DESC_2", "GPC_1"): "GPC_1 loses THURMOND DAM #5 -> center at Evans Primary; 8.18 vs 4.09",
    ("DESC_3", "GPC_2"): "DESC_3 loses Okatie Sub -> center at Jasper; 3.03 vs 5.65",
    ("DESC_3", "GPC_3"): "DESC_3 loses Okatie Sub, GPC_3 loses GOSHEN; 3.03 vs 7.55",
    ("DESC_1", "GPC_1"): "GPC_1 loses THURMOND DAM #5 -> center at Evans Primary; 6.75 vs 8.01",
    ("DESC_5", "GPC_2"): "DESC_5 loses Okatie Sub -> center at Bluffton; 20.46 vs 14.34",
    ("DESC_5", "GPC_3"): "DESC_5 loses Okatie Sub, GPC_3 loses GOSHEN; 20.46 vs 14.81",
}


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


@pytest.fixture(scope="module")
def inputs() -> list[dict]:
    return bd.read_csv(bd.DESC_CSV) + bd.read_csv(bd.GPC_CSV)


@pytest.fixture(scope="module")
def caches() -> list[list[dict]]:
    return bd.read_caches()


@pytest.fixture(scope="module")
def dataset(inputs, caches):
    return build_dataset(inputs, caches)


@pytest.fixture(scope="module")
def committed() -> list[dict]:
    return read_rows(PROJECTS_CSV)


@pytest.fixture(scope="module")
def starter() -> dict[str, dict]:
    return {row["project_id"]: row for row in read_rows(STARTER_CSV)}


@pytest.fixture(scope="module")
def starter_to_real(starter, inputs) -> dict[str, str]:
    """Sponsor ID (DESC_1..GPC_5) -> real project_id, by squashed project name."""
    by_name: dict[str, list[str]] = {}
    for row in inputs:
        by_name.setdefault(squashed(row["project_name"]), []).append(row["project_id"])
    mapping = {}
    for starter_id, row in starter.items():
        matches = by_name.get(squashed(row["project_name"]), [])
        assert len(matches) == 1, f"{starter_id} {row['project_name']!r}: {matches}"
        mapping[starter_id] = matches[0]
    return mapping


def station(name, *, lat=32.0, lon=-81.0, osm_id="node/1", operator=DESC):
    return {"osm_id": osm_id, "name": name, "lat": lat, "lon": lon, "operator": operator}


def raw(project_id="P1", name="Alpha - Beta 115kV: Rebuild", **overrides) -> dict:
    row = {
        "project_id": project_id,
        "utility": DESC,
        "state": "SC",
        "project_name": name,
        "in_service_date": "2026-06-01",
        "est_cost_usd": "1000",
    }
    return {**row, **overrides}


def location(confidence, lat=None, lon=None, candidates=0) -> Location:
    cands = tuple(Candidate(f"node/{i}", "X", 0.0, 0.0, None, 1.0) for i in range(candidates))
    return Location("X", lat, lon, confidence, cands)


# --- Columns, centers, and the loader -----------------------------------------------------------

def test_columns_are_the_seed_columns_plus_cost_and_confidence():
    with STARTER_CSV.open(encoding="utf-8", newline="") as f:
        seed_header = next(csv.reader(f))
    with PROJECTS_CSV.open(encoding="utf-8", newline="") as f:
        header = next(csv.reader(f))
    assert header == [*seed_header, "est_cost_usd", "location_confidence"]


def test_every_row_has_a_center_at_its_located_endpoints(committed):
    assert committed
    for row in committed:
        assert row["lat_center"] and row["lon_center"], row["project_id"]
        coords = [float(row[c]) if row[c] else None for c in ("lat_a", "lon_a", "lat_b", "lon_b")]
        expected = project_center(*coords)
        assert expected is not None, row["project_id"]
        assert float(row["lat_center"]) == pytest.approx(expected[0], abs=1e-6)
        assert float(row["lon_center"]) == pytest.approx(expected[1], abs=1e-6)


def test_the_loader_accepts_every_row(committed):
    rows = read_project_csv(PROJECTS_CSV)  # load.py's own validation, no database
    assert len(rows) == len(committed)
    assert {row.location_confidence for row in rows} <= set(VALID_CONFIDENCE)


def test_committed_csv_is_what_build_dataset_produces_now(dataset, tmp_path):
    fresh = tmp_path / "projects.csv"
    bd.write_csv(dataset.rows, fresh)
    assert fresh.read_bytes() == PROJECTS_CSV.read_bytes(), (
        "data/seed/projects.csv is stale: run python -m pipeline.build_dataset"
    )
    assert b"\r\n" not in fresh.read_bytes()


# --- Inclusion, exclusion, and the printed counts -----------------------------------------------

def test_every_input_project_is_either_included_or_excluded(inputs, dataset):
    included = [row["project_id"] for row in dataset.rows]
    excluded = [project.project_id for project in dataset.excluded]
    assert sorted(included + excluded) == sorted(row["project_id"] for row in inputs)
    assert not set(included) & set(excluded)
    assert {row["utility"] for row in dataset.rows} == {DESC, GPC}


def test_excluded_projects_say_why_for_every_endpoint(dataset):
    assert dataset.excluded
    for project in dataset.excluded:
        # the splitter never fails
        assert project.reason in ("unlocated", "ambiguous", "wrong_state"), project
        assert project.detail.count("'") >= 2, project  # names each endpoint it tried
        if project.reason == "ambiguous":
            assert "far-apart candidates" in project.detail, project
        if project.reason == "wrong_state":
            assert "is in the other state" in project.detail, project


def test_cli_writes_the_csv_and_prints_included_and_excluded_counts(
    dataset, tmp_path, monkeypatch, capsys
):
    out = tmp_path / "projects.csv"
    monkeypatch.setattr(sys, "argv", ["build_dataset", "--out", str(out)])
    bd.main()
    printed = capsys.readouterr().out
    total = len(dataset.rows) + len(dataset.excluded)
    assert f"wrote {len(dataset.rows)} of {total} projects" in printed
    assert f"excluded {len(dataset.excluded)} unlocated projects" in printed
    for project in dataset.excluded:
        assert f"{project.project_id} [{project.reason}]" in printed
    assert out.read_bytes() == PROJECTS_CSV.read_bytes()


# --- Project-level confidence -------------------------------------------------------------------

@pytest.mark.parametrize(
    ("locations", "expected"),
    [
        ([location("confirmed", 1, 1), location("confirmed", 2, 2)], "confirmed"),
        ([location("confirmed", 1, 1)], "confirmed"),  # single-site project
        ([location("confirmed", 1, 1), location("unlocated")], "low"),
        ([location("confirmed", 1, 1), location("low", candidates=2)], "low"),  # ambiguous end
        ([location("confirmed", 1, 1), location("low", 2, 2, candidates=1)], "low"),
        ([location("low", 1, 1, candidates=1)], "low"),
        ([location("unlocated"), location("low", candidates=2)], None),
        ([location("unlocated"), location("unlocated")], None),
        ([location("unlocated")], None),
    ],
)
def test_project_confidence_rule(locations, expected):
    assert project_confidence(locations) == expected


def test_confirmed_rows_have_every_named_endpoint_located(committed):
    for row in committed:
        if row["location_confidence"] == "confirmed":
            assert row["lat_a"], row["project_id"]
            assert bool(row["lat_b"]) == bool(row["name_b"]), row["project_id"]


# --- build_project on small in-memory caches ----------------------------------------------------

def test_a_line_with_both_ends_confirmed_is_centered_between_them():
    caches = [[station("Alpha Sub", lat=32.0, lon=-81.0),
               station("Beta Substation", lat=33.0, lon=-80.0, osm_id="way/2")]]
    row = build_project(raw(), caches)
    assert (row["name_a"], row["name_b"]) == ("Alpha", "Beta")
    assert (row["lat_center"], row["lon_center"]) == ("32.5", "-80.5")
    assert row["location_confidence"] == "confirmed"
    assert row["est_cost_usd"] == "1000"


def test_one_located_end_places_the_project_there_as_low():
    row = build_project(raw(), [[station("Alpha", lat=32.1, lon=-81.2)]])
    assert (row["lat_center"], row["lon_center"]) == ("32.1", "-81.2")
    assert (row["lat_b"], row["lon_b"]) == ("", "")
    assert row["location_confidence"] == "low"


@pytest.mark.parametrize(
    ("cache", "reason"),
    [
        ([], "unlocated"),
        ([station("Alpha", lat=32.0), station("Alpha", lat=34.0, osm_id="node/2")], "ambiguous"),
    ],
)
def test_a_project_with_no_located_endpoint_is_excluded_with_a_reason(cache, reason):
    result = build_project(raw(), [cache])
    assert isinstance(result, ExcludedProject)
    assert (result.project_id, result.reason) == ("P1", reason)
    assert "Beta" in result.detail


def test_a_name_with_no_station_in_it_is_excluded():
    result = build_project(raw(name="(USA): Rebuild"), [[station("Alpha")]])
    assert isinstance(result, ExcludedProject)
    assert result.reason == "no_endpoints"


# --- Wrong-state matches (the sponsor guide's "similar name, wrong area" trap) -----------------

# Real points: Buzzard Roost Dam (Lake Greenwood, SC), Atlanta, and the two banks of the
# Savannah River at the McIntosh plant (GA) and Jasper substation (SC).
BUZZARD_ROOST_DAM_SC = (34.16889, -81.902552)
ATLANTA_GA = (33.749, -84.388)


def test_border_distance_is_positive_in_sc_and_negative_in_ga():
    assert miles_east_of_ga_sc_border(*BUZZARD_ROOST_DAM_SC) > 30
    assert miles_east_of_ga_sc_border(*ATLANTA_GA) < -100
    assert -BORDER_MARGIN_MI < miles_east_of_ga_sc_border(32.352116, -81.175112) < 0  # McIntosh
    assert 0 < miles_east_of_ga_sc_border(32.360699, -81.124152) < BORDER_MARGIN_MI  # Jasper
    assert miles_east_of_ga_sc_border(31.0, -83.0) is None  # south of SC: no GA/SC question
    assert miles_east_of_ga_sc_border(35.5, -82.0) is None  # North Carolina


@pytest.mark.parametrize(
    ("utility", "point", "confidence", "wrong"),
    [
        (GPC, BUZZARD_ROOST_DAM_SC, "low", True),  # a GA project's fuzzy match deep in SC
        (DESC, BUZZARD_ROOST_DAM_SC, "low", False),  # same point, DESC's own side
        (DESC, ATLANTA_GA, "low", True),
        (DESC, ATLANTA_GA, "confirmed", False),  # exact + operator is trusted across the line
        (DESC, (33.660127, -82.195931), "low", False),  # Thurmond, on the line: within margin
        (GPC, (32.360699, -81.124152), "low", False),  # Jasper, just across the river
    ],
)
def test_wrong_side_of_border(utility, point, confidence, wrong):
    loc = Location("X", *point, confidence, location(confidence, *point, candidates=1).candidates)
    assert wrong_side_of_border(loc, utility) is wrong


def test_unlocated_is_never_on_the_wrong_side():
    assert wrong_side_of_border(location("unlocated"), GPC) is False


def gpc_raw(name):
    return raw(name=name, utility=GPC, state="GA")


def buzzard_roost_caches():
    # The real pair: an untagged SC record whose name only fuzzy-matches the GA endpoint.
    return [[station("Adamsville Substation", lat=33.75, lon=-84.50, operator=GPC)],
            [station("Buzzard Roost Dam Substation", lat=BUZZARD_ROOST_DAM_SC[0],
                     lon=BUZZARD_ROOST_DAM_SC[1], osm_id="relation/9", operator=None)]]


def test_a_wrong_state_end_is_dropped_and_the_project_placed_on_its_other_end():
    row = build_project(gpc_raw("ADAMSVILLE - BUZZARD ROOST 230KV REBUILD"), buzzard_roost_caches())
    assert (row["name_a"], row["name_b"]) == ("ADAMSVILLE", "BUZZARD ROOST")
    assert (row["lat_b"], row["lon_b"]) == ("", "")
    assert (row["lat_center"], row["lon_center"]) == ("33.75", "-84.5")
    assert row["location_confidence"] == "low"


def test_a_project_placed_only_by_a_wrong_state_match_is_excluded():
    result = build_project(gpc_raw("BUZZARD ROOST - FACTORY SHOALS 230KV NEW LINE"),
                           buzzard_roost_caches())
    assert isinstance(result, ExcludedProject)
    assert result.reason == "wrong_state"
    assert "'BUZZARD ROOST': only match 'Buzzard Roost Dam Substation'" in result.detail
    assert "'FACTORY SHOALS': no OSM substation" in result.detail


def test_no_placed_endpoint_is_deep_in_the_other_utilitys_state(committed):
    # Only confirmed matches may cross the line (DESC's Thurmond Sub is a Georgia Power station).
    home = {DESC: 1, GPC: -1}
    for row in committed:
        for end in ("a", "b"):
            if not row[f"lat_{end}"] or row["location_confidence"] == "confirmed":
                continue
            east = miles_east_of_ga_sc_border(float(row[f"lat_{end}"]), float(row[f"lon_{end}"]))
            if east is not None:
                assert east * home[row["utility"]] >= -BORDER_MARGIN_MI, (row["project_id"], end)


def test_buzzard_roost_no_longer_makes_fake_overlaps(dataset, committed):
    # 19597/20858/21014/21036 are Atlanta-area lines; placed at Lake Greenwood, SC, each one
    # paired with DESC's VCS2-Ward line 23.6 mi away (4 of the 41 overlaps before this check).
    excluded = {p.project_id: p.reason for p in dataset.excluded}
    for project_id in ("19597", "20858", "21014", "21036"):
        assert excluded.get(project_id) == "wrong_state", project_id
    placed_at_buzzard_roost = {
        row["project_id"] for row in committed
        if "BUZZARD ROOST" in (row["name_a"], row["name_b"])
        and (row["lat_a"] if row["name_a"] == "BUZZARD ROOST" else row["lat_b"])
    }
    assert placed_at_buzzard_roost == set()


# --- Validation at the boundary -----------------------------------------------------------------

def test_a_missing_input_column_fails_loud():
    row = raw()
    del row["est_cost_usd"]
    with pytest.raises(DatasetError, match="P1: missing column"):
        build_dataset([row], [[]])


def test_a_duplicate_project_id_fails_loud():
    with pytest.raises(DatasetError, match="duplicate project_id"):
        build_dataset([raw(), raw(name="Gamma - Delta 115kV")], [[]])


def test_an_unknown_utility_fails_loud():
    with pytest.raises(DatasetError, match="unknown utility"):
        build_dataset([raw(utility="Duke Energy")], [[]])


def test_stored_endpoints_that_disagree_with_endpoints_for_fail_loud():
    stale = raw(name_a="Alpha", name_b="Gamma")
    with pytest.raises(DatasetError, match="differ from endpoints_for"):
        build_dataset([stale], [[station("Alpha")]])


def test_a_row_the_loader_would_reject_fails_at_build_time():
    with pytest.raises(ValueError, match="in_service_date"):
        build_dataset([raw(in_service_date="soon")], [[station("Alpha")]])


def test_build_dataset_is_pure(inputs, caches, dataset, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("build_dataset touched a file or the network")

    sample = inputs[::10]  # a spread of DESC and GPC rows; each row is built independently
    ids = {row["project_id"] for row in sample}
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    result = build_dataset(sample, caches)
    monkeypatch.undo()
    assert result.rows == [row for row in dataset.rows if row["project_id"] in ids]
    assert result.excluded == [p for p in dataset.excluded if p.project_id in ids]
    assert result.rows and result.excluded


# --- Costs --------------------------------------------------------------------------------------

def test_desc_costs_are_carried_through_and_gpc_costs_are_blank(committed):
    desc_costs = {row["project_id"]: row["est_cost_usd"] for row in bd.read_csv(bd.DESC_CSV)}
    by_id = {row["project_id"]: row for row in committed}
    assert by_id["6807 B"]["est_cost_usd"] == "5404301"  # Queensboro, sheet 1 of the PDF
    for row in committed:
        if row["utility"] == DESC:
            assert row["est_cost_usd"] == desc_costs[row["project_id"]], row["project_id"]
            assert row["est_cost_usd"], row["project_id"]
        else:
            assert row["est_cost_usd"] == "", row["project_id"]


# --- End to end against the sponsor's starter table ---------------------------------------------

def test_all_ten_starter_projects_are_in_the_inputs(starter_to_real):
    assert len(starter_to_real) == 10


@pytest.fixture(scope="module")
def engine_pairs():
    rows = read_project_csv(PROJECTS_CSV)
    overlaps = detect_overlaps(to_engine_project(row) for row in rows)
    return {frozenset((o.project_id_a, o.project_id_b)): o for o in overlaps}


def reference_pairs() -> list[dict]:
    rows = read_rows(EXPECTED_OVERLAPS_CSV)
    assert len(rows) == 6
    return rows


def test_every_reference_pair_is_flagged(starter_to_real, engine_pairs):
    for ref in reference_pairs():
        a, b = starter_to_real[ref["project_id_a"]], starter_to_real[ref["project_id_b"]]
        overlap = engine_pairs.get(frozenset((a, b)))
        assert overlap is not None, f"{ref['overlap_id']} ({a} / {b}) not flagged"
        assert overlap.time_gap_days == int(ref["time_gap_days"]), ref["overlap_id"]


def test_reference_distances_match_except_known_endpoint_misses(
    starter, starter_to_real, engine_pairs, committed
):
    by_id = {row["project_id"]: row for row in committed}
    seen = set()
    for ref in reference_pairs():
        key = (ref["project_id_a"], ref["project_id_b"])
        a, b = (starter_to_real[k] for k in key)
        distance = engine_pairs[frozenset((a, b))].distance_mi
        within = abs(distance - float(ref["distance_mi"])) <= DISTANCE_TOLERANCE_MI
        if key not in KNOWN_PAIR_MISSES:
            assert within, (key, distance, ref["distance_mi"])
            continue
        seen.add(key)
        assert not within, f"{key} now matches ({distance}); drop it from KNOWN_PAIR_MISSES"
        # The only acceptable cause: a KNOWN_MISSES endpoint the sponsor located and we don't.
        lost = [
            (sid, starter[sid][f"name_{s}"])
            for sid in key
            for s in ("a", "b")
            if starter[sid][f"name_{s}"] in KNOWN_MISSES
            and starter[sid][f"lat_{s}"]
            and not by_id[starter_to_real[sid]][f"lat_{s}"]
        ]
        assert lost, f"{key} misses for a reason other than KNOWN_MISSES"
    assert seen == set(KNOWN_PAIR_MISSES)


def test_known_pair_misses_are_explained_by_the_lost_endpoints_alone(
    starter, starter_to_real, engine_pairs
):
    """Drop the KNOWN_MISSES endpoints from the sponsor's own coordinates and recompute: the
    distance must then match ours within 0.5 mi, so nothing else differs for these pairs."""

    def center_without_misses(sid):
        row = starter[sid]
        coords = []
        for s in ("a", "b"):
            lost = row[f"name_{s}"] in KNOWN_MISSES or not row[f"lat_{s}"]
            coords += [None, None] if lost else [float(row[f"lat_{s}"]), float(row[f"lon_{s}"])]
        return project_center(*coords)

    for key in KNOWN_PAIR_MISSES:
        a, b = (center_without_misses(sid) for sid in key)
        adjusted = haversine_miles(*a, *b)
        ours = engine_pairs[frozenset(starter_to_real[sid] for sid in key)].distance_mi
        assert abs(ours - adjusted) <= DISTANCE_TOLERANCE_MI, (key, ours, adjusted)
