"""A project's center point, from the substations at its two ends.

docs/prompt.md, method step 3: "project center = midpoint of its two named points (or the
one point if only one is located)". The sponsor's starter table computes that midpoint as a
plain average of latitudes and of longitudes, not a great-circle midpoint — at the tens of
miles a transmission line spans the two differ far below the table's six decimals, and
matching the sponsor exactly is what keeps the golden overlaps reproducible.
"""

from __future__ import annotations


class HalfLocatedEndpointError(ValueError):
    """An endpoint has a latitude without a longitude, or the reverse.

    That is bad data (a truncated row or a mis-mapped column), not an unlocated
    substation, so it fails loud instead of being quietly dropped.
    """


def located_point(
    lat: float | None, lon: float | None, label: str
) -> tuple[float, float] | None:
    """(lat, lon) if both are present, None if neither is; a half-filled pair raises."""
    if lat is None and lon is None:
        return None
    if lat is None or lon is None:
        missing = "latitude" if lat is None else "longitude"
        raise HalfLocatedEndpointError(f"endpoint {label} has no {missing}")
    return lat, lon


def project_center(
    lat_a: float | None,
    lon_a: float | None,
    lat_b: float | None,
    lon_b: float | None,
) -> tuple[float, float] | None:
    """Midpoint of the located endpoints, the one located endpoint, or None if neither is.

    None means the project cannot be placed; the caller decides whether that excludes it
    or aborts the load.
    """
    points = [
        p
        for p in (located_point(lat_a, lon_a, "a"), located_point(lat_b, lon_b, "b"))
        if p is not None
    ]
    if not points:
        return None
    lat = sum(p[0] for p in points) / len(points)
    lon = sum(p[1] for p in points) / len(points)
    return lat, lon
