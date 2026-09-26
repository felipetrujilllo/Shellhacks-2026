"""Split a utility project name into the substation names at its ends.

Every project has to be located by substation name, so "Okatie-Bluffton 115kV: Rebuild" must
become ("Okatie", "Bluffton") and "Edenwood Sub: #1 & #2 230-115kV Autobanks" must become
("Edenwood", None). Pure string work, no I/O.

Two entry points:
- `split_endpoints(project_name)` — the rule pipeline below, name only.
- `endpoints_for(project_id, project_name)` — consults `ENDPOINT_OVERRIDES` (irregular names
  keyed by project_id, DESC or Georgia Power) first and falls back to `split_endpoints`.
  Parsers and `pipeline.build_dataset` call this one.

The rule pipeline, in order:
1. drop a utility prefix ("SAV:", "GTC:") and parenthetical tags ("(USA)", "(1.4 miles)");
2. cut at the first ":" — what follows is the work ("Rebuild", "Construct Tap");
3. cut at the first voltage ("115kV", "115-13.8 kV", "230/115KV") — station names come before
   it, equipment, circuit numbers and second lines after it;
4. cut at a work word ("Rebuild", "Tap", "Fold-in"…), together with any dash in front of it;
5. cut at a joiner ("&", "/", ",", "and") — only the first of several lines/sites is kept;
6. split what is left on dashes (en/em dash, or a hyphen not between two digits) and keep the
   first and last pieces — for a three-station line those are the line's ends;
7. tidy each endpoint: collapse spaces, drop trailing "Sub"/"Substation"/"Transmission"/
   "Line"/"Tie"/"Loop". Original casing is kept.
"""

from __future__ import annotations

import re

# A short all-caps utility/region tag at the very start: "SAV: ", "GTC: ", "MEAG: ".
UTILITY_PREFIX = re.compile(r"^[A-Z]{2,5}:\s*")

# "(Queensboro-James Island Sect)", "(USA)", "(1.4 miles)".
PARENTHETICAL = re.compile(r"\s*\([^)]*\)")

# "115kV", "115 kV", "230-115kV", "115-13.8 kV", "230/115KV". The hyphen/slash here joins
# two numbers, which is why a hyphen between digits is never an endpoint separator.
VOLTAGE = re.compile(r"\b\d+(?:\.\d+)?(?:\s*[-/]\s*\d+(?:\.\d+)?)*\s*kV\b", re.IGNORECASE)

# Words that start the description of the work rather than naming a place. A dash right
# before one of them ("115KV-Rebld", "Tap – Construct") is not a separator, so it goes too.
WORK_WORDS = (
    "Rebuilds?",
    "Rebld",
    "Construct",
    "Replace",
    "Upgrade",
    "Reconductor",
    "Tap",
    "Fold-in",
)
WORK_TERM = re.compile(r"\s*[-–—]?\s*\b(?:" + "|".join(WORK_WORDS) + r")\b", re.IGNORECASE)

# Joins two lines or sites in one name ("A-B 230kV & A-C 230kV", "Sub and Fold-in").
JOINER = re.compile(r"\s*(?:&|/|,|\band\b)", re.IGNORECASE)

# En dash, em dash, or a hyphen that is not between two digits ("VCS1-Denny" splits,
# "1-3" does not).
SEPARATOR = re.compile(r"\s*(?:–|—|(?<!\d)-|-(?!\d))\s*")

# Descriptors that trail a station name without being part of it.
TRAILING_DESCRIPTOR = re.compile(
    r"(?:\s+(?:Sub|Substation|Transmission|Line|Tie|Loop)\b)+$", re.IGNORECASE
)

# Names the rules cannot read correctly, keyed by project_id, each with its explicit result.
ENDPOINT_OVERRIDES: dict[str, tuple[str, str | None]] = {
    # Two lines joined by "&" (Queensboro - Ft Johnson, Queensboro-Bayfront): the first line.
    "6807 B": ("Queensboro", "Ft Johnson"),
    # Church Creek – Faber Place – Charleston Transmission: three stations, the line's ends.
    "6847 A-B, D-H": ("Church Creek", "Charleston"),
    # Cameron Jct – Cameron – St Matthews: three stations, the line's ends.
    "6810 T": ("Cameron Jct", "St Matthews"),
    # "Okatie 230-115kV Substation, Jasper – Yemassee 230kV #1 Fold-in": a substation job plus
    # a fold-in line; the line locates the project, the rules would only find Okatie.
    "0139 M,N": ("Jasper", "Yemassee"),
    # Williams St, AM Williams and McMeekin substation jobs, no line: the first site.
    "1060A, I, L": ("Williams St", None),
    # Georgia Power: "EVANS PRIMARY - THURMOND DAM (USA) #5/#6 115KV REBUILD", circuits 5 and 6
    # between the same two stations. The station at the dam is "Thurmond Substation" in OSM
    # (DESC's Hooks - Thurmond line ends there too); "THURMOND DAM #5" matches nothing.
    "20793": ("EVANS PRIMARY", "THURMOND"),
    "20794": ("EVANS PRIMARY", "THURMOND"),
}


def _cut(pattern: re.Pattern[str], text: str) -> str:
    """Everything before the first match of `pattern` (all of `text` if none)."""
    match = pattern.search(text)
    return text[: match.start()] if match else text


def _tidy(name: str) -> str:
    name = " ".join(name.split())
    name = TRAILING_DESCRIPTOR.sub("", name)
    return name.strip(" -–—#.,")


def split_endpoints(project_name: str) -> tuple[str, str | None]:
    """(name_a, name_b) for a project name; name_b is None for a single-site project."""
    text = UTILITY_PREFIX.sub("", project_name.strip())
    text = PARENTHETICAL.sub("", text)
    text = text.split(":", 1)[0]
    for pattern in (VOLTAGE, WORK_TERM, JOINER):
        text = _cut(pattern, text)

    pieces = [_tidy(piece) for piece in SEPARATOR.split(text)]
    pieces = [piece for piece in pieces if piece]
    if not pieces:
        raise ValueError(f"no substation name found in project name {project_name!r}")
    if len(pieces) == 1:
        return pieces[0], None
    return pieces[0], pieces[-1]


def endpoints_for(project_id: str, project_name: str) -> tuple[str, str | None]:
    """The override for `project_id` if there is one, otherwise the rule-based split."""
    if project_id in ENDPOINT_OVERRIDES:
        return ENDPOINT_OVERRIDES[project_id]
    return split_endpoints(project_name)
