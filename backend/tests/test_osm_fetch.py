"""Tests for the Overpass substation fetch and the caches it committed.

No test here touches the network: `fetch` gets a mocked session, and an autouse guard makes any
real socket connection fail the test.
"""

import json
import socket
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from pipeline.osm_fetch import (
    DESC,
    GPC,
    OVERPASS_ENDPOINT,
    UNTAGGED_SC,
    UTILITIES,
    OverpassError,
    build_query,
    fetch,
    parse_response,
    write_cache,
)

FIXTURE = Path(__file__).parent / "fixtures" / "osm_sample.json"


@pytest.fixture(autouse=True)
def no_real_sockets(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("test attempted a real network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def mock_session(status_code=200, payload=None, text=""):
    response = MagicMock(status_code=status_code, text=text)
    response.json.return_value = payload if payload is not None else {"elements": []}
    session = MagicMock(spec=requests.Session)
    session.post.return_value = response
    return session


# --- build_query -------------------------------------------------------------------------


def test_build_query_matches_guide_filter_with_center_output():
    query = build_query("Georgia Power|Savannah Electric", (30.35, -85.65, 35.0, -80.75))
    assert query == (
        "[out:json][timeout:240];\n"
        "(\n"
        '  nwr["power"="substation"]["operator"~"Georgia Power|Savannah Electric",i]\n'
        "    (30.35,-85.65,35.0,-80.75);\n"
        ");\n"
        "out tags center;\n"
    )


def test_build_query_bbox_is_south_west_north_east():
    query = build_query("X", (1.5, -2.5, 3.5, -0.5))
    assert "(1.5,-2.5,3.5,-0.5)" in query


# --- parse_response ----------------------------------------------------------------------


def test_parse_response_on_synthetic_fixture():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    records, dropped = parse_response(payload)
    assert records == [
        {
            "osm_id": "node/100",
            "name": "St. Andrews Substation",
            "lat": 32.7801876,
            "lon": -79.988828,
            "operator": "SCE&G",
        },
        {
            "osm_id": "relation/300",
            "name": "Thurmond Substation",
            "lat": 33.6601273,
            "lon": -82.1959307,
            "operator": "Georgia Power",
        },
        {
            "osm_id": "way/200",
            "name": "McIntosh Substation",
            "lat": 32.3521162,
            "lon": -81.1751124,
            "operator": "Georgia Power",
        },
    ]
    # unnamed way, way with no tags, named way with no coordinates
    assert dropped == 3


def test_write_cache_is_stable_utf8_json(tmp_path):
    records = [{"osm_id": "node/1", "name": "Jasper – Yemassee", "lat": 1.0, "lon": 2.0,
                "operator": "Dominion Energy"}]
    path = tmp_path / "sub" / "cache.json"
    write_cache(records, path)
    text = path.read_text(encoding="utf-8")
    assert "Jasper – Yemassee" in text  # ensure_ascii=False
    assert text.endswith("]\n")
    assert json.loads(text) == records


def test_build_query_untagged_selects_named_substations_without_operator():
    query = build_query(None, UNTAGGED_SC.bbox)
    assert UNTAGGED_SC.bbox == DESC.bbox
    assert 'nwr["power"="substation"][!"operator"]["name"]' in query
    assert "(32.0,-83.4,35.25,-78.5)" in query
    assert '"operator"~' not in query
    assert "out tags center;" in query
    assert query.startswith("[out:json]")


def test_parse_response_keeps_named_element_without_operator():
    payload = {
        "elements": [
            {"type": "node", "id": 7, "lat": 32.36, "lon": -81.12,
             "tags": {"name": "Jasper Substation", "power": "substation"}},
        ]
    }
    records, dropped = parse_response(payload)
    assert records == [
        {"osm_id": "node/7", "name": "Jasper Substation", "lat": 32.36, "lon": -81.12,
         "operator": None}
    ]
    assert dropped == 0


# --- committed caches --------------------------------------------------------------------


@pytest.mark.parametrize("utility", UTILITIES, ids=lambda u: u.key)
def test_cache_file_is_non_empty_named_and_inside_bbox(utility):
    assert utility.cache_path.exists(), f"missing {utility.cache_path}"
    records = json.loads(utility.cache_path.read_text(encoding="utf-8"))
    assert len(records) > 0
    south, west, north, east = utility.bbox
    for record in records:
        assert isinstance(record["name"], str) and record["name"].strip(), record
        assert isinstance(record["lat"], float) and isinstance(record["lon"], float), record
        assert south <= record["lat"] <= north, record
        assert west <= record["lon"] <= east, record
    ids = [r["osm_id"] for r in records]
    assert len(ids) == len(set(ids))
    assert ids == sorted(ids)


def test_caches_exclude_third_party_operators():
    # Operator-filtered caches only; the untagged cache has operator null by definition and is
    # checked in test_untagged_cache_is_named_operatorless_inside_sc_bbox.
    third_party = ("santee", "duke", "georgia transmission", "meag", "municipal", "corps",
                   "university", "southern power")
    for utility in (DESC, GPC):
        records = json.loads(utility.cache_path.read_text(encoding="utf-8"))
        for record in records:
            operator = (record["operator"] or "").lower()
            assert not any(t in operator for t in third_party), record


def test_untagged_cache_is_named_operatorless_inside_sc_bbox():
    path = UNTAGGED_SC.cache_path
    assert path.exists(), f"missing {path}"
    records = json.loads(path.read_text(encoding="utf-8"))
    assert len(records) > 0
    south, west, north, east = UNTAGGED_SC.bbox
    for record in records:
        assert set(record) == {"osm_id", "name", "lat", "lon", "operator"}, record
        assert isinstance(record["name"], str) and record["name"].strip(), record
        assert isinstance(record["lat"], float) and isinstance(record["lon"], float), record
        assert south <= record["lat"] <= north, record
        assert west <= record["lon"] <= east, record
        assert record["operator"] is None, record
    ids = [r["osm_id"] for r in records]
    assert len(ids) == len(set(ids))
    assert ids == sorted(ids)
    for utility in UTILITIES:
        tagged = json.loads(utility.cache_path.read_text(encoding="utf-8"))
        assert not set(ids) & {r["osm_id"] for r in tagged}, utility.key


# --- fetch -------------------------------------------------------------------------------


def test_fetch_posts_query_with_user_agent_and_returns_json():
    payload = {"elements": [{"type": "node", "id": 1}]}
    session = mock_session(payload=payload)
    assert fetch("QUERY", session) == payload
    args, kwargs = session.post.call_args
    assert args[0] == OVERPASS_ENDPOINT
    assert kwargs["data"] == {"data": "QUERY"}
    assert "GridWatch" in kwargs["headers"]["User-Agent"]
    assert kwargs["timeout"] > 0


@pytest.mark.parametrize("status", [429, 504, 500])
def test_fetch_non_200_fails_loud_with_status(status):
    session = mock_session(status_code=status, text="rate limited")
    with pytest.raises(OverpassError, match=str(status)):
        fetch("QUERY", session)
    assert session.post.call_count == 1  # no retry loop


def test_fetch_connection_error_fails_loud():
    session = MagicMock(spec=requests.Session)
    session.post.side_effect = requests.ConnectionError("name resolution failed")
    with pytest.raises(OverpassError, match="name resolution failed"):
        fetch("QUERY", session, endpoint="https://example.invalid/api")


def test_fetch_non_json_200_fails_loud():
    session = mock_session(text="<html>Too busy</html>")
    session.post.return_value.json.side_effect = requests.exceptions.JSONDecodeError(
        "Expecting value", "<html>", 0
    )
    with pytest.raises(OverpassError, match="non-JSON"):
        fetch("QUERY", session)


def test_fetch_server_side_timeout_remark_fails_loud():
    session = mock_session(payload={"elements": [], "remark": "runtime error: Query timed out"})
    with pytest.raises(OverpassError, match="timed out"):
        fetch("QUERY", session)


def test_socket_guard_blocks_real_http():
    with pytest.raises(AssertionError, match="real network"):
        requests.get("http://127.0.0.1:9", timeout=1)
