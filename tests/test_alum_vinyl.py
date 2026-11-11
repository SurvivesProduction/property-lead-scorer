"""The aluminum_or_vinyl bucket (2026-11-11): matched as a whole label, scored as 75% vinyl + 25% aluminum, real-mode decay 22."""
from __future__ import annotations

import math
from datetime import date

import pytest

from extscorer.digest.copy import _describe_siding
from extscorer.scoring.basic import (
    DEFAULT_REAL_SIDING_ALUM_VINYL_DECAY_YEARS,
    DEFAULT_SIDING_ALUM_VINYL_VINYL_WEIGHT,
    _classify_wall_material,
    rank_candidates,
    real_siding_age_score,
    score_property,
    siding_age_score,
    siding_score,
)

_YEARS = (1900, 1950, 1975, 1980, 1985, 1990, 1995, 2000, 2003, 2005, 2015)


def _p(wall, year=1960, **kw):
    return {"exterior_wall_1": wall, "year_built": year, **kw}


def test_the_named_values_are_the_agreed_ones() -> None:
    assert DEFAULT_SIDING_ALUM_VINYL_VINYL_WEIGHT == 0.75
    assert DEFAULT_REAL_SIDING_ALUM_VINYL_DECAY_YEARS == 22.0


def test_the_label_is_its_own_bucket_matched_as_a_whole_value() -> None:
    assert _classify_wall_material("Alum/Vinyl Siding") == "aluminum_or_vinyl"
    assert _classify_wall_material("  alum/vinyl   siding ") == "aluminum_or_vinyl"
    assert _classify_wall_material("Vinyl Siding") == "vinyl"
    assert _classify_wall_material("Aluminum Siding") == "durable_original"
    assert _classify_wall_material("Aluminum Sidng") == "durable_original"
    assert _classify_wall_material("Alum/Vinyl Siding/Clapboards") == "vinyl"  # not the whole label: old behaviour
    assert _classify_wall_material("Wood Frame") == "durable_original"


@pytest.mark.parametrize("year", _YEARS)
def test_proxy_is_75_percent_vinyl_and_25_percent_aluminum(year) -> None:
    vinyl = siding_age_score(_p("Vinyl Siding", year))
    durable = siding_age_score(_p("Aluminum Siding", year))
    assert siding_age_score(_p("Alum/Vinyl Siding", year)) == pytest.approx(0.75 * vinyl + 0.25 * durable)


def test_the_blend_sits_between_the_curves_and_nearer_vinyl() -> None:
    for year in _YEARS:
        v, d = siding_age_score(_p("Vinyl Siding", year)), siding_age_score(_p("Aluminum Siding", year))
        got = siding_age_score(_p("Alum/Vinyl Siding", year))
        assert min(v, d) - 1e-9 <= got <= max(v, d) + 1e-9
        assert abs(got - v) <= abs(got - d) + 1e-9


def test_the_weight_is_a_parameter_and_one_means_plain_vinyl_zero_plain_aluminum() -> None:
    for year in _YEARS:
        assert siding_age_score(_p("Alum/Vinyl Siding", year), alum_vinyl_vinyl_weight=1.0) == pytest.approx(siding_age_score(_p("Vinyl Siding", year)))
        assert siding_age_score(_p("Alum/Vinyl Siding", year), alum_vinyl_vinyl_weight=0.0) == pytest.approx(siding_age_score(_p("Aluminum Siding", year)))


def test_percent_good_still_nudges_the_blend() -> None:
    assert siding_age_score(_p("Alum/Vinyl Siding", 1985, building_percent_good=0)) > siding_age_score(_p("Alum/Vinyl Siding", 1985))


def _real(wall, **kw):
    return {"permit_data_available": True, "exterior_wall_1": wall, "year_built": 1960, "permit_history": [],
            "most_recent_exterior_permit_date": date(2006, 1, 1), **kw}


def test_real_mode_decays_at_22_years_between_vinyl_and_durable() -> None:
    got = real_siding_age_score(_real("Alum/Vinyl Siding"), as_of_year=2026)
    assert got == pytest.approx(1 - math.exp(-20 / 22))
    assert real_siding_age_score(_real("Vinyl Siding"), as_of_year=2026) > got > real_siding_age_score(_real("Aluminum Siding"), as_of_year=2026)
    assert real_siding_age_score(_real("Alum/Vinyl Siding"), as_of_year=2026, alum_vinyl_decay_years=30.0) == pytest.approx(1 - math.exp(-20 / 30))


def test_the_tunables_reach_score_property_and_rank_candidates() -> None:
    base = {"parcel_id": "1", "town": "T", "address": "1 A ST", "living_area_sqft": 1500, **_p("Alum/Vinyl Siding", 1985)}
    assert siding_score(base, alum_vinyl_vinyl_weight=1.0) == pytest.approx(siding_age_score(_p("Vinyl Siding", 1985)))
    a = score_property(base, as_of_year=2026).siding_component
    b = score_property(base, as_of_year=2026, alum_vinyl_vinyl_weight=0.0).siding_component
    assert a != b and b == pytest.approx(siding_age_score(_p("Aluminum Siding", 1985)))
    (lead,) = rank_candidates([base], as_of_year=2026, alum_vinyl_vinyl_weight=0.0)
    assert lead.siding_component == pytest.approx(b)


def test_the_no_siding_permit_fallback_uses_the_same_weight() -> None:
    parcel = _real("Alum/Vinyl Siding", most_recent_exterior_permit_date=None, permit_history_since=None)
    assert real_siding_age_score(parcel, as_of_year=2026, permit_class_split=True) == pytest.approx(siding_age_score(parcel))
    assert real_siding_age_score(parcel, as_of_year=2026, permit_class_split=True, alum_vinyl_vinyl_weight=0.0) == pytest.approx(
        siding_age_score(parcel, alum_vinyl_vinyl_weight=0.0)
    )


def test_wood_frame_scores_exactly_as_before() -> None:
    assert siding_age_score(_p("Wood Frame", 1900)) == pytest.approx(0.85 + 0.15 * (1 - math.exp(-90 / 25)))


def test_the_digest_says_aluminum_or_vinyl_not_the_abbreviation() -> None:
    text = _describe_siding(_p("Alum/Vinyl Siding", 1985), 2026)
    assert "aluminum-or-vinyl siding" in text and "alum/vinyl" not in text.lower()
    assert "vinyl siding looks original" in _describe_siding(_p("Vinyl Siding", 1985), 2026) or "vinyl siding" in _describe_siding(_p("Vinyl Siding", 1985), 2026)
