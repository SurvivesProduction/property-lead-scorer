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

## Siding signal: real ground truth where available, a proxy everywhere else

This module has ONE siding signal, `siding_score()`, dispatching between
two implementations depending on what data a parcel's source can actually
provide -- not two separately-weighted signals. `siding_score()` reads
`permit_data_available` (a source-level fact) and picks:

- **`real_siding_age_score()`** for any parcel with `permit_data_available`
  true, regardless of WHICH downstream deployment set that flag (this
  function only ever reads the flag + `exterior_wall_1`/permit fields on
  the parcel -- it has no way to tell, and doesn't need to, which of two
  real sources produced them):
  - Killingly, Ashford, and Woodstock's enrichment pass (`propertyrecordcards.com`,
    see `extscorer_full.sources.propertyrecordcards` in `property-lead-
    scorer-full`) exposes a DIRECT `Siding:` field (real current material,
    not inferred) AND real per-parcel permit history together, from one
    platform.
  - Brooklyn, Pomfret, and Thompson (PermitLink, see the separate
    `permit-history-enrichment-full` repo/"Tool 5") get real permit
    history ONLY -- that platform has no parcel/building data at all, so
    `exterior_wall_1` for these towns is still VGSI's own proxy-classified
    material, just paired with a real permit-derived redo year instead of
    a guessed one. `siding_data_source` records which case applies per
    row (`"eqs_direct_siding_field"` when real, absent when it's still
    the VGSI proxy classification) -- don't assume every
    `permit_data_available` parcel has a real material field just because
    it has real permit dates.

  Either way, the "effective redo year" is the most recent exterior-
  relevant permit's year if one exists (real evidence the siding was
  actually worked on, and when), falling back to `year_built` only when
  no such permit is on file (the same "presumed never redone" assumption
  the proxy has to make everywhere, but here it's a fallback for missing
  evidence, not the primary inference).
- **`siding_age_score()`** (the original proxy, unchanged in its own
  logic) for every other parcel -- `exterior_wall_1` + `year_built` only.
  As of 2026-09-16 that's Canterbury and Hampton, confirmed (not merely
  assumed) to have no digital permit source of any kind -- see
  `permit-history-enrichment-full`'s own ARCHITECTURE.md for how that was
  checked. This list will keep shrinking as real sources are found; don't
  hardcode it anywhere else either.

**Direction, both modes**: older/more-outdated siding scores HIGHER
(higher lead priority); brand-new or recently-replaced siding scores
near 0.0. Both modes classify material into the same three families
(`vinyl`/`durable_original`/`other`, see `_classify_wall_material`) --
vinyl has a genuinely shorter real-world lifespan than wood/aluminum/
asbestos siding, so `real_siding_age_score` uses a shorter decay-years
constant for vinyl than for durable materials, same physical reasoning
the proxy's own vinyl-vs-durable split already uses, just applied to a
real confirmed-or-inferred redo year instead of a piecewise year-built
heuristic.

**Recalibrated 2026-09-15 (Prompt S)**, the same real-percentile-driven
process Prompts L/M used for property age and canopy, against the real
1,182-scoreable, 8-town population.

**A real classification bug found in the process, not a curve-shape
issue**: the first pass at this recalibration found `siding_score()`
pinned exactly 314 of 1,182 qualifying parcels (27%) at exactly 0.5 --
investigated by breaking down every exact-0.5 case's real cause rather
than assuming a curve problem, and traced to `_classify_wall_material`'s
keyword list missing the single MOST COMMON real durable-material value
in the actual data, "Clapboard"/"Clapboards" (211 parcels, 18%), plus
several other real VGSI/propertyrecordcards.com material strings (see
`_DURABLE_MATERIAL_KEYWORDS`'s own comment for the full list and exact
counts). Fixed at the classification layer, not by re-tuning weights
around a data quality gap -- only 76 parcels (6.4%) land at exactly 0.5
now, all genuinely explained (missing material data, or a real vinyl-
proxy curve value that coincidentally interpolates to 0.5 for a common
1990s construction year).

