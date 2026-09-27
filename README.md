# Relay

ShellHacks 2026 — Sperry Tech "Gridlock" challenge. (Formerly "GridWatch"; the live URL,
App Platform app and local test-DB names below still use `gridwatch` on purpose.)

## Running locally

Secrets and config go in `.env` files, which are gitignored — never commit keys.

### Backend (Python 3.11+, FastAPI)

```bash
cd backend
python3.12 -m venv .venv            # any Python >= 3.11
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest          # tests
.venv/bin/ruff check .              # lint
```

#### Database tests against a throwaway PostGIS

Most loader tests run against a recording stub, which cannot tell valid SQL from invalid. The
tests that execute the real schema are opt-in and need a scratch Postgres — they TRUNCATE, so
they deliberately ignore `$DATABASE_URL` and read `TEST_DATABASE_URL` instead:

Needs Docker Desktop running (the container is `postgis/postgis`, so PostGIS is already
installed). Start it once; it keeps running across sessions until you remove it:

```bash
docker run -d --name gridwatch-pg -e POSTGRES_HOST_AUTH_METHOD=trust \
    -e POSTGRES_DB=gridwatch_test -p 55432:5432 postgis/postgis:16-3.4

cd backend
TEST_DATABASE_URL=postgresql://postgres@localhost:55432/gridwatch_test \
    .venv/bin/python -m pytest tests/test_load.py tests/test_repository.py
```

On Windows (PowerShell), same container, then:

```powershell
cd backend
$env:TEST_DATABASE_URL = "postgresql://postgres@localhost:55432/gridwatch_test"
.venv\Scripts\python.exe -m pytest tests/test_load.py tests/test_repository.py
```

Done with it: `docker rm -f gridwatch-pg` (it holds nothing worth keeping). If `docker run`
says the name is taken, the container already exists — `docker start gridwatch-pg`.

Trust auth on purpose: the container is throwaway and local-only, so there is no password
to put in a URL and nothing for the credential scanner in `tests/test_env_example.py` to
flag.

Without it, those tests skip and `pytest` still passes — which is how a reserved-word table
name once shipped past green checks. So this run is **required** (see `CLAUDE.md` `## Checks`)
for any change to `backend/db/` or `pipeline/load.py`.

#### Encodings and line endings (Windows + Mac team)

- Always pass `encoding="utf-8"` to `open()`, `Path.read_text()` and `Path.write_text()`:
  Windows defaults to cp1252. `ruff check` enforces this (rule PLW1514), but it cannot see
  through every call — e.g. `SOME_PATH_CONSTANT.read_text()` — so write it anyway.
- `.gitattributes` stores and checks out every text file with LF, on Windows too, and treats
  `*.pdf`/`*.xlsx`/`*.docx` as binary. If `git ls-files --eol | grep i/crlf` ever prints
  anything, fix it with `git add --renormalize <file>`; `tests/test_repo_hygiene.py` fails
  until you do.

### Loading seed data

The demo database serves `data/seed/projects.csv`: the full located dataset (every DESC and
Georgia Power project `pipeline.build_dataset` could place). `data/seed/projects_seed.csv` is
the sponsor's 10-project starter table; it is the golden test fixture and the rollback, not
what the demo serves.

**The load replaces what the live site shows.** `DATABASE_URL` in the repo-root `.env` is the
shared demo database the deployed site reads, and the load truncates and refills both tables
(`projects`, `project_overlaps`) in one transaction. Tell the team before you run it. To
rehearse first, point `--database-url` at the throwaway PostGIS above instead.

1. If the parser CSVs, the OSM caches or `location_overrides.csv` changed, regenerate the
   dataset first (and commit it) so the demo matches the repo:

   ```bash
   cd backend
   .venv/bin/python -m pipeline.build_dataset
   ```

