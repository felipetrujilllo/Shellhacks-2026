# Challenge prompt

Source: `ShellHacks_Challenge_Gridlock.docx` and `finding_real_projects_locations.pdf` in the
sponsor's starter folder (OneDrive package). Sponsor: **Sperry Tech**.

## Prompt — Gridlock

Power grid companies ("utilities") each plan their own future construction projects — new
power lines, upgraded substations, etc. — years in advance. The problem: neighboring
utilities in different states often plan this work without much visibility into what the
other one is doing nearby.

**The challenge:** build a tool that compares at least two utilities' public future
construction plans and flags where their planned work overlaps — either because the projects
are physically close to each other, or because they're scheduled around the same time.

**Why it matters:** when utilities coordinate on nearby projects, they can potentially share
resources (crews, equipment, right-of-way, substation capacity), which saves money and gets
infrastructure built faster. FERC issued Order No. 1920 in 2024 because utilities have
historically planned in isolation.

### Example utilities
- **Utility 1: Dominion Energy South Carolina (DESC)**: 44 projects, one per page, in
  `2024-2028-2million-and-above-project-descriptions.pdf` (SCRTP). Includes cost.
- **Utility 2: Georgia Power (GPC)**: project tables inside `2025 IRP Volume 3 PUBLIC
  DISCLOSURE.pdf` (668 pages; project list in Table 2 on pp. ~177–191, per-project sheets from ~p. 220). Costs are REDACTED.
- They share the Savannah River border, and both are in SERTP. DESC has real planned projects
  along that border that sit close to active GPC work.
- The published challenge's Augusta example (DESC's Urquhart work vs. GPC's Thomson–Vogtle
  line) has no Thomson–Vogtle project in the public 2025 IRP list (#52). See
  `docs/data_audit.md`, "Thomson–Vogtle: not in the public IRP project list".

### What to build
Ingest public future-construction data from at least two utilities and identify where their
planned transmission projects overlap, using two definitions:

- **Geographic overlap (primary):** two projects overlap if their center points are
  **within 25 miles** (straight-line/haversine). Under 25 mi → flag; farther → ignore.
- **Timeline overlap (strong secondary):** projects scheduled in the same build window.
  Recorded as the **time gap in days** between in-service dates, and used *together with*
  geographic overlap, not on its own.

**Expect most of the dataset NOT to overlap.** Finding the real matches is the point.

### Method (from the sponsor's guide)
1. **Get coordinates:** match each project's named endpoints (usually two substations) to real
   features via Overpass Turbo / OSM / Nominatim / Open Infrastructure Map. Query all of a
   utility's substations/lines at once, export GeoJSON, filter to the project list.
2. **Confirm:** re-read the PDF's description/zone/landmarks. Similarly named substations in
   the wrong county are a common false match. If a match can't be confirmed, flag it as
   lower-confidence.
3. **Overlap table:** project center = midpoint of its two named points (or the one point
   if only one is located). Compute haversine distance between every Utility A center and
   every Utility B center; each pair < 25 mi is one row, with the in-service time gap in days.

### Deliverables
- **Required:** an interactive UI (pan/zoom/click, not a static image) showing both
  utilities' planned projects and visually highlighting where overlaps occur.
- **Required:** a **ranked list of the top coordination opportunities**.
- **Bonus:** a rough cost/impact estimate for at least one flagged opportunity (e.g. shared
  land / right-of-way, or a simple explanation of the money saved).
- Format and stack are up to the team. Be creative.
- Only public data. Nothing marked CEII.

### Reference answer (sponsor's starter table: 10 projects → 6 overlaps)
| overlap | A | B | distance_mi | time_gap_days |
|---|---|---|---|---|
| OVL_1 | DESC_2 Hooks–Thurmond 115kV | GPC_1 Evans Primary–Thurmond Dam #5 | 4.09 | 3074 |
| OVL_2 | DESC_3 Jasper–Okatie 230kV #2 | GPC_2 McIntosh–Purrysburg 230kV | 5.65 | 152 |
| OVL_3 | DESC_3 Jasper–Okatie 230kV #2 | GPC_3 Goshen–McIntosh 115kV | 7.55 | 517 |
| OVL_4 | DESC_1 Stevens Creek–Hooks 115kV | GPC_1 Evans Primary–Thurmond Dam #5 | 8.01 | 3074 |
| OVL_5 | DESC_5 Okatie–Bluffton 115kV | GPC_2 McIntosh–Purrysburg 230kV | 14.34 | 365 |
| OVL_6 | DESC_5 Okatie–Bluffton 115kV | GPC_3 Goshen–McIntosh 115kV | 14.81 | 730 |

Verified: haversine (R = 3958.8 mi) on the starter table's `lat_center`/`lon_center`
reproduces all six distances exactly, and the other 19 pairs are all > 25 mi. Use this as
the overlap algorithm's golden test.

## Published spec (ShellHacks challenge page) — closest points and tiers

The challenge text published on the ShellHacks site differs from the starter docs above in
two ways (#51):

- **Distance is measured between closest points, 40 km / 25 mi.** Quoted: "We measure the
  closest points between two projects, not their centers — a 60 km power line can still pass
  within 5 km of the other utility substation, and that counts."
- **Overlaps are ranked in four tiers**, by what the two utilities can share:

| Tier | Closest-point distance | What the utilities can share |
|---|---|---|
| Touching / crossing | 0 (the projects touch or cross) | must coordinate (outage timing, crossing structures) |
| Under 1.6 km | < 1.6 km (1 mi) | can share the land itself (right-of-way, access roads, permits) |
| Under 8 km | < 8 km (5 mi) | can share site logistics (laydown yards, deliveries) |
| Under 40 km | < 40 km (25 mi) | can share crews and equipment |

### Decision (#48–#51)

- **Center gate stays.** A pair is flagged when its project **centers** are < 25 mi apart
  (haversine), exactly as in "What to build" above. Why: there was no time left to move the
  gate, and the center rule reproduces the sponsor's reference table exactly (the golden
  test: 10 projects → the same 6 overlaps and distances).
- **Closest approach sets the tier.** For every flagged pair we also measure the closest
  points of the two projects (each is its A→B line, or its center when an endpoint is
  unknown) and map it to Sperry's tiers, in miles: `crossing` = 0, `shared_land` < 1.0 mi,
  `site_logistics` < 5.0 mi, `crews` otherwise (the 25 mi gate bounds it).
- **Tier-first ranking.** The ranked list is ordered by tier (`crossing` → `shared_land` →
  `site_logistics` → `crews`), then by score. Shipped in #48 (engine), #49 (API), #50 (UI).
- **Known limitation.** Pairs whose lines come within 25 mi but whose centers do not are
  not flagged. Moving the gate from centers to edges (closest points) is the next step.

## Judging criteria
Not listed explicitly. From the deliverables: both utilities on an interactive map with
overlaps highlighted, a ranked opportunity list, a cost/impact estimate (bonus), real
public data correctly located, creativity.

## Other targets
- Best Overall.
- MLH: Best Use of Tiger Data (primary DB), Snowflake API (savings note), DigitalOcean
  (hosting), GoDaddy Registry (domain).
