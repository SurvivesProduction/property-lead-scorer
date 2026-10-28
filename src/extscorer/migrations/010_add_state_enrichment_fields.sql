-- 010_add_state_enrichment_fields.sql
-- Adds the columns needed to merge the state CAMA FeatureServer layer into
-- `parcels` (docs/state-featureserver-audit-2026-10-28.md in the -full
-- repo is the audit this migration implements).
--
-- `last_sale_date`/`last_sale_price` are NOT added here -- they already
-- exist (009_add_cama_fields.sql, built for Windham's CAMA ingestion).
-- This migration only adds what's genuinely new.
--
-- `assessed_value` -- a field NONE of the 8 scraper towns' sources
-- (VGSI, propertyrecordcards.com) have ever exposed; the audit confirmed
-- this is a total gap on our side, not a column that already existed
-- under a different name.
--
-- `state_parcel_ref` (jsonb, not text) -- keeps all 4 of the state
-- layer's own id-ish fields (Parcel_ID/CAMA_Link/Link/link_1) together
-- for reference, since the audit found they're 4 DISTINCT columns, not
-- redundant copies of one id. Deliberately NOT used as a join key by any
-- merge script -- the audit found literal link-ID matching produces
-- only town-specific coincidental collisions (confirmed for Thompson:
-- real, but a one-town fluke, not a generalizable key), so this column
-- exists purely so a human reading a parcel row later can see what the
-- state layer called it, never for a WHERE clause.
--
-- `enrichment_status` -- distinguishes a row this project actually
-- scraped (VGSI/propertyrecordcards.com, full signal set: siding, real
-- permits, a stable per-parcel card URL) from a row that exists ONLY
-- because the state layer's full-town coverage added it (no card URL,
-- no permit visibility, proxy-only siding signal at best). Scoring and
-- the digest/Sheet pipeline both need to tell these apart -- a
-- 'state_only' row is provisional until a real scrape confirms it, see
-- the -full repo's merge/backfill scripts for how this gates digest
-- selection. Existing rows default to 'scraped' via the column default
-- itself (Postgres applies a column default to every existing row when
-- the column is added, no backfill UPDATE needed); every row this
-- migration's own merge step inserts sets 'state_only' explicitly.
--
-- Safe to rerun: `add column if not exists` is idempotent.

alter table parcels
    add column if not exists assessed_value numeric;

alter table parcels
    add column if not exists state_parcel_ref jsonb;

alter table parcels
    add column if not exists enrichment_status text not null default 'scraped';

-- Plain `add constraint if not exists` isn't valid Postgres syntax (only
-- `add column if not exists` is) -- wrapped in a DO block so this
-- migration stays genuinely safe to rerun, same guarantee every other
-- statement here already has.
do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'parcels_enrichment_status_check'
    ) then
        alter table parcels
            add constraint parcels_enrichment_status_check
                check (enrichment_status in ('scraped', 'state_only'));
    end if;
end $$;

create index if not exists idx_parcels_enrichment_status
    on parcels (client_id, enrichment_status);
