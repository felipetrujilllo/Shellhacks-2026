"""Issue #51: the published spec, the center-gate decision and the demo script stay true.

Guards docs/prompt.md (the published closest-point rule, its four tiers and our decision) and
docs/demo.md (the clicked pair, the shipped pitch line and its figures) against drift from
the engine. No network: every figure is recomputed offline by running the engine on
data/seed/projects.csv — the file the demo database is loaded from — and shaping it the way
GET /overlaps serves it (test_demo_data.served_overlaps), which since #62 includes the
standing sample submissions' pairs. The live API was read by hand when
the figures were written; this suite checks they still follow from the code and the seed.
"""

import csv
import re
from pathlib import Path

import pytest
from test_demo_data import PROJECTS_CSV, served_overlaps

from pipeline.overlap import (
    OVERLAP_RADIUS_MI,
    SHARED_LAND_UNDER_MI,
    SITE_LOGISTICS_UNDER_MI,
    TIER_ORDER,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT = REPO_ROOT / "docs" / "prompt.md"
DEMO = REPO_ROOT / "docs" / "demo.md"
PROJECT = REPO_ROOT / "docs" / "project.md"

CLOSEST_POINT_RULE = (
    "We measure the closest points between two projects, not their centers — a 60 km power "
    "line can still pass within 5 km of the other utility substation, and that counts."
)
SHIPPED_PITCH_LINE = (
    "We rank the way Sperry asked — touching first, then shared land, site and crews — "
    "measuring closest approach along the lines. We decide which pairs to flag by project "
    "centers, which reproduces Sperry's reference table exactly; moving that gate to edges is "
    "our next step."
)
FALLBACK_PITCH_LINE = (
    "We gate on project centers, matching Sperry's reference table; closest-point distance "
    "and tier ranking are our next step."
)
CLICKED_DESC = "Jasper – Okatie 230 kV #2: Construct"
CLICKED_GPC = "SAV: MCINTOSH - PURRYSBURG 230KV REACTORS"


def flat(text: str) -> str:
    """Whitespace-normalized, so a phrase wrapped across lines (or \\r\\n) still matches."""
    return " ".join(text.split())


def sections(path: Path, level: str) -> dict[str, str]:
    """Body text under each heading of exactly `level` ('## ' or '### '), keyed by title.

    A section runs until the next heading of the same or a higher level; deeper headings
    stay inside it.
    """
    depth = len(level.strip())
    out: dict[str, list[str]] = {}
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        heading_depth = len(line) - len(line.lstrip("#")) if line.startswith("#") else 0
        if line.startswith(level):
            current = line[len(level):].strip()
            out[current] = []
        elif 0 < heading_depth <= depth:
            current = None
        elif current is not None:
            out[current].append(line)
    return {title: "\n".join(body) for title, body in out.items()}


def table_rows(text: str) -> list[list[str]]:
    """Cells of every markdown table row in `text`, header and separator rows included.

    An escaped pipe (`\\|`, e.g. in the pair id SUB:19598|SUB-7220) stays inside its cell.
    """
    return [
        [
            c.strip().replace("\\|", "|")
            for c in re.split(r"(?<!\\)\|", re.sub(r"^\||(?<!\\)\|$", "", line.strip()))
        ]
        for line in text.splitlines()
        if line.strip().startswith("|")
    ]


@pytest.fixture(scope="module")
def prompt_text() -> str:
    return flat(PROMPT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def decision() -> str:
    found = [
        body for title, body in sections(PROMPT, "### ").items() if title.startswith("Decision")
    ]
    assert len(found) == 1, "docs/prompt.md needs exactly one '### Decision ...' subsection"
    return flat(found[0])


@pytest.fixture(scope="module")
def demo_text() -> str:
    return flat(DEMO.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def figures() -> dict[str, str]:
    body = sections(DEMO, "## ")["Figures"]
    rows = table_rows(body)
    assert rows[0] == ["Figure", "Value"]
    return {row[0]: row[1] for row in rows[2:]}


@pytest.fixture(scope="module")
def served() -> list[dict]:
    return served_overlaps(PROJECTS_CSV)


def by_rank(served: list[dict], rank: int) -> dict:
    (overlap,) = [o for o in served if o["rank"] == rank]
    return overlap


def dollars(value: str) -> int:
    assert re.fullmatch(r"\$[\d,]+", value), value
    return int(value[1:].replace(",", ""))


def miles(value: str) -> float:
    assert value.endswith(" mi"), value
    return float(value[:-3])


def days(value: str) -> int:
    assert value.endswith(" days"), value
    return int(value[:-5].replace(",", ""))


# --- docs/prompt.md: the published spec and the decision ---------------------------------------


def test_prompt_quotes_the_closest_point_rule_and_its_40_km_radius(prompt_text):
    assert CLOSEST_POINT_RULE in prompt_text
    assert "40 km / 25 mi" in prompt_text


def test_prompt_lists_the_four_published_tiers_with_distances_and_what_they_share():
    title = "Published spec (ShellHacks challenge page) — closest points and tiers"
    rows = table_rows(sections(PROMPT, "## ")[title])
    assert rows[0] == ["Tier", "Closest-point distance", "What the utilities can share"]
    tiers = rows[2:]
    assert [r[0] for r in tiers] == [
        "Touching / crossing", "Under 1.6 km", "Under 8 km", "Under 40 km"
    ]
    assert tiers[0][1].startswith("0 ")
    assert [r[1].split(" (")[0] for r in tiers[1:]] == ["< 1.6 km", "< 8 km", "< 40 km"]
    assert tiers[0][2] == "must coordinate (outage timing, crossing structures)"
    assert tiers[1][2] == "can share the land itself (right-of-way, access roads, permits)"
    assert tiers[2][2] == "can share site logistics (laydown yards, deliveries)"
    assert tiers[3][2] == "can share crews and equipment"


def test_prompt_decision_keeps_the_center_gate_and_says_why(decision):
    assert "Center gate stays." in decision
    assert "centers** are < 25 mi apart" in decision
    assert "no time" in decision
    assert "reproduces the sponsor's reference table exactly" in decision
    assert "golden test" in decision


def test_prompt_decision_sets_the_tier_by_closest_approach_and_ranks_tier_first(decision):
    assert "Closest approach sets the tier." in decision
    assert "Tier-first ranking." in decision
    assert "ordered by tier" in decision and "then by score" in decision
    for ticket in ("#48", "#49", "#50"):
        assert ticket in decision


def test_prompt_decision_states_the_known_limitation(decision):
    assert "Known limitation." in decision
    assert "lines come within 25 mi but whose centers do not are not flagged" in decision
    assert "centers to edges" in decision


def test_prompt_tier_thresholds_equal_the_engine_constants(decision):
    assert "`crossing` = 0" in decision
    shared = re.search(r"`shared_land` < ([\d.]+) mi", decision)
    site = re.search(r"`site_logistics` < ([\d.]+) mi", decision)
    gate = re.search(r"centers\*\* are < ([\d.]+) mi apart", decision)
    assert shared and site and gate
    assert float(shared.group(1)) == SHARED_LAND_UNDER_MI
    assert float(site.group(1)) == SITE_LOGISTICS_UNDER_MI
    assert float(gate.group(1)) == OVERLAP_RADIUS_MI
    assert "`crews` otherwise" in decision


def test_prompt_tier_order_equals_the_engine_order(decision):
    order = re.search(r"ordered by tier \(([^)]*)\)", decision)
    assert order
    assert tuple(re.findall(r"`(\w+)`", order.group(1))) == TIER_ORDER


def test_prompt_still_has_the_sponsor_reference_table(prompt_text):
    """The extension must not have rewritten the golden test's source."""
    assert "Reference answer (sponsor's starter table: 10 projects → 6 overlaps)" in prompt_text
    assert prompt_text.count("| OVL_") == 6


# --- docs/demo.md: the clicked pair, the pitch line, the figures --------------------------------


def seed_project_names() -> set[str]:
    with open(PROJECTS_CSV, newline="", encoding="utf-8") as f:
        return {row["project_name"] for row in csv.DictReader(f)}


def test_demo_names_the_clicked_pair_with_its_exact_seed_names(demo_text):
    names = seed_project_names()
    assert CLICKED_DESC in names and CLICKED_GPC in names
    clicked = sections(DEMO, "## ")["The pair we click"]
    assert CLICKED_DESC in flat(clicked) and CLICKED_GPC in flat(clicked)
    assert "strongest savings story" in flat(clicked)


def test_demo_clicked_pair_is_the_engine_pair_it_names(figures, served):
    (clicked,) = [o for o in served if o["overlap_id"] == figures["Clicked pair"]]
    assert {clicked["project_a"]["project_name"], clicked["project_b"]["project_name"]} == {
        CLICKED_DESC,
        CLICKED_GPC,
    }


def test_demo_explains_in_one_line_why_the_pairs_above_it_rank_higher(demo_text, figures, served):
    """#62: the sample submissions put two pairs above the clicked one (it was #3, now #5)."""
    rank = int(figures["Clicked pair rank"])
    above = [o for o in served if o["rank"] < rank]
    assert f"Why #1–#{rank - 1} rank above it" in demo_text
    assert [o["tier"] for o in above].count("crossing") == 3
    assert [o["tier"] for o in above].count("shared_land") == 1 and len(above) == 4
    assert "three crossings and one shared-land pair" in demo_text
    assert "must be coordinated (design, outage timing) whenever each is built" in demo_text
    assert "crew/equipment savings are largest where projects are close in time" in demo_text
    assert f"which is why we click #{rank}" in demo_text
    names = {o[side]["project_name"] for o in above for side in ("project_a", "project_b")}
    assert "Hooks - Thurmond 115kV Tie: Rebuild" in names
    assert {n for n in names if "THURMOND DAM (USA) #5" in n or "THURMOND DAM (USA) #6" in n}
    # The other two are the sample submissions' pairs the doc names.
    assert sorted(o["overlap_id"] for o in above if o["overlap_id"].startswith("SUB:")) == [
        "SUB:10222|SUB-8150", "SUB:19598|SUB-7220"
    ]
    assert {"Lanett - LaGrange Primary 115 kV Tie Line",
            "Columbia - Blakely West 115 kV Interconnection"} <= names
    assert "sample Lanett – LaGrange Primary" in demo_text
    assert "sample Columbia – Blakely West" in demo_text


def test_demo_figures_count_the_sample_submissions_pairs_and_savings(figures, served, demo_text):
    """#62: how much of the headline number is the made-up sample utility, said out loud."""
    samples = [o for o in served if o["overlap_id"].startswith("SUB:")]
    assert samples, "the standing sample submissions no longer add any pair"
    assert int(figures["Sample-submission pairs"]) == len(samples)
    total = sum(o["est_savings_usd"] for o in samples)
    assert dollars(figures["Sample-submission savings"]) == total
    assert f"{len(samples)} of them, ${total:,}, involve the sample uploads" in demo_text
    assert "not** a real utility's filing" in demo_text


def test_demo_has_the_shipped_pitch_line_verbatim_not_the_fallback(demo_text):
    pitch = flat(sections(DEMO, "## ")["Pitch line"])
    assert SHIPPED_PITCH_LINE in pitch
    assert FALLBACK_PITCH_LINE not in demo_text


def test_demo_figures_record_the_as_of_date_and_the_deployment_caveat():
    body = flat(sections(DEMO, "## ")["Figures"])
    assert "As of 2026-09-27." in body
    assert "Re-check the rank numbers on the live site after promotion." in body


def test_demo_pair_count_and_total_savings_match_the_engine(figures, served, demo_text):
    assert int(figures["Flagged pairs"]) == len(served)
    total = sum(o["est_savings_usd"] for o in served if o["est_savings_usd"] is not None)
    assert dollars(figures["Total estimated savings"]) == total
    # The script says the same numbers out loud.
    assert f"{len(served)} coordination opportunities worth an estimated ${total:,}" in demo_text


def test_demo_tier_counts_match_the_engine(figures, served):
    expected = ", ".join(
        f"{tier} {sum(o['tier'] == tier for o in served)}" for tier in TIER_ORDER
    )
    assert figures["Pairs by tier"] == expected


def test_demo_clicked_pair_figures_match_the_engine(figures, served, demo_text):
    clicked = by_rank(served, int(figures["Clicked pair rank"]))
    assert clicked["overlap_id"] == figures["Clicked pair"]
    assert clicked["tier"] == figures["Clicked pair tier"]
    assert clicked["closest_mi"] == miles(figures["Clicked pair closest approach"])
    assert clicked["distance_mi"] == miles(figures["Clicked pair center distance"])
    assert clicked["time_gap_days"] == days(figures["Clicked pair time gap"])
    assert figures["Clicked pair score"] == f"{round(clicked['score'] * 100)}%"
    assert clicked["est_savings_usd"] == dollars(figures["Clicked pair estimated savings"])
    assert f"#{clicked['rank']} — DESC" in demo_text


def test_demo_top_two_figures_match_the_engine(figures, served):
    first, second = by_rank(served, 1), by_rank(served, 2)
    assert first["overlap_id"] == figures["#1 pair"]
    assert first["tier"] == figures["#1 tier"] == "crossing"
    assert first["closest_mi"] == miles(figures["#1 closest approach"])
    assert first["time_gap_days"] == days(figures["#1 time gap"])
    assert second["overlap_id"] == figures["#2 pair"]
    assert second["tier"] == figures["#2 tier"]


# --- docs/project.md points to the one script ---------------------------------------------------


def test_project_md_demo_section_points_to_demo_md():
    body = sections(PROJECT, "## ")["Demo script (< 3 min)"]
    assert "docs/demo.md" in body
    assert not re.search(r"^\s*\d+\.", body, re.MULTILINE), "project.md still has its own script"
