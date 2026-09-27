# Relay — project plan

> Formerly "GridWatch" (working name). Infrastructure names — the live URL
> `gridwatch-b3trj.ondigitalocean.app` and the App Platform app `gridwatch` — keep the old name.

**One-liner:** "Waze for utility construction — before the digging starts."

Ingests two or more utilities' public transmission construction plans (starting with Dominion
Energy South Carolina and Georgia Power), flags cross-utility project pairs whose centers are
within 25 miles, uses the in-service time gap as a secondary signal, and shows the results on
a map with a ranked list of coordination opportunities. Sponsor challenge: **Sperry Tech —
Gridlock** (spec in `docs/prompt.md`).

**Win condition:** a judge looks at the map for 10 seconds, clicks one flagged pair, and
understands without explanation why that overlap matters and roughly what it would save.

## Architecture

```
[Sponsor PDFs: DESC project sheets (44) + GPC IRP Vol 3 tables]
        │  one-time ETL, committed as CSV/GeoJSON — never live-scraped during the demo
        ▼
[Ingestion script] → parse PDF → match endpoints to OSM substations (Overpass, cached)
   → normalize to the sponsor's project-table shape:
   { project_id, utility, state, project_name, name_a, lat_a, lon_a, name_b, lat_b, lon_b,
     lat_center, lon_center, in_service_date, est_cost (nullable; GPC is REDACTED),
     location_confidence: confirmed | low }
        ▼
[Tiger Data: Postgres + PostGIS]   table: projects (above + geom POINT center, geom LINESTRING a→b)
        ▼
[Overlap detection batch job] → writes `project_overlaps` table
   (the SQL table is project_overlaps, NOT overlaps: OVERLAPS is a reserved word in
   Postgres, so `CREATE TABLE overlaps` is a syntax error. The endpoint stays GET /overlaps.)
   every (a, b) with a.utility != b.utility AND haversine(center_a, center_b) < 25 mi
   row: overlap_id, project_id_a, project_id_b, distance_mi, time_gap_days, score
   distance must be haversine, R = 3958.8 mi (ST_DistanceSphere, not the spheroid
   ST_Distance), so it reproduces the sponsor's reference table exactly
        ▼
[REST API]
   GET /projects       all projects, for map layers
   GET /overlaps       flagged pairs, ranked by score, with distance + time gap
   GET /overlaps/:id   detail for the side panel
        ▼
[React + MapLibre frontend]
   per-utility layers, each project drawn as a line between its two substations,
   flagged pairs highlighted + a connector between centers,
   ranked opportunity list beside the map (click → fly to pair),
   click a pair → side panel: distance, time gap, plain-English cost/impact note
```

Locked decisions:
- **Tiger Data is the only database.**
- **Overlap detection is deterministic SQL**, never delegated to an LLM. Snowflake only
  writes the plain-English savings note (and optionally the NL filter reach feature).
- Overlaps are computed in a **batch job**, not live per request, so the table can be
  inspected and re-run.
- **Overlap rule (from the sponsor spec):** geographic < 25 mi between project centers is the
  gate. The time gap is a secondary signal used for ranking, never a gate on its own.
- **Golden test:** the sponsor's 10-project starter table must produce exactly their 6
  overlaps with matching distances (`docs/prompt.md`).

