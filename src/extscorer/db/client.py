"""Generic Postgres client wrapper for extscorer.

Handles connecting to Postgres and the upsert logic for both tables --
`parcels` (client-scoped) and `storm_events` (global, see that table's
migration docstring). Nothing here is specific to any hosting provider
(e.g. Supabase) or client -- that kind of wiring belongs in a downstream
"full" deployment package.

Dedup is a plain exact-match upsert: `parcels` on `(client_id, town,
parcel_id)`, `storm_events` on `(source, event_id)` -- both sources
always expose a genuine stable native identifier (VGSI's parcel id,
NOAA's event id), so no fuzzy-match tier is needed, following Tool 2 and
Tool 3's precedent over Tool 1's 3-tier fuzzy match.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from extscorer.config import DatabaseConfig
from extscorer.normalize.schema import ParcelLeadRecord, StormEventRecord


def get_connection(dsn: str | None = None) -> psycopg.Connection:
    """Open a Postgres connection.

    Uses `dsn` if given, otherwise resolves connection settings from the
    environment via `DatabaseConfig.from_env()`.
    """
    resolved_dsn = dsn or DatabaseConfig.from_env().dsn
    return psycopg.connect(resolved_dsn)


def _parcel_content_params(record: ParcelLeadRecord) -> dict[str, Any]:
    return {
        "county": record.county,
        "address": record.address,
        "source_url": record.source_url,
        "year_built": record.year_built,
        "living_area_sqft": record.living_area_sqft,
        "roof_cover_material": record.roof_cover_material,
        "exterior_wall_1": record.exterior_wall_1,
        "exterior_wall_2": record.exterior_wall_2,
        "building_percent_good": record.building_percent_good,
        "siding_data_source": record.siding_data_source,
        "owner_name": record.owner_name,
        "owner_mailing_address": record.owner_mailing_address,
        "is_absentee_owner": record.is_absentee_owner,
        "latitude": record.latitude,
        "longitude": record.longitude,
        "pct_tree_canopy_nearby": record.pct_tree_canopy_nearby,
        "canopy_data_year": record.canopy_data_year,
        "canopy_source": record.canopy_source,
        "nearest_storm_event_date": record.nearest_storm_event_date,
        "storm_event_summary": record.storm_event_summary,
        "permit_data_available": record.permit_data_available,
        "permit_history": Jsonb(record.permit_history),
        "exterior_permit_count": record.exterior_permit_count,
        "most_recent_exterior_permit_date": record.most_recent_exterior_permit_date,
        "most_recent_exterior_permit_type": record.most_recent_exterior_permit_type,
        "permit_history_since": record.permit_history_since,
        "lead_score": record.lead_score,
        "score_property_component": record.score_property_component,
        "score_canopy_component": record.score_canopy_component,
        "score_storm_component": record.score_storm_component,
        "score_siding_component": record.score_siding_component,
        "has_tax_delinquency": record.has_tax_delinquency,
        "tax_outstanding_balance": record.tax_outstanding_balance,
        "effective_year_built": record.effective_year_built,
        "cama_permit_count": record.cama_permit_count,
        "outbuilding_count": record.outbuilding_count,
        "last_sale_date": record.last_sale_date,
        "last_sale_price": record.last_sale_price,
        "source_dataset_id": record.source_dataset_id,
        "source_fetch_date": record.source_fetch_date,
        "raw_data": Jsonb(record.raw_data),
        "needs_review": record.needs_review,
        "review_reason": record.review_reason,
        "assessed_value": record.assessed_value,
        "state_parcel_ref": Jsonb(record.state_parcel_ref) if record.state_parcel_ref is not None else None,
        "enrichment_status": record.enrichment_status,
    }


def upsert_parcel(conn: psycopg.Connection, record: ParcelLeadRecord) -> dict[str, Any]:
    """Insert or update a parcel, keyed on (client_id, town, parcel_id).

    An exact match refreshes the row's content and bumps `last_seen_at`;
    no match inserts a new row (`first_seen_at` set by the column
    default).

    **Enrichment-only fields are preserved on a bare re-scrape, not blindly
    clobbered** -- fixed 2026-09-15, a real bug found live: a `LeadDataSource`
    like `VgsiParcelSource` never populates `latitude`/`longitude`/canopy/
    storm/score fields at all (those come only from this repo's own
    backfill scripts), so its `ParcelLeadRecord` always carries `None` for
    them. Before this fix, re-running `run_client.py` against an
    already-enriched town (e.g. a scheduled re-scrape) silently WIPED every
    parcel's geocoding/canopy/storm/score data back to `None` on every
    single run, discovered when this session's own re-scrape reset all
    1,600 real parcels' enrichment fields at once. Now these columns use
    `coalesce(excluded.X, parcels.X)`: a source that provides a real value
    (a future canopy-aware source, or literally the enrichment backfill
    scripts themselves, which write via `update_parcel_*` not this
    function) overwrites; a source that provides `None` (every current
    `LeadDataSource`) leaves the existing value alone.

    `permit_data_available`/`permit_history` need a DIFFERENT rule than
    plain coalesce: both default to non-`None` values (`False`/`[]`) on a
    record that never touched them, so a plain coalesce wouldn't help --
    `False`/`[]` aren't `NULL`. Instead: only trust the incoming record's
    permit fields when `excluded.permit_data_available` is true (a real
    `propertyrecordcards.com`-sourced scrape always sets this true and
    provides real data); a VGSI-sourced re-scrape's `False`/`[]` defaults
    never overwrite an existing `Woodstock`-style enrichment pass's real
    `True`/populated data. `exterior_permit_count`/`most_recent_exterior_
    permit_date`/`most_recent_exterior_permit_type` all default to `None`
    on an unenriched record, so plain coalesce already does the right
    thing for those.

    `owner_name`/`owner_mailing_address`/`is_absentee_owner` (2026-09-15,
    Prompt U) are scrape-native like `exterior_wall_1` etc -- both VGSI and
    `propertyrecordcards.com` populate real owner-of-record data on every
    run, so these blind-overwrite on `excluded`, no coalesce needed.
    `has_tax_delinquency` has the SAME `False`-isn't-`NULL` problem as
    `permit_data_available` above (it's an enrichment-only field a bare
    re-scrape never touches, so its incoming default is always `False`,
    not `None`) -- same OR-based fix: only ever moves True via the real
    `backfill_tax_delinquency.py` pass, never reset by an ordinary
    re-scrape. `tax_outstanding_balance` defaults to `None` on an
    unenriched record, so plain coalesce is correct for it.
    """
    query = """
        insert into parcels (
            client_id, town, parcel_id, county, address, source_url,
            year_built, living_area_sqft, roof_cover_material,
            exterior_wall_1, exterior_wall_2, building_percent_good, siding_data_source,
            owner_name, owner_mailing_address, is_absentee_owner,
            latitude, longitude,
            pct_tree_canopy_nearby, canopy_data_year, canopy_source,
            nearest_storm_event_date, storm_event_summary,
            permit_data_available, permit_history, exterior_permit_count,
            most_recent_exterior_permit_date, most_recent_exterior_permit_type, permit_history_since,
            lead_score, score_property_component, score_canopy_component, score_storm_component,
            score_siding_component,
            has_tax_delinquency, tax_outstanding_balance,
            effective_year_built, cama_permit_count, outbuilding_count,
            last_sale_date, last_sale_price,
            source_dataset_id, source_fetch_date,
            raw_data, needs_review, review_reason,
            assessed_value, state_parcel_ref, enrichment_status
        ) values (
            %(client_id)s, %(town)s, %(parcel_id)s, %(county)s, %(address)s, %(source_url)s,
            %(year_built)s, %(living_area_sqft)s, %(roof_cover_material)s,
            %(exterior_wall_1)s, %(exterior_wall_2)s, %(building_percent_good)s, %(siding_data_source)s,
            %(owner_name)s, %(owner_mailing_address)s, %(is_absentee_owner)s,
            %(latitude)s, %(longitude)s,
            %(pct_tree_canopy_nearby)s, %(canopy_data_year)s, %(canopy_source)s,
            %(nearest_storm_event_date)s, %(storm_event_summary)s,
            %(permit_data_available)s, %(permit_history)s, %(exterior_permit_count)s,
            %(most_recent_exterior_permit_date)s, %(most_recent_exterior_permit_type)s, %(permit_history_since)s,
            %(lead_score)s, %(score_property_component)s, %(score_canopy_component)s, %(score_storm_component)s,
            %(score_siding_component)s,
            %(has_tax_delinquency)s, %(tax_outstanding_balance)s,
            %(effective_year_built)s, %(cama_permit_count)s, %(outbuilding_count)s,
            %(last_sale_date)s, %(last_sale_price)s,
            %(source_dataset_id)s, %(source_fetch_date)s,
            %(raw_data)s, %(needs_review)s, %(review_reason)s,
            %(assessed_value)s, %(state_parcel_ref)s, %(enrichment_status)s
        )
        on conflict (client_id, town, parcel_id) do update set
            county = excluded.county,
            address = excluded.address,
            source_url = excluded.source_url,
            year_built = excluded.year_built,
            living_area_sqft = excluded.living_area_sqft,
            roof_cover_material = excluded.roof_cover_material,
            exterior_wall_1 = excluded.exterior_wall_1,
            exterior_wall_2 = excluded.exterior_wall_2,
            building_percent_good = excluded.building_percent_good,
            siding_data_source = coalesce(excluded.siding_data_source, parcels.siding_data_source),
            owner_name = excluded.owner_name,
            owner_mailing_address = excluded.owner_mailing_address,
            is_absentee_owner = excluded.is_absentee_owner,
            latitude = coalesce(excluded.latitude, parcels.latitude),
            longitude = coalesce(excluded.longitude, parcels.longitude),
            pct_tree_canopy_nearby = coalesce(excluded.pct_tree_canopy_nearby, parcels.pct_tree_canopy_nearby),
            canopy_data_year = coalesce(excluded.canopy_data_year, parcels.canopy_data_year),
            canopy_source = coalesce(excluded.canopy_source, parcels.canopy_source),
            nearest_storm_event_date = coalesce(excluded.nearest_storm_event_date, parcels.nearest_storm_event_date),
            storm_event_summary = coalesce(excluded.storm_event_summary, parcels.storm_event_summary),
            -- permit_data_available/permit_history default to False/[] (not
            -- NULL) on a record that never touched them, so plain coalesce
            -- wouldn't help -- only trust the incoming record's permit
            -- fields when it actually claims real permit visibility. See
            -- this function's own docstring.
            permit_data_available = (excluded.permit_data_available or parcels.permit_data_available),
            permit_history = case when excluded.permit_data_available then excluded.permit_history else parcels.permit_history end,
            exterior_permit_count = coalesce(excluded.exterior_permit_count, parcels.exterior_permit_count),
            most_recent_exterior_permit_date = coalesce(excluded.most_recent_exterior_permit_date, parcels.most_recent_exterior_permit_date),
            most_recent_exterior_permit_type = coalesce(excluded.most_recent_exterior_permit_type, parcels.most_recent_exterior_permit_type),
            permit_history_since = coalesce(excluded.permit_history_since, parcels.permit_history_since),
            lead_score = coalesce(excluded.lead_score, parcels.lead_score),
            score_property_component = coalesce(excluded.score_property_component, parcels.score_property_component),
            score_canopy_component = coalesce(excluded.score_canopy_component, parcels.score_canopy_component),
            score_storm_component = coalesce(excluded.score_storm_component, parcels.score_storm_component),
            score_siding_component = coalesce(excluded.score_siding_component, parcels.score_siding_component),
            -- has_tax_delinquency defaults to False (not NULL) on a record
            -- that never touched it -- same problem plain coalesce already
            -- has for permit_data_available above, and the same fix: only
            -- move it True->False if the incoming row is the real
            -- delinquency backfill saying so, never as a side effect of an
            -- ordinary re-scrape (which never sets this field at all).
            has_tax_delinquency = (excluded.has_tax_delinquency or parcels.has_tax_delinquency),
            tax_outstanding_balance = coalesce(excluded.tax_outstanding_balance, parcels.tax_outstanding_balance),
            -- CAMA fields are scrape-native from the one state-dataset
            -- source Windham's town rows ever come from -- blind
            -- overwrite, same as year_built/living_area_sqft, not
            -- coalesce (a real re-fetch should replace a stale eyb, not
            -- preserve it).
            effective_year_built = excluded.effective_year_built,
            cama_permit_count = excluded.cama_permit_count,
            outbuilding_count = excluded.outbuilding_count,
            last_sale_date = excluded.last_sale_date,
            last_sale_price = excluded.last_sale_price,
            source_dataset_id = excluded.source_dataset_id,
            source_fetch_date = excluded.source_fetch_date,
            raw_data = excluded.raw_data,
            needs_review = excluded.needs_review,
            review_reason = excluded.review_reason,
            -- assessed_value/state_parcel_ref are state-layer-only
            -- (2026-10-28) -- no scraped source ever provides them, so
            -- same coalesce-protect treatment as tax_outstanding_balance
            -- above: never clobbered by an ordinary VGSI/propertyrecordcards.com
            -- re-scrape. enrichment_status blind-overwrites like
            -- effective_year_built -- in practice this is moot for a
            -- state-only row's minted `parcel_id` (see
            -- `extscorer.normalize.address.mint_address_town_parcel_id`),
            -- which can never collide with a real scraper's own id, so
            -- this conflict branch never actually fires for a state-only
            -- row today; kept consistent with every other scrape-native
            -- field's treatment regardless.
            assessed_value = coalesce(excluded.assessed_value, parcels.assessed_value),
            state_parcel_ref = coalesce(excluded.state_parcel_ref, parcels.state_parcel_ref),
            enrichment_status = excluded.enrichment_status,
            last_seen_at = now(),
            updated_at = now()
        returning *
    """
    params = {
        "client_id": record.client_id,
        "town": record.town,
        "parcel_id": record.parcel_id,
        **_parcel_content_params(record),
    }
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, params)
        row = cur.fetchone()
    conn.commit()
    assert row is not None
    return row


def parcels_for_client(conn: psycopg.Connection, client_id: str) -> list[dict[str, Any]]:
    """Return every parcel record for `client_id`."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("select * from parcels where client_id = %(client_id)s", {"client_id": client_id})
        return cur.fetchall()


