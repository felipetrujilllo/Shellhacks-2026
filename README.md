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
docker run -d --name gridwatch-pg -e POSTGRES_PASSWORD=throwaway \
    -e POSTGRES_DB=gridwatch_test -p 55432:5432 postgis/postgis:16-3.4

cd backend
TEST_DATABASE_URL=postgresql://postgres:throwaway@localhost:55432/gridwatch_test \
    .venv/bin/python -m pytest
```

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
