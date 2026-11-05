from __future__ import annotations

from pathlib import Path

import pytest

from extscorer.digest.selection import (
    is_non_residential,
    select_new_leads_for_pipeline,
    select_unsent_leads,
)
from extscorer.normalize.use_class import (
    FARM_FOREST_RESIDENTIAL,
    NON_RESIDENTIAL,
    RESIDENTIAL,
    UNKNOWN,
    USE_CLASSES,
    classify_use_class,
    classify_use_class_with_source,
    normalize_use_text,
)


def _p(raw: dict, **extra) -> dict:
    return {"raw_data": raw, "year_built": 1950, "living_area_sqft": 1800, **extra}


@pytest.mark.parametrize(
    "raw",
    [
        {"State_Use_Description": "Single Fam  MDL-01"},
        {"State_Use_Description": "SFR (NL)  MDL-01"},
        {"State_Use_Description": "Residential"},
        {"State_Use_Description": "Condo"},
        {"State_Use_Description": "APT 4+ UNITS  MDL-94"},
        {"State_Use_Description": "Mobile Hom M02"},
        {"state_use_description": "Res Dwelling"},  # Windham's lower-case Socrata key
        {"property_use": "Apartments"},
        {"style": "Cape Cod"},
        {"style": "Townhouse"},
    ],
)
def test_homes_are_residential(raw: dict) -> None:
    assert classify_use_class(_p(raw)) == RESIDENTIAL


@pytest.mark.parametrize(
    "raw",
    [
        {"State_Use_Description": "STORE/SHOP  MDL-94"},
        {"State_Use_Description": "PVT SCHOOL  MDL-01"},
        {"State_Use_Description": "CHURCH  MDL-96"},
        {"State_Use_Description": "FACTORY"},
        {"State_Use_Description": "Mun Library"},
        {"State_Use_Description": "MH PARK  MDL-01"},
        {"State_Use_Description": "OFF CONDO  MDL-06"},
        {"property_use": "Industrial"},
        {"property_use": "Church/NonProfit"},
        {"style": "Warehouse"},
        {"style": "Clubs/Lodges"},
    ],
)
def test_institutional_and_commercial_parcels_are_non_residential(raw: dict) -> None:
    assert classify_use_class(_p(raw)) == NON_RESIDENTIAL


def test_use_assessment_with_a_dwelling_stays_eligible_as_farm_forest_residential() -> None:
    farmhouse = _p({"State_Use_Description": "Use Assessment"}, year_built=1725, living_area_sqft=3133)
    assert classify_use_class(farmhouse) == FARM_FOREST_RESIDENTIAL


def test_use_assessment_land_without_a_building_is_unknown_not_residential() -> None:
    land = {"raw_data": {"State_Use_Description": "Use Assessment"}, "year_built": None, "living_area_sqft": None}
    assert classify_use_class(land) == UNKNOWN


@pytest.mark.parametrize(
    "raw",
    [
        {"State_Use_Description": "Church - Res"},  # a church-owned residence
        {"State_Use_Description": "Residential Business"},
        {"State_Use_Description": "RES / COMM"},
        {"property_use": "Vacant Land"},
        {"property_use": "Elderly"},
        {"style": "Camp"},
        {"style": "Comm/Apt"},
    ],
)
def test_mixed_or_ambiguous_parcels_are_unknown_and_so_stay_eligible(raw: dict) -> None:
    assert classify_use_class(_p(raw)) == UNKNOWN


def test_no_evidence_is_unknown() -> None:
    assert classify_use_class_with_source({"raw_data": {}}) == (UNKNOWN, "none")
    assert classify_use_class_with_source({"raw_data": None}) == (UNKNOWN, "none")


def test_state_description_outranks_the_source_description() -> None:
    # A promoted row carries both; the state CAMA description is the first tier.
    parcel = _p({"State_Use_Description": "Single Family", "style": "Warehouse"})
    assert classify_use_class_with_source(parcel) == (RESIDENTIAL, "state_cama")


def test_sources_are_reported_per_tier() -> None:
    assert classify_use_class_with_source(_p({"property_use": "Office"}))[1] == "prc_property_use"
    assert classify_use_class_with_source(_p({"style": "Ranch"}))[1] == "vgsi_style"


def test_regex_is_only_the_last_resort_for_an_unseen_spelling() -> None:
    assert classify_use_class_with_source(_p({"State_Use_Description": "PVT HOSPITAL"})) == (NON_RESIDENTIAL, "regex")
    assert classify_use_class_with_source(_p({"State_Use_Description": "SFR LAKEFRONT"})) == (RESIDENTIAL, "regex")
    # a table hit never reaches the regex, even if the text would also match a non-residential word
    assert classify_use_class_with_source(_p({"State_Use_Description": "Mobile WF"})) == (RESIDENTIAL, "state_cama")


def test_normalisation_drops_model_suffixes_and_whitespace() -> None:
    assert normalize_use_text("Single Fam  MDL-01") == "single fam"
    assert normalize_use_text("Hsng Auth MDL 94") == "hsng auth"
    assert normalize_use_text("  Mobile Hom M02 ") == "mobile hom"
    assert normalize_use_text(None) == ""


def test_migration_check_constraint_lists_exactly_the_python_classes() -> None:
    sql = (Path(__file__).resolve().parent.parent / "src" / "extscorer" / "migrations" / "012_add_use_class.sql").read_text()
    constraint = sql.split("check (use_class in (")[1].split("))")[0]
    assert {v.strip().strip("'") for v in constraint.split(",")} == set(USE_CLASSES)
    assert "add column if not exists use_class" in sql  # additive and idempotent


# --- digest selection ---

def _ranked(*parcels: dict):
    class Lead:  # minimal stand-in for LeadScore
        pass
    return [(Lead(), p) for p in parcels]


def _row(pid: str, use_class: str | None) -> dict:
    return {"id": pid, "town": "Brooklyn", "parcel_id": pid, "use_class": use_class, "enrichment_status": "scraped"}


def test_is_non_residential_only_for_the_explicit_class() -> None:
    assert is_non_residential({"use_class": "non_residential"}) is True
    for eligible in (None, "unknown", "residential", "farm_forest_residential"):
        assert is_non_residential({"use_class": eligible}) is False
    assert is_non_residential({}) is False


def test_both_digest_selectors_skip_non_residential_but_keep_unclassified_and_unknown() -> None:
    parcels = [_row("a", "non_residential"), _row("b", None), _row("c", "unknown"), _row("d", "farm_forest_residential")]
    ranked = _ranked(*parcels)
    picked = select_unsent_leads(ranked, set(), 10)
    assert [p["parcel_id"] for _, p in picked] == ["b", "c", "d"]
    picked = select_new_leads_for_pipeline(ranked, set(), 10)
    assert [p["parcel_id"] for _, p in picked] == ["b", "c", "d"]