## Stack
| Layer | Choice |
|---|---|
| Frontend | React + Vite + TypeScript, Tailwind, MapLibre GL JS (`react-map-gl/maplibre`, free CARTO/OpenFreeMap style) |
| Backend | Python + FastAPI (ingestion, overlap job and API in one language; `pytest`) |
| Database | Tiger Data (Postgres + PostGIS + time-series) |
| AI | Snowflake Cortex / REST — savings note only |
| Hosting | DigitalOcean App Platform, deployed from GitHub |
| Domain | `relaygrid.us` — registered at Porkbun, DNS managed by DigitalOcean (#30) |
| Geocoding | Nominatim (cache every result), only if source data has addresses |

## MVP (must ship; the first two map to the sponsor's "Required")
1. Data: the sponsor's 10-project starter table loaded into PostGIS first, then extended
   with more real DESC + GPC projects.
2. Overlap detection, passing the golden test.
3. **Interactive map** with both utilities' projects in distinct colors and overlaps
   highlighted. *(required)*
4. **Ranked list of top coordination opportunities.** Score = closer distance + smaller
   time gap. *(required)*
5. Detail panel: distance, time gap, plain-English "why this matters".
6. **Cost/impact estimate for at least one pair.** *(bonus)* Plan for DESC costs being
   public and GPC costs being REDACTED, e.g. estimate from the DESC side or from
   shared right-of-way miles.
7. Deployed, working public URL.

## Reach (only with MVP done and 6+ hours left)
- Real savings model (e.g. shared mobilization/right-of-way as % of the known project cost).
- A third utility (Santee Cooper via SCRTP, or another SERTP member).
- CSV upload so a judge can plot their own list.
- NL query via Snowflake ("overlaps over $500k in the next 6 months").

**Do not attempt:** live scraping during the demo, auth/accounts, mobile app, payments.

## Data plan
Real data is provided, so there is no synthetic fallback. The work is locating projects.
- **Hour 0:** seed from the sponsor's starter table (`Projects_Overlaps.xlsx`: 10 projects
  with coordinates). The whole pipeline can be built against this before any parsing.
- **DESC:** 44 one-page project sheets with name, ID, description, status, in-service date
  and cost. Regular layout, so text extraction (`pdftotext -layout` / pdfplumber) is easy.
- **GPC:** transmission project list in IRP Vol 3 (Table 2, pp. ~177–191; per-project sheets from ~p. 220): project name,
  in-service date, owner. Costs are REDACTED. Filter to projects near the SC border first.
- **Locating:** project names are "Sub A – Sub B". Match each substation to OSM via Overpass
  (by operator, within a bounding box), then take the midpoint. Record
  `location_confidence`, since similarly named substations in the wrong county are the
  common false match.
- Prioritize the Savannah River border (Augusta/Thurmond, Savannah/Jasper County). That's
  where real overlaps are. Most projects will not overlap, and that's expected.
- Commit the cleaned CSV/GeoJSON to the repo so the demo never depends on Overpass being up.

## Phases
- **Phase 1 (hours 0–16)** — skeleton deployed to DigitalOcean by hour 2; data decision by
  hour 4; schema + dataset + overlap query by hour 10; `/projects` and `/overlaps` returning
  real data by hour 16. Thin slice tracked in `docs/backlog.md`.
- **Phase 2 (hours 16–28)** — map with per-utility layers and flagged pairs end-to-end
  against the live API (by 24); detail panel, savings note, polish (by 28).
- **Phase 3 (hours 28–35)** — deploy freeze at 28–29 (test on a phone hotspot); rehearsal
  29–33; buffer + Devpost submission 33–35.

## Roles
- **A — Data/Backend:** PDF parsing, OSM matching, schema, overlap job (paired with a
  second person on locating projects for hours 0–4).
- **B — API/Deploy:** endpoints, DigitalOcean, keeps the app always deployed.
- **C — Frontend/Map:** React + MapLibre, layers, highlighting, detail panel.
- **D — Polish/Demo:** design pass, savings copy/logic (Snowflake), Devpost, owns pitch
  rehearsal from hour 28.

## Risks & fallbacks
| Risk | Fallback |
|---|---|
| Can't locate enough projects | Ship on the starter table + hand-located border projects; show low-confidence ones distinctly |
| OSM false matches | Cross-check against PDF description/zone; `location_confidence` flag |
| PostGIS query bugs | Haversine in app code (it's the spec's formula anyway) |
| Late deploy breakage | Deploy by hour 2; local fallback on presenter's laptop |
| Venue wifi fails | Test on hotspot in rehearsal; offline local build |

## Demo script (< 3 min)
1. (15s) Hook: utilities plan in isolation; FERC 2024 rule.
2. (30s) Map: two utilities, two colors, live.
3. (45s) Click a flagged pair: distance, date overlap, savings — say the number.
4. (30s) Zoom out: "[N] overlaps worth an estimated $[X]."
5. (20s) Tech: real PDFs → OSM-located substations → PostGIS 25-mi overlap job, verified
   against Sperry's reference table; Tiger Data, DigitalOcean.
6. (20s) Close: one-liner + what's next (third utility, live filing ingestion).

## Open questions
- Ranking formula weights (distance vs time gap vs cost) — pick something simple and explainable.
- How many GPC projects to locate: all, or only those within ~50 mi of the SC border?
