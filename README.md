# Shellhacks-2026
Gridlock

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

```bash
docker run -d --name gridwatch-pg -e POSTGRES_HOST_AUTH_METHOD=trust \
    -e POSTGRES_DB=gridwatch_test -p 55432:5432 postgis/postgis:16-3.4

cd backend
TEST_DATABASE_URL=postgresql://postgres@localhost:55432/gridwatch_test \
    .venv/bin/python -m pytest
```

Trust auth on purpose: the container is throwaway and local-only, so there is no password
to put in a URL and nothing for the credential scanner in `tests/test_env_example.py` to
flag.

Without it, those tests skip and `pytest` still passes — so run it before touching
`db/schema.sql` or `pipeline/load.py`.

### Loading seed data

```bash
cd backend
.venv/bin/python -m pipeline.load --csv tests/fixtures/starter_projects.csv
```

Reads `--database-url` or `$DATABASE_URL`, applies `db/schema.sql`, then replaces both tables
in one transaction. Re-running it is the supported way to refresh. The real seed CSV
(`data/seed/projects_seed.csv`) is issue #2's deliverable and does not exist yet; until it
lands, the ten-row sponsor starter table above is the only CSV that loads end to end.

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

## Deploying to DigitalOcean (App Platform)

The whole app is one App Platform app with two components, described by `.do/app.yaml`
(#8). **That file is the source of truth, not the dashboard** — if you change something in
the console, put it in the spec too, or the next `doctl apps update` will undo it.

| Component | Type | Source | Served at |
|---|---|---|---|
| `api` | service (Python buildpack) | `backend/` | `/api` → uvicorn, prefix stripped |
| `web` | static site (Node buildpack) | `frontend/` | `/` → Vite's `dist/` |

Both components live behind one hostname, which is how the chicken-and-egg between the two
URLs is solved: the backend's `FRONTEND_ORIGIN` is `${APP_URL}` (the frontend is served from
that same origin) and the frontend's `VITE_API_URL` is `${api.PUBLIC_URL}` (the app URL plus
`/api`). No hostname is written down anywhere, so renaming the app breaks nothing. Requests
are same-origin in production, so CORS never has to be right for the demo to work.

`VITE_API_URL` is scoped `BUILD_TIME` on purpose: Vite bakes `import.meta.env.VITE_*` into
the bundle when it builds, so a run-time-only value would never reach the browser.

`backend/requirements.txt` holds a single `.` — the Python buildpack refuses to recognize a
component with only a `pyproject.toml`, and `.` makes it install this project, so the
dependency list stays in one place.

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
   curl https://<app>/api/overlaps    # 6 rows; if this 500s, the secret is wrong
   open  https://<app>/               # the frontend, talking to /api
   ```
   `/api/health` passing while `/api/overlaps` fails means the app is up but the credential
   is bad — the health check does not touch Postgres.

### Redeploying

- **Redeploys are manual.** A public-clone (`git:`) source can't redeploy on push, so after
  promoting `test-branch-1` to `main`, trigger it yourself:
  ```bash
  doctl apps list                         # find the app id
  doctl apps create-deployment <app-id>   # rebuilds from the current main
  ```
  Upside: a stray push to `main` can never take the live demo down on its own.
- After editing `.do/app.yaml`: `doctl apps update <app-id> --spec .do/app.yaml`.
  **This wipes `DATABASE_URL`**, because the committed spec declares the key with no value.
  Set it again in the console (step 4) and re-check `/api/overlaps`. To avoid the wipe
  entirely, start from the live spec instead: `doctl apps spec get <app-id> > /tmp/live.yaml`
  keeps the existing encrypted value, so apply your edits to that file and `rm` it after.
- The database is loaded by hand (`python -m pipeline.load`, above) from a laptop. It is not
  part of the deploy; the deployed API only reads.

Keep `main` deployable: it is the demo. Never push a fix straight to `main` to unbreak a
deploy — fix it on `test-branch-1`, gate it, promote it.
