"""Generic, client-agnostic logic for computing % tree canopy near a
geocoded point from NOAA's C-CAP High Resolution Canopy Cover ImageServer.

Nothing here does network I/O -- same public/full split as `scoring.basic`
and `enrichment.storm_backfill`. The live HTTP call itself lives in
`property-lead-scorer-full/scripts/backfill_parcel_canopy.py`.

## Design decisions (resolved against the real live service, not assumed)

**Live REST query, not raster download.** Confirmed live 2026-09-09 against
`coast.noaa.gov/arcgisimg/rest/services/Landcover/CCAP_High_Resolution_Canopy/
ImageServer`: its `computeHistograms` operation accepts a plain WGS84
(lat/lon) polygon directly and returns per-class pixel counts for the
queried area -- no reprojection, no GDAL/rasterio dependency, no 21MB
GeoTIFF to download and manage. Tested against a real wooded Pomfret, CT
point (~65-68% canopy across three different query-shape variants) and a
real more-open village-center point (37.4%) -- confirms real spatial
discrimination, not a constant.

**Pixel semantics are categorical**, confirmed live: `Pixel Type: U8`,
`Service Data Type: esriImageServiceDataTypeThematic`, values `0=
Background, 1=Upland Tree (Forest), 2=Scrub/Shrub, ..., 10=No Data` (per
NOAA InPort item 70562's supplemental attribute table).

**Only class 1 (Upland Tree / Forest) counts as "canopy"** -- NOT class 2
(Scrub/Shrub). Darren's own framing is about overhanging trees near a roof
(falling limbs, trapped moisture/shade), which low scrub/shrub vegetation
doesn't produce. This is a real judgment call, not the only defensible
reading -- flagged here explicitly (same "proposed default, not final"
status as `scoring.basic`'s own weights) in case a future pass should
widen it.

**No-Data pixels (class 10) are excluded from the denominator**, not
counted as non-canopy -- a buffer that partially falls outside the
raster's real coverage should not have its canopy percentage diluted by
pixels that were never actually classified. If EVERY pixel in a buffer is
No-Data, there's no usable measurement at all (`compute_canopy_percentage`
returns `None`), which the caller must flag `needs_review` for -- not
silently report 0% canopy.

**Response binning gotcha**: `computeHistograms` returns a histogram whose
`min`/`max`/`size` describe whatever integer value range is ACTUALLY
present in the queried area (confirmed live: querying an area containing
only classes 0 and 1 returns `{"size":2,"min":-0.5,"max":1.5,...}`, not a
fixed 0-10 range) -- bin-to-class-value mapping must be reconstructed from
`min`/`max`/`size` each time, never assumed to be a fixed 11-bin layout.
"""
from __future__ import annotations

import math
from typing import Any

_TREE_CANOPY_CLASS = 1
_NO_DATA_CLASS = 10


def build_circle_ring(lat: float, lon: float, radius_m: float, n_points: int = 24) -> list[list[float]]:
    """Build a closed polygon ring (WGS84 lon/lat pairs, esri rings order)
    approximating a circle of `radius_m` meters centered on `(lat, lon)`.

    Pure trig, no shapely dependency needed -- confirmed live that the
    ImageServer accepts this directly with `spatialReference: {wkid: 4326}`.
    Uses a local flat-earth approximation (fine at this scale -- tens to
    low hundreds of meters -- not intended for large-area buffers).
    """
    if radius_m <= 0:
        raise ValueError(f"radius_m must be positive, got {radius_m!r}")
    deg_lat_per_m = 1 / 111_320
    deg_lon_per_m = 1 / (111_320 * math.cos(math.radians(lat)))
    ring = []
    for i in range(n_points + 1):  # +1 to close the ring
        angle = 2 * math.pi * i / n_points
        dx = radius_m * math.cos(angle) * deg_lon_per_m
        dy = radius_m * math.sin(angle) * deg_lat_per_m
        ring.append([lon + dx, lat + dy])
    return ring


def compute_canopy_percentage(histogram_response: dict[str, Any]) -> float | None:
    """Given one `computeHistograms` JSON response, return the percentage
    (0-100) of non-No-Data pixels classified as tree canopy, or `None` if
    the buffer has no usable pixels at all (e.g. entirely outside the
    raster's real coverage, or the response is empty/malformed).

    See module docstring for why class 2 (Scrub/Shrub) doesn't count as
    canopy, and why No-Data pixels are excluded from the denominator
    rather than counted as non-canopy.
    """
    histograms = histogram_response.get("histograms") or []
    if not histograms:
        return None
    histogram = histograms[0]
    counts = histogram.get("counts") or []
    size = histogram.get("size")
    min_value = histogram.get("min")
    max_value = histogram.get("max")
    if not counts or not size or min_value is None or max_value is None:
        return None

    bin_width = (max_value - min_value) / size
    canopy_pixels = 0
    usable_pixels = 0  # total pixels EXCLUDING No-Data
    for i, count in enumerate(counts):
        # Bin i covers [min + i*width, min + (i+1)*width) -- reconstruct
        # the integer class value at its center (see module docstring's
        # "Response binning gotcha").
        value = round(min_value + bin_width * (i + 0.5))
        if value == _NO_DATA_CLASS:
            continue
        usable_pixels += count
        if value == _TREE_CANOPY_CLASS:
            canopy_pixels += count

    if usable_pixels == 0:
        return None
    return 100.0 * canopy_pixels / usable_pixels
