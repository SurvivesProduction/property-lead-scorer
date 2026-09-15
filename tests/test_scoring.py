from datetime import date

import pytest

from extscorer.scoring.basic import (
    DEFAULT_CANOPY_WEIGHT,
    DEFAULT_PROPERTY_WEIGHT,
    DEFAULT_STORM_WEIGHT,
    canopy_score,
    property_age_score,
    rank_candidates,
    real_siding_age_score,
    score_property,
    siding_age_score,
    siding_score,
    storm_score,
)

_AS_OF_YEAR = 2026


def test_property_age_score_zero_when_year_built_unknown() -> None:
    assert property_age_score({}, as_of_year=_AS_OF_YEAR) == 0.0


def test_property_age_score_zero_when_not_yet_past_threshold() -> None:
    # Built 2020, as-of 2026 -> 6 years old, below the 20-year threshold.
    assert property_age_score({"year_built": 2020}, as_of_year=_AS_OF_YEAR) == 0.0


def test_property_age_score_matches_the_exponential_saturation_formula() -> None:
    # Real-data-recalibrated shape (2026-09-09, Prompt M): exponential
    # saturation, not a linear ramp to a hard cap -- see module docstring
    # for why. Built 2000, as-of 2026 -> 26 years old, 6 years past the
    # 20-year threshold; decay_scale_years=30 -> 1 - exp(-6/30).
    import math

    score = property_age_score(
        {"year_built": 2000},
        threshold_years=20,
        decay_scale_years=30,
        as_of_year=_AS_OF_YEAR,
    )
    assert score == pytest.approx(1 - math.exp(-6 / 30))


def test_property_age_score_never_exactly_reaches_one_but_saturates_for_the_historic_tail() -> None:
    # Built 1800, as-of 2026 -> 226 years old (the real p5 age among
    # scoreable parcels) -- deep into the historic tail, should be very
    # close to but not exactly 1.0 (the whole point of the exponential
    # shape over the old hard linear cap).
    score = property_age_score(
        {"year_built": 1800},
        threshold_years=20,
        decay_scale_years=30,
        as_of_year=_AS_OF_YEAR,
    )
    assert 0.995 < score < 1.0


def test_property_age_score_spreads_real_scores_across_the_real_percentile_bulk() -> None:
    # Regression test tying the recalibration directly to the real
    # scoreable-population age percentiles found in Prompt M Step 1
    # (p95=25, p90=28, p75=38, p50=54, p25=76, p10=136) -- the whole
    # point of the recalibration was real, monotonic spread across this
    # entire real range, not a pileup at either end.
    ages = {"p95": 25, "p90": 28, "p75": 38, "p50": 54, "p25": 76, "p10": 136}
    scores = {
        label: property_age_score(
            {"year_built": _AS_OF_YEAR - age}, threshold_years=20, decay_scale_years=30, as_of_year=_AS_OF_YEAR
        )
        for label, age in ages.items()
    }
    # Strictly increasing as age increases (p95 is the youngest bucket
    # here, p10 the oldest).
    ordered = [scores[label] for label in ("p95", "p90", "p75", "p50", "p25", "p10")]
    assert ordered == sorted(ordered)
    # Real spread across the bulk, not everyone pinned near 0 or 1 --
    # matches the values reported in scoring/basic.py's own docstring.
    assert scores["p95"] == pytest.approx(0.154, abs=0.01)
    assert scores["p50"] == pytest.approx(0.678, abs=0.01)
    assert scores["p10"] == pytest.approx(0.979, abs=0.01)


def test_canopy_score_zero_at_optimal() -> None:
    # Real-data-recalibrated default (2026-09-09): optimal=35.0, grounded
    # in the actual scoreable population's canopy percentile distribution
    # (see scoring/basic.py's module docstring for the real numbers).
    assert canopy_score({"pct_tree_canopy_nearby": 35.0}) == 0.0


def test_canopy_score_one_at_fully_exposed() -> None:
    assert canopy_score({"pct_tree_canopy_nearby": 0.0}) == 1.0


