"""Demo-path smoke test: prove the real end-to-end path serves the ranked overlaps.

Run with the backend venv's Python from the repo root:

    backend/.venv/bin/python scripts/smoke.py
    backend\\.venv\\Scripts\\python.exe scripts\\smoke.py      (Windows)

By default it starts the API (uvicorn, on a free port) against DATABASE_URL from the
repo-root .env and checks it over HTTP. It never loads, truncates or even connects to the
database itself — the demo DB is loaded once and a smoke run must never replace it.

With BASE_URL set (e.g. https://<app>.ondigitalocean.app/api) it starts nothing and runs the
same checks against that deployed API instead.

Exit code 0 = PASS, 1 = FAIL (with a message saying what broke).
"""

from __future__ import annotations

import csv
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
ENV_FILE = REPO_ROOT / ".env"
UNKNOWN_OVERLAP_ID = "OVL_SMOKE_DOES_NOT_EXIST"
DISTANCE_TOLERANCE_MI = 0.5
READY_TIMEOUT_S = 20.0
HTTP_TIMEOUT_S = 30.0


class SmokeFailure(Exception):
    """A check failed; the message says what and is what the user sees."""


@dataclass(frozen=True)
class ReferencePair:
    """One of the sponsor's reference overlaps, with its project IDs resolved to names."""

    label: str  # e.g. "OVL_1 (DESC_2 x GPC_1)"
    name_a: str
    name_b: str
    distance_mi: float


def normalize(name: str) -> str:
    """Lowercase letters and digits only, so "115kV" and "115 kV" compare equal."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_reference_pairs(repo_root: Path = REPO_ROOT) -> list[ReferencePair]:
    """The sponsor's expected overlaps, with IDs resolved to names via the seed CSV."""
    seed = repo_root / "data" / "seed"
    seed_rows = _read_csv(seed / "projects_seed.csv")
    names = {row["project_id"]: row["project_name"] for row in seed_rows}
    pairs = []
    for row in _read_csv(seed / "expected_overlaps.csv"):
        id_a, id_b = row["project_id_a"], row["project_id_b"]
        missing = [pid for pid in (id_a, id_b) if pid not in names]
        if missing:
            raise SmokeFailure(
                f"expected_overlaps.csv references {missing} not found in projects_seed.csv"
            )
        pairs.append(
            ReferencePair(
                label=f"{row['overlap_id']} ({id_a} x {id_b})",
                name_a=names[id_a],
                name_b=names[id_b],
                distance_mi=float(row["distance_mi"]),
            )
        )
    return pairs


def _matches(overlap: dict, ref: ReferencePair) -> bool:
    got = {normalize(overlap["project_a"]["project_name"]),
           normalize(overlap["project_b"]["project_name"])}
    want = {normalize(ref.name_a), normalize(ref.name_b)}
    return got == want and abs(float(overlap["distance_mi"]) - ref.distance_mi) <= (
        DISTANCE_TOLERANCE_MI
    )


def find_missing_pairs(overlaps: list[dict], reference: list[ReferencePair]) -> list[ReferencePair]:
    """Reference pairs with no matching API overlap (names normalized, either order)."""
    return [ref for ref in reference if not any(_matches(o, ref) for o in overlaps)]


