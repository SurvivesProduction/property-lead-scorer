"""The masonry rule: walls that cannot be re-sided score 0 on siding and are flagged roof-only. Invented parcels."""
from __future__ import annotations

import pytest

from extscorer.digest.copy import describe_lead
from extscorer.normalize.walls import is_masonry_exterior, is_masonry_text
from extscorer.scoring.basic import masonry_roof_only, rank_candidates, score_property, siding_score

_AS_OF = 2026


def _house(wall="Brick", **kw):
    base = {"parcel_id": "1", "town": "T", "address": "1 TEST RD", "year_built": 1850, "living_area_sqft": 2000,
            "exterior_wall_1": wall, "exterior_wall_2": None, "permit_data_available": False, "permit_history": [],
            "pct_tree_canopy_nearby": 35.0, "nearest_storm_event_date": None}
    base.update(kw)
    return base


@pytest.mark.parametrize("wall", ["Brick", "Brick/Masonry", "Brick Veneer", "Concr/Cinder", "Stone/Masonry", "Stucco/Masonry",
                                  "Stone", "Stucco", "Stucco on Wood", "Stucco on Mas.", "Concrete", "Stone Veneer", "Concrete/mas",
                                  "Masonry", "Acrylic Stucco", "Reinforced Concrete", "Brick/Masonry/Concrete"])
def test_masonry_walls_are_recognised(wall) -> None:
    assert is_masonry_text(wall)


@pytest.mark.parametrize("wall", ["Wood Frame/Masonry", "Cement Board", "Fbr cement", "Vinyl Siding", "Clapboard", "Wood Frame",
                                  "Brick/Masonry/Vinyl Siding", "Vinyl Siding/Brick Veneer", "Aluminum Siding/Brick Veneer",
                                  "Vinyl Siding/Stucco", "Clapboards/Stone/Masonry", "Clapboards/Stone Veneer", "Log Cabin/Stone Veneer",
                                  "Pre-Fab Wood/Stone Veneer", "Pre-Finish Metal/Brick", "Concrete/Pre-Finish Metal",
                                  "Clapboards/Cement Board", "", None])
def test_sidable_or_mixed_walls_are_not_masonry(wall) -> None:
    assert not is_masonry_text(wall)


def test_a_sidable_second_wall_keeps_the_normal_score() -> None:
    assert is_masonry_exterior(_house("Brick", exterior_wall_2="Brick Veneer"))
    assert not is_masonry_exterior(_house("Brick", exterior_wall_2="Clapboard"))
    assert not is_masonry_exterior(_house("Brick", exterior_wall_2="Vinyl Siding"))


def test_the_switch_is_off_by_default() -> None:
    normal = score_property(_house(), as_of_year=_AS_OF)
    assert normal.siding_component > 0.5 and normal.roof_only_candidate is False


def test_a_masonry_house_gets_zero_siding_and_the_flag_when_the_switch_is_on() -> None:
    lead = score_property(_house(), as_of_year=_AS_OF, masonry_siding_zero=True)
    assert lead.siding_component == 0.0 and lead.roof_only_candidate is True
    assert lead.score < score_property(_house(), as_of_year=_AS_OF).score
    assert any("roof-only candidate" in r for r in lead.reasons)


def test_a_wood_house_is_unchanged_by_the_switch() -> None:
    a = score_property(_house("Clapboard"), as_of_year=_AS_OF)
    b = score_property(_house("Clapboard"), as_of_year=_AS_OF, masonry_siding_zero=True)
    assert (a.score, a.siding_component) == (b.score, b.siding_component) and b.roof_only_candidate is False


def test_a_real_siding_permit_on_a_masonry_house_wins_over_the_wall_text() -> None:
    permits = [{"permit_number": "1", "permit_type": "Building", "date_opened": "05/01/2019", "reason": "Replace siding on house"}]
    house = _house("Brick", permit_data_available=True, permit_history=permits, exterior_permit_count=1)
    assert masonry_roof_only(house) is False
    lead = score_property(house, as_of_year=_AS_OF, permit_class_split=True, masonry_siding_zero=True)
    assert lead.roof_only_candidate is False and lead.siding_component == siding_score(house, _AS_OF, True)


def test_rank_candidates_passes_the_switch_through() -> None:
    leads = rank_candidates([_house("Brick", parcel_id="a"), _house("Clapboard", parcel_id="b")], as_of_year=_AS_OF, masonry_siding_zero=True)
    by_id = {l.parcel_id: l for l in leads}
    assert by_id["a"].roof_only_candidate and not by_id["b"].roof_only_candidate
    assert by_id["b"].score > by_id["a"].score


def test_the_digest_says_roof_only_for_a_masonry_house_only_when_the_switch_is_on() -> None:
    on = describe_lead(_house("Brick"), _AS_OF, masonry_siding_zero=True)
    off = describe_lead(_house("Brick"), _AS_OF)
    assert "roof job only" in on and "roof job only" not in off
    assert "roof job only" not in describe_lead(_house("Clapboard"), _AS_OF, masonry_siding_zero=True)