def test_canopy_score_one_at_heavy_cover() -> None:
    # Real-data-recalibrated default: high_extreme=95.0 (was 55.0 --
    # confirmed too low against real data: the median real parcel already
    # exceeds it).
    assert canopy_score({"pct_tree_canopy_nearby": 95.0}) == 1.0


def test_canopy_score_caps_beyond_high_extreme() -> None:
    assert canopy_score({"pct_tree_canopy_nearby": 99.0}) == 1.0


def test_canopy_score_scales_on_low_side() -> None:
    # Halfway between fully-exposed (0) and optimal (35) -> 0.5.
    assert canopy_score({"pct_tree_canopy_nearby": 17.5}) == 0.5


def test_canopy_score_middle_of_the_real_high_side_distribution() -> None:
    # The real scoreable population's median canopy (67.4%) should land
    # meaningfully below 1.0 with the recalibrated high_extreme=95.0 --
    # the whole point of the recalibration was to stop the bulk of the
    # real population from clustering at max risk.
    score = canopy_score({"pct_tree_canopy_nearby": 67.4})
    assert 0.4 < score < 0.7


def test_canopy_score_neutral_when_unknown() -> None:
    assert canopy_score({}) == 0.5


def test_canopy_score_handles_decimal_from_a_real_database_row() -> None:
    # Regression test: a real parcel dict sourced from the live database
    # (psycopg's dict_row) carries pct_tree_canopy_nearby as a
    # decimal.Decimal (the column is `numeric`), not a plain float -- a
    # real TypeError surfaced running this against real data for the
    # first time, never caught by the synthetic-float-only tests above.
    from decimal import Decimal

    assert canopy_score({"pct_tree_canopy_nearby": Decimal("35.0")}) == 0.0
    assert canopy_score({"pct_tree_canopy_nearby": Decimal("95.0")}) == 1.0


def test_storm_score_full_for_event_this_year() -> None:
    parcel = {"year_built": 1990, "nearest_storm_event_date": date(_AS_OF_YEAR, 1, 1)}
    assert storm_score(parcel, lookback_years=15, as_of_year=_AS_OF_YEAR) == 1.0


def test_storm_score_zero_beyond_lookback_window() -> None:
    parcel = {"year_built": 1990, "nearest_storm_event_date": date(_AS_OF_YEAR - 15, 1, 1)}
    assert storm_score(parcel, lookback_years=15, as_of_year=_AS_OF_YEAR) == 0.0


def test_storm_score_zero_when_event_predates_construction() -> None:
    parcel = {"year_built": 2010, "nearest_storm_event_date": date(2005, 1, 1)}
    assert storm_score(parcel, as_of_year=_AS_OF_YEAR) == 0.0


def test_storm_score_zero_when_no_event_on_file() -> None:
    assert storm_score({"year_built": 1990}, as_of_year=_AS_OF_YEAR) == 0.0


def test_score_property_none_when_year_built_unknown() -> None:
    assert score_property({"parcel_id": "1", "town": "Canterbury"}, as_of_year=_AS_OF_YEAR) is None


def test_score_property_none_when_too_new() -> None:
    parcel = {"parcel_id": "1", "town": "Canterbury", "year_built": 2020}
    assert score_property(parcel, property_age_threshold_years=20, as_of_year=_AS_OF_YEAR) is None


def test_score_property_returns_lead_score_when_qualified() -> None:
    parcel = {
        "parcel_id": "1",
        "town": "Canterbury",
        "address": "1 Fake St",
        "year_built": 1990,
        "living_area_sqft": 2000,
    }
    # Isolated to the original three signals -- siding is on by default
    # now, tested separately below, and would otherwise add a fourth
    # reason line and a neutral-0.5 component here (no exterior_wall_1 set).
    lead = score_property(parcel, enable_siding_signal=False, as_of_year=_AS_OF_YEAR)
    assert lead is not None
    assert lead.parcel_id == "1"
    assert 0.0 < lead.score <= 1.0
    assert lead.property_component > 0.0
    assert len(lead.reasons) == 3


