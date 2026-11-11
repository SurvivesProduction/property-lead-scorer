"""Wall vocabulary pass 2 (2026-11-11): Al/Vinyl, wood/fiber-cement shorthand, asphalt, quality grades as unknown."""
from __future__ import annotations

import pytest

from extscorer.digest.copy import _describe_siding
from extscorer.normalize.materials import FAMILY_DURABLE, wall_material_families
from extscorer.scoring.basic import (
    MATERIAL_ALUM_OR_VINYL,
    _classify_wall_material,
    is_quality_grade_wall,
    real_siding_age_score,
    score_property,
    siding_age_score,
    usable_wall_text,
)


def _p(wall, year=1960, **kw):
    return {"exterior_wall_1": wall, "year_built": year, **kw}


@pytest.mark.parametrize("label", ["Al/Vinyl", "al/vinyl", " AL/VINYL ", "Alum/Vinyl Siding"])
def test_al_vinyl_labels_are_the_blend(label) -> None:
    assert _classify_wall_material(label) == MATERIAL_ALUM_OR_VINYL
    assert siding_age_score(_p(label, 1990)) == siding_age_score(_p("Alum/Vinyl Siding", 1990))


@pytest.mark.parametrize("label", ["Vinyl Siding/Pre-Finish Metal", "Aluminum Siding/Clapboards", "Shaker Vinyl", "Vinyl"])
def test_other_combined_spellings_are_not_the_blend(label) -> None:
    assert _classify_wall_material(label) != MATERIAL_ALUM_OR_VINYL


@pytest.mark.parametrize(
    "label",
    ["PreFab Wd/T111", "Texture 1-11", "Vertical", "Vertical Siding", "Hardi or Comp", "Fiberboard cem", "Cmnt BD Siding",
     "Asphalt", "Cement Board"],
)
def test_mapped_to_durable(label) -> None:
    assert _classify_wall_material(label) == "durable_original"
    assert siding_age_score(_p(label, 1960)) == siding_age_score(_p("Clapboard", 1960))
    assert FAMILY_DURABLE in wall_material_families(label)


def test_vertical_is_a_whole_value_not_a_substring() -> None:
    assert _classify_wall_material("Vertical Blinds") == "other"


def test_comp_wall_board_stays_unknown() -> None:
    assert _classify_wall_material("Comp./Wall Brd") == "other"
    assert siding_age_score(_p("Comp./Wall Brd")) == 0.5


@pytest.mark.parametrize("label", ["Average", "Minimum", "Above Average", "Below Average", " average "])
def test_quality_grades_are_unknown_like_blank(label) -> None:
    assert is_quality_grade_wall(label) and usable_wall_text(label) is None
    assert _classify_wall_material(label) is None
    assert wall_material_families(label) == []
    for year in (1920, 1960, 1995):
        assert siding_age_score(_p(label, year)) == siding_age_score(_p(None, year)) == 0.5
    parcel = _p(label, 1960, permit_data_available=True, permit_history=[], permit_history_since=None)
    assert real_siding_age_score(parcel) == real_siding_age_score({**parcel, "exterior_wall_1": None}) == 0.5
    assert _describe_siding(parcel, 2026) is None


def test_a_real_material_containing_a_grade_word_is_still_a_material() -> None:
    assert _classify_wall_material("Avrge/Masonite") == "durable_original"


def test_reasons_do_not_echo_a_quality_grade() -> None:
    result = score_property(_p("Average", 1950, permit_data_available=False), as_of_year=2026)
    assert not any("Average" in reason for reason in result.reasons)