def update_parcel_coordinates(
    conn: psycopg.Connection, parcel_id: Any, latitude: float | None, longitude: float | None
) -> dict[str, Any]:
    """Backfill one parcel row's geocoded `latitude`/`longitude` by its own
    primary key (`id`) -- every other column is left untouched. Idempotent:
    always writes the current value (including `None`/`None` for a parcel
    that still hasn't been successfully geocoded), same convention as
    `update_parcel_storm_fields`.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "update parcels set latitude = %(latitude)s, longitude = %(longitude)s, updated_at = now() "
            "where id = %(id)s returning *",
            {"id": parcel_id, "latitude": latitude, "longitude": longitude},
        )
        row = cur.fetchone()
    conn.commit()
    assert row is not None
    return row


def update_parcel_coordinates_and_review(
    conn: psycopg.Connection,
    parcel_id: Any,
    latitude: float | None,
    longitude: float | None,
    needs_review: bool,
    review_reason: str | None,
) -> dict[str, Any]:
    """Backfill one parcel row's geocoded `latitude`/`longitude` AND its
    `needs_review`/`review_reason` together, by its own primary key
    (`id`) -- every other column left untouched.

    Separate from the plain `update_parcel_coordinates` above (used by
    `backfill_parcel_geocoding.py`'s Census-geocoder pass, which doesn't
    flag `needs_review` at all) -- built for a centroid-join pass (e.g.
    Windham's state parcel+CAMA feature-service join,
    `scripts/backfill_windham_centroids.py`) that DOES need to flag "no
    centroid found" / "shares a polygon with another parcel" the same way
    `update_parcel_canopy_fields` flags its own gaps. Caller is expected
    to have already merged this pass's own contribution into
    `review_reason` via `extscorer_full.review_reasons.merge_owned_reason`
    (same "don't clobber a different pass's reason, don't leave a stale
    one behind" discipline) -- this function just writes the final value,
    same "dumb write" convention as `update_parcel_canopy_fields`.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            update parcels
            set latitude = %(latitude)s,
                longitude = %(longitude)s,
                needs_review = %(needs_review)s,
                review_reason = %(review_reason)s,
                updated_at = now()
            where id = %(id)s
            returning *
            """,
            {
                "id": parcel_id,
                "latitude": latitude,
                "longitude": longitude,
                "needs_review": needs_review,
                "review_reason": review_reason,
            },
        )
        row = cur.fetchone()
    conn.commit()
    assert row is not None
    return row


def update_parcel_lead_score(
    conn: psycopg.Connection,
    parcel_id: Any,
    lead_score: float | None,
    score_property_component: float | None,
    score_canopy_component: float | None,
    score_storm_component: float | None,
    score_siding_component: float | None = None,
) -> dict[str, Any]:
    """Backfill one parcel row's `lead_score`/per-component fields by its
    own primary key (`id`) -- every other column is left untouched.
    `None`s (a disqualified, non-scoreable parcel, or a component that
    wasn't evaluated -- see `extscorer.scoring.basic.score_property`'s
    qualifying gate and its per-component "None means not evaluated"
    convention) are written just as readily as real values, same
    idempotent-refresh convention as
    `update_parcel_storm_fields`/`update_parcel_canopy_fields`.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            update parcels
            set lead_score = %(lead_score)s,
                score_property_component = %(property_component)s,
                score_canopy_component = %(canopy_component)s,
                score_storm_component = %(storm_component)s,
                score_siding_component = %(siding_component)s,
                updated_at = now()
            where id = %(id)s
            returning *
            """,
            {
                "id": parcel_id,
                "lead_score": lead_score,
                "property_component": score_property_component,
                "canopy_component": score_canopy_component,
                "storm_component": score_storm_component,
                "siding_component": score_siding_component,
            },
        )
        row = cur.fetchone()
    conn.commit()
    assert row is not None
    return row


def update_parcel_permit_and_siding_fields(
    conn: psycopg.Connection,
    parcel_id: Any,
    exterior_wall_1: str | None,
    siding_data_source: str | None,
    permit_data_available: bool,
    permit_history: list[dict[str, Any]],
    exterior_permit_count: int | None,
    most_recent_exterior_permit_date: date | None,
    most_recent_exterior_permit_type: str | None,
    permit_history_since: date | None = None,
) -> dict[str, Any]:
    """Backfill one parcel row's real-siding/permit-history fields by its
    own primary key (`id`) -- every other column is left untouched.

    Built for `property-lead-scorer-full/scripts/backfill_woodstock_prc_enrichment.py`:
    Woodstock's 200 parcels were already scraped from VGSI (see
    `sources/woodstock_vgsi.py`) and don't need re-scraping from scratch --
    this is a cross-source ENRICHMENT pass, matching each existing row by
    address to its propertyrecordcards.com counterpart and overwriting only
    the fields that source can improve on. `exterior_wall_1` IS
    overwritten here (with the real "Siding:" field value, provenance
    recorded in `siding_data_source`) -- deliberately more trustworthy than
    VGSI's own same-named field, not merely a fallback. Same idempotent-
    refresh convention as `update_parcel_storm_fields`/
    `update_parcel_canopy_fields`: always writes the current computed
    value, safe to rerun.

    `permit_history_since` (2026-10-26, Windham build) -- also used by
    `permit-history-enrichment-full`'s Windham PermitLink backfill (via
    `permit_enrichment.db`'s re-export of this same function): the
    earliest date this parcel's town's permit source can actually attest
    to, so `extscorer.scoring.basic.real_siding_age_score` never reads a
    short/new history's "no permit found" as "never redone." Defaults to
    `None` (unchanged behavior) for every existing caller that doesn't
    pass it.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            update parcels
            set exterior_wall_1 = %(exterior_wall_1)s,
                siding_data_source = %(siding_data_source)s,
                permit_data_available = %(permit_data_available)s,
                permit_history = %(permit_history)s,
                exterior_permit_count = %(exterior_permit_count)s,
                most_recent_exterior_permit_date = %(most_recent_exterior_permit_date)s,
                most_recent_exterior_permit_type = %(most_recent_exterior_permit_type)s,
                permit_history_since = coalesce(%(permit_history_since)s, permit_history_since),
                updated_at = now()
            where id = %(id)s
            returning *
            """,
            {
                "id": parcel_id,
                "exterior_wall_1": exterior_wall_1,
                "siding_data_source": siding_data_source,
                "permit_data_available": permit_data_available,
                "permit_history": Jsonb(permit_history),
                "exterior_permit_count": exterior_permit_count,
                "most_recent_exterior_permit_date": most_recent_exterior_permit_date,
                "most_recent_exterior_permit_type": most_recent_exterior_permit_type,
                "permit_history_since": permit_history_since,
            },
        )
        row = cur.fetchone()
    conn.commit()
    assert row is not None
    return row


def update_parcel_tax_delinquency_fields(
    conn: psycopg.Connection,
    parcel_id: Any,
    has_tax_delinquency: bool,
    tax_outstanding_balance: float | None,
) -> dict[str, Any]:
    """Backfill one parcel row's mytaxbill.org delinquency fields by its own
    primary key (`id`) -- every other column is left untouched.

    Built for `property-lead-scorer-full/scripts/backfill_tax_delinquency.py`
    (2026-09-15, Prompt U): a real per-parcel lookup against mytaxbill.org
    (a shared CT municipal tax portal covering all 8 target towns), run as
    a separate enrichment pass well after the initial scrape -- same
    idempotent-refresh convention as `update_parcel_storm_fields`/
    `update_parcel_canopy_fields`: always writes the current computed
    value (including `False`/`None` for a parcel confirmed current on
    taxes), safe to rerun.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            update parcels
            set has_tax_delinquency = %(has_tax_delinquency)s,
                tax_outstanding_balance = %(tax_outstanding_balance)s,
                updated_at = now()
            where id = %(id)s
            returning *
            """,
            {
                "id": parcel_id,
                "has_tax_delinquency": has_tax_delinquency,
                "tax_outstanding_balance": tax_outstanding_balance,
            },
        )
        row = cur.fetchone()
    conn.commit()
    assert row is not None
    return row


def fill_state_enrichment_fields_if_null(
    conn: psycopg.Connection,
    parcel_id: Any,
    latitude: float | None,
    longitude: float | None,
    assessed_value: float | None,
    last_sale_date: date | None,
    last_sale_price: float | None,
    state_parcel_ref: dict[str, Any] | None,
) -> dict[str, Any]:
    """Backfill an EXISTING (already-scraped) parcel row from the state
    CAMA layer, by its own primary key (`id`) -- 2026-10-28, the state
    FeatureServer merge (docs/state-featureserver-audit-2026-10-28.md,
    property-lead-scorer-full).

    Deliberately NARROWER than `upsert_parcel`'s own ON CONFLICT clause:
    this function ONLY ever touches the 5 columns above, and the SQL
    itself (`coalesce(parcels.X, %(x)s)`, existing value first) guarantees
    it only ever fills a currently-NULL value -- it can never overwrite a
    real existing value, even if called with a non-NULL argument. This is
    the audit's own "existing rows: fill ONLY where our value is NULL"
    rule enforced at the SQL level, not just by caller discipline, since
    `upsert_parcel` blind-overwrites `address`/`year_built`/
    `living_area_sqft`/`owner_name`/etc on conflict -- exactly the columns
    this merge must NEVER touch on an existing row. `address`/`town`/
    `parcel_id` are not parameters here at all, not just left alone by
    convention -- they can't be passed to this function.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            update parcels
            set latitude = coalesce(parcels.latitude, %(latitude)s),
                longitude = coalesce(parcels.longitude, %(longitude)s),
                assessed_value = coalesce(parcels.assessed_value, %(assessed_value)s),
                last_sale_date = coalesce(parcels.last_sale_date, %(last_sale_date)s),
                last_sale_price = coalesce(parcels.last_sale_price, %(last_sale_price)s),
                state_parcel_ref = coalesce(parcels.state_parcel_ref, %(state_parcel_ref)s),
                updated_at = now()
            where id = %(id)s
            returning *
            """,
            {
                "id": parcel_id,
                "latitude": latitude,
                "longitude": longitude,
                "assessed_value": assessed_value,
                "last_sale_date": last_sale_date,
                "last_sale_price": last_sale_price,
                "state_parcel_ref": Jsonb(state_parcel_ref) if state_parcel_ref is not None else None,
            },
        )
        row = cur.fetchone()
    conn.commit()
    assert row is not None
    return row


def update_parcel_scraped_base_fields(
    conn: psycopg.Connection,
    parcel_id: Any,
    year_built: int | None,
    living_area_sqft: int | None,
    roof_cover_material: str | None,
    exterior_wall_1: str | None,
    exterior_wall_2: str | None,
    building_percent_good: int | None,
    owner_name: str | None,
    owner_mailing_address: str | None,
    is_absentee_owner: bool,
    source_url: str | None,
    enrichment_status: str,
    needs_review: bool,
    review_reason: str | None,
) -> dict[str, Any]:
    """Promote a `state_only` row to a fully-scraped one -- Phase 2
    enrichment (2026-10-29, property-lead-scorer-full's targeted VGSI/
    propertyrecordcards.com enrichment of the score-ceiling slice).

    Blind-overwrites every field here (never coalesced) -- the merge
    rule this implements is "a real scrape wins over the state layer's
    own value for every overlapping field," the same direction
    `upsert_parcel`'s own blind-overwrite columns already use for a
    genuine re-scrape. Deliberately NARROWER than `upsert_parcel`: no
    `address`/`town`/`parcel_id` parameter exists here at all, so this
    function physically cannot touch a row's identity, even though this
    merge rule is the opposite direction from `fill_state_enrichment_
    fields_if_null`'s NULL-only one -- the one thing both functions
    agree on is identity is never a parameter either way.

    `assessed_value`/`state_parcel_ref`/`last_sale_date`/`last_sale_
    price` are NOT touched here -- VGSI/propertyrecordcards.com never
    expose those fields (confirmed in the original audit), so the
    state layer's own values for them are simply left in place, no
    conflict to resolve.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            update parcels
            set year_built = %(year_built)s,
                living_area_sqft = %(living_area_sqft)s,
                roof_cover_material = %(roof_cover_material)s,
                exterior_wall_1 = %(exterior_wall_1)s,
                exterior_wall_2 = %(exterior_wall_2)s,
                building_percent_good = %(building_percent_good)s,
                owner_name = %(owner_name)s,
                owner_mailing_address = %(owner_mailing_address)s,
                is_absentee_owner = %(is_absentee_owner)s,
                source_url = %(source_url)s,
                enrichment_status = %(enrichment_status)s,
                needs_review = %(needs_review)s,
                review_reason = %(review_reason)s,
                updated_at = now()
            where id = %(id)s
            returning *
            """,
            {
                "id": parcel_id,
                "year_built": year_built,
                "living_area_sqft": living_area_sqft,
                "roof_cover_material": roof_cover_material,
                "exterior_wall_1": exterior_wall_1,
                "exterior_wall_2": exterior_wall_2,
                "building_percent_good": building_percent_good,
                "owner_name": owner_name,
                "owner_mailing_address": owner_mailing_address,
                "is_absentee_owner": is_absentee_owner,
                "source_url": source_url,
                "enrichment_status": enrichment_status,
                "needs_review": needs_review,
                "review_reason": review_reason,
            },
        )
        row = cur.fetchone()
    conn.commit()
    assert row is not None
    return row


def update_parcel_canopy_fields(
    conn: psycopg.Connection,
    parcel_id: Any,
    pct_tree_canopy_nearby: float | None,
    canopy_data_year: int | None,
    canopy_source: str | None,
    needs_review: bool,
    review_reason: str | None,
) -> dict[str, Any]:
    """Backfill one parcel row's denormalized canopy fields by its own
    primary key (`id`) -- every other column is left untouched.

    `needs_review`/`review_reason` here are the CALLER's already-computed
    final values (typically the parcel's existing VGSI-scrape reason, with
    a canopy-specific reason appended if this pass found its own gap) --
    this function never reads or merges prior state itself, to keep it a
    simple, dumb write like `update_parcel_storm_fields`/
    `update_parcel_coordinates`. See `property-lead-scorer-full/scripts/
    backfill_parcel_canopy.py` for the merge logic.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            update parcels
            set pct_tree_canopy_nearby = %(pct)s,
                canopy_data_year = %(year)s,
                canopy_source = %(source)s,
                needs_review = %(needs_review)s,
                review_reason = %(review_reason)s,
                updated_at = now()
            where id = %(id)s
            returning *
            """,
            {
                "id": parcel_id,
                "pct": pct_tree_canopy_nearby,
                "year": canopy_data_year,
                "source": canopy_source,
                "needs_review": needs_review,
                "review_reason": review_reason,
            },
        )
        row = cur.fetchone()
    conn.commit()
    assert row is not None
    return row


def update_parcel_storm_fields(
    conn: psycopg.Connection,
    parcel_id: Any,
    nearest_storm_event_date: date | None,
    storm_event_summary: str | None,
) -> dict[str, Any]:
    """Backfill/refresh one parcel row's denormalized storm fields by its
    own primary key (`id`) -- every other column is left untouched.

    Idempotent by construction: always writes the CURRENT computed value
    (including `None`/`None` for a parcel with no qualifying event), so
    re-running the backfill after new storm events or parcels are added
    converges to the right state rather than only ever adding matches.
    See `extscorer.enrichment.storm_backfill` for how the value to write
    is actually chosen.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            update parcels
            set nearest_storm_event_date = %(event_date)s,
                storm_event_summary = %(summary)s,
                updated_at = now()
            where id = %(id)s
            returning *
            """,
            {"id": parcel_id, "event_date": nearest_storm_event_date, "summary": storm_event_summary},
        )
        row = cur.fetchone()
    conn.commit()
    assert row is not None
    return row


def upsert_storm_event(conn: psycopg.Connection, record: StormEventRecord) -> dict[str, Any]:
    """Insert or update a storm event, keyed on (source, event_id).

    `storm_events` carries no `client_id` -- see that table's migration
    docstring for why (it's global reference data, shared across every
    client that ever cares about a given county's storm history).
    """
    query = """
        insert into storm_events (
            source, event_id, county, state, event_date, event_type,
            magnitude, narrative, property_damage_estimate, raw_data,
            needs_review, review_reason
        ) values (
            %(source)s, %(event_id)s, %(county)s, %(state)s, %(event_date)s, %(event_type)s,
            %(magnitude)s, %(narrative)s, %(property_damage_estimate)s, %(raw_data)s,
            %(needs_review)s, %(review_reason)s
        )
        on conflict (source, event_id) do update set
            county = excluded.county,
            state = excluded.state,
            event_date = excluded.event_date,
            event_type = excluded.event_type,
            magnitude = excluded.magnitude,
            narrative = excluded.narrative,
            property_damage_estimate = excluded.property_damage_estimate,
            raw_data = excluded.raw_data,
            needs_review = excluded.needs_review,
            review_reason = excluded.review_reason
        returning *
    """
    params = {
        "source": record.source,
        "event_id": record.event_id,
        "county": record.county,
        "state": record.state,
        "event_date": record.event_date,
        "event_type": record.event_type,
        "magnitude": record.magnitude,
        "narrative": record.narrative,
        "property_damage_estimate": record.property_damage_estimate,
        "raw_data": Jsonb(record.raw_data),
        "needs_review": record.needs_review,
        "review_reason": record.review_reason,
    }
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, params)
        row = cur.fetchone()
    conn.commit()
    assert row is not None
    return row


def storm_events_for_county(conn: psycopg.Connection, county: str, state: str) -> list[dict[str, Any]]:
    """Return every storm event on file for `county`/`state`, most recent first."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "select * from storm_events where county = %(county)s and state = %(state)s "
            "order by event_date desc",
            {"county": county, "state": state},
        )
        return cur.fetchall()


