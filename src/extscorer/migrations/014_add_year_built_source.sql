-- 014_add_year_built_source.sql
-- Adds `parcels.year_built_source`: where the build year used for scoring came from.
--   actual              the recorded year_built (the default)
--   effective_fallback  year_built is the 1900 placeholder and `effective_year_built` was used instead
--   unknown             year_built is the 1900 placeholder with no usable effective year: age scored neutral
-- NULL means "not computed yet", treated like actual by every consumer. Written by `backfill_lead_scores` (property-lead-scorer-full)
-- when the `year_built_placeholder_fallback` switch is on.
--
-- Additive and idempotent: one nullable column and one CHECK constraint, no default, no rewrite of existing rows. RLS is untouched.
alter table parcels add column if not exists year_built_source text;

do $$
begin
    if not exists (select 1 from pg_constraint where conname = 'parcels_year_built_source_check') then
        alter table parcels
            add constraint parcels_year_built_source_check
            check (year_built_source in ('actual', 'effective_fallback', 'unknown'));
    end if;
end $$;
