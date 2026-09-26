"""Tests for splitting project names into endpoint substation names (#21)."""

import csv
import re
from pathlib import Path

import pytest

from pipeline.endpoints import ENDPOINT_OVERRIDES, endpoints_for, split_endpoints

REPO_ROOT = Path(__file__).parents[2]
SPONSOR_CSV = REPO_ROOT / "data" / "seed" / "projects_seed.csv"
DESC_CSV = REPO_ROOT / "data" / "seed" / "desc_projects.csv"

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
}


def test_overrides_hold_the_required_entries_exactly():
    for project_id, expected in REQUIRED_OVERRIDES.items():
        assert ENDPOINT_OVERRIDES.get(project_id) == expected, project_id


def test_every_override_key_is_a_real_desc_project():
    ids = {row["project_id"] for row in read_rows(DESC_CSV)}

    assert set(ENDPOINT_OVERRIDES) <= ids


def test_endpoints_for_prefers_the_override():
    name = "Okatie 230-115kV Substation, Jasper – Yemassee 230kV #1 Fold-in"

    assert split_endpoints(name) == ("Okatie", None)
    assert endpoints_for("0139 M,N", name) == ("Jasper", "Yemassee")


def test_endpoints_for_falls_back_to_the_rules():
    assert endpoints_for("6808 S", "Okatie-Bluffton 115kV: Rebuild") == ("Okatie", "Bluffton")
