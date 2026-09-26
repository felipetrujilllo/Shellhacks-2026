# Backlog

## Goal
GridWatch compares Dominion Energy South Carolina's and Georgia Power's public transmission
construction plans. It flags cross-utility project pairs whose centers are within 25 miles,
using the in-service time gap as a secondary signal, and presents them on an interactive map
with a ranked list of coordination opportunities (Sperry Tech — Gridlock; full spec in
`docs/prompt.md`).

## Judging criteria
Not published explicitly. The spec's deliverables stand in for them:
- Interactive UI with both utilities' projects and overlaps highlighted — **required**
- Ranked list of top coordination opportunities — **required**
- Cost/impact estimate for at least one flagged pair — bonus
- Real public data, correctly located (the sponsor's guide stresses verifying matches)
- Creativity

## Vertical slice (MVP)
**Outcome:** A judge opens the site and sees DESC and Georgia Power projects in two colors
on an interactive map, with the sponsor's 6 real overlaps highlighted and ranked in a list
beside it.

**End-to-end path:** `data/seed/projects_seed.csv` → Python overlap engine (haversine,
< 25 mi, time gap, rank) → Tiger Data PostGIS `projects` / `project_overlaps` tables → FastAPI
`GET /overlaps` → React `api.ts` → GeoJSON builders → MapLibre layers + ranked list.

**Out of scope for the slice:** GPC PDF parsing, OSM location matching, detail panel,
cost/impact estimate, Snowflake note, third utility, filters/search, visual polish, custom
domain, auth.

**Critical path:** #1 → #2 → #4 → #5 → #11 (data), with #7 also blocking #5;
#3 → #6 → #8 (API/deploy); #3 → #9 → #10 (frontend).

## Tasks
Tracked as GitHub issues. Regenerate this snapshot with `gh issue list --state all`.

| Issue | Task | Owner | Size | Status |
|-------|------|-------|------|--------|
| #1 | [P1-INFRA] Scaffold backend + frontend with test runners and fill ## Checks | @felipetrujilllo | M | closed |
| #2 | [P1-DATA] Add sponsor source files and convert the starter table to seed CSVs | @felipetrujilllo | S | closed |
| #3 | [P1-API] Define the API contract: Pydantic schemas + docs/api.md | @fredmaster1928 | S | closed |
| #4 | [P1-DATA] Overlap engine: haversine, 25-mi cross-utility pairs, time gap, ranking | @Eveliox | M | closed |
| #5 | [P1-DATA] DB schema + loader: seed CSV into Tiger Data projects/overlaps tables | @Eveliox | M | closed |
| #6 | [P1-API] FastAPI endpoints: /health, /projects, /overlaps, /overlaps/{id} | @fredmaster1928 | M | closed |
| #7 | [P1-INFRA] Provision Tiger Data + DigitalOcean accounts and .env.example | @felipetrujilllo | S | closed |
| #8 | [P1-API] Deploy backend + frontend to DigitalOcean App Platform | @fredmaster1928 | M | open |
| #9 | [P1-FE] API client + GeoJSON builders for projects and overlaps | @roliv091 | M | closed |
| #10 | [P1-FE] Map page: utility layers, overlap highlights, ranked opportunity list | @roliv091 | M | open |
| #11 | [P1-INFRA] Demo-path smoke test script | @felipetrujilllo | S | open |
| #12 | [P1-DATA] Parse Dominion's 44 project sheets into CSV | @Eveliox | M | closed |
| #13 | [P2-DATA] Compute project centers from endpoints | @Eveliox | S | open |
| #14 | [P2-DATA] Fetch and cache OSM substations for DESC and GPC | @felipetrujilllo | S | open |
| #15 | [P2-DATA] Match projects to OSM substations with confidence | @Eveliox | M | open |
| #16 | [P2-FE] Overlap detail panel with savings estimate | @roliv091 | M | open |
| #17 | [P2-INFRA] Guard SQL tests, encodings and line endings in Checks | @felipetrujilllo | S | open |
| #18 | [P2-DATA] Parse Georgia Power transmission projects from IRP Vol 3 | @felipetrujilllo | M | open |
| #19 | [P2-DATA] Build and load the full located dataset | @Eveliox | M | open |
| #20 | [P2-API] Estimate cost/impact per overlap | @fredmaster1928 | M | open |
| #21 | [P2-DATA] Split project names into substation endpoints | @Eveliox | M | open |