2. Load it (from `backend/`; reads `--database-url`, else `$DATABASE_URL`, else `.env`):

   ```bash
   .venv/bin/python -m pipeline.load --csv ../data/seed/projects.csv
   ```

   It applies `db/schema.sql`, runs the overlap engine over the CSV and prints
   `loaded N projects and M overlaps`. On any bad row it fails before writing anything.

3. Verify, from the repo root (both are read-only: they start the API against `.env` on a free
   port and only make GET requests):

   ```bash
   backend/.venv/bin/python scripts/smoke.py            # the sponsor's 6 pairs are served
   backend/.venv/bin/python scripts/check_demo_data.py  # /projects and /overlaps == the CSV
   ```

   `check_demo_data.py` passes only if `GET /projects` serves exactly the CSV's projects and
   `GET /overlaps` exactly the pairs the engine flags on it. Both take `BASE_URL` to check the
   deployed API instead (the API base, including `/api`; see `## Checks` in `CLAUDE.md`).

**Roll back** to the sponsor's 10-project sample the same way:

```bash
cd backend
.venv/bin/python -m pipeline.load --csv ../data/seed/projects_seed.csv
cd .. && backend/.venv/bin/python scripts/check_demo_data.py --csv data/seed/projects_seed.csv
```

On Windows use `.venv\Scripts\python.exe` and `backend\.venv\Scripts\python.exe` in the
commands above.

`tests/test_demo_data.py` checks all of this without touching the demo: offline, that smoke's
6 pairs are in what `projects.csv` would serve; with `TEST_DATABASE_URL` set, a full load of
`projects.csv` into the throwaway database and the real API over it.

`schema.sql` uses `CREATE TABLE IF NOT EXISTS`, so **editing it does nothing to a database
that already has the tables** — drop them first (`DROP TABLE project_overlaps, projects;`) and
re-run. There are no migrations.

### Frontend (React + Vite + TypeScript, Tailwind, MapLibre)

```bash
cd frontend
npm install
npm run dev          # dev server
npm test             # vitest run
npm run typecheck    # tsc -b (type-checks app + tests + vite config)
npm run build        # production build into dist/
```

### Running the app (API + site) locally

Two terminals, both from this checkout. The API reads the repo-root `.env` and serves the demo
database read-only; the site reads `VITE_API_URL` from `frontend/.env`
(`VITE_API_URL=http://localhost:8000`, see `.env.example`).

```bash
cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8000 --env-file ../.env
cd frontend && npm run dev
```

Windows (PowerShell):

```powershell
cd backend; .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000 --env-file ..\.env
cd frontend; npm run dev
```