def already_sent_parcel_ids(conn: psycopg.Connection, client_id: str) -> set[Any]:
    """Return the set of `parcels.id` already recorded in `lead_digest_sends`
    for `client_id` -- the dedup filter a lead-digest send checks before
    picking its next batch (see that table's migration docstring for why
    this is per-parcel, not a `first_seen_at`-style date cutoff).
    """
    with conn.cursor() as cur:
        cur.execute("select parcel_id from lead_digest_sends where client_id = %(client_id)s", {"client_id": client_id})
        return {row[0] for row in cur.fetchall()}


def record_lead_digest_sends(conn: psycopg.Connection, client_id: str, parcel_ids: list[Any]) -> None:
    """Record that `parcel_ids` were just included in a sent lead digest
    for `client_id`. Call this ONLY after a successful send -- a failed
    send must not falsely mark these leads as delivered, same discipline
    Tool 1's `record_digest_run` already follows for its own table.
    """
    if not parcel_ids:
        return
    with conn.cursor() as cur:
        cur.executemany(
            "insert into lead_digest_sends (client_id, parcel_id) values (%(client_id)s, %(parcel_id)s)",
            [{"client_id": client_id, "parcel_id": parcel_id} for parcel_id in parcel_ids],
        )
    conn.commit()


def lead_pipeline_keys_for_client(conn: psycopg.Connection, client_id: str) -> set[str]:
    """Return every `lead_key` on file in `lead_pipeline` for `client_id`,
    regardless of `status` -- the dedup filter `extscorer.digest.selection
    .select_new_leads_for_pipeline` checks (a lead marked `dead` or `won`
    must never come back as new, same as one marked `new` itself).
    """
    with conn.cursor() as cur:
        cur.execute("select lead_key from lead_pipeline where client_id = %(client_id)s", {"client_id": client_id})
        return {row[0] for row in cur.fetchall()}


