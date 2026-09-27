# Relay API contract

The shapes every layer builds against. Models live in `backend/app/schemas.py`; field names
match the `projects` / `project_overlaps` tables in `backend/db/schema.sql` and the seed CSV columns
read by `backend/pipeline/load.py`.

All responses are JSON. Dates are ISO `YYYY-MM-DD`. Coordinates are WGS84 decimal degrees.

> The example JSON blocks below are the test fixtures: `backend/tests/test_schemas.py` reads
> every block tagged `<!-- example: ... -->` from this file and validates it against the
> models. Edit an example here and the test checks it.

## Models

### `Project`

One utility's planned transmission project — one row of `data/seed/projects_seed.csv`.

| Field | Type | Notes |
|-------|------|-------|
| `project_id` | string | unique; `SUB-<client id>` for an uploaded project (`POST /workspace` only) |
| `utility` | string | e.g. `Dominion Energy South Carolina`, `Georgia Power` |
| `state` | string | `SC`, `GA` |
| `project_name` | string | |
| `name_a`, `name_b` | string \| null | endpoint (substation) names |
| `lat_a`, `lon_a`, `lat_b`, `lon_b` | number \| null | null when that endpoint could not be located |
| `lat_center`, `lon_center` | number | **required** — what overlap detection compares |
| `in_service_date` | date | ISO only; anything else is rejected |
| `est_cost_usd` | integer \| null | whole dollars; null where redacted (all of Georgia Power) |
| `location_confidence` | `"confirmed"` \| `"low"` | defaults to `confirmed`; `low` = unverified match |

### `Overlap`

One flagged cross-utility pair (project centers < 25 mi apart).

| Field | Type | Notes |
|-------|------|-------|
| `overlap_id` | string | `OVL_1..OVL_N`, numbered by ascending distance (engine order); `SUB:<project_id_a>\|<project_id_b>` for a pair involving an uploaded project (`POST /workspace` only) |
| `rank` | integer ≥ 1 | position by descending `score`; 1 = best opportunity |
| `score` | number 0–1 | `0.6·(1 − distance/25) + 0.4·(1 − min(gap, 1825)/1825)` (`pipeline/overlap.py`) |
| `distance_mi` | number 0–25 | haversine between centers, R = 3958.8 mi, 2 decimals |
| `time_gap_days` | integer ≥ 0 | absolute gap between the two in-service dates |
| `project_a`, `project_b` | `Project` | the pair, full records |
| `est_savings_usd` | integer ≥ 0 \| null | rough shared-mobilization savings, whole dollars; null when neither project's cost is known (never invented) |
| `savings_basis` | string | plain-English explanation of the figure, or why there is none (e.g. "cost redacted in Georgia Power IRP"); shown verbatim in the detail panel |

`est_savings_usd` is derived, not stored (`backend/pipeline/savings.py`):
`0.05 · known_cost · (1 − 0.9·distance/25) · 0.5^(gap/365)`, where `known_cost` is the
smaller known `est_cost_usd` of the pair. The 5% shared-mobilization share is an assumption,
not a sourced figure; the estimate falls to 10% of full value at the 25 mi radius and halves
for every year between in-service dates.

## Endpoints

**Database unavailable.** When the database cannot be reached (down, restarting, a network
blip), `GET /projects`, `GET /overlaps`, `GET /overlaps/{overlap_id}` and `POST /workspace`
return **503** within the connect timeout (5 s), with this body; the cause is only logged
server-side:

```json
{"detail": "database unavailable"}
```

Any other server error is still a **500**.

### `GET /health`

Liveness check: never touches the database, so it stays **200** while the database is down.

<!-- example: health -->
```json
{"status": "ok"}
```

### `GET /projects`

Every **published** project, for the map layers. Uploaded projects are never here: they live in
the uploader's browser and are scored through `POST /workspace`. Response: `Project[]`.

