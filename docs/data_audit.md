# Data audit: the top 10 live overlaps (#39)

**Result:** we checked all 10 overlaps and the 11 distinct projects in them. All 11 are
**confirmed**: none was corrected or excluded. `data/seed/projects.csv`,
`location_overrides.csv` and `build_dataset.py` are unchanged, and the demo database does not
need a reload.

There is one open question, about **0139 M,N** (the center it is given, not whether its
stations are right). See [Open question](#open-question-where-to-center-0139-mn).

## What was audited, and from where

- **Ranking:** `GET https://gridwatch-b3trj.ondigitalocean.app/api/overlaps`, fetched
  2026-09-26 23:31 UTC. It returned 39 overlaps, ranked by score. The deployed site runs
  `main` against the shared demo database. At audit time (`test-branch-1` at `1b98839`),
  `scripts/check_demo_data.py` confirmed that this database serves exactly what
  `data/seed/projects.csv` loads: 115 projects and 39 overlaps. So the live ranking is the
  committed data's ranking.
- **Project facts** (name, in-service/need date, cost) come from the sponsor PDFs. These are
  committed under `data/source/Project Listings/`. Each is read at the
  `source_page` in `desc_projects.csv` / `gpc_projects.csv`:
  - DESC: `Dominion Energy/2024-2028-2million-and-above-project-descriptions.pdf` (44 pages,
    one project per page).
  - GPC: `Georgia Power/2025 IRP Volume 3 PUBLIC DISCLOSURE.pdf` (668 pages; the Ten-Year Plan
    project sheets). GPC costs are `REDACTED` on every sheet, so `est_cost_usd` is blank for
    all GPC rows. GPC's "Need Date" is used as the in-service date, as the sponsor's table
    does.
- **Locations:** each station was checked in three ways:
  - the OSM feature it matched in the committed caches (`data/interim/osm_substations_*.json`:
    id, name, operator and coordinates);
  - the sponsor's starter table (`data/seed/projects_seed.csv`), where it covers the station;
  - the PDF's own description (line lengths, "at McIntosh", etc.).

  For the one hand-placed station (Okatie), we also ran a live Overpass query for
  substations within 3 km of the point (overpass-api.de, 2026-09-26 23:36 UTC).

### What `low` means here

`low` does not mean "probably wrong". A project is `low` when any of its endpoints is one of
these:

- an OSM match with no `operator` tag (Jasper);
- a manual coordinate (Okatie);
- a "nearest same-named candidate" pick (Savannah's GOSHEN);
- not in OSM at all (PURRYSBURG, Hooks).

A project is `confirmed` only when every endpoint is a unique, exact-name match on an
operator-tagged record. The audit below judges each `low` project on the evidence instead of
on its label.

## The 10 overlaps

Distances are between project centers (haversine). The time gap is the gap between
in-service dates. "Margin" is how far a center could move before the pair would stop
counting as an overlap (25 mi minus the distance). A center moved by *d* changes the pair's
distance by at most *d*.

| Rank | Overlap | Project A | Project B | Distance | Time gap | Margin | Sponsor pair? | Verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | OVL_3 | 06367 D - G Jasper – Okatie 230 kV #2: Construct | 20277 SAV: MCINTOSH - PURRYSBURG 230KV REACTORS | 5.66 mi | 152 d | 19.3 mi | yes (DESC_3–GPC_2, 5.65 mi) | real |
| 2 | OVL_4 | 06367 D - G Jasper – Okatie 230 kV #2 | 20065 SAV: GOSHEN (SAV) - MCINTOSH 115KV LINE REBUILD | 7.40 mi | 517 d | 17.6 mi | yes (DESC_3–GPC_3, 7.55 mi) | real |
| 3 | OVL_9 | 06367 D - G Jasper – Okatie 230 kV #2 | 20785 SAV: GOSHEN (SAV) - KRAFT 115KV LINE REBUILD | 11.81 mi | 517 d | 13.2 mi | no | real |
| 4 | OVL_11 | 20277 MCINTOSH - PURRYSBURG 230KV REACTORS | 6808 S Okatie-Bluffton 115kV: Rebuild | 14.34 mi | 365 d | 10.7 mi | yes (DESC_5–GPC_2, 14.34 mi) | real |
| 5 | OVL_17 | 20067 SAV: DEPTFORD - MAGNOLIA 115KV RECONDUCTOR | 6808 S Okatie-Bluffton 115kV: Rebuild | 18.08 mi | 0 d | 6.9 mi | no | real |
| 6 | OVL_1 | 20793 EVANS PRIMARY - THURMOND DAM (USA) #5 115KV REBUILD | 6810 A Hooks - Thurmond 115kV Tie: Rebuild | 4.09 mi | 3074 d | 20.9 mi | yes (DESC_2–GPC_1, 4.09 mi) | real |
| 7 | OVL_2 | 20794 EVANS PRIMARY - THURMOND DAM (USA) #6 115KV REBUILD | 6810 A Hooks - Thurmond 115kV Tie: Rebuild | 4.09 mi | 3074 d | 20.9 mi | no (#6 is the parallel circuit of the sponsor's #5) | real |
| 8 | OVL_16 | 0139 M,N Okatie 230-115kV Substation, Jasper – Yemassee 230kV #1 Fold-in | 20277 MCINTOSH - PURRYSBURG 230KV REACTORS | 16.16 mi | 517 d | 8.8 mi | no | real (distance likely overstated; see the open question) |
| 9 | OVL_14 | 20065 GOSHEN (SAV) - MCINTOSH 115KV LINE REBUILD | 6808 S Okatie-Bluffton 115kV: Rebuild | 14.61 mi | 730 d | 10.4 mi | yes (DESC_5–GPC_3, 14.81 mi) | real |
| 10 | OVL_18 | 20066 SAV: BOULEVARD - DEPTFORD 115KV RECONDUCTOR | 6808 S Okatie-Bluffton 115kV: Rebuild | 18.27 mi | 365 d | 6.7 mi | no | real |

Five of the ten are pairs from the sponsor's golden table, at the sponsor's distances (within
0.2 mi). Every time gap was recomputed from the PDF dates below and matches the API.

## The 11 projects

**Location source** gives the OSM feature (from the committed caches) or the override for
each endpoint, with its coordinates.

### 06367 D - G: Jasper – Okatie 230 kV #2: Construct (DESC, `low`)

| | |
|---|---|
| **PDF** | DESC p. 23. Planned in-service 12/31/25; cost $23,787,423. Both match the CSV. |
| **PDF description** | "Construct a 230 kV line … from Jasper to Okatie 230/115kV Substation. The line is estimated to be 6.5 miles long." |
| **Location source** | Jasper: OSM `way/185380597` "Jasper Substation" (no operator), 32.360699, -81.124152. Okatie: `location_overrides.csv`, 32.333758, -81.032495. |
| **Verdict** | **Confirmed** |

**Evidence for the verdict:**

- **Jasper:**
  - It is the only substation of that name in any cache. It is 2 mi east of the Savannah
    River (SC side), in Jasper County, across the river from Plant McIntosh (3.0 mi).
  - It is 0.11 mi from the sponsor's "Jasper Sub" (DESC_3: 32.35912, -81.1246).
- **Okatie:**
  - It is the sponsor's own "Okatie Sub" coordinate (DESC_3 and DESC_5).
  - The live Overpass query found an unnamed 230 kV `power=substation` (`way/1064022697`,
    `substation=switching`, 32.3337624, -81.0326063) 0.01 mi from that point, and another
    230 kV yard (`way/498967280`) 0.15 mi away. So a real 230 kV station is where the
    override puts Okatie. It is not in our caches because they keep only named features.
- **Line length:** Jasper to Okatie is 5.66 mi in a straight line, which fits the PDF's
  6.5-mi line.

### 20277: SAV: MCINTOSH - PURRYSBURG 230KV REACTORS (GPC, `low`)

| | |
|---|---|
| **PDF** | GPC p. 227 (Teams # 20277). Need date 06/01/2026; cost REDACTED. Both match the CSV. |
| **PDF description** | "Install reactors on the McIntosh - Purrysburg (Black and White) 230kV tie lines **at McIntosh**. Rebuild 0.1 miles (GPC portion)…" |
| **Location source** | MCINTOSH: OSM `way/121624352` "McIntosh Substation", operator Georgia Power, 32.352116, -81.175112. PURRYSBURG: no OSM substation by that name, so it has blank coordinates. |
| **Verdict** | **Confirmed** |

**Evidence for the verdict:**

- The work is at McIntosh (reactors) plus 0.1 mi of line, so centering the project on
  McIntosh is where the work actually happens.
- McIntosh is a unique, operator-tagged exact match. It sits on the GA bank at Plant McIntosh
  and is identical to the sponsor's GPC_2 point.
- It is `low` only because PURRYSBURG is missing. The sponsor also left PURRYSBURG blank.

### 20065: SAV: GOSHEN (SAV) - MCINTOSH 115KV LINE REBUILD (GPC, `low`)

| | |
|---|---|
| **PDF** | GPC p. 314 (Teams # 20065). Need date 06/01/2027; cost REDACTED. |
| **PDF description** | "Rebuild the Goshen (Savannah) - Georgia Pacific (Rincon) section, approximately 6.7 miles…" |
| **Location source** | GOSHEN: OSM `way/1008141064` "Goshen Substation", Georgia Power, 32.248701, -81.209472, picked by `nearest_to_other_end`. MCINTOSH: `way/121624352` (as above). |
| **Verdict** | **Confirmed** |

**Evidence for the verdict:**

- The PDF says "(SAV)"/"(Savannah)" and "Rincon".
- The cache has two Georgia Power "Goshen Substation" features. The one we use is in
  Effingham County near Rincon, 7.4 mi from McIntosh. The other (`way/52019569`, 33.320,
  -81.995) is near Augusta, 82 mi away.
- Our GOSHEN is identical to the sponsor's GPC_3 point.
- 7.4 mi between the ends fits a line with a 6.7-mi Goshen–Rincon section.

### 20785: SAV: GOSHEN (SAV) - KRAFT 115KV LINE REBUILD (GPC, `low`)

| | |
|---|---|
| **PDF** | GPC p. 313 (Teams # 20785). Need date 06/01/2027; cost REDACTED. |
| **PDF description** | "Rebuild 9.3 miles of Goshen - Kraft 115kV line from Kraft - Godley J - Rice Hope…" |
| **Location source** | GOSHEN: `way/1008141064` (as above). KRAFT: OSM `way/121986375` "Kraft Substation", Georgia Power, 32.148135, -81.145983. |
| **Verdict** | **Confirmed** |

**Evidence for the verdict:**

- It is the same Savannah-area Goshen: 7.9 mi from Kraft, against 94.8 mi for the Augusta
  Goshen.
- KRAFT is a unique, operator-tagged exact match on the Savannah River north of Savannah (the
  paper-mill area).
- The 7.9 mi between the ends fits a 9.3-mi rebuild that runs via Godley J and Rice Hope.

### 6808 S: Okatie-Bluffton 115kV: Rebuild (DESC, `low`)

| | |
|---|---|
| **PDF** | DESC p. 10. Planned in-service 06/01/2025; cost $40,660,000. Both match the CSV. |
| **PDF description** | End-of-life rebuild of the line (steel structures, 1272 ACSR). |
| **Location source** | Okatie: override (as for 06367 D - G). Bluffton: OSM `way/498967268` "Bluffton Substation", operator South Carolina Electric & Gas (DESC's former name), 32.235027, -80.853384. |
| **Verdict** | **Confirmed** |

**Evidence for the verdict:**

- Bluffton is a unique, operator-tagged exact match at Bluffton, SC. It is identical to the
  sponsor's DESC_5 point.
- For Okatie, see the evidence under 06367 D - G.
- The center is identical to the sponsor's DESC_5 center.

### 20067: SAV: DEPTFORD - MAGNOLIA 115KV RECONDUCTOR (GPC, `confirmed`)

| | |
|---|---|
| **PDF** | GPC p. 245 (Teams # 20067). Need date 06/01/2025; cost REDACTED. |
| **PDF description** | "Reconductor the Deptford - Magnolia 115kV line (approximately 5 miles)…" |
| **Location source** | DEPTFORD: OSM `way/122007500`, Georgia Power, 32.066828, -81.048384. MAGNOLIA: OSM `way/121857248`, Georgia Power, 32.022687, -81.086181. |
| **Verdict** | **Confirmed** |

**Evidence for the verdict:** both are unique, operator-tagged exact matches in Savannah. The
3.8 mi between them fits a line of about 5 mi.

### 20793: EVANS PRIMARY - THURMOND DAM (USA) #5 115KV REBUILD (GPC, `confirmed`)

| | |
|---|---|
| **PDF** | GPC p. 410 (Teams # 20793). Need date 06/01/2033; cost REDACTED. |
| **PDF description** | "Rebuild approximately 5.45 miles of Euchee Creek - Thurmond Dam segment… Replace the main bus… at Thurmond Dam (USA)." |
| **Location source** | EVANS PRIMARY: OSM `way/52103255`, Georgia Power, 33.543994, -82.168648. THURMOND: OSM `way/52102019` "Thurmond Substation", Georgia Power, 33.660127, -82.195931. THURMOND DAM is renamed to THURMOND in `endpoints.ENDPOINT_OVERRIDES`. |
| **Verdict** | **Confirmed** |

**Evidence for the verdict:**

- Both points are identical to the sponsor's GPC_1 points.
- Thurmond Substation is at the J. Strom Thurmond (Clarks Hill) dam on the GA bank.
- The 8.2 mi between the ends fits the line.

### 20794: EVANS PRIMARY - THURMOND DAM (USA) #6 115KV REBUILD (GPC, `confirmed`)

| | |
|---|---|
| **PDF** | GPC p. 411 (Teams # 20794). Need date 06/01/2033; cost REDACTED. |
| **PDF description** | "Rebuild approximately 8.9 miles of the Evans Primary - Thurmond Dam (USA) #6 115kV line…" |
| **Location source** | Same two features as 20793. |
| **Verdict** | **Confirmed** |

**Evidence for the verdict:**

- It is the parallel #6 circuit between the same two stations, so it shares 20793's center.
- The 8.9-mi line length closely matches the 8.2-mi straight-line distance between the ends.

### 6810 A: Hooks - Thurmond 115kV Tie: Rebuild (DESC, `low`)

| | |
|---|---|
| **PDF** | DESC p. 31. Planned in-service 12/31/2024; cost $2,200,080. Both match the CSV. |
| **PDF description** | "Rebuilding section of line between Hooks and Thurmond. Approximately 2.3 miles." |
| **Location source** | Hooks: no OSM substation by that name, so it has blank coordinates. Thurmond: `way/52102019` (as above). |
| **Verdict** | **Confirmed** |

**Evidence for the verdict:**

- It is centered on Thurmond, exactly as in the sponsor's DESC_2 row, which also leaves Hooks
  blank. OVL_1 therefore reproduces the sponsor's 4.09 mi.
- It is a short (2.3 mi) rebuild of a tie line into GPC's Thurmond station. To break OVL_1
  or OVL_2 (20.9 mi margin), Hooks would have to be more than 40 mi from Thurmond, which
  does not fit a tie line.

### 0139 M,N: Okatie 230-115kV Substation, Jasper – Yemassee 230kV #1 Fold-in (DESC, `low`)

| | |
|---|---|
| **PDF** | DESC p. 3. Planned in-service 12/31/2024; cost $11,116,933. Both match the CSV. |
| **PDF description** | "Expand existing Okatie Transmission sub, add a 230-115 autobank and fold the Jasper – Yemassee 230 kV #1 line into the 230 kV side. Construct two additional 115 kV bus tie lines." |
| **Location source** | `endpoints.ENDPOINT_OVERRIDES["0139 M,N"] = ("Jasper", "Yemassee")`. Jasper: `way/185380597` (as above). Yemassee: OSM `way/185317032` "Yemassee Substation", operator South Carolina Electric & Gas Company, 32.697426, -80.863793. |
| **Verdict** | **Confirmed** (both stations are right; the center is flagged below) |

**Evidence for the verdict:**

- Both named stations are right. Jasper is as above. Yemassee is a unique, operator-tagged
  exact match at Yemassee, SC.
- The project's center is the midpoint of the 27.8-mi Jasper–Yemassee line (32.529,
  -80.994). But the PDF puts the work at the Okatie substation, and that midpoint is
  **13.7 mi from Okatie**.
- The overlap itself is real either way. With the project centered on Okatie, OVL_16 would
  be 8.42 mi, not 16.16 mi.

### 20066: SAV: BOULEVARD - DEPTFORD 115KV RECONDUCTOR (GPC, `confirmed`)

| | |
|---|---|
| **PDF** | GPC p. 277 (Teams # 20066). Need date 06/01/2026; cost REDACTED. |
| **PDF description** | "Reconductor the Boulevard - Deptford 115kV line (approximately 8 miles)… Upgrade main bus and jumpers at Bolton substation…" |
| **Location source** | BOULEVARD: OSM `way/381797798`, Georgia Power, 32.041231, -81.144464. DEPTFORD: `way/122007500` (as above). |
| **Verdict** | **Confirmed** |

**Evidence for the verdict:**

- Both are unique, operator-tagged exact matches in Savannah. The 5.9 mi between them fits
  a line of about 8 mi.
- The Bolton station the PDF mentions is OSM's "Bolton Street Substation" (`way/964045266`,
  Georgia Power). It lies between the two ends: 3.6 mi from Boulevard and 2.4 mi from
  Deptford.

## Open question: where to center 0139 M,N

For 0139 M,N, the team chose to locate the project by the line it folds in:
`ENDPOINT_OVERRIDES` maps it to ("Jasper", "Yemassee"), with the comment "the line locates the
project, the rules would only find Okatie". `test_endpoints.py` pins that choice
(`REQUIRED_OVERRIDES`, `test_endpoints_for_prefers_the_override`). The choice was made before
Okatie could be placed. Okatie can be placed now, through `location_overrides.csv`.

The alternative is to drop the endpoint override. The rule-based split already gives
("Okatie", None), and the project would then sit on the substation it expands. Effect on the
data:

- 39 → 48 overlaps (9 new pairs, all Savannah-area GPC projects between 9.6 and 23.2 mi
  away).
- OVL_16 would shrink from 16.16 to 8.42 mi.
- 0139 M,N–20065 would shrink from 19.58 to 9.61 mi.

We did **not** make this change in #39, for three reasons:

- The stations are right, so no location is wrong in the sense this audit fixes.
- The change goes through `endpoints.py`, which this ticket does not own, rather than
  `location_overrides.csv`.
- It would mean changing existing tests that deliberately pin the current choice.

It needs a team decision and its own ticket. That ticket would change `endpoints.py`, update
the pinned endpoint tests and `desc_projects.csv` (re-run `parse_desc`), regenerate
`projects.csv`, update `AUDITED_TOP10_PROJECTS` in `test_build_dataset.py`, and reload the
demo database.

## Thomson–Vogtle: not in the public IRP project list (#52)

The published challenge pairs DESC's Urquhart work with "Georgia Power's Thomson–Vogtle
transmission line" near Augusta. We have the Urquhart projects (6852, 6810 O) and both
Thomson projects (14222, 17993), but no project names Vogtle.

**Conclusion:** the public 2025 IRP Vol 3 has **no planned Thomson–Vogtle project**. No
line or project anywhere in the PDF is named Thomson–Vogtle (or Vogtle–Thomson), and no
Table 2 row (the Ten-Year Plan project list) mentions Vogtle. It is not hidden by
redaction: Table 2 redacts only costs, never project names. So seed data is unchanged and the
demo database does not need a reload.

**How we searched:** we extracted the text of **all 668 pages** with pdfplumber (every page
has a text layer, so none were skipped). We then matched each line, ignoring case, against
`vogtle` (this also covers "VOGTLE" and "Plant Vogtle"), `waynesboro`, `thomson`, `burke`
and `thomson - vogtle` / `vogtle - thomson`. `burke` and both line names had no hits.

Hits for a transmission project or line:

| Page | Where | Text | What it is |
|---|---|---|---|
| p189 | Table 2 | 14222 THOMSON PRIMARY [230/115KV SECOND TRANSFORMER] | planned; already in `projects.csv` |
| p190 | Table 2 | 17993 EVANS PRIMARY - THOMSON [PRIMARY 115KV REBUILD] | planned; already in `projects.csv` |
| p420, p425 | project sheets | the same two projects (14222, 17993) | planned; already in `projects.csv` |
| p191 | Table 3, cancelled | 19623 GTC: AUGUSTA CORPORATE PARK - VOGTLE 230KV REBUILD | cancelled, not planned |
| p191 | Table 3, cancelled | 20266 GTC: GOSHEN - VOGTLE 230KV REBUILD | cancelled, not planned |
| p192 | Table 4, completed | 14271 THOMSON PRI - WARRENTON PRI 115KV WHITE LINE REBUILD | completed (2024), not planned |
| p209 | Table 8, operating guides | Augusta Corporate Park - Vogtle 230kV Operating Guide | operating procedure, not construction |
| p211 | Table 8, operating guides | Goshen - Vogtle 230kV Operating Guide; Evans Primary - Thomson Primary 115kV Operating Guide | operating procedures, not construction |
| p212 | Table 8, operating guides | Thomson Primary 230/115kV Bank C Operating Guide | operating procedure, not construction |
| p382 | project sheet | 21116 GOSHEN AREA STRATEGIC SOLUTION: "a 230kV switching station on the Waynesboro - Wilson 230kV line ... outside of the existing constrained Goshen - Vogtle corridor" | planned, but not Thomson–Vogtle (see below) |
| p452, p453 | Hatch–Wadley 500 kV study tables | Thomson 500/230 kV Bank D | existing equipment it monitors, not a project |

The other hits are about generation, not transmission projects: p97 and p100 (Vogtle and
McIntosh units in study cases), p428 and p429 (the Vogtle nuclear FSAR study), p437 (the
VOGTLE 1–4 unit list), and p495–p498 (unit outage probability tables).

**The nearest real project is 21116, Goshen Area Strategic Solution** (p382, need date
2030-06-01). It is on the Augusta side, near the Goshen–Vogtle corridor. It is already in
`gpc_projects.csv`, but `build_dataset` leaves it out of `projects.csv` as `unlocated`,
because its name has no substation to locate. It could be placed only by hand-picking
endpoints (Goshen, plus a switching station that is not built yet). We did not do that in
the 30-minute timebox for #52. It would need its own ticket and a team decision.

**Guard:** `backend/tests/test_thomson_vogtle_finding.py` checks this section against the
seed CSVs. If a Vogtle project is added to the seed data later, that test fails, which flags
this finding as stale.

## Regression guard

`backend/tests/test_build_dataset.py::test_audited_top10_projects_stay_where_the_audit_confirmed_them`
covers each of the 11 projects. It checks that the center `build_dataset` computes stays
within 1 mi of the center built from the audited station coordinates above. A change to the
matcher, the caches or the overrides that moves one of these projects fails the test, which
flags that the audit needs redoing for that project.