def lead_pipeline_rows_for_client(conn: psycopg.Connection, client_id: str) -> list[dict[str, Any]]:
    """Return every `lead_pipeline` row for `client_id` as a dict, keyed by
    column name -- used by the sheets sync module's pull step (to compare
    against the Sheet's current Master tab) and by verification/reporting
    code that wants the full row, not just the key set above.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("select * from lead_pipeline where client_id = %(client_id)s", {"client_id": client_id})
        return cur.fetchall()


def insert_lead_pipeline_entries(conn: psycopg.Connection, client_id: str, entries: list[dict[str, Any]]) -> None:
    """Insert new `lead_pipeline` rows -- one per newly-surfaced lead this
    digest cycle just pushed onto the Sheet's Master tab. Each entry is
    `{"lead_key": ..., "parcel_id": ...}`; `status` always starts `new`,
    `owner`/`notes` always start blank, matching the blank row the Sheet
    append writes for the same lead (see `extscorer_full`'s sheets sync
    module) -- this table and the Sheet must agree on a brand-new lead's
    starting state.

    Call this ONLY after the Sheet append itself has succeeded (same
    "don't record what wasn't actually delivered" discipline
    `record_lead_digest_sends` already follows) -- an entry recorded here
    with no matching Sheet row would make that lead silently
    un-re-surfaceable forever, with no way for a human to ever see or work
    it.
    """
    if not entries:
        return
    with conn.cursor() as cur:
        cur.executemany(
            "insert into lead_pipeline (client_id, lead_key, parcel_id, status, owner, notes) "
            "values (%(client_id)s, %(lead_key)s, %(parcel_id)s, 'new', null, null) "
            "on conflict (client_id, lead_key) do nothing",
            [
                {"client_id": client_id, "lead_key": entry["lead_key"], "parcel_id": entry["parcel_id"]}
                for entry in entries
            ],
        )
    conn.commit()


def update_lead_pipeline_from_sheet_rows(conn: psycopg.Connection, client_id: str, rows: list[dict[str, Any]]) -> None:
    """Mirror the Sheet's Master tab's human-owned fields (`status`,
    `owner`, `notes`) into `lead_pipeline` -- the sync cycle's "pull" step
    (see Prompt V Step 2.1: "the Sheet is the source of truth for the
    human-owned fields"). Each row is `{"lead_key": ..., "status": ...,
    "owner": ..., "notes": ...}`.

    Only updates a row that already exists for `(client_id, lead_key)` --
    this function never inserts (a Master row with no matching
    `lead_pipeline` row is not expected once Step 4's seeding has run, and
    silently inserting one here would bypass the real `parcel_id` foreign
    key this table requires, which the Sheet alone can't supply).
    `last_updated` is stamped `now()` on every call, not conditionally --
    harmless on a re-run where nothing actually changed (same idempotency
    tolerance the rest of this sync cycle already has).
    """
    if not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(
            "update lead_pipeline set status = %(status)s, owner = %(owner)s, notes = %(notes)s, "
            "last_updated = now() where client_id = %(client_id)s and lead_key = %(lead_key)s",
            [
                {
                    "client_id": client_id,
                    "lead_key": row["lead_key"],
                    "status": row["status"],
                    "owner": row.get("owner") or None,
                    "notes": row.get("notes") or None,
                }
                for row in rows
            ],
        )
    conn.commit()


def lead_pipeline_row_count_for_client(conn: psycopg.Connection, client_id: str) -> int:
    """Row count for `client_id` in `lead_pipeline` -- used to verify the
    Sheet's Master tab row count matches the DB 1:1 (Prompt V Step 6).
    """
    with conn.cursor() as cur:
        cur.execute("select count(*) from lead_pipeline where client_id = %(client_id)s", {"client_id": client_id})
        return cur.fetchone()[0]