def test_score_property_high_priority_case() -> None:
    # A clear high-priority real-shaped lead: very old (deep into the
    # exponential curve's saturation zone -- see Prompt M's recalibration),
    # near-optimal canopy, and a recent qualifying storm -- all three
    # components should be strong.
    parcel = {
        "parcel_id": "1",
        "town": "Canterbury",
        "address": "1 Old House Rd",
        "year_built": 1900,
        "living_area_sqft": 2200,
        "pct_tree_canopy_nearby": 35.0,  # exactly optimal -> lowest canopy risk
        "nearest_storm_event_date": date(_AS_OF_YEAR, 5, 19),
    }
    # Isolated to the original three signals -- see the equivalent note on
    # test_score_property_returns_lead_score_when_qualified above.
    lead = score_property(parcel, enable_siding_signal=False, as_of_year=_AS_OF_YEAR)
    assert lead is not None
    assert lead.property_component > 0.95
    assert lead.canopy_component == 0.0
    assert lead.storm_component == 1.0
    # property_weight dominates, but a 0 canopy_component still pulls the
    # total well below a perfect 1.0.
    assert 0.65 < lead.score < 0.8


def test_score_property_low_priority_case() -> None:
    # A clear low-priority case: just barely old enough to qualify at all
    # (property_component near 0), heavy canopy cover (near max risk), no
    # storm history.
    parcel = {
        "parcel_id": "2",
        "town": "Canterbury",
        "address": "2 New House Rd",
        "year_built": _AS_OF_YEAR - 21,  # 21 years old, 1 year past the 20-year threshold
        "living_area_sqft": 1200,
        "pct_tree_canopy_nearby": 96.0,  # near max canopy risk
    }
    # Isolated to the original three signals -- see the equivalent note on
    # test_score_property_returns_lead_score_when_qualified above.
    lead = score_property(parcel, enable_siding_signal=False, as_of_year=_AS_OF_YEAR)
    assert lead is not None
    assert lead.property_component < 0.1
    assert lead.canopy_component > 0.9
    assert lead.storm_component == 0.0
    assert lead.score < 0.35


def test_score_property_partial_signal_missing_canopy_uses_neutral_default() -> None:
    # Step 1's resolved design: a qualifying parcel missing canopy (a real
    # 20.5% case among real scoreable parcels, from a geocoding gap
    # unrelated to lead quality) gets canopy_score's existing neutral 0.5
    # default -- not renormalized weights, not excluded from ranking.
    # Since a HIGHER canopy_component means higher risk/priority (worse
    # canopy conditions push the score UP, same direction as the other
    # components), the neutral default must land strictly between a
    # genuinely optimal (lowest-risk, component 0.0) and a genuinely
    # worst-case (highest-risk, component ~1.0) real measured value --
    # neither penalized nor rewarded relative to real data either way.
    base = {
        "parcel_id": "3",
        "town": "Canterbury",
        "address": "3 Rd",
        "year_built": 1960,
        "nearest_storm_event_date": date(_AS_OF_YEAR, 5, 19),
    }
    optimal = dict(base, parcel_id="optimal", pct_tree_canopy_nearby=35.0)  # component 0.0
    missing = dict(base, parcel_id="missing", pct_tree_canopy_nearby=None)  # component 0.5
    worst = dict(base, parcel_id="worst", pct_tree_canopy_nearby=100.0)  # component ~1.0

    lead_optimal = score_property(optimal, as_of_year=_AS_OF_YEAR)
    lead_missing = score_property(missing, as_of_year=_AS_OF_YEAR)
    lead_worst = score_property(worst, as_of_year=_AS_OF_YEAR)

    assert lead_optimal is not None and lead_missing is not None and lead_worst is not None
    assert lead_missing.canopy_component == 0.5
    assert lead_optimal.score < lead_missing.score < lead_worst.score


