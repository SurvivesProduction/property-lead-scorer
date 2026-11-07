"""The 1900 placeholder rule: effective-year fallback, else neutral age. Behind a switch (off by default). Invented parcels."""
from __future__ import annotations

import pytest

from extscorer.digest.copy import describe_lead
from extscorer.normalize.year_built import ACTUAL, EFFECTIVE_FALLBACK, UNKNOWN, renovation_suggested, resolve_year_built
from extscorer.scoring.basic import PLACEHOLDER_NEUTRAL_AGE_SCORE, property_age_score, rank_candidates, score_property

_AS_OF = 2026


def _house(year=1900, effective=None, **kw):
    base = {"parcel_id": "1", "town": "T", "address": "1 TEST RD", "year_built": year, "effective_year_built": effective,
            "living_area_sqft": 2000, "exterior_wall_1": "Clapboard", "permit_data_available": False, "permit_history": [],
            "pct_tree_canopy_nearby": 35.0, "nearest_storm_event_date": None}
    base.update(kw)
    return base


@pytest.mark.parametrize("parcel,switch,expected", [
    (_house(1900, 1985), True, (1985, EFFECTIVE_FALLBACK)),
    (_house(1900, None), True, (None, UNKNOWN)),
    (_house(1900, 1900), True, (None, UNKNOWN)),          # the effective year is itself the placeholder
    (_house(1900, 0), True, (None, UNKNOWN)),
    (_house(1850, 1985), True, (1850, ACTUAL)),           # circa years are kept as they are
    (_house(1950, None), True, (1950, ACTUAL)),
    (_house(1900, 1985), False, (1900, ACTUAL)),          # switch off: nothing changes
    (_house(None), True, (None, ACTUAL)),
])
def test_resolve_year_built(parcel, switch, expected) -> None:
    assert resolve_year_built(parcel, switch, _AS_OF) == expected


def test_the_switch_is_off_by_default() -> None:
    lead = score_property(_house(1900, 1985), as_of_year=_AS_OF)
    assert lead.year_built_source == "actual" and lead.property_component == property_age_score(_house(1900, 1985), as_of_year=_AS_OF)


def test_a_placeholder_with_an_effective_year_is_scored_from_the_effective_year() -> None:
    lead = score_property(_house(1900, 1985), as_of_year=_AS_OF, year_built_placeholder_fallback=True)
    assert lead.year_built_source == EFFECTIVE_FALLBACK
    assert lead.property_component == pytest.approx(property_age_score({"year_built": 1985}, as_of_year=_AS_OF))
    assert lead.year_built == 1900  # the recorded year is reported unchanged
    assert any("effective year 1985" in r for r in lead.reasons)


def test_a_placeholder_with_no_effective_year_scores_a_neutral_age_and_stays_qualified() -> None:
    lead = score_property(_house(1900, None), as_of_year=_AS_OF, year_built_placeholder_fallback=True)
    assert lead is not None and lead.year_built_source == UNKNOWN
    assert lead.property_component == PLACEHOLDER_NEUTRAL_AGE_SCORE == 0.5
    assert lead.siding_component == 0.5  # the siding proxy has no year to work from: neutral too
    assert any("placeholder" in r and "neutral" in r for r in lead.reasons)


def test_a_fallback_never_disqualifies_an_effective_year_that_is_too_recent_gives_a_neutral_age() -> None:
    house = _house(1900, 2015)  # effective year 2015 would make it 11 years old
    lead = score_property(house, as_of_year=_AS_OF, year_built_placeholder_fallback=True)
    assert lead is not None and lead.year_built_source == UNKNOWN
    assert lead.property_component == PLACEHOLDER_NEUTRAL_AGE_SCORE and lead.siding_component == 0.5
    assert any("effective year 2015" in r and "suggests renovation" in r for r in lead.reasons)
    assert renovation_suggested(house, _AS_OF) is True
    assert score_property(house, as_of_year=_AS_OF) is not None  # switch off: still the recorded 1900


def test_the_age_guard_boundary_is_the_scoring_threshold() -> None:
    assert resolve_year_built(_house(1900, 2006), True, 2026, 20) == (2006, EFFECTIVE_FALLBACK)   # exactly 20 years: usable
    assert resolve_year_built(_house(1900, 2007), True, 2026, 20) == (None, UNKNOWN)               # 19 years: renovation guard
    assert resolve_year_built(_house(1900, 2007), True, 2026, 15) == (2007, EFFECTIVE_FALLBACK)    # a different threshold is respected
    assert renovation_suggested(_house(1900, None), 2026) is False and renovation_suggested(_house(1900, 1900), 2026) is False
    assert renovation_suggested(_house(1850, 2015), 2026) is False


def test_the_fallback_lowers_a_placeholder_house_and_leaves_other_houses_alone() -> None:
    on = score_property(_house(1900, 1975), as_of_year=_AS_OF, year_built_placeholder_fallback=True)
    off = score_property(_house(1900, 1975), as_of_year=_AS_OF)
    assert on.score < off.score
    normal_on = score_property(_house(1850, 1985), as_of_year=_AS_OF, year_built_placeholder_fallback=True)
    normal_off = score_property(_house(1850, 1985), as_of_year=_AS_OF)
    assert (normal_on.score, normal_on.year_built_source) == (normal_off.score, "actual")


def test_storm_still_uses_the_recorded_parcel() -> None:
    house = _house(1900, 2000, nearest_storm_event_date=__import__("datetime").date(1999, 6, 1))
    on = score_property(house, as_of_year=_AS_OF, year_built_placeholder_fallback=True)
    off = score_property(house, as_of_year=_AS_OF)
    assert on.storm_component == off.storm_component  # a 1999 storm is not discarded because the effective year is 2000


def test_rank_candidates_passes_the_switch_and_the_digest_words_the_clause() -> None:
    leads = rank_candidates([_house(1900, 1985)], as_of_year=_AS_OF, year_built_placeholder_fallback=True)
    assert leads[0].year_built_source == EFFECTIVE_FALLBACK
    text = describe_lead(_house(1900, 1985), _AS_OF, year_built_placeholder_fallback=True)
    assert "placeholder" in text and "effective year is 1985" in text and "built in 1900 (126 years old)" not in text.lower()
    unknown = describe_lead(_house(1900, None), _AS_OF, year_built_placeholder_fallback=True)
    assert "real age is unknown" in unknown
    assert "built in 1900 (126 years old)" in describe_lead(_house(1900, 1985), _AS_OF).lower()  # switch off: unchanged
