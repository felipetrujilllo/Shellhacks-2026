"""Post-load check: does the demo API serve exactly what data/seed/projects.csv loads?

Run it right after `python -m pipeline.load` (README "Loading seed data"), from the repo root:

    backend/.venv/bin/python scripts/check_demo_data.py
    backend\\.venv\\Scripts\\python.exe scripts\\check_demo_data.py      (Windows)

It reads the CSV and runs the overlap engine on it exactly as pipeline.load does, then asks
the API for GET /projects and GET /overlaps and compares: same project IDs (so the counts
match), and the same cross-utility pairs as the engine flags. smoke.py checks the sponsor's
6 pairs are there; this checks nothing else is missing or left over from an older load.

Like smoke.py, it starts the API locally against DATABASE_URL from the repo-root .env
(read-only: it never connects to the database itself), or with BASE_URL set
(e.g. https://<app>.ondigitalocean.app/api) checks that deployed API instead. After rolling
back to the sponsor's sample, pass `--csv data/seed/projects_seed.csv`.

Exit code 0 = PASS, 1 = FAIL (with a message saying what differs).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx
import smoke  # scripts/smoke.py: shares its server lifecycle and failure type

from app.submissions import SUBMITTED_ID_PREFIX, SUBMITTED_OVERLAP_PREFIX
from pipeline.load import read_project_csv, to_engine_project
from pipeline.overlap import detect_overlaps

DEFAULT_CSV = smoke.REPO_ROOT / "data" / "seed" / "projects.csv"
SHOW_AT_MOST = 5  # IDs listed per difference, so a wrong-dataset load stays readable

Pair = frozenset[str]  # the two project IDs of an overlap, order-free


@dataclass(frozen=True)
class ExpectedData:
    """What the API should serve after loading one CSV."""

    project_ids: frozenset[str]
    overlap_pairs: frozenset[Pair]


def expected_from_csv(csv_path: Path) -> ExpectedData:
    """Read and run the engine exactly as pipeline.load's main() does."""
    rows = read_project_csv(csv_path)
    overlaps = detect_overlaps(to_engine_project(r) for r in rows)
    return ExpectedData(
        project_ids=frozenset(r.project_id for r in rows),
        overlap_pairs=frozenset(frozenset((o.project_id_a, o.project_id_b)) for o in overlaps),
    )


def _sample(items) -> str:
    shown = sorted(items)[:SHOW_AT_MOST]
    more = len(items) - len(shown)
    return "; ".join(shown) + (f" (+{more} more)" if more else "")


def _pair_label(pair: Pair) -> str:
    return " x ".join(sorted(pair))


def find_differences(
    expected: ExpectedData, projects: Sequence[dict], overlaps: Sequence[dict]
) -> list[str]:
    """Every way the API's response differs from `expected`; empty means they agree."""
    problems = []

    served_ids = [p["project_id"] for p in projects]
    if len(served_ids) != len(expected.project_ids):
        problems.append(
            f"GET /projects: {len(served_ids)} projects, but the CSV has "
            f"{len(expected.project_ids)}"
        )
    missing = expected.project_ids - set(served_ids)
    extra = set(served_ids) - expected.project_ids
    if missing:
        problems.append(f"GET /projects: missing {len(missing)} from the CSV: {_sample(missing)}")
    if extra:
        problems.append(f"GET /projects: {len(extra)} not in the CSV: {_sample(extra)}")

    served_pairs = [
        frozenset((o["project_a"]["project_id"], o["project_b"]["project_id"])) for o in overlaps
    ]
    if len(served_pairs) != len(expected.overlap_pairs):
        problems.append(
            f"GET /overlaps: {len(served_pairs)} overlaps, but the engine flags "
            f"{len(expected.overlap_pairs)} on the CSV"
        )
    missing_pairs = expected.overlap_pairs - set(served_pairs)
    extra_pairs = set(served_pairs) - expected.overlap_pairs
    if missing_pairs:
        problems.append(
            f"GET /overlaps: missing {len(missing_pairs)} engine pairs: "
            f"{_sample({_pair_label(p) for p in missing_pairs})}"
        )
    if extra_pairs:
        problems.append(
            f"GET /overlaps: {len(extra_pairs)} pairs the engine does not flag: "
            f"{_sample({_pair_label(p) for p in extra_pairs})}"
        )
    return problems