<!-- example: projects -->
```json
[
  {"project_id": "DESC_3", "utility": "Dominion Energy South Carolina", "state": "SC", "project_name": "Jasper - Okatie 230 kV #2: Construct", "name_a": "Jasper Sub", "lat_a": 32.35912, "lon_a": -81.1246, "name_b": "Okatie Sub", "lat_b": 32.333758, "lon_b": -81.032495, "lat_center": 32.346439, "lon_center": -81.0785475, "in_service_date": "2025-12-31", "est_cost_usd": 23787423, "location_confidence": "confirmed"},
  {"project_id": "GPC_2", "utility": "Georgia Power", "state": "GA", "project_name": "SAV: MCINTOSH - PURRYSBURG 230KV REACTORS", "name_a": "MCINTOSH", "lat_a": 32.352116, "lon_a": -81.175112, "name_b": "PURRYSBURG", "lat_b": null, "lon_b": null, "lat_center": 32.352116, "lon_center": -81.175112, "in_service_date": "2026-06-01", "est_cost_usd": null, "location_confidence": "confirmed"}
]
```

### `GET /overlaps`

Every flagged pair between published projects, **ranked: `rank` 1 first** (descending
`score`), from the `project_overlaps` table the batch load writes. Response: `Overlap[]`.
Pairs involving an upload are only in the `POST /workspace` response.

<!-- example: overlaps -->
```json
[
  {
    "overlap_id": "OVL_2", "rank": 1, "score": 0.8311, "distance_mi": 5.65, "time_gap_days": 152,
    "project_a": {"project_id": "DESC_3", "utility": "Dominion Energy South Carolina", "state": "SC", "project_name": "Jasper - Okatie 230 kV #2: Construct", "name_a": "Jasper Sub", "lat_a": 32.35912, "lon_a": -81.1246, "name_b": "Okatie Sub", "lat_b": 32.333758, "lon_b": -81.032495, "lat_center": 32.346439, "lon_center": -81.0785475, "in_service_date": "2025-12-31", "est_cost_usd": 23787423, "location_confidence": "confirmed"},
    "project_b": {"project_id": "GPC_2", "utility": "Georgia Power", "state": "GA", "project_name": "SAV: MCINTOSH - PURRYSBURG 230KV REACTORS", "name_a": "MCINTOSH", "lat_a": 32.352116, "lon_a": -81.175112, "name_b": "PURRYSBURG", "lat_b": null, "lon_b": null, "lat_center": 32.352116, "lon_center": -81.175112, "in_service_date": "2026-06-01", "est_cost_usd": null, "location_confidence": "confirmed"},
    "est_savings_usd": 709900, "savings_basis": "Assumed shared mobilization of 5% of the Dominion Energy South Carolina project's $23,787,423 cost, x0.80 for 5.65 mi apart and x0.75 for 152 days between in-service dates. No figure for the Georgia Power project (cost redacted in Georgia Power IRP)."
  },
  {
    "overlap_id": "OVL_3", "rank": 2, "score": 0.7055, "distance_mi": 7.55, "time_gap_days": 517,
    "project_a": {"project_id": "DESC_3", "utility": "Dominion Energy South Carolina", "state": "SC", "project_name": "Jasper - Okatie 230 kV #2: Construct", "name_a": "Jasper Sub", "lat_a": 32.35912, "lon_a": -81.1246, "name_b": "Okatie Sub", "lat_b": 32.333758, "lon_b": -81.032495, "lat_center": 32.346439, "lon_center": -81.0785475, "in_service_date": "2025-12-31", "est_cost_usd": 23787423, "location_confidence": "confirmed"},
    "project_b": {"project_id": "GPC_3", "utility": "Georgia Power", "state": "GA", "project_name": "SAV: GOSHEN (SAV) - MCINTOSH 115KV LINE REBUILD", "name_a": "GOSHEN", "lat_a": 32.248701, "lon_a": -81.209472, "name_b": "MCINTOSH", "lat_b": 32.352116, "lon_b": -81.182105, "lat_center": 32.3004085, "lon_center": -81.1957885, "in_service_date": "2027-06-01", "est_cost_usd": null, "location_confidence": "confirmed"},
    "est_savings_usd": 324472, "savings_basis": "Assumed shared mobilization of 5% of the Dominion Energy South Carolina project's $23,787,423 cost, x0.73 for 7.55 mi apart and x0.37 for 517 days between in-service dates. No figure for the Georgia Power project (cost redacted in Georgia Power IRP)."
  }
]
```

