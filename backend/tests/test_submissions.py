"""Uploaded projects: preparing an upload, and the pairs it adds to the ranked list (no DB)."""

import csv
from pathlib import Path

import pytest

from app.repository import ranked_overlaps
from app.schemas import Project
from app.submissions import SubmissionConflict, prepare_submission, submitted_overlaps
from pipeline.overlap import (
    TIER_ORDER,
    closest_approach_miles,
    coordination_tier,
    detect_overlaps,
    footprint,
)
from pipeline.overlap import Overlap as EngineOverlap
from pipeline.overlap import Project as EngineProject

STARTER_CSV = Path(__file__).parent / "fixtures" / "starter_projects.csv"
STARTER_OVERLAPS_CSV = Path(__file__).parent / "fixtures" / "starter_overlaps.csv"

# GPC_2's center and in-service date in the sponsor's starter table.
GPC_2_LAT, GPC_2_LON, GPC_2_DATE = 32.352116, -81.175112, "2026-06-01"


def published() -> list[Project]:
    with open(STARTER_CSV, newline="", encoding="utf-8") as f:
        return [Project.model_validate(row) for row in csv.DictReader(f)]


def stored_overlaps() -> list[EngineOverlap]:
    """What pipeline.load writes to project_overlaps for the starter table."""
    return detect_overlaps(
        EngineProject(p.project_id, p.utility, p.lat_center, p.lon_center, p.in_service_date)
        for p in published()
    )


def upload(**overrides) -> Project:
    """One uploaded row as the frontend sends it; defaults sit exactly on GPC_2."""
    return Project.model_validate(
        {
            "project_id": "client-ref-1",
            "utility": "Tidewater Grid Co.",
            "state": "SC",
            "project_name": "Savannah River crossing",
            "lat_center": GPC_2_LAT,
            "lon_center": GPC_2_LON,
            "in_service_date": GPC_2_DATE,
            "location_confidence": "confirmed",
            **overrides,
        }
    )


# --- prepare_submission ---------------------------------------------------------------------


def test_every_project_is_served_as_sub_plus_the_id_the_browser_gave_it():
    prepared = prepare_submission(
        [upload(project_id="b1-1"), upload(project_id="b1-2", project_name="Second line")],
        published(),
    )
    assert [p.project_id for p in prepared] == ["SUB-b1-1", "SUB-b1-2"]


def test_the_same_upload_gets_the_same_ids_on_every_call():
    """The browser re-sends its uploads on every load and keys the selection on these ids."""
    sent = [upload(project_id="b1-1"), upload(project_id="b1-2", project_name="Second line")]
    assert prepare_submission(sent, published()) == prepare_submission(sent, published())


def test_two_uploads_with_different_client_ids_never_share_an_id():
    [first, second] = prepare_submission(
        [upload(project_id="a-1"), upload(project_id="b-1", project_name="Other")], published()
    )
    assert first.project_id != second.project_id


def test_a_client_id_used_twice_in_one_upload_is_refused():
    with pytest.raises(SubmissionConflict, match="reuses the id 'b1-1'"):
        prepare_submission(
            [upload(project_id="b1-1"), upload(project_id="b1-1", project_name="Other")], []
        )


def test_uploaded_locations_are_marked_low_confidence_even_if_the_client_says_confirmed():
    [project] = prepare_submission([upload(location_confidence="confirmed")], published())
    assert project.location_confidence == "low"


def test_everything_else_the_client_sent_is_kept():
    sent = upload(est_cost_usd=2_500_000, name_a="West Sub", lat_a=32.35, lon_a=-81.18)
    [project] = prepare_submission([sent], published())
    kept = project.model_dump(exclude={"project_id", "location_confidence"})
    assert kept == sent.model_dump(exclude={"project_id", "location_confidence"})


def test_a_utility_matching_a_published_one_ignoring_case_takes_its_spelling():
    [project] = prepare_submission([upload(utility="  georgia POWER ")], published())
    assert project.utility == "Georgia Power"