def test_rank_candidates_tiebreaks_on_living_area_sqft_then_parcel_id() -> None:
    # All three parcels share year_built and no canopy/storm data on file,
    # so property_component, canopy_component (neutral 0.5), and
    # storm_component (0.0) are identical across all three -- the total
    # score ties, and only living_area_sqft (then parcel_id) can break it.
    parcels = [
        {"parcel_id": "B", "town": "Canterbury", "address": "b", "year_built": 1990, "living_area_sqft": 1000},
        {"parcel_id": "A", "town": "Canterbury", "address": "a", "year_built": 1990, "living_area_sqft": 3000},
        {"parcel_id": "C", "town": "Canterbury", "address": "c", "year_built": 1990, "living_area_sqft": 2000},
    ]
    ranked = rank_candidates(parcels, as_of_year=_AS_OF_YEAR)

    scores = {lead.score for lead in ranked}
    assert len(scores) == 1, "test setup should produce a genuine tie on score"
    assert [lead.parcel_id for lead in ranked] == ["A", "C", "B"]


def test_rank_candidates_excludes_unqualified_parcels() -> None:
    parcels = [
        {"parcel_id": "OLD", "town": "Canterbury", "address": "a", "year_built": 1990},
        {"parcel_id": "NEW", "town": "Canterbury", "address": "b", "year_built": 2020},
    ]
    ranked = rank_candidates(parcels, as_of_year=_AS_OF_YEAR)
    assert [lead.parcel_id for lead in ranked] == ["OLD"]


# --- siding_age_score -------------------------------------------------
# Year Remodeled/Condition were part of the original spec for this signal
# but a field audit found VGSI doesn't expose either for single-family
# cards -- these tests only exercise exterior_wall_1 + year_built (+
# building_percent_good as a modifier), per that finding.


def test_siding_age_score_neutral_when_wall_material_missing() -> None:
    assert siding_age_score({"year_built": 1950}) == 0.5


def test_siding_age_score_neutral_when_year_built_missing() -> None:
    assert siding_age_score({"exterior_wall_1": "Vinyl Siding"}) == 0.5


def test_siding_age_score_neutral_for_unrecognized_material() -> None:
    # Brick/stone/masonry etc. are now classified as durable_original (a
    # real fix, 2026-09-15 -- see _DURABLE_MATERIAL_KEYWORDS' own
    # comment); "Average" is a real VGSI value confirmed to still fall
    # through genuinely unclassified (not a material description at all).
    assert siding_age_score({"exterior_wall_1": "Average", "year_built": 1950}) == 0.5


def test_siding_age_score_vinyl_pre_1975_is_not_prime() -> None:
    # Vinyl wasn't common residential siding before ~1975 -- a pre-1975
    # house with vinyl NOW implies an unknown-timing re-side already
    # happened, so this is deliberately scored LOW, not high, despite the
    # house itself being old.
    score = siding_age_score({"exterior_wall_1": "Vinyl Siding", "year_built": 1920})
    assert score == pytest.approx(0.15)


def test_siding_age_score_wood_pre_1990_is_prime() -> None:
    # Durable original material + old house -> likely never re-sided ->
    # highest-scoring bucket.
    score = siding_age_score({"exterior_wall_1": "Wood Shingle", "year_built": 1900})
    assert score > 0.95


def test_siding_age_score_aluminum_and_asbestos_use_the_same_durable_curve() -> None:
    parcel_year = 1950
    wood = siding_age_score({"exterior_wall_1": "Wood Shingle", "year_built": parcel_year})
    aluminum = siding_age_score({"exterior_wall_1": "Aluminum Siding", "year_built": parcel_year})
    asbestos = siding_age_score({"exterior_wall_1": "Asbestos Shingle", "year_built": parcel_year})
    assert wood == pytest.approx(aluminum) == pytest.approx(asbestos)


