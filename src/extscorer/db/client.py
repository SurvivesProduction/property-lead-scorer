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
        "lead_score": record.lead_score,
        "score_property_component": record.score_property_component,
        "score_canopy_component": record.score_canopy_component,
        "score_storm_component": record.score_storm_component,
        "score_siding_component": record.score_siding_component,
        "raw_data": Jsonb(record.raw_data),
        "needs_review": record.needs_review,
        "review_reason": record.review_reason,
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
    """
    query = """
        insert into parcels (
            client_id, town, parcel_id, county, address, source_url,
            year_built, living_area_sqft, roof_cover_material,
            exterior_wall_1, exterior_wall_2, building_percent_good, siding_data_source,
            latitude, longitude,
            pct_tree_canopy_nearby, canopy_data_year, canopy_source,
            nearest_storm_event_date, storm_event_summary,
            permit_data_available, permit_history, exterior_permit_count,
            most_recent_exterior_permit_date, most_recent_exterior_permit_type,
            lead_score, score_property_component, score_canopy_component, score_storm_component,
            score_siding_component,
            raw_data, needs_review, review_reason
        ) values (
            %(client_id)s, %(town)s, %(parcel_id)s, %(county)s, %(address)s, %(source_url)s,
            %(year_built)s, %(living_area_sqft)s, %(roof_cover_material)s,
            %(exterior_wall_1)s, %(exterior_wall_2)s, %(building_percent_good)s, %(siding_data_source)s,
            %(latitude)s, %(longitude)s,
            %(pct_tree_canopy_nearby)s, %(canopy_data_year)s, %(canopy_source)s,
            %(nearest_storm_event_date)s, %(storm_event_summary)s,
            %(permit_data_available)s, %(permit_history)s, %(exterior_permit_count)s,
            %(most_recent_exterior_permit_date)s, %(most_recent_exterior_permit_type)s,
            %(lead_score)s, %(score_property_component)s, %(score_canopy_component)s, %(score_storm_component)s,
            %(score_siding_component)s,
            %(raw_data)s, %(needs_review)s, %(review_reason)s
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
            lead_score = coalesce(excluded.lead_score, parcels.lead_score),
            score_property_component = coalesce(excluded.score_property_component, parcels.score_property_component),
            score_canopy_component = coalesce(excluded.score_canopy_component, parcels.score_canopy_component),
            score_storm_component = coalesce(excluded.score_storm_component, parcels.score_storm_component),
            score_siding_component = coalesce(excluded.score_siding_component, parcels.score_siding_component),
            raw_data = excluded.raw_data,
            needs_review = excluded.needs_review,
            review_reason = excluded.review_reason,
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