def test_a_utility_with_extra_inner_spaces_still_matches_the_published_one():
    [project] = prepare_submission([upload(utility="georgia  POWER")], published())
    assert project.utility == "Georgia Power"


def test_a_new_utility_keeps_its_own_spelling_trimmed():
    [project] = prepare_submission([upload(utility=" Tidewater Grid Co. ")], published())
    assert project.utility == "Tidewater Grid Co."


def test_a_project_that_already_exists_is_refused_ignoring_case():
    existing = published()
    duplicate = upload(utility="georgia power", project_name=existing[5].project_name.upper())
    with pytest.raises(SubmissionConflict, match="already exists"):
        prepare_submission([upload(), duplicate], existing)


def test_the_same_project_twice_in_one_upload_is_refused():
    with pytest.raises(SubmissionConflict, match="appears twice"):
        prepare_submission([upload(), upload(project_name="savannah river CROSSING ")], [])


# --- submitted_overlaps ---------------------------------------------------------------------


def test_an_upload_on_top_of_a_published_project_is_flagged_at_zero_miles():
    submitted = prepare_submission([upload(project_id="b1-1")], published())
    found = submitted_overlaps(published(), submitted)
    pairs = {(o.project_id_a, o.project_id_b): o for o in found}

    pair = pairs[("GPC_2", "SUB-b1-1")]
    assert pair.overlap_id == "SUB:GPC_2|SUB-b1-1"
    assert (pair.distance_mi, pair.time_gap_days, pair.score) == (0.0, 0, 1.0)
    # DESC_3 is 5.65 mi from GPC_2 in the sponsor's table, so it is 5.65 mi from the upload too.
    assert pairs[("DESC_3", "SUB-b1-1")].distance_mi == 5.65


def test_published_only_pairs_are_left_to_the_stored_table():
    submitted = prepare_submission([upload()], published())
    for pair in submitted_overlaps(published(), submitted):
        assert pair.overlap_id.startswith("SUB:")
        assert submitted[0].project_id in (pair.project_id_a, pair.project_id_b)


def test_an_upload_far_from_everything_adds_no_pairs():
    # Birmingham, AL: hundreds of miles from every starter project.
    far = upload(lat_center=33.5186, lon_center=-86.8104)
    assert submitted_overlaps(published(), prepare_submission([far], published())) == []


def test_an_upload_is_never_paired_with_its_own_utility_however_it_is_spelled():
    submitted = prepare_submission([upload(utility="GEORGIA power")], published())
    partners = {
        p
        for o in submitted_overlaps(published(), submitted)
        for p in (o.project_id_a, o.project_id_b)
    }
    assert not {"GPC_2", "GPC_3"} & partners
    assert "DESC_3" in partners


def test_two_uploads_from_different_utilities_pair_with_each_other():
    submitted = prepare_submission(
        [upload(project_id="a-1"), upload(project_id="b-1", utility="Palmetto Co-op")], []
    )
    [pair] = submitted_overlaps([], submitted)
    assert (pair.project_id_a, pair.project_id_b) == ("SUB-a-1", "SUB-b-1")


# --- ranked_overlaps ------------------------------------------------------------------------


def test_without_uploads_the_ranking_is_the_sponsors_six_tier_first_then_by_score():
    ranked = ranked_overlaps(stored_overlaps(), published(), [])
    assert [o.rank for o in ranked] == [1, 2, 3, 4, 5, 6]
    with open(STARTER_OVERLAPS_CSV, newline="", encoding="utf-8") as f:
        assert {o.overlap_id for o in ranked} == {row["overlap_id"] for row in csv.DictReader(f)}
    # Tier first (OVL_1 touches at Thurmond), then by descending score within each tier.
    assert [(o.overlap_id, o.tier) for o in ranked] == [
        ("OVL_1", "crossing"),
        ("OVL_2", "site_logistics"),
        ("OVL_3", "site_logistics"),
        ("OVL_5", "crews"),
        ("OVL_6", "crews"),
        ("OVL_4", "crews"),
    ]
    for tier in TIER_ORDER:
        scores = [o.score for o in ranked if o.tier == tier]
        assert scores == sorted(scores, reverse=True), tier