def check_api(client: httpx.Client, reference: list[ReferencePair]) -> str:
    """Run every check against `client`'s base URL; return a PASS summary or raise."""
    health = client.get("/health")
    if health.status_code != 200 or health.json() != {"status": "ok"}:
        raise SmokeFailure(f"GET /health: expected 200 {{'status': 'ok'}}, got "
                           f"{health.status_code} {health.text[:200]}")

    resp = client.get("/overlaps")
    if resp.status_code != 200:
        raise SmokeFailure(f"GET /overlaps: expected 200, got {resp.status_code} "
                           f"{resp.text[:200]}")
    overlaps = resp.json()
    if not isinstance(overlaps, list) or not overlaps:
        raise SmokeFailure(f"GET /overlaps: expected a non-empty list, got {overlaps!r:.200}")
    ranks = [o["rank"] for o in overlaps]
    if ranks != sorted(ranks):
        raise SmokeFailure(f"GET /overlaps: not sorted by rank (rank 1 first), got ranks {ranks}")
    missing = find_missing_pairs(overlaps, reference)
    if missing:
        detail = "; ".join(
            f"{r.label}: {r.name_a!r} x {r.name_b!r} ~{r.distance_mi} mi" for r in missing
        )
        raise SmokeFailure(
            f"GET /overlaps: {len(missing)} of the sponsor's {len(reference)} reference pairs "
            f"missing — {detail}"
        )

    unknown = client.get(f"/overlaps/{UNKNOWN_OVERLAP_ID}")
    if unknown.status_code != 404:
        raise SmokeFailure(f"GET /overlaps/{UNKNOWN_OVERLAP_ID}: expected 404, got "
                           f"{unknown.status_code}")

    return (f"smoke OK: {len(overlaps)} overlaps, ranked, the sponsor's {len(reference)} "
            f"reference pairs present; unknown overlap is 404")


def free_port() -> int:
    """A port nothing is listening on right now (the OS picks it)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def stop_process(proc: subprocess.Popen) -> None:
    """Stop a process this script started: terminate, then kill if it won't exit."""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


@contextmanager
def managed_process(cmd: list[str], cwd: Path) -> Iterator[tuple[subprocess.Popen, object]]:
    """Start `cmd` with output captured to a temp file; always stop it on exit."""
    with tempfile.TemporaryFile() as log:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
        try:
            yield proc, log
        finally:
            stop_process(proc)


def _log_tail(log, lines: int = 20) -> str:
    log.seek(0)
    text = log.read().decode("utf-8", errors="replace")
    return "\n".join(text.splitlines()[-lines:])


def wait_until_ready(proc: subprocess.Popen, log, base_url: str,
                     timeout: float = READY_TIMEOUT_S) -> None:
    """Poll /health until the server answers; fail loud with its output if it never does."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise SmokeFailure(f"API server exited with code {proc.returncode} before it was "
                               f"ready. Its output:\n{_log_tail(log)}")
        try:
            httpx.get(f"{base_url}/health", timeout=2)
            return
        except httpx.TransportError:
            time.sleep(0.25)
    raise SmokeFailure(f"API server not ready after {timeout:.0f}s. Its output:\n{_log_tail(log)}")


@contextmanager
def local_server() -> Iterator[str]:
    """Start uvicorn against the repo-root .env on a free port; yield its base URL."""
    if not ENV_FILE.is_file():
        raise SmokeFailure(f"{ENV_FILE} not found: it must hold DATABASE_URL (see .env.example)")
    port = free_port()
    cmd = [sys.executable, "-m", "uvicorn", "app.main:app",
           "--env-file", str(ENV_FILE), "--host", "127.0.0.1", "--port", str(port)]
    base_url = f"http://127.0.0.1:{port}"
    with managed_process(cmd, BACKEND_DIR) as (proc, log):
        wait_until_ready(proc, log, base_url)
        yield base_url


def run_checks(base_url: str, transport: httpx.BaseTransport | None = None) -> str:
    reference = load_reference_pairs()
    with httpx.Client(base_url=base_url, timeout=HTTP_TIMEOUT_S, transport=transport) as client:
        try:
            return check_api(client, reference)
        except httpx.HTTPError as exc:
            raise SmokeFailure(f"HTTP request to {base_url} failed: {exc!r}") from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise SmokeFailure(f"malformed API response from {base_url}: {exc!r}") from exc


def main(environ: Mapping[str, str] | None = None,
         transport: httpx.BaseTransport | None = None) -> int:
    env = os.environ if environ is None else environ
    base_url = (env.get("BASE_URL") or "").strip().rstrip("/")
    try:
        if base_url:
            print(f"smoke: checking deployed API at {base_url}")
            summary = run_checks(base_url, transport)
        else:
            print("smoke: starting the API locally against DATABASE_URL (read-only)")
            with local_server() as local_url:
                summary = run_checks(local_url, transport)
    except SmokeFailure as exc:
        print(f"smoke FAIL: {exc}", file=sys.stderr)
        return 1
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
