from datetime import date

import pytest
from pydantic import ValidationError

from extscorer.normalize.schema import ParcelLeadRecord, StormEventRecord


def test_parcel_lead_record_accepts_full_valid_record() -> None:
    record = ParcelLeadRecord(
        client_id="demo",
        town="Canterbury",
        county="Windham",
        address="123 Example Rd",
        parcel_id="0042",
        source_url="https://gis.vgsi.com/canterburyct/Parcel.aspx?pid=42",
        year_built=1978,
        living_area_sqft=1850,
        roof_cover_material="Asphalt Shingle",
        latitude=41.7,
        longitude=-71.97,
        pct_tree_canopy_nearby=32.5,
        canopy_data_year=2021,
        canopy_source="noaa_ccap_2021",
        nearest_storm_event_date=date(2023, 7, 14),
        storm_event_summary="Hail near Putnam, 1.00 in",
        lead_score=0.71,
        score_property_component=0.8,
        score_canopy_component=0.4,
        score_storm_component=0.6,
        raw_data={"pid": "42"},
    )
    assert record.town == "Canterbury"
    assert record.needs_review is False
    assert record.review_reason is None


def test_parcel_lead_record_allows_optional_fields_to_be_omitted() -> None:
    record = ParcelLeadRecord(
        client_id="demo",
        town="Canterbury",
        county="Windham",
        address="123 Example Rd",
        parcel_id="0042",
    )
    assert record.year_built is None
    assert record.pct_tree_canopy_nearby is None
    assert record.lead_score is None
    assert record.raw_data == {}


def test_parcel_lead_record_requires_core_fields() -> None:
    with pytest.raises(ValidationError):
        ParcelLeadRecord(client_id="demo", town="Canterbury")


def test_parcel_lead_record_accepts_needs_review_flag_with_reason() -> None:
    record = ParcelLeadRecord(
        client_id="demo",
        town="Canterbury",
        county="Windham",
        address="123 Example Rd",
        parcel_id="0042",
        needs_review=True,
        review_reason="year_built unparseable on card",
    )
    assert record.needs_review is True
    assert record.review_reason == "year_built unparseable on card"


def test_storm_event_record_accepts_full_valid_record() -> None:
    record = StormEventRecord(
        event_id="10001",
        county="Windham",
        state="CT",
        event_date=date(2023, 7, 14),
        event_type="Hail",
        magnitude="1.00 in",
        narrative="Quarter-size hail reported near Putnam.",
        property_damage_estimate=5000.0,
        raw_data={"EVENT_ID": "10001"},
    )
    assert record.source == "noaa_ncei"
    assert record.magnitude == "1.00 in"


def test_storm_event_record_requires_core_fields() -> None:
    with pytest.raises(ValidationError):
        StormEventRecord(county="Windham", state="CT")