def test_classify_wall_material_catches_real_variants_missed_before_2026_09_15() -> None:
    # Regression test for a real bug found while recalibrating (Prompt S):
    # these are real, common exterior_wall_1/Siding values from the live
    # data that used to silently fall through to "other" (a flat neutral
    # 0.5, contributing zero signal) -- confirmed via a real percentile
    # analysis that 27% of the qualifying population was pinned at
    # exactly 0.5 before this fix, dominated by "Clapboard"/"Clapboards"
    # (211 of 1,182 parcels, 18%, the single most common material in the
    # real data) alongside VGSI's abbreviated "Asbest Shingle" and
    # "Pre-finsh Metl". All of these must classify as durable_original,
    # matching Wood Shingle's own curve, not fall back to neutral.
    parcel_year = 1950
    wood = siding_age_score({"exterior_wall_1": "Wood Shingle", "year_built": parcel_year})
    for real_value in ("Clapboard", "Clapboards", "Asbest Shingle", "Pre-finsh Metl", "Board & Batten", "Brick/Masonry"):
        assert siding_age_score({"exterior_wall_1": real_value, "year_built": parcel_year}) == pytest.approx(wood), real_value


def test_siding_age_score_durable_material_decays_smoothly_after_the_never_resided_year() -> None:
    # A durable-material house built well AFTER 1990 is less overdue than
    # one built well before it -- continuous decay, not a cliff.
    at_cutoff = siding_age_score({"exterior_wall_1": "Wood Shingle", "year_built": 1990})
    just_after = siding_age_score({"exterior_wall_1": "Wood Shingle", "year_built": 2010})
    much_later = siding_age_score({"exterior_wall_1": "Wood Shingle", "year_built": 2024})
    assert at_cutoff == pytest.approx(0.85)
    assert at_cutoff > just_after > much_later


def test_siding_age_score_vinyl_moderate_band_1985_to_2000() -> None:
    # 1985 (older end of the moderate band) should score higher than 2000
    # (newer end) -- older-within-band vinyl is more likely actually due.
    at_1985 = siding_age_score({"exterior_wall_1": "Vinyl Siding", "year_built": 1985})
    at_2000 = siding_age_score({"exterior_wall_1": "Vinyl Siding", "year_built": 2000})
    assert at_1985 == pytest.approx(0.60)
    assert at_2000 == pytest.approx(0.45)
    assert at_1985 > at_2000
    # Both clearly below the durable-material PRIME range and clearly
    # above the vinyl not-prime/near-zero floors.
    assert 0.15 < at_2000 < at_1985 < 0.85


def test_siding_age_score_vinyl_post_2005_is_near_zero() -> None:
    score = siding_age_score({"exterior_wall_1": "Vinyl Siding", "year_built": 2015})
    assert score == pytest.approx(0.03)


def test_siding_age_score_vinyl_interpolates_the_1975_to_1985_transition_gap() -> None:
    # Not a named bucket in the client's original spec -- the midpoint of
    # the transition zone between "not prime" (1975) and "moderate" (1985).
    score = siding_age_score({"exterior_wall_1": "Vinyl Siding", "year_built": 1980})
    assert score == pytest.approx(0.375)


def test_siding_age_score_vinyl_interpolates_the_2000_to_2005_transition_gap() -> None:
    score = siding_age_score({"exterior_wall_1": "Vinyl Siding", "year_built": 2002})
    assert score == pytest.approx(0.282, abs=0.001)


def test_siding_age_score_percent_good_modifier_is_neutral_at_50() -> None:
    without = siding_age_score({"exterior_wall_1": "Vinyl Siding", "year_built": 2015})
    at_50 = siding_age_score(
        {"exterior_wall_1": "Vinyl Siding", "year_built": 2015, "building_percent_good": 50}
    )
    assert without == pytest.approx(at_50)


def test_siding_age_score_percent_good_modifier_direction() -> None:
    # Worse condition (lower percent-good) should nudge the score UP, same
    # direction as this project's other signals -- but only as a modifier,
    # it shouldn't flip a near-zero vinyl-post-2005 case into a prime one.
    worst_condition = siding_age_score(
        {"exterior_wall_1": "Vinyl Siding", "year_built": 2015, "building_percent_good": 0}
    )
    best_condition = siding_age_score(
        {"exterior_wall_1": "Vinyl Siding", "year_built": 2015, "building_percent_good": 100}
    )
    baseline = siding_age_score({"exterior_wall_1": "Vinyl Siding", "year_built": 2015})
    assert best_condition < baseline < worst_condition
    assert worst_condition < 0.3  # still nowhere near the prime range


