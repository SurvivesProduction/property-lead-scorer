"""Wall vocabulary pass 2 (2026-11-11): Al/Vinyl, wood/fiber-cement shorthand, asphalt, quality grades as unknown."""
from __future__ import annotations

import math
from datetime import date

import pytest

from extscorer.digest.copy import _describe_siding
from extscorer.normalize.materials import FAMILY_DURABLE, wall_material_families
from extscorer.normalize.permits import SIDING, dated_permits_by_class, is_document_scan, real_permits, summarize_permit_history, tag_document_scans
from extscorer.scoring.basic import (
    DEFAULT_REAL_SIDING_FIBER_CEMENT_DECAY_YEARS,
    DEFAULT_SIDING_FIBER_CEMENT_SCORE,
    MATERIAL_ALUM_OR_VINYL,
    MATERIAL_FIBER_CEMENT,
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
    ["PreFab Wd/T111", "Texture 1-11", "Vertical", "Vertical Siding",
     "Asphalt"],
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


_FIBER_CEMENT = ["Cement Board", "Fbr cement", "Fibr/cem Board", "Hardy Plank", "Hardy plank", "Hardi or Comp", "Cmnt BD Siding",
                 "Fiberboard cem", " cement  board ", "Hardie Plank"]


@pytest.mark.parametrize("label", _FIBER_CEMENT)
def test_fiber_cement_is_its_own_family(label) -> None:
    assert _classify_wall_material(label) == MATERIAL_FIBER_CEMENT


def test_the_named_fiber_cement_values_are_the_agreed_ones() -> None:
    assert DEFAULT_SIDING_FIBER_CEMENT_SCORE == 0.10
    assert DEFAULT_REAL_SIDING_FIBER_CEMENT_DECAY_YEARS == 40.0


@pytest.mark.parametrize("year", [1900, 1950, 1990, 2005, 2020])
def test_fiber_cement_proxy_is_flat(year) -> None:
    assert siding_age_score(_p("Hardy Plank", year, building_percent_good=20)) == 0.10
    assert siding_age_score(_p("Cement Board", year), fiber_cement_score=0.2) == 0.2


def test_fiber_cement_real_mode_decays_over_40_years() -> None:
    parcel = _p("Cement Board", 1990, permit_data_available=True, permit_history=[], permit_history_since=date(1990, 1, 1))
    got = real_siding_age_score(parcel, as_of_year=2026)
    assert got == pytest.approx(1 - math.exp(-36 / 40))
    assert real_siding_age_score(parcel, as_of_year=2026, fiber_cement_decay_years=20) == pytest.approx(1 - math.exp(-36 / 20))


def test_composites_with_another_material_stay_durable() -> None:
    for label in ("Clapboards/Cement Board", "Board & Batten/Hardie Plank", "Cement Board/Wood Shingles"):
        assert _classify_wall_material(label) == "durable_original"


def test_fiber_cement_is_not_masonry() -> None:
    result = score_property(_p("Cement Board", 1990, permit_data_available=False), as_of_year=2026, masonry_siding_zero=True)
    assert not result.roof_only_candidate


def _scan(reason="Scanned: 138 Preston City Rd Plans.pdf", date_opened="03/11/2025"):
    return {"reason": reason, "date_opened": date_opened, "permit_type": "Miscellaneous", "permit_number": "Misc", "status": "Closed"}


def test_scan_detection_and_tagging() -> None:
    assert is_document_scan(_scan()) and is_document_scan({"reason": "x", "document_scan": True})
    assert not is_document_scan({"reason": "Re-roof 20 sq. See scanned plans"})
    tagged, newly = tag_document_scans([_scan(), {"reason": "Reside house", "date_opened": "05/01/2024"}, _scan()])
    assert newly == 2 and [bool(e.get("document_scan")) for e in tagged] == [True, False, True]
    assert tag_document_scans(tagged)[1] == 0
    assert len(tagged) == 3  # entries are kept


def test_scans_are_not_permits() -> None:
    history = [_scan("Scanned: 12 Main St siding roof.pdf"), {"reason": "Install vinyl siding", "date_opened": "06/01/2023", "permit_type": "Building", "status": "Closed"}]
    assert len(real_permits(history)) == 1
    assert dated_permits_by_class(history)[SIDING] == [date(2023, 6, 1)]
    only_scans = [_scan("Scanned: re-roof siding house wrap.pdf")]
    assert dated_permits_by_class(only_scans) == {SIDING: [], "roof": [], "other_exterior": []}
    assert summarize_permit_history(only_scans)["exterior_permit_count"] == 0
    assert summarize_permit_history(history)["exterior_permit_count"] == 1
