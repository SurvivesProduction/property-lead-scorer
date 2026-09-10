"""Pure-function tests for the canopy zonal-stats logic -- no network, per
this project's two-layer testing standard. Live tests against the real
NOAA ImageServer live in property-lead-scorer-full's own test suite.
"""
from __future__ import annotations

import math

import pytest

from extscorer.enrichment.canopy_lookup import build_circle_ring, compute_canopy_percentage


def test_build_circle_ring_is_closed_and_roughly_correct_radius() -> None:
    lat, lon = 41.897, -71.961
    radius_m = 100
    ring = build_circle_ring(lat, lon, radius_m, n_points=24)

    assert ring[0] == ring[-1]  # closed ring
    assert len(ring) == 25

    # Every vertex should be ~radius_m from the center (within a few
    # percent -- flat-earth approximation, not exact geodesy).
    for point_lon, point_lat in ring[:-1]:
        dx_m = (point_lon - lon) * 111_320 * math.cos(math.radians(lat))
        dy_m = (point_lat - lat) * 111_320
        distance = math.hypot(dx_m, dy_m)
        assert abs(distance - radius_m) < radius_m * 0.05


def test_build_circle_ring_rejects_nonpositive_radius() -> None:
    with pytest.raises(ValueError):
        build_circle_ring(41.9, -71.9, 0)
    with pytest.raises(ValueError):
        build_circle_ring(41.9, -71.9, -10)


def test_compute_canopy_percentage_real_wooded_response_shape() -> None:
    # Real response shape confirmed live 2026-09-09 against a wooded
    # Pomfret, CT point: {"size":2,"min":-0.5,"max":1.5,"counts":[18093,37963]}
    # -- bin 0 = class 0 (Background), bin 1 = class 1 (Upland Tree).
    response = {"histograms": [{"size": 2, "min": -0.5, "max": 1.5, "counts": [18093, 37963]}]}
    pct = compute_canopy_percentage(response)
    assert pct == pytest.approx(100.0 * 37963 / (18093 + 37963))


def test_compute_canopy_percentage_excludes_no_data_from_denominator() -> None:
    # Synthetic -- a buffer straddling the raster's real coverage edge:
    # class 0 (Background), class 1 (Tree), and class 10 (No Data) all
    # present. Matches the service's real contiguous-bin-per-integer
    # behavior for a min=-0.5/max=10.5 span: size=11, one bin per integer
    # value 0-10, width exactly 1.0. No-Data (index 10, value 10) must not
    # dilute the percentage.
    counts = [0] * 11
    counts[0] = 30  # value 0 (Background)
    counts[1] = 20  # value 1 (Tree)
    counts[10] = 50  # value 10 (No Data)
    response = {"histograms": [{"size": 11, "min": -0.5, "max": 10.5, "counts": counts}]}

    pct = compute_canopy_percentage(response)
    # Denominator excludes the 50 No-Data pixels: 20 / (30 + 20) = 40%.
    assert pct == pytest.approx(100.0 * 20 / 50)


def test_compute_canopy_percentage_all_no_data_returns_none() -> None:
    # A buffer entirely outside the raster's real coverage -- only class
    # 10 (No Data) present.
    response = {"histograms": [{"size": 1, "min": 9.5, "max": 10.5, "counts": [500]}]}
    assert compute_canopy_percentage(response) is None


def test_compute_canopy_percentage_no_canopy_present() -> None:
    # Only Background (0) present -- 0% canopy, a real valid result, not
    # a failure.
    response = {"histograms": [{"size": 1, "min": -0.5, "max": 0.5, "counts": [1000]}]}
    assert compute_canopy_percentage(response) == 0.0


def test_compute_canopy_percentage_scrub_shrub_does_not_count_as_canopy() -> None:
    # Regression test for the real design decision: class 2 (Scrub/Shrub)
    # must NOT be counted as tree canopy.
    response = {"histograms": [{"size": 2, "min": 0.5, "max": 2.5, "counts": [400, 600]}]}
    # bin 0 -> value 1 (Tree), bin 1 -> value 2 (Scrub/Shrub)
    pct = compute_canopy_percentage(response)
    assert pct == pytest.approx(100.0 * 400 / 1000)


def test_compute_canopy_percentage_returns_none_on_empty_response() -> None:
    assert compute_canopy_percentage({"histograms": []}) is None
    assert compute_canopy_percentage({}) is None


def test_compute_canopy_percentage_returns_none_on_malformed_response() -> None:
    assert compute_canopy_percentage({"histograms": [{"size": 0, "min": None, "max": None, "counts": []}]}) is None
