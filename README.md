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

### Frontend (React + Vite + TypeScript, Tailwind, MapLibre)

```bash
cd frontend
npm install
npm run dev          # dev server
npm test             # vitest run
npm run typecheck    # tsc -b (type-checks app + tests + vite config)
npm run build        # production build into dist/
```
