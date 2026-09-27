"""Issue #52: the Thomson–Vogtle finding in docs/data_audit.md stays true.

The published challenge pairs DESC's Urquhart work with GPC's Thomson–Vogtle line. The
public 2025 IRP has no such planned project, so the finding is written down instead of seed
data. These tests pin the written finding (search terms, pages, conclusion) and check it
against the seed CSVs, so the doc fails loud if a Vogtle project is ever added.
"""

import csv
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT = REPO_ROOT / "docs" / "data_audit.md"
PROMPT = REPO_ROOT / "docs" / "prompt.md"
GPC_CSV = REPO_ROOT / "data" / "seed" / "gpc_projects.csv"
PROJECTS_CSV = REPO_ROOT / "data" / "seed" / "projects.csv"

HEADING = "## Thomson–Vogtle: not in the public IRP project list (#52)"
SEARCH_TERMS = ("vogtle", "waynesboro", "thomson", "burke", "Plant Vogtle")
# Every page the section cites as a hit.
CITED_PAGES = ("p97", "p100", "p189", "p190", "p191", "p192", "p209", "p211", "p212", "p382",
               "p420", "p425", "p428", "p429", "p437", "p452", "p453", "p495")
THOMSON_IDS = {"14222", "17993"}
URQUHART_IDS = {"6852", "6810 O"}
GOSHEN_AREA_ID = "21116"


def flat(text: str) -> str:
    """Whitespace-normalized, so a phrase wrapped across lines (or \\r\\n) still matches."""
    return " ".join(text.split())


def section() -> str:
    text = AUDIT.read_text(encoding="utf-8")
    assert HEADING in text, f"{AUDIT.name} lost the #52 finding section"
    body = text.split(HEADING, 1)[1]
    return flat(re.split(r"\r?\n## ", body, maxsplit=1)[0])


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_finding_states_the_conclusion():
    body = section()
    assert "has **no planned Thomson–Vogtle project**" in body
    assert "no Table 2 row (the Ten-Year Plan project list) mentions Vogtle" in body


def test_finding_names_the_search_terms_and_pages_searched():
    body = section()
    assert "**all 668 pages**" in body
    for term in SEARCH_TERMS:
        assert term in body, f"search term {term!r} missing from the finding"
    for page in CITED_PAGES:
        assert re.search(rf"\b{page}\b", body), f"hit page {page} missing from the finding"


def test_prompt_points_to_the_finding():
    prompt = flat(PROMPT.read_text(encoding="utf-8"))
    assert "no Thomson–Vogtle project in the public 2025 IRP list (#52)" in prompt
    assert "Thomson–Vogtle: not in the public IRP project list" in prompt


def test_no_seed_project_mentions_vogtle():
    # If this fails, a Vogtle project was added: the #52 finding is stale, update the doc.
    for path in (GPC_CSV, PROJECTS_CSV):
        hits = [r["project_id"] for r in rows(path) if "VOGTLE" in r["project_name"].upper()]
        assert hits == [], f"{path.name} now has Vogtle projects {hits}; update docs/data_audit.md"


def test_seed_matches_what_the_finding_says_we_have():
    projects = {r["project_id"]: r for r in rows(PROJECTS_CSV)}
    thomson = {pid for pid, r in projects.items() if "THOMSON" in r["project_name"].upper()}
    assert thomson == THOMSON_IDS
    assert URQUHART_IDS <= projects.keys()
    for pid in URQUHART_IDS:
        assert projects[pid]["project_name"].startswith("Urquhart")
    # 21116 is parsed from the IRP but left out of projects.csv as unlocated.
    gpc = {r["project_id"]: r for r in rows(GPC_CSV)}
    assert gpc[GOSHEN_AREA_ID]["project_name"] == "GOSHEN AREA STRATEGIC SOLUTION"
    assert gpc[GOSHEN_AREA_ID]["source_page"] == "382"
    assert GOSHEN_AREA_ID not in projects
