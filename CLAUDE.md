# CLAUDE.md

## Event
ShellHacks 2026 — FIU.
<START DATETIME> – <END DATETIME>. Team of 4.

## Challenge: "Gridlock" (Sperry Tech sponsor challenge — see `docs/prompt.md`)
> If you pivot mid-event: note the pivot here with a timestamp and one line on why, and say
> which doc got overwritten and that it's recoverable from git history. Don't delete the old
> plan's doc content by hand — let git history hold it; just overwrite `docs/project.md` and
> note it here. Don't silently close the old plan's issues — flag them as stale and let a
> human decide.

Full prompt and judging criteria live in `docs/prompt.md` (`plan-slice` reads it).

- **Core requirement:** ingest DESC + Georgia Power public transmission plans; flag
  cross-utility pairs whose project centers are < 25 mi apart (haversine); record the
  in-service time gap in days as a secondary signal. Required: interactive map with overlaps
  highlighted + a ranked list of top coordination opportunities.
- **Go further (bonus):** cost/impact estimate for at least one flagged pair.
- **Golden test:** the sponsor's 10-project starter table must yield exactly its 6 overlaps
  (`docs/prompt.md`).

Working name: **GridWatch** (plan in `docs/project.md`).

## Team
- **A — Data/Backend:** @Eveliox — PDF parsing, OSM matching, DB schema, overlap engine
- **B — API/Deploy:** @fredmaster1928 — FastAPI endpoints, config, DigitalOcean deploy
- **C — Frontend/Map:** @roliv091 — React + MapLibre map, ranked list, detail panel
- **D — Infra/Docs/PM:** @felipetrujilllo — scaffolding, accounts, smoke test, docs; owns
  watching the tracker and running `/pm` at phase boundaries

## Stack
- **Backend:** Python + FastAPI (Pydantic models at the API boundary), run locally with
  `uvicorn` from `backend/`. Data ingestion (PDF parsing, Overpass/OSM matching) and the
  overlap job are Python too, in `backend/`.
- **Database:** Tiger Data (Postgres + PostGIS) — the only database
- **AI:** Snowflake Cortex — savings note only; overlap detection stays deterministic SQL
- **Frontend:** React + Vite + TypeScript, Tailwind, MapLibre GL JS via `react-map-gl/maplibre`
  (free CARTO/OpenFreeMap vector style, no API key), scaffolded in `frontend/`
- **Hosting:** DigitalOcean App Platform; domain via GoDaddy Registry

## Structure
- `frontend/` — client app
- `backend/app/` — FastAPI app (routes, schemas, config, DB access)
- `backend/pipeline/` — ingestion + overlap engine (pure Python, no web code)
- `backend/db/` — SQL schema
- `data/source/` — sponsor's raw files (PDFs, starter xlsx); `data/seed/` — cleaned CSVs
- `docs/` — prompt, plan, backlog, submission material

## Checks
Single source of truth for "does the project still work". The `test-gate` skill/agent, `pm`,
and every verifier run exactly these. Update this section the moment a layer gets a build or
test command — an empty entry means that layer is unguarded, and the gate will say so.

| Layer | Build | Test | Lint/typecheck |
|-------|-------|------|----------------|
| backend | `cd backend && .venv/bin/python -m compileall -q app pipeline` (one-time setup: see README) | `cd backend && .venv/bin/python -m pytest` | `cd backend && .venv/bin/ruff check .` |
| frontend | `cd frontend && npm run build` | `cd frontend && npx vitest run` | `cd frontend && npx tsc -b` (bare `tsc --noEmit` checks nothing: root tsconfig is references-only) |

**Smoke test (demo path):** <one command or short script that exercises the real end-to-end
path, e.g. start backend, hit the core endpoint, assert on the response shape — "none yet"
until the slice exists>

## Tickets
- Tasks are tracked as GitHub Issues (`gh issue list`). The `pm` and `plan-slice` skills
  read and create them there.
- The user can also hand a raw ticket (pasted text, not an issue) straight to
  `/implement-ticket` — treat raw text and a GitHub issue the same once the requirements are
  in hand.
- A ticket is not done until `test-gate` returns APPROVE: every acceptance criterion has a
  test that actually asserts it, and the full suite + smoke test still pass.

## Code principles
Stack-agnostic, apply pragmatically — this is a ~36-hour build with 4 people touching the
same code, not a design review. These reduce merge pain and debugging time more than they
cost:
- **DRY** — extract shared logic once it's actually duplicated 2-3+ times; don't
  pre-extract for hypothetical reuse.
- **Separation of concerns** — keep UI, business/AI logic, and data access in distinct
  files/layers.
- **Single responsibility** — each function/module does one thing.
- **KISS** — ship the simplest thing that works. No speculative abstractions.
- **YAGNI** — don't build for requirements you don't have yet.
- **Single source of truth** — one place for config, constants, and API keys (`.env`), not
  copy-pasted across frontend/backend.
- **Secrets never in code** — API keys and credentials go in `.env` (gitignored), never
  hardcoded or committed. Judges and other teams may see the repo.
- **Fail loud, not silent** — surface errors instead of swallowing them.
- **Validate at boundaries** — check/sanitize input where it enters the system; trust your
  own internal code elsewhere.
- **Consistent naming** — use the same term for the same concept across frontend and backend.
- **Small, focused commits** — easier to merge across 4 people and easier to revert one thing
  if it breaks the demo.
- **Tests guard the demo, not coverage numbers** — test each acceptance criterion and the
  demo path. Never delete, skip, or loosen an existing test to make a change pass; if a test
  is genuinely wrong, say so and fix it deliberately.
- **AI calls are mocked in unit tests** — tests must not hit a paid/rate-limited model API or
  need a real key. Keep at most one opt-in live test for the demo path.

## Working style
- This is a timeboxed hackathon. Prioritize working code over polish — get a thin end-to-end
  slice running before adding features.
- Don't scaffold speculative structure until the prompt and team decisions make it necessary.
- Never run `git push` unless the user explicitly says to push in that same message. Do
  not assume or infer it from "commit", "save", "done", "ship it", or a push earlier in
  the conversation. If in doubt, stop and ask.
- Same for `git commit`: only commit when explicitly asked in that message.
- Before committing or pushing (when asked), run `/test-gate` if it hasn't run since the last
  change. Don't commit on a BLOCK verdict unless the user overrides it in their own words.

## Still open
- Test frameworks per layer (fill in `## Checks`)
- Final project name
