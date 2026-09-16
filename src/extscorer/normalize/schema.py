"""The normalized output contracts every `LeadDataSource` must produce.

Two schemas, not one -- unlike `oppscanner.normalize.schema.OpportunityRecord`
(Tool 3's single unified shape for both bid and permit postings), this
tool genuinely has two independent output shapes: a per-parcel lead
record (from a town's VGSI scrape) and a storm-event record (from NOAA's
bulk CSV). They don't belong in one schema -- a parcel isn't a kind of
storm event, and vice versa -- so `LeadDataSource.normalize()` is typed
`-> Any` rather than one fixed return type (see `sources/base.py`).
"""
from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ParcelLeadRecord(BaseModel):
    """A normalized residential parcel/exterior-renovation-lead record.

    `parcel_id` is required: like Tool 2's `PropertyRecord.parcel_id`,
    town property-assessor rolls are built around a stable parcel
    identifier (VGSI's own, or the town's), so this schema assumes one
    exists and dedups on it directly, scoped per town (`unique (client_id,
    town, parcel_id)` in the migration) since parcel numbering is only
    guaranteed unique within one town's own assessor roll, not across all
    ten target towns.

    `source_url` is the VGSI card URL when a real, stable one exists --
    only ever populated with a genuine per-parcel link, never a shared
    listing-page URL (see Tool 3's `general_url` precedent for what NOT
    to do here, and Tools 1-3's "only hyperlink where a real stable URL
    exists" rule).

    `pct_tree_canopy_nearby`/`canopy_data_year`/`canopy_source` and
    `nearest_storm_event_date`/`storm_event_summary` are enrichment
    fields computed by a later pass (a zonal-stats buffer join against
    the canopy raster, and a nearest-event lookup against `storm_events`)
    once `latitude`/`longitude` are known via geocoding -- a VGSI
    scrape's own `normalize()` leaves them `None`. This package stays
    generic and doesn't ship that enrichment logic itself; a downstream
    deployment's backfill scripts populate these fields after the fact
    (see property-lead-scorer-full's own README for its real, live
    implementation of both).

    `lead_score`/`score_property_component`/`score_canopy_component`/
    `score_storm_component`/`score_siding_component` are populated by the
    scoring layer (`extscorer.scoring.basic`), not by any
    `LeadDataSource` -- left `None` on a freshly-normalized record
    straight out of a scraper.

    `needs_review`/`review_reason` follow Tool 1/2/3's precedent: a
    source that hits missing/unparseable data on an otherwise-required
    field flags the row for a human instead of silently shipping a
    useless value or dropping it.

    `exterior_wall_1`/`exterior_wall_2`/`building_percent_good` added
    2026-09-10 for the siding-age lead signal. `building_percent_good` is
    VGSI's own condition proxy (its card literally labels it "Building
    Percent Good") -- there's no field on VGSI literally called "Dep %";
    this is the real equivalent (100 - Percent Good is effectively a
    depreciation percent). It's genuinely absent (not just blank) on some
    towns' card templates -- confirmed missing outright on every sampled
    Pomfret card -- so `None` here can mean either "no building" or "this
    town's template doesn't carry the field," not a parse failure.

    `permit_data_available`/`permit_history`/`exterior_permit_count`/
    `most_recent_exterior_permit_date`/`most_recent_exterior_permit_type`/
    `siding_data_source` added 2026-09-15 for the two eQuality Valuation
    Services towns (Killingly, Ashford, `propertyrecordcards.com`) plus
    Woodstock's enrichment backfill from that same source. Unlike
    `exterior_wall_1`'s VGSI proxy, this source exposes REAL per-parcel
    permit history and a direct "Siding:" field -- see
    `extscorer_full.sources.propertyrecordcards` and migration
    `005_add_permit_signal_and_siding_source.sql` for the full reasoning.
    `exterior_wall_1`/`exterior_wall_2` are reused (not duplicated) for a
    propertyrecordcards.com-sourced parcel's Siding value, since it's the
    same underlying concept (current exterior material) as VGSI's field;
    `siding_data_source` records which real source populated it.

    `owner_name`/`owner_mailing_address`/`is_absentee_owner` added
    2026-09-15 (Prompt U) -- both VGSI and propertyrecordcards.com expose
    a real owner-of-record mailing address (VGSI: `#MainContent_
    lblGenOwner`/`#MainContent_lblAddr1`; propertyrecordcards.com: the
    "Owner's Information" table), confirmed live before building this.
    `is_absentee_owner` is computed at normalize time (not scraped) by
    comparing the mailing address against this same record's own
    `address`/`town` -- see each source module's own normalize function
    for the comparison logic; kept as a first-class field here (not
    recomputed later from raw text) so a caller never has to re-parse
    `owner_mailing_address` to answer "is this likely an absentee owner."

    `has_tax_delinquency`/`tax_outstanding_balance` added the same day --
    real per-parcel data from mytaxbill.org (a shared CT municipal tax
    portal covering all 8 target towns, confirmed live, no login needed),
    populated by a separate one-time/periodic enrichment backfill (see
    `property-lead-scorer-full/scripts/backfill_tax_delinquency.py`), the
    same "not scraped by any LeadDataSource, backfilled after the fact"
    treatment `pct_tree_canopy_nearby`/`latitude`/`longitude` already get.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    client_id: str
    town: str
    county: str
    address: str
    parcel_id: str
    source_url: str | None = None
    year_built: int | None = None
    living_area_sqft: int | None = None
    roof_cover_material: str | None = None
    exterior_wall_1: str | None = None
    exterior_wall_2: str | None = None
    building_percent_good: int | None = None
    siding_data_source: str | None = None
    owner_name: str | None = None
    owner_mailing_address: str | None = None
    is_absentee_owner: bool = False
    latitude: float | None = None
    longitude: float | None = None
    pct_tree_canopy_nearby: float | None = None
    canopy_data_year: int | None = None
    canopy_source: str | None = None
    nearest_storm_event_date: date | None = None
    storm_event_summary: str | None = None
    permit_data_available: bool = False
    permit_history: list[dict[str, Any]] = Field(default_factory=list)
    exterior_permit_count: int | None = None
    most_recent_exterior_permit_date: date | None = None
    most_recent_exterior_permit_type: str | None = None
    lead_score: float | None = None
    score_property_component: float | None = None
    score_canopy_component: float | None = None
    score_storm_component: float | None = None
    score_siding_component: float | None = None
    has_tax_delinquency: bool = False
    tax_outstanding_balance: float | None = None
    raw_data: dict[str, Any] = Field(default_factory=dict)
    needs_review: bool = False
    review_reason: str | None = None


class StormEventRecord(BaseModel):
    """A normalized storm/hail event, bulk-loaded from NOAA NCEI's Storm
    Events Database.

    Deliberately carries no `client_id` -- see `migrations/001_init_schema.sql`'s
    `storm_events` table docstring for why: a storm event is an objective
    public fact about a county, not client data. `event_id` is NOAA's own
    native identifier and is the real dedup key (`unique (source,
    event_id)`) -- unlike Tool 1's bid awards, this source always has a
    genuine stable native id, so no fuzzy-match tier is needed.

    `needs_review`/`review_reason` added in `migrations/
    002_add_needs_review_to_storm_events.sql`, after this schema's initial
    design -- same discipline `ParcelLeadRecord` always had: a row with an
    unparseable date or missing critical field is flagged for a human, not
    silently dropped or guessed at.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    event_id: str
    county: str
    state: str
    event_date: date | None = None
    event_type: str
    magnitude: str | None = None
    narrative: str | None = None
    property_damage_estimate: float | None = None
    source: str = "noaa_ncei"
    raw_data: dict[str, Any] = Field(default_factory=dict)
    needs_review: bool = False
    review_reason: str | None = None
