"""Guards for the two bug classes that once slipped past green checks (#17).

- Windows encodings: ruff's PLW1514 must flag `open()` without `encoding=`, because the
  platform default on Windows is cp1252, not UTF-8.
- Line endings: `.gitattributes` pins text to LF so the Windows laptop and the Macs never
  flip each other's files, and sponsor documents stay binary.

These shell out to the real ruff and git. If either is missing the test fails - a hygiene
guard that skips itself guards nothing.
"""

import json
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
PYPROJECT = BACKEND_DIR / "pyproject.toml"
RUFF = Path(sys.executable).parent / ("ruff.exe" if sys.platform == "win32" else "ruff")


def ruff_codes(tmp_path: Path, source: str) -> tuple[int, list[str]]:
    """Lint `source` with the backend's ruff config; return (exit code, rule codes hit)."""
    target = tmp_path / "sample.py"
    target.write_text(source, encoding="utf-8")
    proc = subprocess.run(
        [str(RUFF), "check", "--no-cache", "--output-format", "json",
         "--config", str(PYPROJECT), str(target)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode in (0, 1), f"ruff crashed: {proc.stderr}"
    return proc.returncode, [d["code"] for d in json.loads(proc.stdout)]


def git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8",
        check=True,
    )
    return proc.stdout


def test_ruff_flags_open_without_encoding(tmp_path):
    returncode, codes = ruff_codes(tmp_path, 'open("x")\n')
    assert returncode != 0
    assert codes == ["PLW1514"]


def test_ruff_accepts_open_with_encoding(tmp_path):
    # Control: the failure above is PLW1514 specifically, not the config rejecting any file.
    returncode, codes = ruff_codes(tmp_path, 'open("x", encoding="utf-8")\n')
    assert (returncode, codes) == (0, [])


def test_schema_is_read_as_utf8():
    # PLW1514 cannot see through the SCHEMA_PATH module constant, so pin it by hand.
    source = (BACKEND_DIR / "pipeline" / "load.py").read_text(encoding="utf-8")
    assert 'SCHEMA_PATH.read_text(encoding="utf-8")' in source
    assert "SCHEMA_PATH.read_text()" not in source


def check_attr(path: str) -> dict[str, str]:
    """`git check-attr -a` for one (possibly hypothetical) path, as {attribute: value}."""
    attrs = {}
    for line in git("check-attr", "-a", "--", path).splitlines():
        _, attr, value = line.split(": ", 2)
        attrs[attr] = value
    return attrs


def test_text_files_are_lf_everywhere():
    for path in ("backend/pipeline/load.py", "data/seed/desc_projects.csv", "new_file.txt"):
        attrs = check_attr(path)
        assert attrs.get("text") == "auto", (path, attrs)
        assert attrs.get("eol") == "lf", (path, attrs)


def test_sponsor_documents_are_binary():
    for path in ("data/source/x.pdf", "x.xlsx", "docs/x.docx"):
        attrs = check_attr(path)
        # `binary` is the macro for -text -diff: no EOL conversion and no text diffs.
        assert attrs.get("binary") == "set", (path, attrs)
        assert attrs.get("text") == "unset", (path, attrs)
        assert attrs.get("diff") == "unset", (path, attrs)


def test_no_crlf_text_files_in_index():
    lines = git("ls-files", "--eol").splitlines()
    assert lines, "git ls-files returned nothing; not running inside the repo?"
    crlf = [line for line in lines if line.startswith("i/crlf")]
    assert crlf == []