**Always start the API with `--reload`.** Without it uvicorn keeps serving the code it started
with, so commits made after that (a pull, a teammate's merge, a ticket landing) never show up
on the local site, and nothing warns you. Before starting it, check nothing already holds port
8000 (`Get-NetTCPConnection -LocalPort 8000` / `lsof -i :8000`); if something does, stop it and
start fresh rather than trusting it. To confirm the API is current, compare a field from the
latest backend change against `curl http://localhost:8000/overlaps`.

## Deploying to DigitalOcean (App Platform)

The whole app is one App Platform app with two components, described by `.do/app.yaml`
(#8). **That file is the source of truth, not the dashboard** — if you change something in
the console, put it in the spec too, or the next `doctl apps update` will undo it.

| Component | Type | Source | Served at |
|---|---|---|---|
| `api` | service (Python buildpack) | `backend/` | `/api` → uvicorn, prefix stripped |
| `web` | static site (Node buildpack) | `frontend/` | `/` → Vite's `dist/` |

Both components live behind the same hostname, which is how the chicken-and-egg between the
two URLs is solved: the frontend's `VITE_API_URL` is the relative path `/api`, so the browser
calls the API on whichever host served the page, and the backend's `FRONTEND_ORIGIN` is
`${APP_URL}` (the frontend is served from that same origin). No hostname is baked into the
bundle, so renaming the app or adding a domain breaks nothing. Requests are same-origin in
production, so CORS never has to be right for the demo to work.

`VITE_API_URL` is scoped `BUILD_TIME` on purpose: Vite bakes `import.meta.env.VITE_*` into
the bundle when it builds, so a run-time-only value would never reach the browser.

`backend/requirements.txt` holds a single `.` — the Python buildpack refuses to recognize a
component with only a `pyproject.toml`, and `.` makes it install this project, so the
dependency list stays in one place.

### Live site

- **https://relaygrid.us** — the primary custom domain (`https://www.relaygrid.us` is an
  alias for it).
- **https://gridwatch-b3trj.ondigitalocean.app** — the app's default host, which keeps
  working alongside the domain.

Both serve the same App Platform app `gridwatch`, built from `main`: the frontend at `/`, the
API at `/api`. Check each with the smoke test against the **API base, including `/api`**:

```bash
BASE_URL=https://relaygrid.us/api backend/.venv/bin/python scripts/smoke.py
BASE_URL=https://gridwatch-b3trj.ondigitalocean.app/api backend/.venv/bin/python scripts/smoke.py
BASE_URL=https://gridwatch-b3trj.ondigitalocean.app/api backend/.venv/bin/python scripts/check_demo_data.py
```

It reads the same Tiger Data database as local dev, so reloading the demo data (above) shows
up on the live site immediately; code changes after a promote, which CI/CD redeploys (below).

### Custom domain

`relaygrid.us` is registered at Porkbun, but its DNS is managed by DigitalOcean: at Porkbun
the domain's authoritative nameservers are set to `ns1.digitalocean.com`,
`ns2.digitalocean.com` and `ns3.digitalocean.com`. The hosts themselves are declared in the
`domains:` block of `.do/app.yaml` — `relaygrid.us` as `PRIMARY`, `www.relaygrid.us` as
`ALIAS`, both in zone `relaygrid.us` — so App Platform creates the DNS records and issues the
TLS certificate automatically once the nameservers resolve (minutes to a few hours). Until
then the domain fails its smoke test; the `*.ondigitalocean.app` host is unaffected. The CI
deploy job keeps smoke-testing that default host.

Why `VITE_API_URL` is the relative `/api` and not `${api.PUBLIC_URL}`: with a `PRIMARY`
domain, App Platform resolves `${api.PUBLIC_URL}` to `https://relaygrid.us/api`. The bundle
served at `www.relaygrid.us` or `gridwatch-b3trj.ondigitalocean.app` would then call
`relaygrid.us` cross-origin, and the backend's CORS (one allowed origin, `FRONTEND_ORIGIN`)
would reject it. A relative path is same-origin on every host. Local dev keeps the absolute
`http://localhost:8000` in `frontend/.env`, because there the two are separate origins.

**Applying a spec change safely** (e.g. the `domains:` block): don't update from the repo
file directly. `.do/app.yaml` declares `DATABASE_URL` with no value, so
`doctl apps update <app-id> --spec .do/app.yaml` sends it empty and wipes the secret. Start
from the live spec instead, which carries the secret as an encrypted `EV[...]` value:

```bash
doctl apps spec get <app-id> > /tmp/live.yaml
# edit the domains / envs in /tmp/live.yaml to match .do/app.yaml (leave DATABASE_URL alone)
doctl apps update <app-id> --spec /tmp/live.yaml && rm /tmp/live.yaml
```

### First deploy (once, by hand — needs a DigitalOcean account with the repo connected)

1. Make sure `main` is current: `/test-gate full` must be APPROVE on `test-branch-1`, then
   promote it (see `CLAUDE.md` `## Branches`). App Platform builds `main`, never
   `test-branch-1`.
2. The repo must be **public**. `.do/app.yaml` clones it anonymously over https (a `git:`
   source) rather than through DigitalOcean's GitHub integration, because that integration
   only reaches repos on the connecting user's own GitHub account — and this one lives on a
   teammate's personal account. Nothing to authorize; if the repo ever goes private again the
   build fails at the clone step.
3. Create the app from the spec, not from the wizard's guesses:
   ```bash
   doctl auth init                       # paste a personal access token
   doctl apps create --spec .do/app.yaml
   ```
   Or in the console: **Create App → ... → Edit your App Spec** and paste `.do/app.yaml`.
4. **Set the `DATABASE_URL` secret.** It is intentionally absent from the spec — it is the
   Tiger Data credential from the gitignored root `.env`, and it never goes in git.
   Use the console: **Settings → api → Environment Variables → DATABASE_URL**, paste the
   value, tick *Encrypt*, Save. Keep the `?sslmode=require` on the end — Tiger Data needs it.

   There is no `--env` flag on `doctl apps update`; it only takes `--spec`. To do it from the
   CLI you have to edit the live spec, which means the credential touches a file on disk:
   ```bash
   doctl apps spec get <app-id> > /tmp/live.yaml   # encrypted value comes back as EV[1:...]
   # add `value: <the URL>` under the DATABASE_URL env, then:
   doctl apps update <app-id> --spec /tmp/live.yaml && rm /tmp/live.yaml
   ```
   The console is the better path for a secret. Until it is set the service exits on boot with
   `ConfigError: DATABASE_URL is not set` and the deploy is marked failed — that is
   deliberate, not a bug.
5. Check it, in this order (`<app>` is the assigned `*.ondigitalocean.app` host):
   ```bash
   curl https://<app>/api/health      # {"status":"ok"} — no database needed
   curl https://<app>/api/overlaps    # 39 rows (6 on the sponsor sample); a 500 = bad secret
   open  https://<app>/               # the frontend, talking to /api
   ```
   `/api/health` passing while `/api/overlaps` fails means the app is up but the credential
   is bad — the health check does not touch Postgres.

### Redeploying

- **Redeploys are automatic after CI passes on `main`.** A public-clone (`git:`) source
  can't redeploy on push by itself, so `.github/workflows/ci.yml` does it: on every push to
  `main` (i.e. a promote), once the backend and frontend jobs pass, the `deploy` job runs
  `doctl apps create-deployment --wait`, fails unless the deployment ends `ACTIVE`, then runs
  `scripts/smoke.py` against the live `/api`. If CI fails, nothing deploys. If the deploy
  fails, App Platform keeps the previous deployment serving and the job goes red. To redeploy
  without a new commit, use **Actions → CI/CD → Run workflow** on `main`.
- **One-time setup:** the repo needs a `DIGITALOCEAN_ACCESS_TOKEN` Actions secret (repo
  **Settings → Secrets and variables → Actions**, which only the repo owner can open). Make it
  in the DigitalOcean account that owns the app (**API → Generate New Token**): custom scopes,
  `app` read + update, with an expiry past the event. Without it the deploy job fails loudly at
  its first step and nothing is deployed.
- Manual fallback (e.g. Actions is down), from a laptop with `doctl auth init` done:
  ```bash
  doctl apps list                         # find the app id
  doctl apps create-deployment <app-id>   # rebuilds from the current main
  ```
- After editing `.do/app.yaml`: `doctl apps update <app-id> --spec .do/app.yaml`.
  **This wipes `DATABASE_URL`**, because the committed spec declares the key with no value.
  Set it again in the console (step 4) and re-check `/api/overlaps`. To avoid the wipe
  entirely, start from the live spec instead: `doctl apps spec get <app-id> > /tmp/live.yaml`
  keeps the existing encrypted value, so apply your edits to that file and `rm` it after.
- The database is loaded by hand (`python -m pipeline.load`, above) from a laptop. It is not
  part of the deploy; the deployed API only reads.

Keep `main` deployable: it is the demo. Never push a fix straight to `main` to unbreak a
deploy — fix it on `test-branch-1`, gate it, promote it.