**With that fixed, the real `siding_score()` distribution spreads
healthily across the full range** (combined real+proxy, n=1,182):
p5=0.08, p10=0.12, p25=0.17, p50=0.51, p75=0.87, p90=0.97, p95=0.99,
mean=0.54 -- comparable spread to `property_age_score`'s own recalibrated
distribution (p25=0.45, p50=0.67, p75=0.85), and genuinely better spread
in the middle 50% than canopy's. `DEFAULT_REAL_SIDING_VINYL_DECAY_YEARS=
18`/`DURABLE_DECAY_YEARS=35`/`OTHER_DECAY_YEARS=26` (the real-mode decay
constants) were checked against this distribution and left as originally
chosen -- they already produced a healthy spread with no further pileup,
once the classification bug above was the actual fix needed.

**Weight ordering** (client's explicit priority, confirmed 2026-09-15):
property age remains the leading signal (`DEFAULT_PROPERTY_WEIGHT=0.50`);
siding is now the strongest signal after property age
(`DEFAULT_SIDING_WEIGHT=0.30`) -- above canopy (`DEFAULT_CANOPY_WEIGHT=
0.15`), which stays well above storm (`DEFAULT_STORM_WEIGHT=0.05`,
unchanged from the prior recalibration -- `storm_score` is STILL a pure
constant 1.0 across the entire real population, re-confirmed this session,
zero real differentiating power). This reflects that real per-parcel
siding evidence (material + permit-confirmed-or-inferred age) is now on
file for over a third of the population (449 of 1,182) and is a more
direct physical indicator of exterior-renovation need than canopy cover
ever was, even though canopy itself is still real and still contributes.
Sanity-checked the COMBINED weighted score, not just each raw component,
before finalizing: the real `rank_candidates` output at these weights has
no degenerate tie clusters (only 1 exact tie at the very top, expected
for a continuous real-valued score), a healthy overall spread (p5=0.34,
p50=0.60, p95=0.91), and the top/bottom 15 real leads are exactly what
they should be -- genuinely old (1720s-1900s) high-canopy/durable-siding
properties at the top, genuinely new (2002-2006) vinyl-sided properties
at the bottom.

Retires the two previously-separate `enable_siding_age_signal`/
`enable_permit_signal` opt-in flags and their own weights -- there is now
just one `enable_siding_signal` (default `True`) and one `siding_weight`,
since the dispatch between real and proxy modes happens automatically per
parcel based on what data that parcel's source actually has, the same way
a caller never has to choose between `canopy_score`'s "known" and
"unknown" branches by hand.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any

# Proposed defaults -- see module docstring's "Real-data recalibration"
# section. A downstream deployment's client config is expected to
# override these per-client, not edit them here.
#
# Recalibrated 2026-09-15 (Prompt S) alongside adding the siding signal
# below -- property/canopy/storm were re-checked against the real
# 1,182-scoreable population (up from 872 at the last recalibration) at
# the same time siding's own weight was set, since all four now have to
# sum to a coherent whole together, not siding bolted on as an extra.
# Property stays the clear leader; canopy and storm both step down to
# make room for siding sitting solidly in second place -- see module
# docstring's "Siding signal" section for the ordering the client asked
# for and the real percentile distribution that grounded these numbers.
DEFAULT_PROPERTY_WEIGHT = 0.50
DEFAULT_CANOPY_WEIGHT = 0.15
DEFAULT_STORM_WEIGHT = 0.05

DEFAULT_PROPERTY_AGE_THRESHOLD_YEARS = 20
DEFAULT_PROPERTY_AGE_DECAY_YEARS = 30

DEFAULT_CANOPY_OPTIMAL_PCT = 35.0
DEFAULT_CANOPY_LOW_EXTREME_PCT = 0.0
DEFAULT_CANOPY_HIGH_EXTREME_PCT = 95.0

DEFAULT_STORM_LOOKBACK_YEARS = 15

# Unified siding signal -- see module docstring's "Siding signal" section.
# Enabled by default: the proxy mode's bucket boundaries below are still
# domain-judgment placeholders, but the real mode is grounded in actual
# per-parcel evidence, and the client has explicitly reviewed and
# requested this signal's priority (2026-09-15), so there's no reason to
# gate it off pending review the way it was when it was proxy-only.
DEFAULT_ENABLE_SIDING_SIGNAL = True
# See module docstring's "Siding signal" section for the real-percentile
# reasoning: siding is the strongest signal after property age, above
# canopy, well above storm.
DEFAULT_SIDING_WEIGHT = 0.30

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
# the 0/100 extremes. Proxy mode only -- building_percent_good is a VGSI
# field, never extracted by propertyrecordcards.com at all (so Killingly/
# Ashford, PRC-only towns, never have it) -- every OTHER real-mode town
# (Woodstock, Brooklyn, Thompson; Pomfret's own VGSI scrape happens not to
# have populated it, unexplained, not investigated as part of a docs-only
# pass) is VGSI-sourced and so COULD have it. Real mode deliberately
# doesn't use it regardless, to avoid a modifier that's live for some
# real-mode parcels and silently absent for others depending on which of
# two totally different platforms/repos set `permit_data_available`.
DEFAULT_SIDING_PERCENT_GOOD_MODIFIER_STRENGTH = 0.15

# Real-mode siding signal (`real_siding_age_score`) -- see module
# docstring's "Siding signal" section. Vinyl's real-world lifespan is
# shorter than durable materials' (wood/aluminum/asbestos), so it
# saturates toward max-priority faster (smaller decay-years constant) for
# the SAME number of years since its confirmed-or-inferred install/redo
# date. Recalibrated 2026-09-15 against the real distribution of
# `real_siding_age_score` output across all 553 real-mode-eligible
# parcels -- see each constant's own comment for the specific percentiles.
DEFAULT_REAL_SIDING_VINYL_DECAY_YEARS = 18.0
DEFAULT_REAL_SIDING_DURABLE_DECAY_YEARS = 35.0
DEFAULT_REAL_SIDING_OTHER_DECAY_YEARS = 26.0


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


## Real production bug found and fixed 2026-09-15 (Prompt S), while
## sanity-checking the new siding signal for pileups: this keyword list
## used to be just ("wood", "aluminum", "asbestos"), which silently
## missed the single MOST COMMON real durable-material value in the
## actual data -- "Clapboard"/"Clapboards" (211 of 1,182 real qualifying
## parcels, 18% -- confirmed by counting the real distribution, not
## guessed), plus VGSI's abbreviated "Asbest Shingle" (missing the "os"
## suffix "asbestos" requires as a substring) and "Pre-finsh Metl"
## (missing the "al" "metal" requires), "Board & Batten", "Cedar or
## Redwd", "Log"/"Log Cabin", "Cement Board", and masonry-family
## materials (Brick/Stone/Stucco/Concrete/Cinder -- arguably even MORE
## durable than wood, folded into the same bucket rather than a third
## tier this session doesn't have real data to justify splitting out).
## Every one of these was silently falling into "other" -> a flat
## neutral 0.5, contributing ZERO real signal for a full 20% of the
## qualifying population (314 of 1,182 parcels scored exactly 0.5) --
## confirmed a real pileup, not a display artifact, by breaking down
## every exact-0.5 case's actual cause before concluding this was the
## root cause rather than assuming it. Fixed: only 76 parcels (6.4%) now
## land at exactly 0.5, all genuinely explained (70 missing
## `exterior_wall_1` entirely, plus 6 real vinyl-proxy curve values that
## coincidentally interpolate to 0.5 for a common 1990s construction
## year -- not a classification gap).
_DURABLE_MATERIAL_KEYWORDS = (
    "wood",
    "aluminum",
    "asbest",  # catches both "Asbestos ..." and VGSI's abbreviated "Asbest Shingle"
    "clapboard",
    "shingle",
    "board & batten",
    "cedar",
    "redwd",
    "redwood",
    "log",
    "metal",
    "metl",  # VGSI's own abbreviated "Pre-finsh Metl"
    "masonry",
    "brick",
    "stone",
    "stucco",
    "concr",  # "Concrete"/"Concr/Cinder"
    "cinder",
    "fibr/cem",
    "fiber cement",
    "cement",  # e.g. "Cement Board" -- a fiber-cement product, not vinyl
    "hardboard",
    "masonite",
)


def _classify_wall_material(exterior_wall_1: str | None) -> str | None:
    """Bucket a raw VGSI/propertyrecordcards.com `Exterior Wall 1`/`Siding`
    string into a material family.

    Free text ("Vinyl Siding", "Wood Shingle", "Clapboards", "Asbest
    Shingle", "Brick/Masonry", ...), not a fixed enum -- match by case-
    insensitive substring against `_DURABLE_MATERIAL_KEYWORDS`, same
    defensive style already used for VGSI field-label matching elsewhere
    in this codebase (see `vgsi.py`'s `_find_building_attribute` colon-
    suffix handling), rather than an exact-match lookup that silently
    misses real variants -- see that constant's own comment for the real
    pileup this fix resolved.
    """
    if not exterior_wall_1:
        return None
    text = exterior_wall_1.lower()
    if "vinyl" in text:
        return "vinyl"
    if any(keyword in text for keyword in _DURABLE_MATERIAL_KEYWORDS):
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
) -> float | None:
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

    This is the PROXY mode of the unified siding signal -- see
    `siding_score()`, which dispatches to this function for a parcel
    whose source has no real permit history, and to
    `real_siding_age_score()` for one that does. Doesn't check
    `permit_data_available` itself (added 2026-09-15: that dispatch
    decision now lives in `siding_score()` alone, not duplicated here) --
    calling this function directly always runs the proxy logic regardless
    of what data the parcel actually has, by design, so a caller
    deliberately wanting the proxy value for comparison/testing can.
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


def real_siding_age_score(
    parcel: dict[str, Any],
    vinyl_decay_years: float = DEFAULT_REAL_SIDING_VINYL_DECAY_YEARS,
    durable_decay_years: float = DEFAULT_REAL_SIDING_DURABLE_DECAY_YEARS,
    other_decay_years: float = DEFAULT_REAL_SIDING_OTHER_DECAY_YEARS,
    as_of_year: int | None = None,
) -> float | None:
    """Score 0-1: real-mode siding material+age, using the direct
    `Siding:` field and real permit history together -- see module
    docstring's "Siding signal" section for the full reasoning. This is
    the REAL-DATA mode of the unified siding signal; `siding_score()`
    dispatches here for a parcel whose source has real permit visibility
    (`permit_data_available` true), and to the `siding_age_score` proxy
    otherwise.

    Returns `None` when `permit_data_available` is false -- calling this
    function directly on a proxy-only parcel is a caller error made safe,
    not a silent guess (mirrors `permit_data_available`-gated functions
    elsewhere in this module's history).

    Returns a neutral 0.5 when `exterior_wall_1` or `year_built` is
    missing -- same "unknown is neutral" convention as the proxy and
    `canopy_score`.

    **Effective redo year**: the most recent exterior-relevant permit's
    year if one is on file (real, dated evidence the siding was actually
    worked on) -- otherwise `year_built` (the same "presumed never
    redone" fallback the proxy has to assume everywhere, used here only
    when there's no better evidence, not as the primary inference).

    **Short permit history guard (2026-10-26, Windham build)**: the
    "otherwise `year_built`" fallback above is only safe when the permit
    source's own history is long/established enough that "nothing on
    file" plausibly means "never redone" over the parcel's whole
    lifetime. `parcel["permit_history_since"]` makes that assumption
    explicit per parcel: `None` (every pre-Windham permit-visible town)
    keeps the fallback above unchanged. A real date (Windham's PermitLink
    portal only covers 2026-04-15 forward) means the opposite -- "no
    permit found" there is NOT evidence of anything, since literally
    every parcel in that town would show the same absence regardless of
    its real roof age. In that case this function falls back to
    `siding_age_score`'s material+age-only proxy instead of fabricating a
    decades-old redo year -- the same honest "we don't have enough real
    evidence, estimate from material+age" answer a town with zero permit
    visibility already gets, not a new third behavior.

    **Material-sensitive decay**: `1 - exp(-(years_since_redone) /
    decay_years)`, the same exponential-saturation shape
    `property_age_score` uses, with `decay_years` chosen by material
    family (`_classify_wall_material`) -- vinyl's real-world lifespan is
    shorter than wood/aluminum/asbestos, so it saturates toward 1.0 (most
    overdue) faster for the same number of years since redone. Returns
    0.0 (lowest priority) for a redo year at or after the current year --
    e.g. a permit opened this year.
    """
    if not parcel.get("permit_data_available"):
        return None

    exterior_wall_1 = parcel.get("exterior_wall_1")
    year_built = parcel.get("year_built")
    if not exterior_wall_1 or year_built is None:
        return 0.5

    material = _classify_wall_material(exterior_wall_1)
    if material == "vinyl":
        decay_years = vinyl_decay_years
    elif material == "durable_original":
        decay_years = durable_decay_years
    else:
        decay_years = other_decay_years

    most_recent_exterior_permit_date = parcel.get("most_recent_exterior_permit_date")
    if most_recent_exterior_permit_date is not None:
        effective_redo_year = most_recent_exterior_permit_date.year
    elif parcel.get("permit_history_since") is not None:
        # No permit on file, but this town's permit source can't attest
        # to anything before permit_history_since -- too short a window
        # to trust the absence as "never redone." Fall back to the
        # material+age-only proxy rather than year_built.
        return siding_age_score(parcel)
    else:
        effective_redo_year = year_built

    years_since_redone = _current_year(as_of_year) - effective_redo_year
    if years_since_redone <= 0:
        return 0.0
    if decay_years <= 0:
        return 1.0
    return 1.0 - math.exp(-years_since_redone / decay_years)


def siding_score(parcel: dict[str, Any], as_of_year: int | None = None) -> float | None:
    """The one unified siding signal `score_property` actually uses --
    dispatches purely on each parcel's own `permit_data_available` flag,
    never on a hardcoded town list (that list has already changed once --
    Brooklyn/Pomfret/Thompson moved from the proxy to real permit data via
    a separate `permit-history-enrichment-full` deployment after this
    function was first written, with zero change needed here, which is
    the entire point of dispatching on the flag instead of on `town`).
    Real permit visibility currently comes from two different downstream
    sources depending on the parcel's town -- a `property-lead-scorer-full`
    enrichment pass (Killingly, Ashford, Woodstock) or the separate
    `permit-history-enrichment-full` repo (Brooklyn, Pomfret, Thompson) --
    this function has no way to tell which, and doesn't need to. Everyone
    else falls to the `siding_age_score` proxy. See module docstring's
    "Siding signal" section.

    Both branches use each other's own default tunables (not exposed as
    pass-through parameters here) -- same minimal-surface convention
    `score_property` already uses for the proxy's own fine-grained
    constants; call `siding_age_score`/`real_siding_age_score` directly
    with explicit overrides if a caller needs to tune those.
    """
    if parcel.get("permit_data_available"):
        return real_siding_age_score(parcel, as_of_year=as_of_year)
    return siding_age_score(parcel)


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
    # None when the siding signal is disabled -- distinct from a computed
    # 0.0/neutral-0.5, so a caller/digest can tell "this signal wasn't
    # evaluated" apart from "this signal was evaluated and scored low."
    # Computed by `siding_score()` -- real mode (`real_siding_age_score`)
    # for a permit_data_available parcel, proxy mode (`siding_age_score`)
    # otherwise; the caller can't tell which mode produced this value from
    # the field alone, only from the parcel's own `permit_data_available`.
    siding_component: float | None = None


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
    enable_siding_signal: bool = DEFAULT_ENABLE_SIDING_SIGNAL,
    siding_weight: float = DEFAULT_SIDING_WEIGHT,
    as_of_year: int | None = None,
) -> LeadScore | None:
    """Score one parcel as an exterior-renovation-lead candidate, or None if it doesn't qualify.

    One hard qualifying condition: `year_built` must be known and the
    property must already be at least `property_age_threshold_years`
    old. Property age is this tool's leading signal (per the client
    brief) -- a property that hasn't cleared that bar at all isn't a
    plausible candidate yet, so it's excluded (returns None) rather than
    merely scored low. Canopy, storm, and siding are supporting signals
    only: none of them can make an otherwise-too-new property qualify.

    Among properties that qualify, `score` is the weighted AVERAGE of the
    active component scores (sum of weight*component, divided by the sum
    of active weights) -- not a plain weighted sum. `property_weight` +
    `canopy_weight` + `storm_weight` + `siding_weight` sum to 1.0 by
    construction when `enable_siding_signal` is true (the normal case, see
    `DEFAULT_SIDING_WEIGHT`'s own recalibration comment); dividing by the
    weight sum keeps the combined score correctly bounded to [0, 1]
    whether or not siding ends up contributing for a given parcel or is
    disabled entirely for a caller that wants the pre-siding-signal
    behavior.
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

    siding_component: float | None = None
    if enable_siding_signal:
        siding_component = siding_score(parcel, as_of_year)
        if siding_component is not None:
            weighted_sum += siding_weight * siding_component
            total_weight += siding_weight

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
    if enable_siding_signal and siding_component is not None:
        exterior_wall_1 = parcel.get("exterior_wall_1")
        if parcel.get("permit_data_available"):
            most_recent = parcel.get("most_recent_exterior_permit_date")
            if most_recent is not None:
                reasons.append(
                    f"Siding: {exterior_wall_1}; most recent exterior-relevant permit "
                    f"({parcel.get('most_recent_exterior_permit_type', 'unknown type')}) opened {most_recent}."
                )
            else:
                exterior_permit_count = parcel.get("exterior_permit_count") or 0
                reasons.append(
                    f"Siding: {exterior_wall_1}; no exterior-relevant permit on file "
                    f"({exterior_permit_count} permits checked)."
                )
        else:
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
        siding_component=siding_component,
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
    enable_siding_signal: bool = DEFAULT_ENABLE_SIDING_SIGNAL,
    siding_weight: float = DEFAULT_SIDING_WEIGHT,
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
            enable_siding_signal=enable_siding_signal,
            siding_weight=siding_weight,
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
