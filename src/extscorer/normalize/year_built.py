"""Placeholder build years (added 2026-11-08).

1,693 parcels are recorded as built exactly 1900, about 85 times what the neighbouring years predict, in every town; 447
sales are dated exactly 1900 too. Assessor systems use 1900 for "old, year unknown". The circa years (1700, 1750, 1800,
1850) also cluster but are plausible estimates for genuinely old houses, so only 1900 is treated as a placeholder.

`resolve_year_built` gives the year the scorer should use and where it came from:
- `actual`: the recorded year (the default for every parcel, and always when the switch is off);
- `effective_fallback`: the recorded year is 1900 and `effective_year_built` is present, not itself 1900, and old enough
  (at least `min_age_years`), so use that;
- `unknown`: the recorded year is 1900 and there is no usable effective year; the scorer uses a neutral age.

The guard (2026-11-08): a fallback can lower a score but never disqualify. When the effective year would make the house
younger than `min_age_years` (a renovated old house), the result is `unknown` (neutral age) instead, and
`renovation_suggested` is True so the caller can say why ("effective year suggests renovation").
"""
from __future__ import annotations

from datetime import date
from typing import Any

PLACEHOLDER_YEAR = 1900
DEFAULT_MIN_AGE_YEARS = 20
ACTUAL = "actual"
EFFECTIVE_FALLBACK = "effective_fallback"
UNKNOWN = "unknown"
YEAR_BUILT_SOURCES = (ACTUAL, EFFECTIVE_FALLBACK, UNKNOWN)


def resolve_year_built(
    parcel: dict[str, Any],
    placeholder_fallback: bool = False,
    as_of_year: int | None = None,
    min_age_years: int = DEFAULT_MIN_AGE_YEARS,
) -> tuple[int | None, str]:
    """`(year to use, source)`. With the switch off this is always `(recorded year, 'actual')`."""
    year = parcel.get("year_built")
    if not placeholder_fallback or year != PLACEHOLDER_YEAR:
        return year, ACTUAL
    effective = parcel.get("effective_year_built")
    if effective and effective != PLACEHOLDER_YEAR:
        if (as_of_year or date.today().year) - int(effective) >= min_age_years:
            return int(effective), EFFECTIVE_FALLBACK
    return None, UNKNOWN


def renovation_suggested(parcel: dict[str, Any], as_of_year: int | None = None, min_age_years: int = DEFAULT_MIN_AGE_YEARS) -> bool:
    """True for a 1900 parcel whose effective year is present but too recent to use (the guard fired): the house was likely renovated."""
    year, effective = parcel.get("year_built"), parcel.get("effective_year_built")
    if year != PLACEHOLDER_YEAR or not effective or effective == PLACEHOLDER_YEAR:
        return False
    return (as_of_year or date.today().year) - int(effective) < min_age_years
