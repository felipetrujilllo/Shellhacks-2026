"""Guards for #7: `.env.example` template and no committed credentials."""

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO_ROOT / ".env.example"
REQUIRED_KEYS = ("DATABASE_URL", "FRONTEND_ORIGIN", "VITE_API_URL")

# user:password@ portion of a Postgres URL.
PG_CREDS_RE = re.compile(r"postgres(?:ql)?://([^:\s/]+):([^@\s]+)@")
PLACEHOLDER_CREDS = {("USER", "PASSWORD")}
SKIP_FILES = {"package-lock.json"}


def _parse_env(path: Path) -> dict[str, str]:
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        assert sep, f"malformed line in {path.name}: {line!r}"
        env[key.strip()] = value.strip()
    return env


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )


def test_env_example_defines_required_keys():
    assert ENV_EXAMPLE.is_file(), ".env.example is missing at the repo root"
    env = _parse_env(ENV_EXAMPLE)
    for key in REQUIRED_KEYS:
        assert env.get(key), f"{key} missing or empty in .env.example"


def test_database_url_is_placeholder():
    url = _parse_env(ENV_EXAMPLE)["DATABASE_URL"]
    assert url.startswith(("postgres://", "postgresql://"))
    for token in ("USER", "PASSWORD", "HOST"):
        assert token in url, f"DATABASE_URL should use placeholder token {token}"
    for real_host in ("tsdb.cloud.timescale.com", ".tsdb.cloud"):
        assert real_host not in url, "DATABASE_URL looks like a real Tiger Data host"


def test_env_is_gitignored_and_example_is_not():
    assert _git("check-ignore", "-q", ".env").returncode == 0, ".env must be gitignored"
    assert _git("check-ignore", "-q", ".env.example").returncode == 1, (
        ".env.example must not be gitignored"
    )


def test_no_real_postgres_credentials_in_repo():
    tracked = _git("ls-files").stdout.splitlines()
    untracked = _git("ls-files", "--others", "--exclude-standard").stdout.splitlines()
    offenders = []
    for rel in sorted(set(tracked + untracked)):
        path = REPO_ROOT / rel
        if path.name in SKIP_FILES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for user, password in PG_CREDS_RE.findall(text):
            if (user, password) not in PLACEHOLDER_CREDS:
                offenders.append(f"{rel}: {user}:***@")
    assert not offenders, f"possible real Postgres credentials in: {offenders}"


def test_secret_scan_regex_catches_real_credentials():
    # Sanity check that the scanner would actually flag a real-looking URL.
    # Built by concatenation so this file does not itself trip the repo scan.
    fake_real = "postgres" + "://tsdbadmin:s3cr3tPass@abc.example.com:5432/tsdb"
    assert PG_CREDS_RE.findall(fake_real) == [("tsdbadmin", "s3cr3tPass")]
