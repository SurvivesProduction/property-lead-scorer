"""Generic, client-agnostic exterior-renovation lead scoring.

Nothing in this module encodes any client-specific business logic -- no
hardcoded target towns, no hardcoded "final" weights. A downstream
deployment (e.g. the full/paid overlay) supplies its own values as
parameters, the same way `leadscorer.scoring.basic`'s functions take
`threshold_year`/`retrofit_keywords` rather than hardcoding them.

Every function here is a pure function over plain dicts (no database
connection, no I/O) specifically so it's unit-testable against synthetic
data -- same split as `leadscorer.scoring.basic` / `oppscanner`'s pure
insight functions.

**All default weights and thresholds below are proposed, not final** --
same status as Tool 1's `REBID_WINDOW_DAYS=90` default when it was first
written: a real number in real code, meant to be tuned once real data and
the client's (Darren's) own judgment are available, not treated as
settled. See this repo's README for the reasoning behind each default.

## Real-data recalibration (2026-09-09, once all 3 signals were live on
all 1,200 persisted parcels -- see property-lead-scorer-full's own
backfill scripts)

**Canopy** (`DEFAULT_CANOPY_OPTIMAL_PCT`/`DEFAULT_CANOPY_HIGH_EXTREME_PCT`):
the original guessed 25%/55% bathtub-curve points would pin the MAJORITY
of the real population at maximum canopy risk -- confirmed directly: the
872 real scoreable parcels' canopy percentile distribution is p5=21.9,
p25=50, p50=67.4, p75=85.3, p90=94.3, p95=96.8 (a genuinely forested rural
region), so a 55% high-extreme cutoff caps over half the population at
1.0 with zero further differentiation. Recalibrated to `optimal=35.0`
(kept as a real, literature-typical "balanced shade" value -- deliberately
NOT chased up to match the local median, since Darren's physical claim
that heavy cover shortens roof life doesn't become less true just because
it's locally common) and `high_extreme=95.0` (grounded in the real
p90/p95, so only the genuinely most-heavily-wooded local tail approaches
max risk, restoring real spread across the bulk of the population).
`low_extreme=0.0` is unchanged -- a natural boundary that doesn't need
real-data calibration.

**Weights**: `property=0.65` (up slightly from 0.6 -- still the confirmed
leading signal), `canopy=0.28` (up from 0.25 -- now has real, confirmed
differentiating power once recalibrated above), `storm=0.07` (down
substantially from 0.15). The storm reduction is grounded in a real,
concrete finding, not a guess: querying the real persisted data found
literally ALL 872 real scoreable parcels share the IDENTICAL single
`nearest_storm_event_date` (every qualifying property's `year_built` is
old enough that the county's one most-recent event trivially qualifies
for everyone) -- `storm_component` is currently a pure constant across
the whole real population, contributing zero differentiating power to
ranking. Kept non-zero rather than eliminated, since the "recent storm
nearby" reasoning text is still real and informative, and a future
magnitude-weighted refinement (the real event's `magnitude` is already
carried in `storm_events.raw_data`, unused by this scoring pass) or a
future storm hitting only some of the towns could restore real
differentiation later.

**Property age** (2026-09-09, follow-up prompt): flagged above as
unfixed, now recalibrated the same way. The real scoreable population's
age percentiles are heavily right-skewed (a genuine historic-New-England
tail): p95=25yr, p90=28yr, p75=38yr, p50=54yr, p25=76yr, p10=136yr,
p5=226yr (one real Canterbury property dates to 1690). The old linear
ramp-to-`max_years_past_threshold=35` cap meant 708 of 872 real scoreable
parcels (81.2%) were already pinned at the max score of 1.0 -- a
placement problem, not a granularity one (the function was already
continuous, just capped at an age the real median had long since passed).

Rather than simply raising the linear cap, `property_age_score` now uses
an **exponential-saturation ("diminishing returns") curve**:
`score = 1 - exp(-(age - threshold_years) / decay_scale_years)`. A pure
higher linear cap was considered and rejected: `year_built` is the
ORIGINAL building's construction year, not the roof's own installation
date (VGSI has no renovation-year field) -- a 300-year-old house and a
150-year-old house give no more real information about CURRENT roof
condition than a 100-year-old one (the physical signal genuinely
saturates over centuries, since a roof that old has almost certainly been
replaced independently of the building's own age), so treating "206 years
past threshold" as meaningfully worse than "116 years past threshold"
would overstate what year_built alone can actually tell us. The
exponential curve rises quickly where the age signal is most informative
(just past the qualifying threshold) and flattens gracefully for the
historic tail, instead of an arbitrary hard cutoff.

`DEFAULT_PROPERTY_AGE_DECAY_YEARS = 30` was chosen and verified directly
against the real percentiles above -- it spreads scores meaningfully
across the ENTIRE real bulk of the distribution (0.154 at p95's age of 25,
0.451 at p75's 38, 0.678 at the median's 54, 0.845 at p25's 76) while only
the genuine historic-outlier tail (p10=136yr and beyond) saturates near
1.0, rather than the old cap's 81.2%-of-the-population pileup. See Prompt
M's own before/after tie-cluster comparison for the real ranking impact.
`DEFAULT_PROPERTY_AGE_THRESHOLD_YEARS=20` (the hard qualifying gate, a
different concept from the decay shape) is unchanged.

## Siding-age proxy signal (new, opt-in, NOT yet real-data-calibrated)

`siding_age_score()` below is a fourth, optional signal built at Darren's
request once `exterior_wall_1`/`building_percent_good` were added to the
schema. Unlike the three signals above, its defaults are **pure domain-
judgment placeholders**, not grounded in a real fill-rate/distribution
pass the way property/canopy/storm were (`exterior_wall_1` was just
backfilled -- there hasn't been a chance yet to run the same kind of
percentile/tie-cluster check against it). Treat it with LESS confidence
than the other three until a follow-up recalibration pass does that.

A field audit (2026-09) confirmed VGSI's property cards expose no "Year
Remodeled" or "Condition" field for single-family homes (only present,
and blank, on the rare condo-template card) -- the original spec for this
signal asked for those as modifiers, but they simply aren't obtainable
from this data source. The signal below uses only `exterior_wall_1` +
`year_built`, with `building_percent_good` folded in as a soft modifier
since it's real, available data in a similar spirit (worse condition ->
higher score, same direction as the other signals).

Disabled by default (`DEFAULT_ENABLE_SIDING_AGE_SIGNAL = False`) --
Darren hasn't reviewed this signal or its bucket boundaries yet. When
disabled, `score_property`/`rank_candidates` behave EXACTLY as before
this signal existed (see the weighting note in `score_property`'s
docstring).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any

# Proposed defaults -- see module docstring's "Real-data recalibration"
# section. A downstream deployment's client config is expected to
# override these per-client, not edit them here.
DEFAULT_PROPERTY_WEIGHT = 0.65
DEFAULT_CANOPY_WEIGHT = 0.28
DEFAULT_STORM_WEIGHT = 0.07

DEFAULT_PROPERTY_AGE_THRESHOLD_YEARS = 20
DEFAULT_PROPERTY_AGE_DECAY_YEARS = 30

DEFAULT_CANOPY_OPTIMAL_PCT = 35.0
DEFAULT_CANOPY_LOW_EXTREME_PCT = 0.0
DEFAULT_CANOPY_HIGH_EXTREME_PCT = 95.0

DEFAULT_STORM_LOOKBACK_YEARS = 15

# Siding-age signal -- see module docstring's "Siding-age proxy signal"
# section. All of these are judgment-call placeholders pending Darren's
# review and a future real-data recalibration pass, NOT yet grounded the
# way the three signals above are.
DEFAULT_ENABLE_SIDING_AGE_SIGNAL = False
DEFAULT_SIDING_AGE_WEIGHT = 0.15

# Vinyl siding didn't become a common RESIDENTIAL exterior material until
# the mid-1970s. A house built before this year that has vinyl NOW must
# have been re-sided at some unknown later point -- we can't tell how
# recently, so treat it conservatively as "already addressed" rather than
# assume it's overdue. By ~1985 vinyl was mainstream enough that a house
# built then plausibly still has its ORIGINAL vinyl, so year_built starts
# being usable as a proxy for siding age again from that point on -- hence
# the score rises across 1975-1985 even though the underlying interpretation
# flips (from "residing happened at an unknown time" to "this may well be
# original"). See DEFAULT_SIDING_VINYL_NOT_PRIME_SCORE's docstring note.
DEFAULT_SIDING_VINYL_UNKNOWN_RESIDE_CUTOFF_YEAR = 1975
# 1985-2000: vinyl (typical 20-40yr lifespan) installed in this window is
# now old enough that, IF it's original, it's approaching or past typical
# replacement age -- the "moderate" bucket. Scored as a gentle downward
# slope (older/1985 end higher than newer/2000 end), not a flat plateau,
# since within this window the older vinyl is more likely to actually be
# due.
DEFAULT_SIDING_VINYL_REPLACEMENT_AGE_START_YEAR = 1985
DEFAULT_SIDING_VINYL_REPLACEMENT_AGE_END_YEAR = 2000
# Vinyl from a house built in/after this year is still comfortably within
# its typical lifespan -- low priority regardless of exact age.
DEFAULT_SIDING_VINYL_TOO_NEW_YEAR = 2005
DEFAULT_SIDING_VINYL_NOT_PRIME_SCORE = 0.15
DEFAULT_SIDING_VINYL_MODERATE_HIGH_SCORE = 0.60
DEFAULT_SIDING_VINYL_MODERATE_LOW_SCORE = 0.45
DEFAULT_SIDING_VINYL_NEAR_ZERO_SCORE = 0.03

# Wood/aluminum/asbestos are treated as durable ORIGINAL materials --
# unlike vinyl, there's no widely-available cheap alternative these would
# typically have been replaced BY before this project's target era, so a
# house built well before this year that still has one of these materials
# has very likely never been re-sided at all -- the prime case. The curve
# is centered (continuous, not a hard step) on this year rather than a
# strict "pre-1990 only" cutoff, so a house built in, say, 1988 doesn't
# fall off a cliff relative to one built in 1985.
DEFAULT_SIDING_DURABLE_NEVER_RESIDED_YEAR = 1990
DEFAULT_SIDING_DURABLE_DECAY_YEARS = 25.0
DEFAULT_SIDING_DURABLE_BASELINE_SCORE = 0.85

# How much building_percent_good (VGSI's real "Dep %" equivalent -- see
# vgsi.py) can nudge the base material/age score, worse-condition-scores-
# higher, same direction as this project's other signals. Deliberately a
# SOFT modifier (not a primary driver): at pct_good=50 the modifier is
# exactly 0 (neutral midpoint), scaling linearly to +/-half this value at
# the 0/100 extremes.
DEFAULT_SIDING_PERCENT_GOOD_MODIFIER_STRENGTH = 0.15


def _current_year(as_of_year: int | None) -> int:
    return as_of_year if as_of_year is not None else date.today().year


def property_age_score(
    parcel: dict[str, Any],
    threshold_years: int = DEFAULT_PROPERTY_AGE_THRESHOLD_YEARS,
    decay_scale_years: float = DEFAULT_PROPERTY_AGE_DECAY_YEARS,
    as_of_year: int | None = None,
) -> float:
    """Score 0-1: how far past `threshold_years` old this property is,
    using an exponential-saturation ("diminishing returns") curve --
    `1 - exp(-(age - threshold_years) / decay_scale_years)` -- rather than
    a hard linear cap. See module docstring's "Real-data recalibration"
    section for the real-percentile-grounded reasoning: `year_built` is
    the ORIGINAL building's construction year (this schema doesn't track
    a separate renovation year), so its signal value for CURRENT roof
    condition genuinely diminishes for very old buildings rather than
    growing linearly forever -- a 300-year-old and a 150-year-old building
    tell us little more than a 100-year-old one does.

    Uses `year_built`. Returns 0.0 if `year_built` isn't known, or if the
    property isn't yet older than `threshold_years`. Approaches but never
    exactly reaches 1.0 -- `decay_scale_years` controls how quickly it
    rises (a real, tunable parameter, not a hard cutoff).
    """
    year_built = parcel.get("year_built")
    if year_built is None:
        return 0.0
    age = _current_year(as_of_year) - year_built
    years_past_threshold = age - threshold_years
    if years_past_threshold <= 0:
        return 0.0
    if decay_scale_years <= 0:
        return 1.0
    return 1.0 - math.exp(-years_past_threshold / decay_scale_years)


def canopy_score(
    parcel: dict[str, Any],
    optimal_pct: float = DEFAULT_CANOPY_OPTIMAL_PCT,
    low_extreme_pct: float = DEFAULT_CANOPY_LOW_EXTREME_PCT,
    high_extreme_pct: float = DEFAULT_CANOPY_HIGH_EXTREME_PCT,
) -> float:
    """Score 0-1: risk from tree-canopy coverage near the property.

    Deliberately NOT linear or monotonic: per Darren, heavy tree cover
    AND a fully open/exposed site both shorten roof lifespan, just for
    different reasons (debris/moisture buildup vs. UV/wind exposure). So
    this is a "bathtub" curve -- lowest risk (0.0) at `optimal_pct`
    canopy nearby, rising to 1.0 at either `low_extreme_pct` (fully
    exposed) or `high_extreme_pct` (heavy cover), each side scaled
    independently since the two spans aren't necessarily symmetric.

    Returns a neutral 0.5 (not 0.0) when `pct_tree_canopy_nearby` isn't
    known yet -- same "unknown is neutral, not confirmed-safe" reasoning
    as `leadscorer.scoring.basic.size_score`'s treatment of missing
    square footage.

    A real parcel dict sourced from the live database (via psycopg's
    `dict_row`) carries `pct_tree_canopy_nearby` as a `decimal.Decimal`
    (the column is `numeric`), not a plain `float` -- confirmed live
    2026-09-09 running this against real data for the first time (a
    `Decimal - float` arithmetic error the original synthetic-dict-only
    tests never exercised). Cast to `float` explicitly so this function
    stays agnostic to which numeric type its caller's data source uses.
    """
    pct = parcel.get("pct_tree_canopy_nearby")
    if pct is None:
        return 0.5
    pct = float(pct)

    if pct <= optimal_pct:
        span = optimal_pct - low_extreme_pct
        if span <= 0:
            return 0.0
        return min((optimal_pct - pct) / span, 1.0)

    span = high_extreme_pct - optimal_pct
    if span <= 0:
        return 1.0
    return min((pct - optimal_pct) / span, 1.0)


def storm_score(
    parcel: dict[str, Any],
    lookback_years: int = DEFAULT_STORM_LOOKBACK_YEARS,
    as_of_year: int | None = None,
) -> float:
    """Score 0-1: how recent the property's nearest qualifying storm event was.

    Reads the parcel's own denormalized `nearest_storm_event_date` (see
    `migrations/001_init_schema.sql`'s `parcels` table docstring for why
    it's cached there rather than requiring a `storm_events` join to
    score). Returns 0.0 if no event is on file, or if the event predates
    `year_built` (a storm can't have damaged a roof that didn't exist yet
    -- when `year_built` is unknown this check is skipped, since there's
    no basis to exclude the event). Decays linearly from 1.0 (this year)
    to 0.0 at `lookback_years` years ago -- a simple recency placeholder,
    not a magnitude-weighted model; the real event's `magnitude` is
    carried in `storm_events.raw_data` for a future refinement once real
    storm data is on file to tune against.
    """
    event_date = parcel.get("nearest_storm_event_date")
    if event_date is None:
        return 0.0

    year_built = parcel.get("year_built")
    if year_built is not None and event_date.year < year_built:
        return 0.0

    years_since_event = _current_year(as_of_year) - event_date.year
    if years_since_event < 0 or years_since_event >= lookback_years:
        return 0.0
    return 1.0 - (years_since_event / lookback_years)


def _classify_wall_material(exterior_wall_1: str | None) -> str | None:
    """Bucket a raw VGSI `Exterior Wall 1` string into a material family.

    VGSI's own values are free text ("Vinyl Siding", "Wood Shingle",
    "Aluminum Siding", "Asbestos Shingle", ...), not a fixed enum -- match
    by case-insensitive substring, same defensive style already used for
    VGSI field-label matching elsewhere in this codebase (see `vgsi.py`'s
    `_find_building_attribute` colon-suffix handling), rather than an
    exact-match lookup that would silently miss real variants.
    """
    if not exterior_wall_1:
        return None
    text = exterior_wall_1.lower()
    if "vinyl" in text:
        return "vinyl"
    if any(keyword in text for keyword in ("wood", "aluminum", "asbestos")):
        return "durable_original"
    return "other"


def _vinyl_siding_age_score(
    year_built: int,
    unknown_reside_cutoff_year: int,
    replacement_age_start_year: int,
    replacement_age_end_year: int,
    too_new_year: int,
    not_prime_score: float,
    moderate_high_score: float,
    moderate_low_score: float,
    near_zero_score: float,
) -> float:
    """Piecewise-linear over 4 named anchor years -- see the
    `DEFAULT_SIDING_VINYL_*` constants' own comments for the reasoning
    behind each segment. Deliberately linear (not an exponential curve
    like `property_age_score`'s) since there's no real-data distribution
    yet to justify a particular curve shape -- linear is the simplest
    defensible interpolation between the client's named anchor points.
    """
    if year_built <= unknown_reside_cutoff_year:
        return not_prime_score
    if year_built <= replacement_age_start_year:
        span = replacement_age_start_year - unknown_reside_cutoff_year
        t = (year_built - unknown_reside_cutoff_year) / span if span else 1.0
        return not_prime_score + t * (moderate_high_score - not_prime_score)
    if year_built <= replacement_age_end_year:
        span = replacement_age_end_year - replacement_age_start_year
        t = (year_built - replacement_age_start_year) / span if span else 0.0
        return moderate_high_score + t * (moderate_low_score - moderate_high_score)
    if year_built <= too_new_year:
        span = too_new_year - replacement_age_end_year
        t = (year_built - replacement_age_end_year) / span if span else 1.0
        return moderate_low_score + t * (near_zero_score - moderate_low_score)
    return near_zero_score


def _durable_material_age_score(
    year_built: int,
    never_resided_year: int,
    decay_years: float,
    baseline_score: float,
) -> float:
    """Continuous curve centered on `never_resided_year` (not a hard step):
    houses built well before it saturate toward 1.0 (very likely original,
    never re-sided); houses built at or after it decay from `baseline_score`
    toward 0.0 the more recently they were built. The two halves meet
    exactly at `baseline_score` when `year_built == never_resided_year`, so
    there's no discontinuity at the boundary.

    Unlike `property_age_score`, this takes no `as_of_year` -- the signal
    is about how the house's build year relates to `never_resided_year`
    (a fixed calendar year, not "years old today"), so today's date never
    enters the calculation.
    """
    years_before_cutoff = never_resided_year - year_built
    if decay_years <= 0:
        return baseline_score if years_before_cutoff <= 0 else 1.0
    if years_before_cutoff >= 0:
        return baseline_score + (1.0 - baseline_score) * (1 - math.exp(-years_before_cutoff / decay_years))
    years_after_cutoff = -years_before_cutoff
    return baseline_score * math.exp(-years_after_cutoff / decay_years)


def siding_age_score(
    parcel: dict[str, Any],
    unknown_reside_cutoff_year: int = DEFAULT_SIDING_VINYL_UNKNOWN_RESIDE_CUTOFF_YEAR,
    replacement_age_start_year: int = DEFAULT_SIDING_VINYL_REPLACEMENT_AGE_START_YEAR,
    replacement_age_end_year: int = DEFAULT_SIDING_VINYL_REPLACEMENT_AGE_END_YEAR,
    too_new_year: int = DEFAULT_SIDING_VINYL_TOO_NEW_YEAR,
    vinyl_not_prime_score: float = DEFAULT_SIDING_VINYL_NOT_PRIME_SCORE,
    vinyl_moderate_high_score: float = DEFAULT_SIDING_VINYL_MODERATE_HIGH_SCORE,
    vinyl_moderate_low_score: float = DEFAULT_SIDING_VINYL_MODERATE_LOW_SCORE,
    vinyl_near_zero_score: float = DEFAULT_SIDING_VINYL_NEAR_ZERO_SCORE,
    durable_never_resided_year: int = DEFAULT_SIDING_DURABLE_NEVER_RESIDED_YEAR,
    durable_decay_years: float = DEFAULT_SIDING_DURABLE_DECAY_YEARS,
    durable_baseline_score: float = DEFAULT_SIDING_DURABLE_BASELINE_SCORE,
    percent_good_modifier_strength: float = DEFAULT_SIDING_PERCENT_GOOD_MODIFIER_STRENGTH,
) -> float:
    """Score 0-1: how likely this property's exterior siding is original
    and overdue for replacement, from `exterior_wall_1` + `year_built`
    (`building_percent_good` as a soft modifier). See module docstring's
    "Siding-age proxy signal" section for the full reasoning, and NOTE:
    these defaults are unreviewed judgment calls, not yet real-data-
    calibrated like the other three signals in this module.

    Two different material families use `year_built` completely
    differently (see `_vinyl_siding_age_score`/`_durable_material_age_score`
    for why) -- `wood`/`aluminum`/`asbestos` (durable, presumed-original)
    score HIGHER the older the house is; `vinyl` scores highest in a
    *middle* band (1985-2000-built) since very old houses with vinyl NOW
    imply an unknown-timing re-side already happened, not that the vinyl
    itself is old.

    Returns a neutral 0.5 when `exterior_wall_1` is missing (not yet
    backfilled, or genuinely blank on the card) or doesn't match a known
    material family (brick, stone, composite, etc. -- no established
    heuristic for these yet) -- same "unknown is neutral, not confirmed-
    safe" convention as `canopy_score`'s missing-data handling.
    """
    exterior_wall_1 = parcel.get("exterior_wall_1")
    year_built = parcel.get("year_built")
    if not exterior_wall_1 or year_built is None:
        return 0.5

    material = _classify_wall_material(exterior_wall_1)
    if material == "vinyl":
        base = _vinyl_siding_age_score(
            year_built,
            unknown_reside_cutoff_year,
            replacement_age_start_year,
            replacement_age_end_year,
            too_new_year,
            vinyl_not_prime_score,
            vinyl_moderate_high_score,
            vinyl_moderate_low_score,
            vinyl_near_zero_score,
        )
    elif material == "durable_original":
        base = _durable_material_age_score(
            year_built, durable_never_resided_year, durable_decay_years, durable_baseline_score
        )
    else:
        return 0.5

    percent_good = parcel.get("building_percent_good")
    if percent_good is not None:
        # Cast defensively -- a real DB row (via psycopg's dict_row) can
        # carry a numeric column as decimal.Decimal, not plain float, the
        # same gotcha canopy_score already had to guard against.
        percent_good = float(percent_good)
        modifier = percent_good_modifier_strength * (0.5 - percent_good / 100.0)
        base += modifier

    return max(0.0, min(1.0, base))


@dataclass(frozen=True)
class LeadScore:
    """A scored, ranked exterior-renovation-lead candidate."""

    parcel_id: str
    town: str
    address: str
    score: float
    property_component: float
    canopy_component: float
    storm_component: float
    year_built: int | None
    living_area_sqft: int | None
    reasons: tuple[str, ...]
    # None when the siding-age signal is disabled (the default) -- distinct
    # from a computed 0.0/neutral-0.5, so a caller/digest can tell "this
    # signal wasn't evaluated" apart from "this signal was evaluated and
    # scored low." Defaulted so existing positional/keyword construction
    # elsewhere in this codebase (none currently exists outside this
    # module, but future callers shouldn't be forced to know about this)
    # keeps working unchanged.
    siding_age_component: float | None = None


def score_property(
    parcel: dict[str, Any],
    property_age_threshold_years: int = DEFAULT_PROPERTY_AGE_THRESHOLD_YEARS,
    property_age_decay_years: float = DEFAULT_PROPERTY_AGE_DECAY_YEARS,
    canopy_optimal_pct: float = DEFAULT_CANOPY_OPTIMAL_PCT,
    canopy_low_extreme_pct: float = DEFAULT_CANOPY_LOW_EXTREME_PCT,
    canopy_high_extreme_pct: float = DEFAULT_CANOPY_HIGH_EXTREME_PCT,
    storm_lookback_years: int = DEFAULT_STORM_LOOKBACK_YEARS,
    property_weight: float = DEFAULT_PROPERTY_WEIGHT,
    canopy_weight: float = DEFAULT_CANOPY_WEIGHT,
    storm_weight: float = DEFAULT_STORM_WEIGHT,
    enable_siding_age_signal: bool = DEFAULT_ENABLE_SIDING_AGE_SIGNAL,
    siding_age_weight: float = DEFAULT_SIDING_AGE_WEIGHT,
    as_of_year: int | None = None,
) -> LeadScore | None:
    """Score one parcel as an exterior-renovation-lead candidate, or None if it doesn't qualify.

    One hard qualifying condition: `year_built` must be known and the
    property must already be at least `property_age_threshold_years`
    old. Property age is this tool's leading signal (per the client
    brief) -- a property that hasn't cleared that bar at all isn't a
    plausible candidate yet, so it's excluded (returns None) rather than
    merely scored low. Canopy and storm history are supporting signals
    only: neither can make an otherwise-too-new property qualify.

    Among properties that qualify, `score` is the weighted AVERAGE of the
    active component scores (sum of weight*component, divided by the sum
    of active weights) -- not a plain weighted sum. `property_weight` +
    `canopy_weight` + `storm_weight` already sum to 1.0 by construction,
    so dividing by the weight sum is a no-op for them; it only matters
    once `enable_siding_age_signal` adds a fourth weight into the mix,
    keeping the combined score correctly bounded to [0, 1] without having
    to shrink the other three (still-unreviewed) weights to compensate.
    When `enable_siding_age_signal` is False (the default), this produces
    IDENTICAL output to the pre-siding-signal version of this function --
    see each component function's own docstring for its reasoning.
    """
    year_built = parcel.get("year_built")
    if year_built is None:
        return None
    age = _current_year(as_of_year) - year_built
    if age < property_age_threshold_years:
        return None

    property_component = property_age_score(
        parcel, property_age_threshold_years, property_age_decay_years, as_of_year
    )
    canopy_component = canopy_score(
        parcel, canopy_optimal_pct, canopy_low_extreme_pct, canopy_high_extreme_pct
    )
    storm_component = storm_score(parcel, storm_lookback_years, as_of_year)

    weighted_sum = (
        property_weight * property_component
        + canopy_weight * canopy_component
        + storm_weight * storm_component
    )
    total_weight = property_weight + canopy_weight + storm_weight

    siding_age_component: float | None = None
    if enable_siding_age_signal:
        siding_age_component = siding_age_score(parcel)
        weighted_sum += siding_age_weight * siding_age_component
        total_weight += siding_age_weight

    score = weighted_sum / total_weight if total_weight > 0 else 0.0

    living_area_sqft = parcel.get("living_area_sqft")
    reasons = [
        f"Built in {year_built}, {age} years old ({_current_year(as_of_year)} - {year_built}), "
        f"{age - property_age_threshold_years} years past the {property_age_threshold_years}-year threshold.",
        (
            f"{parcel['pct_tree_canopy_nearby']:.0f}% tree canopy nearby."
            if parcel.get("pct_tree_canopy_nearby") is not None
            else "No tree-canopy data on file yet."
        ),
        (
            f"Nearest storm event on {parcel['nearest_storm_event_date']}."
            if parcel.get("nearest_storm_event_date") is not None
            else "No storm-event history on file yet."
        ),
    ]
    if enable_siding_age_signal:
        exterior_wall_1 = parcel.get("exterior_wall_1")
        reasons.append(
            f"Exterior wall: {exterior_wall_1}." if exterior_wall_1 else "No exterior-wall-material data on file yet."
        )

    return LeadScore(
        parcel_id=parcel.get("parcel_id", ""),
        town=parcel.get("town", ""),
        address=parcel.get("address", ""),
        score=score,
        property_component=property_component,
        canopy_component=canopy_component,
        storm_component=storm_component,
        year_built=year_built,
        living_area_sqft=living_area_sqft,
        reasons=tuple(reasons),
        siding_age_component=siding_age_component,
    )


def rank_candidates(
    parcels: list[dict[str, Any]],
    property_age_threshold_years: int = DEFAULT_PROPERTY_AGE_THRESHOLD_YEARS,
    property_age_decay_years: float = DEFAULT_PROPERTY_AGE_DECAY_YEARS,
    canopy_optimal_pct: float = DEFAULT_CANOPY_OPTIMAL_PCT,
    canopy_low_extreme_pct: float = DEFAULT_CANOPY_LOW_EXTREME_PCT,
    canopy_high_extreme_pct: float = DEFAULT_CANOPY_HIGH_EXTREME_PCT,
    storm_lookback_years: int = DEFAULT_STORM_LOOKBACK_YEARS,
    property_weight: float = DEFAULT_PROPERTY_WEIGHT,
    canopy_weight: float = DEFAULT_CANOPY_WEIGHT,
    storm_weight: float = DEFAULT_STORM_WEIGHT,
    enable_siding_age_signal: bool = DEFAULT_ENABLE_SIDING_AGE_SIGNAL,
    siding_age_weight: float = DEFAULT_SIDING_AGE_WEIGHT,
    as_of_year: int | None = None,
) -> list[LeadScore]:
    """Score and rank every qualifying parcel, highest score first.

    Ties break on three factors, in order: `living_area_sqft` (largest
    first, unknown treated as smallest -- a bigger home is a bigger
    potential siding/roofing job, same reasoning as
    `leadscorer.scoring.basic.rank_candidates`'s square-footage
    tiebreak), then `year_built` (oldest first -- a more clearly overdue
    property among otherwise-equal candidates), then `parcel_id`
    (lexicographic, the final fully-deterministic tiebreak). Both
    `property_age_score` and `canopy_score` cap at 1.0, so ties at the
    exact maximum combined score are expected to be common once real
    data is on file -- see Tool 2's real 214-way tie at score 1.0 for why
    leaving ties in input order is a real bug, not a theoretical one.
    """
    scored = []
    for parcel in parcels:
        lead = score_property(
            parcel,
            property_age_threshold_years=property_age_threshold_years,
            property_age_decay_years=property_age_decay_years,
            canopy_optimal_pct=canopy_optimal_pct,
            canopy_low_extreme_pct=canopy_low_extreme_pct,
            canopy_high_extreme_pct=canopy_high_extreme_pct,
            storm_lookback_years=storm_lookback_years,
            property_weight=property_weight,
            canopy_weight=canopy_weight,
            storm_weight=storm_weight,
            enable_siding_age_signal=enable_siding_age_signal,
            siding_age_weight=siding_age_weight,
            as_of_year=as_of_year,
        )
        if lead is not None:
            scored.append(lead)

    return sorted(
        scored,
        key=lambda lead: (
            lead.score,
            lead.living_area_sqft or 0,
            -(lead.year_built or 0),
            lead.parcel_id,
        ),
        reverse=True,
    )
