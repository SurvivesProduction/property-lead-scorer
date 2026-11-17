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


def test_comp_wall_board_is_a_replacement_lead_not_unknown() -> None:
    assert _classify_wall_material("Comp./Wall Brd") == "replacement_lead"
    assert siding_age_score(_p("Comp./Wall Brd")) != 0.5


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
    assert _classify_wall_material("Avrge/Masonite") == "replacement_lead"


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


@pytest.mark.parametrize("label", _FIBER_CEMENT)
def test_fiber_cement_has_its_own_board_filter_family(label) -> None:
    from extscorer.normalize.materials import FAMILY_FIBER_CEMENT

    assert wall_material_families(label) == [FAMILY_FIBER_CEMENT]


def test_composite_fiber_cement_label_keeps_the_durable_filter_family() -> None:
    assert wall_material_families("Clapboards/Cement Board") == [FAMILY_DURABLE]


# --- vocabulary pass 3 (2026-11-16): Precast Panel is masonry, Enameled Steel is metal; composition board and the rest stay unmapped ---


def test_precast_panel_is_masonry_so_roof_only_and_no_siding_score() -> None:
    from extscorer.normalize.walls import is_masonry_text

    assert is_masonry_text("Precast Panel") and is_masonry_text("Precast Concrete")
    assert wall_material_families("Precast Panel") == [FAMILY_DURABLE]


def test_enameled_steel_is_a_durable_metal_wall() -> None:
    assert _classify_wall_material("Enameled Steel") == "durable_original"
    assert wall_material_families("Enameled Steel") == [FAMILY_DURABLE]
    assert wall_material_families("Pre-finsh Metl") == [FAMILY_DURABLE]


@pytest.mark.parametrize("raw", ["Single Siding", "Glass/Thermo.", "FLYASH ICON"])
def test_values_held_back_from_the_vocabulary_stay_other(raw) -> None:
    assert _classify_wall_material(raw) == "other"
    assert wall_material_families(raw) == ["other"]


@pytest.mark.parametrize("raw", ["Average", "Minimum", "Above Average", "Below Average"])
def test_quality_grades_stay_unknown(raw) -> None:
    assert usable_wall_text(raw) is None and wall_material_families(raw) == []


# --- composition / hardboard siding is its own replacement-lead family (2026-11-16) -----------------------------

@pytest.mark.parametrize("label", ["Comp./Wall Brd", "Masonite", "Hardboard", "Avrge/Masonite"])
def test_composition_board_is_a_replacement_lead(label):
    from extscorer.normalize.materials import FAMILY_REPLACEMENT_LEAD
    from extscorer.scoring.basic import MATERIAL_REPLACEMENT_LEAD, _classify_wall_material
    assert _classify_wall_material(label) == MATERIAL_REPLACEMENT_LEAD
    assert FAMILY_REPLACEMENT_LEAD in wall_material_families(label)
    assert FAMILY_DURABLE not in wall_material_families(label)


def test_hardi_or_comp_stays_fiber_cement():
    from extscorer.scoring.basic import MATERIAL_FIBER_CEMENT, _classify_wall_material
    assert _classify_wall_material("Hardi or Comp") == MATERIAL_FIBER_CEMENT


def test_replacement_lead_scores_above_durable_and_rises_with_age():
    from extscorer.scoring.basic import siding_age_score
    comp = lambda year: siding_age_score({"exterior_wall_1": "Comp./Wall Brd", "year_built": year})
    wood = lambda year: siding_age_score({"exterior_wall_1": "Wood", "year_built": year})
    assert comp(1960) > comp(1980) > comp(1990) > comp(2005)
    assert comp(1960) > wood(1960) and comp(1990) > wood(1990)
    assert comp(2005) < wood(2005)  # decays faster once newer than the cutoff


def test_replacement_lead_real_mode_decays_faster_than_durable():
    from datetime import date
    from extscorer.scoring.basic import real_siding_age_score

    def parcel(wall, permit=True):
        # permit_class_split=False (the default) reads `most_recent_exterior_permit_date`, so the fixture sets that, not only the history
        return {"exterior_wall_1": wall, "year_built": 1975, "permit_data_available": True,
                "most_recent_exterior_permit_date": date(2006, 5, 1) if permit else None}

    comp, wood = real_siding_age_score(parcel("Comp./Wall Brd"), as_of_year=2026), real_siding_age_score(parcel("Wood"), as_of_year=2026)
    # 20 years since the re-side: 1 - exp(-20 / decay); decay 20 (replacement lead) vs 35 (durable)
    assert comp == pytest.approx(1 - math.exp(-20 / 20)) and wood == pytest.approx(1 - math.exp(-20 / 35)) and comp > wood
    # and the permit is what is being scored: with no permit the same parcels fall back to year_built 1975 (51 years), a different value
    assert real_siding_age_score(parcel("Comp./Wall Brd", permit=False), as_of_year=2026) == pytest.approx(1 - math.exp(-51 / 20))
    assert real_siding_age_score(parcel("Comp./Wall Brd", permit=False), as_of_year=2026) != pytest.approx(comp)
