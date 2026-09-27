# Relay — demo script (< 3 min)

The one demo script (it replaces the old one in `docs/project.md`). Figures are in the
[Figures](#figures) table at the bottom; `backend/tests/test_demo_doc.py` recomputes them from
`data/seed/projects.csv` and fails if the engine and this page drift apart.

## The pair we click

**#3 — DESC "Jasper – Okatie 230 kV #2: Construct" ↔ GPC "SAV: MCINTOSH - PURRYSBURG 230KV
REACTORS"** (`OVL_3`, tier `site_logistics`). It has the strongest savings story: the lines
come within 3.03 mi of each other, the two jobs go into service only 152 days (~5 months)
apart, and the DESC side's public cost gives a real estimate, $709,579 of shared
mobilization.

**Why #1 and #2 rank above it (say it in one line):** Hooks – Thurmond ↔ Evans Primary –
Thurmond Dam #5 and #6 physically touch at the Thurmond substation, and a crossing must be
coordinated (design, outage timing) whenever each is built, even ~8.4 years apart; the
crew/equipment savings are largest where projects are close in time, which is why we click #3.

## Script

1. **(15s) Hook.** Neighboring utilities plan their transmission work in isolation — FERC
   Order No. 1920 (2024) exists because of it. Relay puts two utilities' public plans on one
   map.
2. **(30s) Map.** Dominion Energy South Carolina and Georgia Power, two colors, live data from
   their public filings. Along the Savannah River, 39 flagged pairs; each card shows its tier
   chip.
3. **(45s) Click #3, Jasper – Okatie ↔ McIntosh – Purrysburg.** Closest approach 3.03 mi
   (site logistics: shared laydown yards and deliveries), centers 5.66 mi apart, in service
   152 days apart, score 83%. Say the number: **about $709,579** from sharing mobilization.
   Then the one line on #1/#2 above: touching at Thurmond means they must coordinate, even
   8 years apart.
4. **(30s) Zoom out.** "39 coordination opportunities worth an estimated $4,242,766."
5. **(20s) Tech.** Real PDFs → OSM-located substations → Tiger Data (Postgres + PostGIS)
   25-mile overlap job, verified against Sperry's reference table; closest-approach tiers;
   deployed on DigitalOcean. Pitch line (below).
6. **(20s) Close.** "Waze for utility construction — before the digging starts." Next: gate
   on edges, a third utility, live filing ingestion.

## Pitch line

What shipped (#48–#50 are in), said verbatim:

> We rank the way Sperry asked — touching first, then shared land, site and crews — measuring closest approach along the lines. We decide which pairs to flag by project centers, which reproduces Sperry's reference table exactly; moving that gate to edges is our next step.

## Figures

As of 2026-09-27. Read live from `GET /overlaps` on the `test-branch-1` API, which reads the
same demo database (Tiger Data) the deployed site reads, and recomputed offline from
`data/seed/projects.csv` (the file that database is loaded from) — the two agree exactly.

The deployed site (`main`) serves the same database, so the pair count, distances, time gaps
and savings are the same there. It shows the tier chips and the tier-first ranks only once
`test-branch-1` is promoted to `main`; until then its ranks are by score alone. **Re-check the
rank numbers on the live site after promotion.**

| Figure | Value |
|---|---|
| Flagged pairs | 39 |
| Pairs by tier | crossing 2, shared_land 0, site_logistics 4, crews 33 |
| Total estimated savings | $4,242,766 |
| Clicked pair | OVL_3 |
| Clicked pair rank | 3 |
| Clicked pair tier | site_logistics |
| Clicked pair closest approach | 3.03 mi |
| Clicked pair center distance | 5.66 mi |
| Clicked pair time gap | 152 days |
| Clicked pair score | 83% |
| Clicked pair estimated savings | $709,579 |
| #1 pair | OVL_1 |
| #1 tier | crossing |
| #1 closest approach | 0 mi |
| #1 time gap | 3,074 days |
| #2 pair | OVL_2 |
| #2 tier | crossing |

The total is the sum of every pair's `est_savings_usd` (all 39 have one: each pair has at
least one DESC project with a published cost). #1's estimate is only $274 — 3,074 days apart,
the time factor halves the estimate every year.