### `GET /overlaps/{overlap_id}`

One published pair, for the detail panel. Response: `Overlap`. A `SUB:` pair is never found here (404).

<!-- example: overlap -->
```json
{
  "overlap_id": "OVL_2", "rank": 1, "score": 0.8311, "distance_mi": 5.65, "time_gap_days": 152,
  "project_a": {"project_id": "DESC_3", "utility": "Dominion Energy South Carolina", "state": "SC", "project_name": "Jasper - Okatie 230 kV #2: Construct", "name_a": "Jasper Sub", "lat_a": 32.35912, "lon_a": -81.1246, "name_b": "Okatie Sub", "lat_b": 32.333758, "lon_b": -81.032495, "lat_center": 32.346439, "lon_center": -81.0785475, "in_service_date": "2025-12-31", "est_cost_usd": 23787423, "location_confidence": "confirmed"},
  "project_b": {"project_id": "GPC_2", "utility": "Georgia Power", "state": "GA", "project_name": "SAV: MCINTOSH - PURRYSBURG 230KV REACTORS", "name_a": "MCINTOSH", "lat_a": 32.352116, "lon_a": -81.175112, "name_b": "PURRYSBURG", "lat_b": null, "lon_b": null, "lat_center": 32.352116, "lon_center": -81.175112, "in_service_date": "2026-06-01", "est_cost_usd": null, "location_confidence": "confirmed"},
  "est_savings_usd": 709900, "savings_basis": "Assumed shared mobilization of 5% of the Dominion Energy South Carolina project's $23,787,423 cost, x0.80 for 5.65 mi apart and x0.75 for 152 days between in-service dates. No figure for the Georgia Power project (cost redacted in Georgia Power IRP)."
}
```

Unknown `overlap_id` → **404** with FastAPI's default error body:

<!-- example: not_found -->
```json
{"detail": "overlap OVL_99 not found"}
```

