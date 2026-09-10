-- 001_init_schema.sql
-- Initial schema for extscorer: parcels + storm_events.
-- Written to be safe to rerun (idempotent): every statement uses an
-- `if not exists` guard (and `enable row level security` is itself
-- idempotent -- re-enabling an already-enabled table is a no-op).
--
-- Deployment note (updated 2026-09-08): originally written for a
-- separate, dedicated Supabase project for this client. That never
-- materialized (no live database existed for this client before this
-- decision), and the client chose to switch this deployment onto Elite
-- Electric's existing shared Supabase project instead -- see
-- property-lead-scorer-full's ARCHITECTURE.md section 2 for the current
-- reasoning. `parcels`/`storm_events` are confirmed not to collide with
-- that project's existing tables (bid_awards, candidate_dropouts,
-- candidate_snapshots, digest_runs, occupancy_checks, opportunities,
-- permits, properties, sources, vendor_aliases).
--
-- RLS is enabled on both tables at creation time in this same migration
-- (not as a later follow-up fix) -- mirrors the RLS audit run against
-- this same project's other 10 tables. No policies are added: nothing
-- in this project (or Tools 1-3's) uses the anon/public key anywhere,
-- confirmed by that same audit -- every DB access goes through a
-- service-role-equivalent connection that bypasses RLS entirely, so
-- enabling RLS with zero policies is the correct "deny anon/authenticated
-- roles, no-op for the real backend" state, not an oversight.

create extension if not exists pgcrypto;

-- Normalized parcel/lead records. `client_id` is data ownership (which
-- client's dashboard this belongs to); `town`/`county` are the
-- jurisdiction the parcel sits in (county kept as a real column even
-- though it's 'Windham' for every record today, so the tool can expand
-- to other CT counties or other states later without a schema rework --
-- mirrors Tool 3's jurisdiction-tagging decision).
--
-- Per-component score fields (`score_property_component`,
-- `score_canopy_component`, `score_storm_component`) exist alongside
-- `lead_score` so the final ranking is debuggable, not a black box --
-- mirroring the transparency Tool 2's ROI ranking needed.
--
-- `nearest_storm_event_date`/`storm_event_summary` are a denormalized
-- cache of the closest relevant row in `storm_events` (below), computed
-- at scoring time -- keeps the score explainable from this one row
-- without a join, while `storm_events` itself stays the real,
-- deduplicated bulk-loaded source of truth.
create table if not exists parcels (
    id uuid primary key default gen_random_uuid(),
    client_id text not null,
    town text not null,
    county text not null,
    address text not null,
    parcel_id text not null,
    source_url text,
    year_built int,
    living_area_sqft int,
    roof_cover_material text,
    latitude double precision,
    longitude double precision,
    pct_tree_canopy_nearby numeric,
    canopy_data_year int,
    canopy_source text,
    nearest_storm_event_date date,
    storm_event_summary text,
    lead_score numeric,
    score_property_component numeric,
    score_canopy_component numeric,
    score_storm_component numeric,
    raw_data jsonb,
    needs_review boolean not null default false,
    review_reason text,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (client_id, town, parcel_id)
);

alter table parcels enable row level security;

create index if not exists idx_parcels_client_town on parcels (client_id, town);
create index if not exists idx_parcels_client_county on parcels (client_id, county);
create index if not exists idx_parcels_client_score on parcels (client_id, lead_score desc);
create index if not exists idx_parcels_needs_review on parcels (client_id) where needs_review;

-- Storm/hail event history, bulk-loaded from NOAA NCEI's Storm Events
-- Database. Deliberately global (no client_id) and NOT flattened into
-- `parcels`: a storm event is an objective fact about a county,
-- independent of which client's dashboard is asking about it -- same
-- reasoning as oppscanner's `sources` registry table being
-- client-agnostic. Deduped on NOAA's own `event_id`, not a guessed
-- composite key -- a county can have two genuinely distinct hail events
-- on the same calendar day.
create table if not exists storm_events (
    id uuid primary key default gen_random_uuid(),
    event_id text not null,
    county text not null,
    state text not null,
    event_date date not null,
    event_type text not null,
    magnitude text,
    narrative text,
    property_damage_estimate numeric,
    source text not null default 'noaa_ncei',
    raw_data jsonb,
    created_at timestamptz not null default now(),
    unique (source, event_id)
);

alter table storm_events enable row level security;

create index if not exists idx_storm_events_county_state_date
    on storm_events (county, state, event_date);