def test_siding_age_score_gracefully_degrades_when_percent_good_is_none() -> None:
    # Pomfret's card template lacks this block entirely, and not every
    # parcel is backfilled yet -- must not error or skew toward a default.
    with_none = siding_age_score(
        {"exterior_wall_1": "Wood Shingle", "year_built": 1900, "building_percent_good": None}
    )
    without_key = siding_age_score({"exterior_wall_1": "Wood Shingle", "year_built": 1900})
    assert with_none == pytest.approx(without_key)


def test_siding_age_score_tolerates_decimal_percent_good() -> None:
    # A real DB row can carry a numeric column as decimal.Decimal, not
    # plain float -- the same gotcha canopy_score already guards against.
    from decimal import Decimal

    score = siding_age_score(
        {"exterior_wall_1": "Vinyl Siding", "year_built": 2015, "building_percent_good": Decimal("83")}
    )
    assert isinstance(score, float)


def test_siding_age_score_never_exceeds_bounds() -> None:
    extreme_high = siding_age_score(
        {"exterior_wall_1": "Wood Shingle", "year_built": 1700, "building_percent_good": 0}
    )
    extreme_low = siding_age_score(
        {"exterior_wall_1": "Vinyl Siding", "year_built": 2026, "building_percent_good": 100}
    )
    assert 0.0 <= extreme_low <= extreme_high <= 1.0


# --- score_property / rank_candidates wiring ---------------------------


def test_score_property_siding_signal_enabled_by_default() -> None:
    # The siding signal is ON by default (unlike its original opt-in-only
    # history) -- a plain score_property call with no override populates
    # siding_component and adds the fourth reason line.
    parcel = {
        "parcel_id": "1",
        "town": "Canterbury",
        "address": "1 Old House Rd",
        "year_built": 1900,
        "living_area_sqft": 2200,
        "exterior_wall_1": "Wood Shingle",
        "pct_tree_canopy_nearby": 35.0,
        "nearest_storm_event_date": date(_AS_OF_YEAR, 5, 19),
    }
    lead = score_property(parcel, as_of_year=_AS_OF_YEAR)
    assert lead is not None
    assert lead.siding_component is not None
    assert len(lead.reasons) == 4


def test_score_property_siding_signal_disabled_matches_three_signal_formula() -> None:
    # With the flag explicitly off, score_property falls back to the
    # plain property/canopy/storm weighted average -- siding_component
    # left None, no fourth reason line.
    parcel = {
        "parcel_id": "1",
        "town": "Canterbury",
        "address": "1 Old House Rd",
        "year_built": 1900,
        "living_area_sqft": 2200,
        "exterior_wall_1": "Wood Shingle",
        "pct_tree_canopy_nearby": 35.0,
        "nearest_storm_event_date": date(_AS_OF_YEAR, 5, 19),
    }
    lead = score_property(parcel, enable_siding_signal=False, as_of_year=_AS_OF_YEAR)
    assert lead is not None
    assert lead.siding_component is None
    assert len(lead.reasons) == 3  # no fourth (siding) reason line when disabled
    # A weighted AVERAGE, not a weighted sum -- property/canopy/storm no
    # longer sum to 1.0 on their own now that siding_weight claims a real
    # share, so the three active weights' own sum is the real denominator.
    total_weight = DEFAULT_PROPERTY_WEIGHT + DEFAULT_CANOPY_WEIGHT + DEFAULT_STORM_WEIGHT
    expected = (
        DEFAULT_PROPERTY_WEIGHT * lead.property_component
        + DEFAULT_CANOPY_WEIGHT * lead.canopy_component
        + DEFAULT_STORM_WEIGHT * lead.storm_component
    ) / total_weight
    assert lead.score == pytest.approx(expected)