def _get_list(client: httpx.Client, path: str) -> list[dict]:
    resp = client.get(path)
    if resp.status_code != 200:
        raise smoke.SmokeFailure(f"GET {path}: expected 200, got {resp.status_code} "
                                 f"{resp.text[:200]}")
    body = resp.json()
    if not isinstance(body, list):
        raise smoke.SmokeFailure(f"GET {path}: expected a list, got {body!r:.200}")
    return body


def check_api(client: httpx.Client, expected: ExpectedData) -> str:
    """Compare `client`'s API with `expected`; return a PASS summary or raise SmokeFailure.

    GET /projects serves only the published plans; GET /overlaps also serves the standing
    sample submissions' pairs (SUB: ids, #62: never in the database, see backend/app/samples.py).
    A deployed API still on the old shared-uploads code served uploads (SUB- ids) on both. None
    of those come from the CSV, so they are left out of the comparison and only counted in the
    summary.
    """
    served_projects = _get_list(client, "/projects")
    served_overlaps = _get_list(client, "/overlaps")
    projects = [p for p in served_projects
                if not p["project_id"].startswith(SUBMITTED_ID_PREFIX)]
    overlaps = [o for o in served_overlaps
                if not o["overlap_id"].startswith(SUBMITTED_OVERLAP_PREFIX)]
    problems = find_differences(expected, projects, overlaps)
    if problems:
        raise smoke.SmokeFailure("the API does not serve the CSV's data:\n  - "
                                 + "\n  - ".join(problems))
    summary = (f"demo data OK: {len(projects)} projects and {len(overlaps)} overlaps, "
               f"matching the CSV and the engine")
    uploaded = len(served_projects) - len(projects)
    uploaded_pairs = len(served_overlaps) - len(overlaps)
    if uploaded:
        summary += (f" (ignored {uploaded} uploaded project(s) and "
                    f"{uploaded_pairs} of their pair(s))")
    elif uploaded_pairs:
        summary += f" (ignored {uploaded_pairs} sample-submission pair(s))"
    return summary


def run_checks(base_url: str, expected: ExpectedData,
               transport: httpx.BaseTransport | None = None) -> str:
    with httpx.Client(base_url=base_url, timeout=smoke.HTTP_TIMEOUT_S,
                      transport=transport) as client:
        try:
            return check_api(client, expected)
        except httpx.HTTPError as exc:
            raise smoke.SmokeFailure(f"HTTP request to {base_url} failed: {exc!r}") from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise smoke.SmokeFailure(f"malformed API response from {base_url}: {exc!r}") from exc


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None,
         transport: httpx.BaseTransport | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the API serves the loaded CSV's data.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV,
                        help="the CSV that was loaded (default: data/seed/projects.csv)")
    args = parser.parse_args(argv)

    env = os.environ if environ is None else environ
    base_url = (env.get("BASE_URL") or "").strip().rstrip("/")
    try:
        expected = expected_from_csv(args.csv)
        if base_url:
            print(f"check_demo_data: checking deployed API at {base_url}")
            summary = run_checks(base_url, expected, transport)
        else:
            print("check_demo_data: starting the API locally against DATABASE_URL (read-only)")
            with smoke.local_server() as local_url:
                summary = run_checks(local_url, expected, transport)
    except smoke.SmokeFailure as exc:
        print(f"check_demo_data FAIL: {exc}", file=sys.stderr)
        return 1
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