Database unreachable → **503** `{"detail": "database unavailable"}` (see the top of
[Endpoints](#endpoints)), here as on `/projects` and `/overlaps`.

### `POST /workspace`

The published plans **plus the caller's own uploads**, scored and ranked together. Nothing is
stored: each visitor's uploads live in their own browser (`localStorage` key
`relay.uploads.v1`, see `frontend/src/uploadCache.ts`), which sends them with every page load and
every new upload. Nobody else ever sees them; clearing the browser's site data loses them.

Body: `{"projects": Project[]}`, **0–1000** projects (empty is fine: the published plans alone),
each validated like a published one, except `project_id`:

- `project_id` is the id the browser gave the upload once, when it was imported, and keeps for
  good: 1–64 characters from `A–Z a–z 0–9 _ -` (anything else is a 422). It is served as
  `SUB-<project_id>`, so the same uploads get the same ids (and pair ids) on every call.
- `location_confidence` is always served as `low`: the coordinates are the uploader's, not
  matched to OSM;
- a `utility` equal to a published one ignoring case and spacing takes the published spelling.

<!-- example: workspace_request -->
```json
{"projects": [
  {"project_id": "3f9a1c2e-5b7d-4e8f-9a0b-1c2d3e4f5a6b-1", "utility": "Tidewater Grid Co.", "state": "SC", "project_name": "Savannah River crossing", "name_a": null, "lat_a": null, "lon_a": null, "name_b": null, "lat_b": null, "lon_b": null, "lat_center": 32.36, "lon_center": -81.16, "in_service_date": "2026-09-01", "est_cost_usd": 2500000, "location_confidence": "low"}
]}
```

**200** with `projects` = every published project (as `GET /projects`) followed by the uploads
in the order sent, and `overlaps` = the published pairs plus every pair involving an upload
(`SUB:<project_id_a>|<project_id_b>`, computed by the same engine, `pipeline/overlap.py`),
ranked in one list exactly like `GET /overlaps`, so an upload can take rank 1. Abridged here to
one project of each kind and the upload's pair:

<!-- example: workspace -->
```json
{
  "projects": [
    {"project_id": "GPC_2", "utility": "Georgia Power", "state": "GA", "project_name": "SAV: MCINTOSH - PURRYSBURG 230KV REACTORS", "name_a": "MCINTOSH", "lat_a": 32.352116, "lon_a": -81.175112, "name_b": "PURRYSBURG", "lat_b": null, "lon_b": null, "lat_center": 32.352116, "lon_center": -81.175112, "in_service_date": "2026-06-01", "est_cost_usd": null, "location_confidence": "confirmed"},
    {"project_id": "SUB-3f9a1c2e-5b7d-4e8f-9a0b-1c2d3e4f5a6b-1", "utility": "Tidewater Grid Co.", "state": "SC", "project_name": "Savannah River crossing", "name_a": null, "lat_a": null, "lon_a": null, "name_b": null, "lat_b": null, "lon_b": null, "lat_center": 32.36, "lon_center": -81.16, "in_service_date": "2026-09-01", "est_cost_usd": 2500000, "location_confidence": "low"}
  ],
  "overlaps": [
    {
      "overlap_id": "SUB:GPC_2|SUB-3f9a1c2e-5b7d-4e8f-9a0b-1c2d3e4f5a6b-1", "rank": 1, "score": 0.9549, "distance_mi": 1.04, "time_gap_days": 92,
      "project_a": {"project_id": "GPC_2", "utility": "Georgia Power", "state": "GA", "project_name": "SAV: MCINTOSH - PURRYSBURG 230KV REACTORS", "name_a": "MCINTOSH", "lat_a": 32.352116, "lon_a": -81.175112, "name_b": "PURRYSBURG", "lat_b": null, "lon_b": null, "lat_center": 32.352116, "lon_center": -81.175112, "in_service_date": "2026-06-01", "est_cost_usd": null, "location_confidence": "confirmed"},
      "project_b": {"project_id": "SUB-3f9a1c2e-5b7d-4e8f-9a0b-1c2d3e4f5a6b-1", "utility": "Tidewater Grid Co.", "state": "SC", "project_name": "Savannah River crossing", "name_a": null, "lat_a": null, "lon_a": null, "name_b": null, "lat_b": null, "lon_b": null, "lat_center": 32.36, "lon_center": -81.16, "in_service_date": "2026-09-01", "est_cost_usd": 2500000, "location_confidence": "low"},
      "est_savings_usd": 101033, "savings_basis": "Assumed shared mobilization of 5% of the Tidewater Grid Co. project's $2,500,000 cost, x0.96 for 1.04 mi apart and x0.84 for 92 days between in-service dates. No figure for the Georgia Power project (cost redacted in Georgia Power IRP)."
    }
  ]
}
```

A utility + project name (ignoring case) that is already published or appears twice in the
uploads, or a `project_id` used twice → **409** with a readable reason:

<!-- example: conflict -->
```json
{"detail": "project 1 ('Savannah River crossing' by 'Tidewater Grid Co.') already exists"}
```

An invalid body (more than 1000 projects, a bad `project_id`, coordinate or date, ...) →
**422** with FastAPI's validation error body.

**Old shared uploads.** Before this endpoint, `POST /submissions` stored uploads for everyone
in a `submitted_projects` table. That endpoint is gone and **no code reads the table any
more**; it is left untouched in the demo database (its rows are hidden, not deleted, and its
DDL is in git history as `backend/db/submissions.sql`).

## Repository functions

What the route handlers call (`backend/app/repository.py`). Read-only; each returns
validated models, and the routes stay thin.

```python
def list_projects() -> list[Project]: ...
def list_overlaps() -> list[Overlap]:  # ranked, rank 1 first
    ...
def get_overlap(overlap_id: str) -> Overlap | None:  # None -> route returns 404
    ...
def published_plans() -> PublishedPlans:  # projects + stored engine pairs, one snapshot,
    ...                                        # scored with the caller's uploads by POST /workspace
```