def test_score_property_siding_signal_enabled_populates_component_and_reason() -> None:
    parcel = {
        "parcel_id": "1",
        "town": "Canterbury",
        "address": "1 Old House Rd",
        "year_built": 1900,
        "living_area_sqft": 2200,
        "exterior_wall_1": "Wood Shingle",
        "pct_tree_canopy_nearby": 35.0,
    }
    lead = score_property(parcel, as_of_year=_AS_OF_YEAR)
    assert lead is not None
    assert lead.siding_component is not None
    assert lead.siding_component > 0.95  # prime wood/pre-1990 case
    assert len(lead.reasons) == 4
    assert "Wood Shingle" in lead.reasons[-1]
    assert 0.0 <= lead.score <= 1.0


def test_score_property_siding_signal_enabled_still_bounded_when_all_components_maxed() -> None:
    # A parcel that maxes every component (including siding) must still
    # produce a score <= 1.0 -- the weighted-average-over-total-weight
    # formula, not a plain weighted sum, is what guarantees this once a
    # fourth weight is in play.
    parcel = {
        "parcel_id": "1",
        "town": "Canterbury",
        "address": "1 Old House Rd",
        "year_built": 1700,
        "living_area_sqft": 2200,
        "exterior_wall_1": "Wood Shingle",
        "pct_tree_canopy_nearby": 95.0,
        "nearest_storm_event_date": date(_AS_OF_YEAR, 5, 19),
    }
    lead = score_property(parcel, as_of_year=_AS_OF_YEAR)
    assert lead is not None
    assert lead.score <= 1.0


def test_rank_candidates_siding_signal_disabled_excludes_it_entirely() -> None:
    parcels = [
        {
            "parcel_id": "A",
            "town": "Canterbury",
            "address": "a",
            "year_built": 1900,
            "exterior_wall_1": "Vinyl Siding",  # would score very differently with the signal ON
        },
        {"parcel_id": "B", "town": "Canterbury", "address": "b", "year_built": 1990},
    ]
    ranked_default = rank_candidates(parcels, as_of_year=_AS_OF_YEAR)
    ranked_signal_off = rank_candidates(parcels, enable_siding_signal=False, as_of_year=_AS_OF_YEAR)
    assert all(lead.siding_component is not None for lead in ranked_default)  # on by default
    assert all(lead.siding_component is None for lead in ranked_signal_off)
    assert [lead.score for lead in ranked_default] != [lead.score for lead in ranked_signal_off]


def test_siding_age_score_ignores_permit_data_available() -> None:
    # siding_age_score is the pure PROXY function -- it always runs the
    # proxy logic regardless of permit_data_available; dispatch between
    # real and proxy modes is siding_score()'s job alone (see its own
    # docstring). Calling siding_age_score directly on a permit-tracked
    # parcel still returns the proxy's real computed value, not None.
    with_permit_flag = siding_age_score({"exterior_wall_1": "Vinyl Siding", "year_built": 1920, "permit_data_available": True})
    without_permit_flag = siding_age_score({"exterior_wall_1": "Vinyl Siding", "year_built": 1920})
    assert with_permit_flag == without_permit_flag
    assert with_permit_flag is not None


def test_real_siding_age_score_none_when_source_has_no_permit_visibility() -> None:
    assert real_siding_age_score({"permit_data_available": False}) is None
    assert real_siding_age_score({}) is None


def test_real_siding_age_score_neutral_when_material_or_year_built_missing() -> None:
    assert real_siding_age_score({"permit_data_available": True}) == 0.5
    assert real_siding_age_score({"permit_data_available": True, "exterior_wall_1": "Clapboards"}) == 0.5


def test_real_siding_age_score_zero_right_after_a_confirmed_permit() -> None:
    score = real_siding_age_score(
        {
            "permit_data_available": True,
            "exterior_wall_1": "Clapboards",
            "year_built": 1950,
            "most_recent_exterior_permit_date": date(_AS_OF_YEAR, 3, 1),
        },
        as_of_year=_AS_OF_YEAR,
    )
    assert score == 0.0


