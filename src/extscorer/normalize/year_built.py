"""Placeholder build years (added 2026-11-08).

1,693 parcels are recorded as built exactly 1900, about 85 times what the neighbouring years predict, in every town; 447
sales are dated exactly 1900 too. Assessor systems use 1900 for "old, year unknown". The circa years (1700, 1750, 1800,
1850) also cluster but are plausible estimates for genuinely old houses, so only 1900 is treated as a placeholder.

`resolve_year_built` gives the year the scorer should use and where it came from:
- `actual`: the recorded year (the default for every parcel, and always when the switch is off);
- `effective_fallback`: the recorded year is 1900 and `effective_year_built` is present and not itself 1900, so use that;
- `unknown`: the recorded year is 1900 and there is no usable effective year; the scorer uses a neutral age.
"""
from __future__ import annotations

from typing import Any

PLACEHOLDER_YEAR = 1900
ACTUAL = "actual"
EFFECTIVE_FALLBACK = "effective_fallback"
UNKNOWN = "unknown"
YEAR_BUILT_SOURCES = (ACTUAL, EFFECTIVE_FALLBACK, UNKNOWN)


def resolve_year_built(parcel: dict[str, Any], placeholder_fallback: bool = False) -> tuple[int | None, str]:
    """`(year to use, source)`. With the switch off this is always `(recorded year, 'actual')`."""
    year = parcel.get("year_built")
    if not placeholder_fallback or year != PLACEHOLDER_YEAR:
        return year, ACTUAL
    effective = parcel.get("effective_year_built")
    if effective and effective != PLACEHOLDER_YEAR:
        return int(effective), EFFECTIVE_FALLBACK
    return None, UNKNOWN
