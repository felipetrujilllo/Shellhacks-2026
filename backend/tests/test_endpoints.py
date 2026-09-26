"""Tests for splitting project names into endpoint substation names (#21, #29)."""

import csv
import re
from pathlib import Path

import pytest

from pipeline.endpoints import ENDPOINT_OVERRIDES, endpoints_for, split_endpoints
from pipeline.load import read_project_csv, to_engine_project
from pipeline.overlap import detect_overlaps

REPO_ROOT = Path(__file__).parents[2]
SPONSOR_CSV = REPO_ROOT / "data" / "seed" / "projects_seed.csv"
DESC_CSV = REPO_ROOT / "data" / "seed" / "desc_projects.csv"
GPC_CSV = REPO_ROOT / "data" / "seed" / "gpc_projects.csv"

# All 10 sponsor rows match after normalization, so there is no list of accepted mismatches.


def normalized(name: str | None) -> str | None:
    """Case, a trailing "Sub"/"Substation" and parenthetical tags do not change the site."""
    if not name:
        return None
    name = re.sub(r"\([^)]*\)", "", name)
    name = re.sub(r"\s+(sub|substation)\s*$", "", name.strip(), flags=re.IGNORECASE)
    return " ".join(name.lower().split())


def read_rows(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# --- the sponsor's 10 projects -----------------------------------------------------


@pytest.mark.parametrize("row", read_rows(SPONSOR_CSV), ids=lambda r: r["project_id"])
def test_matches_the_sponsors_endpoint_names(row):
    name_a, name_b = split_endpoints(row["project_name"])

    assert (normalized(name_a), normalized(name_b)) == (
        normalized(row["name_a"]),
        normalized(row["name_b"]),
    )


def test_all_ten_sponsor_projects_are_compared():
    assert len(read_rows(SPONSOR_CSV)) == 10


# --- separators vs. voltages -------------------------------------------------------


@pytest.mark.parametrize(
    ("project_name", "expected"),
    [
        # A hyphen with no spaces between two names is a separator.
        ("Okatie-Bluffton 115kV: Rebuild", ("Okatie", "Bluffton")),
        # A hyphen between two numbers is a voltage, never a separator.
        ("Union Pier 115-13.8 kV Sub: Tap", ("Union Pier", None)),
        # En dashes separate too, and the "#2" circuit number is not a name.
        ("Jasper – Okatie 230 kV #2: Construct", ("Jasper", "Okatie")),
        # Utility prefix stripped; equipment after the voltage dropped.
        ("SAV: MCINTOSH - PURRYSBURG 230KV REACTORS", ("MCINTOSH", "PURRYSBURG")),
        ("Hopkins-CIP 230kV: Rebuild", ("Hopkins", "CIP")),
    ],
)
def test_separator_rules(project_name, expected):
    assert split_endpoints(project_name) == expected


def test_alphanumeric_station_names_split():
    name = "VCS1-Denny Terrace 230kV & VCS1-Pineland 230kV: Rebuild Single Circuit Sections"

    assert split_endpoints(name)[0] == "VCS1"
    assert split_endpoints(name) == ("VCS1", "Denny Terrace")
    assert split_endpoints("VCS2-Ward 230kV: Rebuild Line") == ("VCS2", "Ward")


def test_a_dash_before_a_work_word_is_not_a_separator():
    assert split_endpoints("Harleyville 115KV Transmission Tap – Construct (1.4 miles)") == (
        "Harleyville",
        None,
    )
    assert split_endpoints("Canadys-Ritter 115KV-Rebld SPDC 230/115KV 1272 (Approx 18 Miles)") == (
        "Canadys",
        "Ritter",
    )
    # The same rule without a voltage in the way.
    assert split_endpoints("Riverport – Construct Tap") == ("Riverport", None)
    assert split_endpoints("Riverport-Rebuild") == ("Riverport", None)


def test_fold_in_is_a_work_term_not_a_separator():
    assert split_endpoints("Scout 230 kV Sub and Fold-in: Construct") == ("Scout", None)
    assert split_endpoints("Scout Sub and Fold-in") == ("Scout", None)


def test_parenthetical_tags_are_dropped():
    assert split_endpoints("SAV: GOSHEN (SAV) - MCINTOSH 115KV LINE REBUILD") == (
        "GOSHEN",
        "MCINTOSH",
    )


def test_a_second_line_after_a_slash_is_dropped():
    assert split_endpoints("Stevens Creek - Hooks 115kV/LR Plumb Branch 46kV Rebuilds") == (
        "Stevens Creek",
        "Hooks",
    )


def test_a_three_station_name_keeps_the_ends():
    assert split_endpoints("Cameron Jct – Cameron – St Matthews 46 kV Rebuild") == (
        "Cameron Jct",
        "St Matthews",
    )


def test_original_casing_is_kept():
    assert split_endpoints("JESUP - LUDOWICI PRIMARY 115KV REBUILD") == (
        "JESUP",
        "LUDOWICI PRIMARY",
    )


def test_a_name_with_no_site_fails_loudly():
    with pytest.raises(ValueError, match="no substation name"):
        split_endpoints("230kV: Rebuild")


# --- single-site projects ------------------------------------------------------------


@pytest.mark.parametrize(
    ("project_name", "site"),
    [
        ("Edenwood Sub: #1 & #2 230-115kV Autobanks, Replace with 336MVA", "Edenwood"),
        ("Wagener 115kV Tap: Construct Tap", "Wagener"),
        ("Riverport Tap: Construct Tap", "Riverport"),
        ("Summerville 115kV Loop: Rebuild", "Summerville"),
        ("Summerville: Replace and Spare 230-115kV 336MVA Auto Bank", "Summerville"),
        ("Dawson 230kV Sub and Fold-in: Construct and Rebuild", "Dawson"),
    ],
)
def test_single_site_projects_never_get_a_second_endpoint(project_name, site):
    assert split_endpoints(project_name) == (site, None)


# --- overrides -----------------------------------------------------------------------

REQUIRED_OVERRIDES = {
    "6807 B": ("Queensboro", "Ft Johnson"),
    "6847 A-B, D-H": ("Church Creek", "Charleston"),
    "6810 T": ("Cameron Jct", "St Matthews"),
    "0139 M,N": ("Jasper", "Yemassee"),
    "1060A, I, L": ("Williams St", None),
    # Georgia Power, #23: THURMOND DAM #5 / #6 end at OSM's "Thurmond Substation".
    "20793": ("EVANS PRIMARY", "THURMOND"),
    "20794": ("EVANS PRIMARY", "THURMOND"),
}


def test_overrides_hold_the_required_entries_exactly():
    for project_id, expected in REQUIRED_OVERRIDES.items():
        assert ENDPOINT_OVERRIDES.get(project_id) == expected, project_id


def test_every_override_key_is_a_real_project():
    # DESC or Georgia Power: build_dataset checks project_ids are unique across the two.
    ids = {row["project_id"] for row in read_rows(DESC_CSV) + read_rows(GPC_CSV)}

    assert set(ENDPOINT_OVERRIDES) <= ids


def test_thurmond_dam_is_named_as_osm_names_the_station():
    names = {row["project_id"]: row["project_name"] for row in read_rows(GPC_CSV)}
    for project_id, circuit in (("20793", "#5"), ("20794", "#6")):
        name = names[project_id]
        assert name == f"EVANS PRIMARY - THURMOND DAM (USA) {circuit} 115KV REBUILD"
        # The rules keep the dam and circuit, which no OSM substation is called ...
        assert split_endpoints(name) == ("EVANS PRIMARY", f"THURMOND DAM {circuit}")
        # ... so the override names the station the way OSM does ("Thurmond Substation").
        assert endpoints_for(project_id, name) == ("EVANS PRIMARY", "THURMOND")


def test_endpoints_for_prefers_the_override():
    name = "Okatie 230-115kV Substation, Jasper – Yemassee 230kV #1 Fold-in"

    assert split_endpoints(name) == ("Okatie", None)
    assert endpoints_for("0139 M,N", name) == ("Jasper", "Yemassee")


def test_endpoints_for_falls_back_to_the_rules():
    assert endpoints_for("6808 S", "Okatie-Bluffton 115kV: Rebuild") == ("Okatie", "Bluffton")


# --- Georgia Power program tags and more work words (#29) ----------------------------

PROJECTS_CSV = REPO_ROOT / "data" / "seed" / "projects.csv"
PROGRAM_TAGS = {"cc", "grid"}


def gpc_names() -> dict[str, str]:
    return {row["project_id"]: row["project_name"] for row in read_rows(GPC_CSV)}


def test_no_gpc_project_yields_a_program_tag_as_an_endpoint():
    names = gpc_names()
    tagged = {pid for pid, name in names.items() if re.match(r"(?:SAV: )?(?:CC|GRID) -", name)}
    assert len(tagged) == 22  # the names this ticket is about, so the check below is not vacuous

    for project_id, name in names.items():
        # The rules alone, and what build_dataset actually uses (overrides first).
        for endpoints in (split_endpoints(name), endpoints_for(project_id, name)):
            words = {w.lower() for e in endpoints if e for w in re.findall(r"\w+", e)}
            assert not words & PROGRAM_TAGS, (project_id, name, endpoints)


@pytest.mark.parametrize(
    ("project_id", "expected"),
    [
        # "CC - " / "GRID - " open the name like a utility prefix, also after "SAV:".
        ("19187", ("BREMEN", "CROOKED CREEK")),  # GRID - BREMEN - CROOKED CREEK (APC) 115 KV
        ("18573", ("ARKWRIGHT", "LLOYD SHOALS")),  # GRID - ARKWRIGHT - LLOYD SHOALS 115KV
        ("19966", ("BIG OGEECHEE", None)),  # SAV: CC - BIG OGEECHEE 500/230KV (CC NETWORK ...)
        ("20717", ("TOMOCHICHI", None)),  # CC - TOMOCHICHI 500/230KV SOLUTION (CC NETWORK ...)
        ("20781", ("SUMMER LAKE", "VILLA RICA")),  # CC - SUMMER LAKE - VILLA RICA 230KV REBUILD
        # A trailing "- CC IMPROVEMENTS" is work, not a third station.
        ("20152", ("CASS PINE", "HILL VIEW")),  # CC - CASS PINE- HILL VIEW 230 KV LINE- CC IMPR.
        ("20150", ("HILL VIEW", None)),  # CC - HILL VIEW & GRASSY HOLLOW SUB - CC IMPROVEMENTS
        # "230/25" is a voltage pair even without "kV"; QCELLS is the customer.
        ("20151", ("CASS PINE", None)),  # CC - CASS PINE 230/25 NEW SUB - QCELLS - CC IMPR.
        # OSM names switching stations "... Switching Station", so that part is kept.
        ("20243", ("GARRETT ROAD SWITCHING STATION", "TRAE LANE")),
        ("20771", ("GULLATT ROAD", None)),  # CC - GULLATT ROAD TRANSMISSION IMPROVEMENTS
        ("20774", ("VILLA RICA", None)),  # CC - VILLA RICA UPGRADES (CC NETWORK IMPROVEMENTS)
        ("20018", ("QTS FAYETTEVILLE", None)),  # CC - QTS FAYETTEVILLE TRANSMISSION NEEDS
        ("19706", ("GAINESVILLE #2", None)),  # GRID - GAINESVILLE #2 EQUIPMENT REPLACEMENT
        # Installation / Modernization / Replacement / Removal, and the equipment before them.
        ("20490", ("KLONDIKE", None)),  # KLONDIKE RELAY MODERNIZATION
        ("18832", ("FORTSON", None)),  # MEAG: FORTSON SUBSTATION MODERNIZATION
        ("19999", ("ROBINS SPRING", None)),  # GTC: ROBINS SPRING BUS REPLACEMENT
        ("20001", ("ROBINS SPRING", None)),  # GTC: ROBINS SPRING CAPACITOR BANK INSTALLATION
        ("20796", ("MELDRIM", None)),  # SAV: MELDRIM BANK D REPLACEMENT
        ("21022", ("OHARA", None)),  # OHARA BREAKER REPLACEMENT
        # "Reactor" is left alone: it ends real station names ("L Reactor", Savannah River Site).
        ("18690", ("PALMYRA REACTOR", None)),  # PALMYRA REACTOR REMOVAL
    ],
)
def test_real_gpc_names_split_to_their_station(project_id, expected):
    assert endpoints_for(project_id, gpc_names()[project_id]) == expected


def test_hyundai_is_named_as_osm_names_the_plants_station():
    name = gpc_names()["19523"]
    assert name == "SAV: CC - HYUNDAI MOTORS SAVANNAH AKA. PROJECT EA"
    # Prefixes gone, but the rules keep the alias, which no OSM substation is called ...
    assert split_endpoints(name) == ("HYUNDAI MOTORS SAVANNAH AKA. PROJECT EA", None)
    # ... so the override names the station the way OSM does ("Hyundai Motors Substation").
    assert endpoints_for("19523", name) == ("HYUNDAI MOTORS", None)


@pytest.mark.parametrize(
    ("project_name", "expected"),
    [
        # CC / GRID only count as a tag at the very start and before a dash.
        ("CC ROAD - BETA 115KV REBUILD", ("CC ROAD", "BETA")),
        ("GRIDLEY - ACCESS 115KV", ("GRIDLEY", "ACCESS")),
        ("ALPHA - CC 115KV", ("ALPHA", "CC")),
        # A trailing "- CC IMPROVEMENTS" never becomes the last station, voltage or not.
        ("CC - ALPHA - BETA - CC IMPROVEMENTS", ("ALPHA", "BETA")),
        # Equipment words are only stripped from the end, and never the whole name.
        ("GTC: BANKS CROSSING - POND FORK 115 KV", ("BANKS CROSSING", "POND FORK")),
        ("Bus Station Road - Relay Hill 115kV: Rebuild", ("Bus Station Road", "Relay Hill")),
        ("Network Sub: Rebuild", ("Network", None)),
        ("Breaker Replacement", ("Breaker", None)),
    ],
)
def test_program_tags_and_equipment_words_never_eat_a_station_name(project_name, expected):
    assert split_endpoints(project_name) == expected


def test_every_desc_and_gpc_name_still_yields_a_station():
    for row in read_rows(DESC_CSV) + read_rows(GPC_CSV):
        name_a, _ = endpoints_for(row["project_id"], row["project_name"])
        assert name_a.strip(), row["project_id"]


# The regenerated projects.csv (test_build_dataset.py checks it is exactly what the code builds).

LOCATED_BEFORE_29 = 110  # located projects in projects.csv before this ticket


def test_the_located_count_does_not_drop():
    assert len(read_rows(PROJECTS_CSV)) >= LOCATED_BEFORE_29 + 5


@pytest.mark.parametrize(
    ("project_id", "name_a", "confidence"),
    [
        ("20490", "KLONDIKE", "confirmed"),
        ("19999", "ROBINS SPRING", "confirmed"),
        ("20001", "ROBINS SPRING", "confirmed"),
        ("20796", "MELDRIM", "confirmed"),
        # OSM's Hyundai Motors Substation carries no operator tag, so it is only low.
        ("19523", "HYUNDAI MOTORS", "low"),
    ],
)
def test_projects_the_new_rules_locate_are_on_the_map(project_id, name_a, confidence):
    row = {r["project_id"]: r for r in read_rows(PROJECTS_CSV)}[project_id]

    assert (row["name_a"], row["location_confidence"]) == (name_a, confidence)
    assert row["lat_a"] and row["lat_center"]


def test_meldrim_is_a_new_savannah_border_overlap():
    overlaps = detect_overlaps(to_engine_project(r) for r in read_project_csv(PROJECTS_CSV))
    pairs = {frozenset((o.project_id_a, o.project_id_b)): o for o in overlaps}

    # Georgia Power's Meldrim (west of Savannah) and DESC's Jasper – Okatie line.
    overlap = pairs[frozenset(("20796", "06367 D - G"))]
    assert overlap.distance_mi < 25
