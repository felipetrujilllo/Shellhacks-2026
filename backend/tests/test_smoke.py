"""scripts/smoke.py: the demo-path smoke test's checks, exit codes and server lifecycle.

No network and no DB: the API is faked with httpx.MockTransport.
"""

import copy
import importlib.util
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("smoke", REPO_ROOT / "scripts" / "smoke.py")
smoke = importlib.util.module_from_spec(_spec)
sys.modules["smoke"] = smoke  # dataclasses look their module up here
_spec.loader.exec_module(smoke)

REFERENCE = smoke.load_reference_pairs(REPO_ROOT)


def overlap(name_a: str, name_b: str, distance_mi: float, rank: int) -> dict:
    return {
        "overlap_id": f"OVL_{rank}", "rank": rank, "score": 0.5,
        "distance_mi": distance_mi, "time_gap_days": 0,
        "project_a": {"project_id": "A", "project_name": name_a},
        "project_b": {"project_id": "B", "project_name": name_b},
    }


def reference_overlaps() -> list[dict]:
    """A fake /overlaps response holding exactly the sponsor's 6 pairs, ranked."""
    return [overlap(r.name_a, r.name_b, r.distance_mi, i + 1) for i, r in enumerate(REFERENCE)]


def fake_api(*, health=None, overlaps=None, unknown_status=404, prefix=""):
    health = {"status": "ok"} if health is None else health
    overlaps = reference_overlaps() if overlaps is None else overlaps

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix(prefix)
        if path == "/health":
            return httpx.Response(200, json=health)
        if path == "/overlaps":
            return httpx.Response(200, json=overlaps)
        if path.startswith("/overlaps/"):
            if unknown_status == 404:
                return httpx.Response(404, json={"detail": "not found"})
            return httpx.Response(unknown_status, json=overlaps[0] if overlaps else {})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def client_for(transport) -> httpx.Client:
    return httpx.Client(base_url="http://smoke.test", transport=transport)


# --- reference data ---------------------------------------------------------------------

def test_load_reference_pairs_reads_the_six_sponsor_pairs_with_names():
    assert len(REFERENCE) == 6
    first = REFERENCE[0]
    assert first.label.startswith("OVL_1 (DESC_2 x GPC_1)")
    assert first.name_a == "Hooks - Thurmond 115 kV Tie: Rebuild"
    assert first.distance_mi == pytest.approx(4.09)
    assert all(r.name_a and r.name_b for r in REFERENCE)


def test_normalize_keeps_only_lowercase_letters_and_digits():
    assert smoke.normalize("Hooks - Thurmond 115 kV Tie: Rebuild") == "hooksthurmond115kvtierebuild"
    assert smoke.normalize("Jasper – Yemassee") == "jasperyemassee"


# --- pair matching ----------------------------------------------------------------------

def test_all_reference_pairs_found_in_seed_built_overlaps():
    assert smoke.find_missing_pairs(reference_overlaps(), REFERENCE) == []


def test_pair_found_despite_spacing_punctuation_and_case_differences():
    ref = REFERENCE[0]  # "Hooks - Thurmond 115 kV Tie: Rebuild"
    renamed = overlap(ref.name_a.replace("115 kV", "115kV").upper(),
                      ref.name_b.lower() + ".", ref.distance_mi, 1)
    assert smoke.find_missing_pairs([renamed], [ref]) == []


def test_pair_found_when_a_and_b_are_swapped():
    ref = REFERENCE[1]
    assert smoke.find_missing_pairs([overlap(ref.name_b, ref.name_a, ref.distance_mi, 1)],
                                    [ref]) == []


def test_pair_missing_when_absent():
    overlaps = reference_overlaps()[1:]
    assert smoke.find_missing_pairs(overlaps, REFERENCE) == [REFERENCE[0]]


def test_pair_distance_tolerance_is_half_a_mile():
    ref = REFERENCE[2]
    within = overlap(ref.name_a, ref.name_b, ref.distance_mi + 0.49, 1)
    beyond = overlap(ref.name_a, ref.name_b, ref.distance_mi + 0.51, 1)
    assert smoke.find_missing_pairs([within], [ref]) == []
    assert smoke.find_missing_pairs([beyond], [ref]) == [ref]


def test_extra_non_reference_overlaps_do_not_fail():
    overlaps = reference_overlaps() + [overlap("Some Other Line", "Another Line", 3.0, 7)]
    assert smoke.find_missing_pairs(overlaps, REFERENCE) == []
    assert "7 overlaps" in smoke.check_api(client_for(fake_api(overlaps=overlaps)), REFERENCE)


# --- check_api against a fake API -------------------------------------------------------

def test_check_api_passes_for_a_well_formed_api():
    summary = smoke.check_api(client_for(fake_api()), REFERENCE)
    assert summary.startswith("smoke OK: 6 overlaps")


