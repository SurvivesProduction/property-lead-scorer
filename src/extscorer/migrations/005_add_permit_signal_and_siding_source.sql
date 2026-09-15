-- Adds real permit-history fields and a siding-data-provenance marker to
-- parcels, for the two new eQuality Valuation Services (propertyrecordcards.com)
-- towns (Killingly, Ashford) and Woodstock's enrichment backfill from the
-- same source (2026-09-15).
--
-- Unlike exterior_wall_1/exterior_wall_2 (VGSI's proxy material field,
-- 004_add_exterior_wall_and_pct_good.sql), propertyrecordcards.com exposes
-- REAL per-parcel permit history (permit number, type, date opened,
-- reason) and a direct "Siding:" field -- not a heuristic. permit_history
-- stores every permit found (not just exterior-relevant ones) for
-- transparency/debugging; exterior_permit_count/most_recent_exterior_*
-- are denormalized from the subset classified as exterior-relevant
-- (siding/roof/window/gutter keyword match against type+reason text --
-- see extscorer_full.sources.propertyrecordcards._is_exterior_permit),
-- same "cache a computed summary on the parcel row so scoring stays
-- debuggable without unpacking raw_data" precedent nearest_storm_event_date
-- already established.
--
-- permit_data_available distinguishes "this town's source doesn't expose
-- permit history at all" (VGSI towns -- false, exterior_permit_count stays
-- NULL, the permit signal is not evaluated) from "checked, genuinely zero
-- permits on file" (eQS towns with no permit history at all -- true,
-- exterior_permit_count = 0, a real informative value). See
-- extscorer.scoring.basic.permit_history_score's docstring.
--
-- siding_data_source records which field a parcel's exterior_wall_1
-- actually came from ('vgsi_exterior_wall_proxy' vs
-- 'eqs_direct_siding_field') -- both are stored in the SAME column
-- (exterior_wall_1) since they represent the same underlying concept
-- (current exterior material), but this marker keeps the provenance
-- honest for anyone reading the data directly.
--
-- Safe to rerun: `add column if not exists` is idempotent.

alter table parcels
    add column if not exists permit_data_available boolean not null default false,
    add column if not exists permit_history jsonb not null default '[]'::jsonb,
    add column if not exists exterior_permit_count int,
    add column if not exists most_recent_exterior_permit_date date,
    add column if not exists most_recent_exterior_permit_type text,
    add column if not exists siding_data_source text,
    add column if not exists score_permit_component numeric;