def test_an_upload_right_on_a_published_project_ranks_first_and_keeps_every_published_pair():
    submitted = prepare_submission([upload(project_id="b1-1")], published())
    ranked = ranked_overlaps(stored_overlaps(), published(), submitted)

    assert ranked[0].overlap_id == "SUB:GPC_2|SUB-b1-1"
    assert ranked[0].project_b.utility == "Tidewater Grid Co."
    assert [o.rank for o in ranked] == list(range(1, len(ranked) + 1))
    assert {f"OVL_{n}" for n in range(1, 7)} <= {o.overlap_id for o in ranked}


def test_an_uploaded_pair_with_a_cost_carries_a_savings_estimate():
    submitted = prepare_submission([upload(est_cost_usd=2_000_000)], published())
    top = ranked_overlaps(stored_overlaps(), published(), submitted)[0]
    # 5% of the known cost at 0 mi and a 0-day gap (pipeline/savings.py): nothing discounted.
    assert top.est_savings_usd == 100_000


def test_every_ranked_pair_carries_closest_mi_and_tier_from_the_engine():
    submitted = prepare_submission([upload(project_id="b1-1")], published())
    ranked = ranked_overlaps(stored_overlaps(), published(), submitted)

    assert any(o.overlap_id.startswith("SUB:") for o in ranked)
    for o in ranked:
        shapes = [
            footprint(p.lat_a, p.lon_a, p.lat_b, p.lon_b, p.lat_center, p.lon_center)
            for p in (o.project_a, o.project_b)
        ]
        assert o.closest_mi == closest_approach_miles(*shapes), o.overlap_id
        assert o.tier == coordination_tier(o.closest_mi), o.overlap_id


def test_an_upload_without_endpoints_is_measured_from_its_center_and_ranked_tier_first():
    # 1.04 mi from GPC_2's center: the best score of any pair, but not a crossing.
    near = upload(project_id="b1-1", lat_center=32.36, lon_center=-81.16)
    assert None in (near.lat_a, near.lon_a, near.lat_b, near.lon_b)
    submitted = prepare_submission([near], published())

    ranked = ranked_overlaps(stored_overlaps(), published(), submitted)
    pair = next(o for o in ranked if o.overlap_id == "SUB:GPC_2|SUB-b1-1")

    assert (pair.closest_mi, pair.tier) == (1.04, "site_logistics")
    assert pair.score == max(o.score for o in ranked)
    assert ranked[0].overlap_id == "OVL_1" and ranked[0].tier == "crossing"
    assert pair.rank == 2
    tiers = [TIER_ORDER.index(o.tier) for o in ranked]
    assert tiers == sorted(tiers)


def test_an_upload_with_endpoints_crossing_a_published_line_ranks_as_a_crossing():
    # A short line cutting straight across DESC_3's Jasper-Okatie segment (north to south at
    # its midpoint). Its center sits just off DESC_3's, so only the segments touch: measured
    # center to center it would not be a crossing.
    near = upload(
        project_id="b1-1",
        lat_a=32.39, lon_a=-81.0785475, lat_b=32.30, lon_b=-81.0785475,
        lat_center=32.345, lon_center=-81.0785475,
    )
    submitted = prepare_submission([near], published())

    ranked = ranked_overlaps(stored_overlaps(), published(), submitted)
    pair = next(o for o in ranked if o.overlap_id == "SUB:DESC_3|SUB-b1-1")

    assert (pair.closest_mi, pair.tier) == (0.0, "crossing")
    assert pair.distance_mi > 0
    # Two crossings now (it and OVL_1); its far higher score puts it first.
    assert [o.overlap_id for o in ranked if o.tier == "crossing"] == [
        "SUB:DESC_3|SUB-b1-1", "OVL_1"
    ]
    assert pair.rank == 1
