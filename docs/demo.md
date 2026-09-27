# Relay — demo script (< 3 min)

The one demo script (it replaces the old one in `docs/project.md`). Figures are in the
[Figures](#figures) table at the bottom; `backend/tests/test_demo_doc.py` recomputes them from
`data/seed/projects.csv` plus the standing sample submissions (`backend/app/sample_submissions.csv`)
and fails if the engine and this page drift apart.

**Sample data on the map.** Every visitor also sees "Tallapoosa Grid Partners" (Alabama):
31 made-up sample projects the API serves as if someone had already uploaded them, with the
"Uploaded" tag (#62, `docs/api.md` "Standing sample submissions"). They are **not** a real
utility's filing — say so if a judge asks. 7 of the pairs below are theirs.

## The pair we click

**#5 — DESC "Jasper – Okatie 230 kV #2: Construct" ↔ GPC "SAV: MCINTOSH - PURRYSBURG 230KV
REACTORS"** (`OVL_3`, tier `site_logistics`). It has the strongest savings story: the lines
come within 3.03 mi of each other, the two jobs go into service only 152 days (~5 months)
apart, and the DESC side's public cost gives a real estimate, $709,579 of shared
mobilization.

**Why #1–#4 rank above it (say it in one line):** three crossings and one shared-land pair
come first — the sample Lanett – LaGrange Primary tie line touches Georgia Power's Dresden –
LaGrange Primary at LaGrange Primary, Hooks – Thurmond touches Evans Primary – Thurmond Dam #5
and #6 at the Thurmond substation, and the sample Columbia – Blakely West line runs 0.71 mi
from Blakely Primary – Huckleberry; a crossing must be coordinated (design, outage timing)
whenever each is built, even ~8.4 years apart; the crew/equipment savings are largest where
projects are close in time, which is why we click #5.

## Script

1. **(15s) Hook.** Neighboring utilities plan their transmission work in isolation — FERC
   Order No. 1920 (2024) exists because of it. Relay puts two utilities' public plans on one
   map.
2. **(30s) Map.** Dominion Energy South Carolina and Georgia Power, two colors, live data from
   their public filings, plus a sample third utility shown as uploads (Tallapoosa Grid
   Partners, made-up demo data). 46 flagged pairs; each card shows its tier chip.
3. **(45s) Click #5, Jasper – Okatie ↔ McIntosh – Purrysburg.** Closest approach 3.03 mi
   (site logistics: shared laydown yards and deliveries), centers 5.66 mi apart, in service
   152 days apart, score 83%. Say the number: **about $709,579** from sharing mobilization.
   Then the one line on #1–#4 above: touching lines must coordinate, even 8 years apart.
4. **(30s) Zoom out.** "46 coordination opportunities worth an estimated $5,853,104" — 7 of
   them, $1,610,338, involve the sample uploads.
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
same demo database (Tiger Data) the deployed site reads and merges in the standing sample
submissions (#62), and recomputed offline from `data/seed/projects.csv` (the file that
database is loaded from) plus `backend/app/sample_submissions.csv` — the two agree exactly.

The deployed site (`main`) serves the same database, so the published pairs' distances, time
gaps and savings are the same there. It shows the sample submissions (and their 7 pairs), the
tier chips and the tier-first ranks only once `test-branch-1` is promoted to `main`; until
then it has the 39 published pairs ($4,242,766) and ranks them as its code does. **Re-check
the rank numbers on the live site after promotion.**

| Figure | Value |
|---|---|
| Flagged pairs | 46 |
| Sample-submission pairs | 7 |
| Pairs by tier | crossing 3, shared_land 1, site_logistics 5, crews 37 |
| Total estimated savings | $5,853,104 |
| Sample-submission savings | $1,610,338 |
| Clicked pair | OVL_3 |
| Clicked pair rank | 5 |
| Clicked pair tier | site_logistics |
| Clicked pair closest approach | 3.03 mi |
| Clicked pair center distance | 5.66 mi |
| Clicked pair time gap | 152 days |
| Clicked pair score | 83% |
| Clicked pair estimated savings | $709,579 |
| #1 pair | SUB:19598\|SUB-7220 |
| #1 tier | crossing |
| #1 closest approach | 0 mi |
| #1 time gap | 0 days |
| #2 pair | OVL_1 |
| #2 tier | crossing |

The total is the sum of every pair's `est_savings_usd` (all 46 have one: each published pair
has at least one DESC project with a published cost, and every sample project has a cost).
#1 is a sample pair (Lanett – LaGrange Primary ↔ MEAG: Dresden – LaGrange Primary, same
in-service date). #2 and #3 (`OVL_1`, `OVL_2`) estimate only $274 each — 3,074 days apart,
the time factor halves the estimate every year.