def test_check_api_fails_when_health_not_ok():
    with pytest.raises(smoke.SmokeFailure, match="GET /health"):
        smoke.check_api(client_for(fake_api(health={"status": "down"})), REFERENCE)


def test_check_api_fails_when_overlaps_empty():
    with pytest.raises(smoke.SmokeFailure, match="non-empty"):
        smoke.check_api(client_for(fake_api(overlaps=[])), REFERENCE)


def test_check_api_fails_when_overlaps_not_sorted_by_rank():
    overlaps = reference_overlaps()
    overlaps[0], overlaps[1] = overlaps[1], overlaps[0]
    with pytest.raises(smoke.SmokeFailure, match="not sorted by rank"):
        smoke.check_api(client_for(fake_api(overlaps=overlaps)), REFERENCE)


def test_check_api_fails_naming_the_missing_reference_pair():
    overlaps = reference_overlaps()
    del overlaps[3]
    for i, o in enumerate(overlaps):
        o["rank"] = i + 1
    expected = r"1 of the sponsor's 6 .*OVL_4 \(DESC_1 x GPC_1\)"
    with pytest.raises(smoke.SmokeFailure, match=expected):
        smoke.check_api(client_for(fake_api(overlaps=overlaps)), REFERENCE)


def test_check_api_fails_when_unknown_overlap_is_not_404():
    with pytest.raises(smoke.SmokeFailure, match="expected 404, got 200"):
        smoke.check_api(client_for(fake_api(unknown_status=200)), REFERENCE)


# --- main: BASE_URL mode and exit codes -------------------------------------------------

def test_main_base_url_mode_passes_and_starts_no_server(monkeypatch, capsys):
    def no_server():
        raise AssertionError("BASE_URL mode must not start a server")

    monkeypatch.setattr(smoke, "local_server", no_server)
    seen = []
    inner = fake_api(prefix="/api")

    def recording(request):
        seen.append(str(request.url))
        return inner.handle_request(request)

    code = smoke.main({"BASE_URL": "https://gridwatch.example/api/"},
                      transport=httpx.MockTransport(recording))
    assert code == 0
    assert "smoke OK" in capsys.readouterr().out
    # trailing slash stripped, and the path prefix of BASE_URL is kept
    assert seen[0] == "https://gridwatch.example/api/health"


def test_main_exits_nonzero_with_clear_message_on_failure(capsys):
    code = smoke.main({"BASE_URL": "http://smoke.test"},
                      transport=fake_api(unknown_status=200))
    assert code == 1
    assert "smoke FAIL: GET /overlaps/" in capsys.readouterr().err


def test_main_exits_nonzero_on_malformed_response(capsys):
    broken = copy.deepcopy(reference_overlaps())
    del broken[0]["project_a"]
    code = smoke.main({"BASE_URL": "http://smoke.test"}, transport=fake_api(overlaps=broken))
    assert code == 1
    assert "smoke FAIL: malformed API response" in capsys.readouterr().err


def test_main_exits_nonzero_when_server_unreachable(capsys):
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    code = smoke.main({"BASE_URL": "http://smoke.test"}, transport=httpx.MockTransport(refuse))
    assert code == 1
    assert "smoke FAIL: HTTP request to http://smoke.test failed" in capsys.readouterr().err


# --- server lifecycle -------------------------------------------------------------------

SLEEPER = [sys.executable, "-c", "import time; time.sleep(60)"]


def test_managed_process_is_stopped_when_checks_raise(tmp_path):
    with pytest.raises(smoke.SmokeFailure):
        with smoke.managed_process(SLEEPER, tmp_path) as (proc, _log):
            assert proc.poll() is None
            raise smoke.SmokeFailure("a check failed")
    assert proc.poll() is not None


def test_wait_until_ready_fails_loud_with_output_when_server_dies(tmp_path):
    dies = [sys.executable, "-c", "import sys; print('boom: no DATABASE_URL'); sys.exit(3)"]
    with smoke.managed_process(dies, tmp_path) as (proc, log):
        proc.wait(timeout=10)
        with pytest.raises(smoke.SmokeFailure, match=r"(?s)exited with code 3.*boom"):
            smoke.wait_until_ready(proc, log, "http://127.0.0.1:9", timeout=5)


def test_wait_until_ready_times_out(tmp_path):
    with smoke.managed_process(SLEEPER, tmp_path) as (proc, log):
        with pytest.raises(smoke.SmokeFailure, match="not ready after"):
            smoke.wait_until_ready(proc, log, f"http://127.0.0.1:{smoke.free_port()}",
                                   timeout=0.5)
    assert proc.poll() is not None


def test_stop_process_leaves_finished_process_alone():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(timeout=10)
    smoke.stop_process(proc)  # must not raise
    assert proc.returncode == 0
