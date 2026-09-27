"""Guards the Devpost write-up (docs/devpost.md, #36) against silent drift.

Checks structure and the claims a judge can verify against the repo: the nine required
sections in order, the product name, post-freeze placeholders, the Snowflake note staying
under "What's next" (it is not wired into the API or UI), and every coverage number matching
docs/coverage.md. Numbers taken from the live /api/overlaps (pair count, top pair, savings
total) are verified by hand at writing time, not here: this suite never touches the network.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEVPOST = REPO_ROOT / "docs" / "devpost.md"
COVERAGE = REPO_ROOT / "docs" / "coverage.md"

REQUIRED_SECTIONS = [
    "Inspiration",
    "What it does",
    "How we built it",
    "Data & limitations",
    "Challenges",
    "Accomplishments",
    "What's next",
    "Built with",
    "Team",
]

# The one place the old working name may appear: the DigitalOcean default hostname.
LIVE_HOSTNAME = "gridwatch-b3trj.ondigitalocean.app"

# devpost.md abbreviates DESC in its coverage table; coverage.md spells it out.
UTILITY_ALIASES = {"DESC": "Dominion Energy South Carolina"}


@pytest.fixture(scope="module")
def devpost_lines() -> list[str]:
    return DEVPOST.read_text(encoding="utf-8").splitlines()


@pytest.fixture(scope="module")
def devpost_text(devpost_lines) -> str:
    return "\n".join(devpost_lines)


@pytest.fixture(scope="module")
def coverage_text() -> str:
    return "\n".join(COVERAGE.read_text(encoding="utf-8").splitlines())


def _sections(lines: list[str]) -> dict[str, list[str]]:
    """Body lines under each `## ` heading, keyed by heading text."""
    sections: dict[str, list[str]] = {}
    current = None
    for line in lines:
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return sections


def _utility_table(text: str) -> dict[str, list[int]]:
    """Rows of a 'Utility | Parsed | Located | Confirmed | Low | Excluded' table -> numbers."""
    rows: dict[str, list[int]] = {}
    in_table = False
    for line in text.splitlines():
        cells = [c.strip().strip("*").strip() for c in line.strip().strip("|").split("|")]
        if cells[:2] == ["Utility", "Parsed"]:
            in_table = True
            continue
        if not in_table:
            continue
        if not line.strip().startswith("|"):
            break
        if set(cells[0]) <= {"-", " "}:
            continue
        name = UTILITY_ALIASES.get(cells[0], cells[0])
        rows[name] = [int(c) for c in cells[1:]]
    return rows


def test_has_the_nine_required_sections_in_order(devpost_lines):
    headings = [line[3:].strip() for line in devpost_lines if line.startswith("## ")]
    assert headings == REQUIRED_SECTIONS


def test_calls_the_product_relay(devpost_lines, devpost_text):
    assert devpost_lines[0] == "# Relay"
    assert devpost_text.count("Relay") >= 3


def test_gridwatch_appears_only_in_the_live_hostname(devpost_text):
    without_hostname = devpost_text.replace(LIVE_HOSTNAME, "")
    assert "gridwatch" not in without_hostname.lower()


def test_has_screenshot_and_video_placeholders(devpost_text):
    assert "[SCREENSHOT" in devpost_text
    assert "[VIDEO" in devpost_text


def test_snowflake_is_mentioned_only_under_whats_next(devpost_lines):
    for heading, body in _sections(devpost_lines).items():
        if heading == "What's next":
            continue
        for line in body:
            assert not re.search(r"snowflake|cortex", line, re.IGNORECASE), (
                f"Snowflake/Cortex mentioned under '{heading}': {line!r}"
            )
    first_heading = next(i for i, line in enumerate(devpost_lines) if line.startswith("## "))
    intro = devpost_lines[:first_heading]
    assert not any(re.search(r"snowflake|cortex", line, re.IGNORECASE) for line in intro)


def test_whats_next_says_the_snowflake_note_is_not_live(devpost_lines):
    body = " ".join(" ".join(_sections(devpost_lines)["What's next"]).split())
    assert "Snowflake" in body
    assert "not wired into the API or the UI" in body


def test_coverage_table_matches_coverage_report(devpost_text, coverage_text):
    devpost_rows = _utility_table(devpost_text)
    coverage_rows = _utility_table(coverage_text)
    assert set(devpost_rows) == {"Dominion Energy South Carolina", "Georgia Power", "Total"}
    assert devpost_rows == coverage_rows


def test_prose_coverage_numbers_match_coverage_report(devpost_text, coverage_text):
    total = _utility_table(coverage_text)["Total"]
    parsed, located, _confirmed, _low, excluded = total

    not_on_map = re.search(r"(\d+) of (\d+) projects are not on the map", devpost_text)
    assert not_on_map, "the excluded-projects sentence is missing"
    assert [int(n) for n in not_on_map.groups()] == [excluded, parsed]

    located_claim = re.search(r"among \*\*(\d+) located projects\*\*", devpost_text)
    assert located_claim, "the located-projects count is missing"
    assert int(located_claim.group(1)) == located


@pytest.mark.parametrize(
    ("reason", "devpost_pattern"),
    [
        ("unlocated", r"(\d+) have no endpoint that matches an OSM"),
        ("wrong_state", r"(\d+) match only a substation well inside the other utility's state"),
        ("ambiguous", r"(\d+) match\s+several far-apart substations"),
    ],
)
def test_exclusion_reason_counts_match_coverage_report(
    devpost_text, coverage_text, reason, devpost_pattern
):
    in_coverage = re.search(rf"\| `{reason}` \| (\d+) \|", coverage_text)
    assert in_coverage, f"coverage.md has no count for {reason}"
    in_devpost = re.search(devpost_pattern, devpost_text)
    assert in_devpost, f"devpost.md has no count for {reason}"
    assert in_devpost.group(1) == in_coverage.group(1)