def test_real_siding_age_score_falls_back_to_year_built_when_no_permit_on_file() -> None:
    # No exterior-relevant permit -> effective redo year is year_built
    # itself (presumed never redone), same fallback direction the proxy
    # uses everywhere.
    old_house = real_siding_age_score(
        {"permit_data_available": True, "exterior_wall_1": "Clapboards", "year_built": 1900, "exterior_permit_count": 0},
        as_of_year=_AS_OF_YEAR,
    )
    new_house = real_siding_age_score(
        {"permit_data_available": True, "exterior_wall_1": "Clapboards", "year_built": 2020, "exterior_permit_count": 0},
        as_of_year=_AS_OF_YEAR,
    )
    assert old_house > new_house
    assert old_house > 0.9
    assert new_house < 0.5


def test_real_siding_age_score_vinyl_saturates_faster_than_durable_material() -> None:
    # Same effective redo year (no permit, fall back to year_built), same
    # years-since-redone -- vinyl's shorter real-world lifespan means it
    # should score HIGHER (more overdue) than a durable material at the
    # identical age.
    year_built = _AS_OF_YEAR - 25
    vinyl = real_siding_age_score(
        {"permit_data_available": True, "exterior_wall_1": "Vinyl Siding", "year_built": year_built},
        as_of_year=_AS_OF_YEAR,
    )
    durable = real_siding_age_score(
        {"permit_data_available": True, "exterior_wall_1": "Wood Shingle", "year_built": year_built},
        as_of_year=_AS_OF_YEAR,
    )
    assert vinyl > durable


def test_real_siding_age_score_never_exceeds_bounds() -> None:
    ancient = real_siding_age_score(
        {"permit_data_available": True, "exterior_wall_1": "Vinyl Siding", "year_built": 1700},
        as_of_year=_AS_OF_YEAR,
    )
    assert 0.0 <= ancient <= 1.0


def test_siding_score_dispatches_to_real_mode_when_permit_data_available() -> None:
    real_mode_parcel = {
        "permit_data_available": True,
        "exterior_wall_1": "Vinyl Siding",
        "year_built": 1950,
        "most_recent_exterior_permit_date": date(_AS_OF_YEAR, 1, 1),
    }
    assert siding_score(real_mode_parcel, as_of_year=_AS_OF_YEAR) == real_siding_age_score(real_mode_parcel, as_of_year=_AS_OF_YEAR)


def test_siding_score_dispatches_to_proxy_mode_when_no_permit_visibility() -> None:
    proxy_parcel = {"exterior_wall_1": "Wood Shingle", "year_built": 1900}
    assert siding_score(proxy_parcel, as_of_year=_AS_OF_YEAR) == siding_age_score(proxy_parcel)


def test_score_property_recent_exterior_permit_lowers_score_vs_never_redone() -> None:
    base_parcel = {
        "parcel_id": "1",
        "town": "Killingly",
        "address": "1 Main St",
        "year_built": 1950,
        "living_area_sqft": 1800,
        "pct_tree_canopy_nearby": 35.0,
        "exterior_wall_1": "Vinyl Siding",
        "permit_data_available": True,
    }
    recently_addressed = score_property(
        {**base_parcel, "most_recent_exterior_permit_date": date(_AS_OF_YEAR, 1, 1)},
        as_of_year=_AS_OF_YEAR,
    )
    never_addressed = score_property({**base_parcel, "exterior_permit_count": 0}, as_of_year=_AS_OF_YEAR)
    assert recently_addressed is not None and never_addressed is not None
    assert recently_addressed.siding_component == 0.0
    assert never_addressed.siding_component is not None and never_addressed.siding_component > 0.0
    assert recently_addressed.score < never_addressed.score


def test_score_property_real_mode_siding_reason_mentions_permit() -> None:
    parcel = {
        "parcel_id": "1",
        "town": "Killingly",
        "address": "1 Main St",
        "year_built": 1950,
        "living_area_sqft": 1800,
        "exterior_wall_1": "Clapboards",
        "permit_data_available": True,
        "most_recent_exterior_permit_date": date(2020, 5, 1),
        "most_recent_exterior_permit_type": "Roofing",
    }
    lead = score_property(parcel, as_of_year=_AS_OF_YEAR)
    assert lead is not None
    assert "Siding: Clapboards" in lead.reasons[-1]
    assert "Roofing" in lead.reasons[-1]
    assert "2020-05-01" in lead.reasons[-1]
