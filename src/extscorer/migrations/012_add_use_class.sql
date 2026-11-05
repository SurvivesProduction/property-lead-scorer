-- 012_add_use_class.sql
-- Adds `parcels.use_class`: is this parcel a home we can sell exterior work on?
--   residential              a dwelling
--   farm_forest_residential  a dwelling on farm/forest ("Use Assessment") land; stays eligible
--   non_residential          industrial / commercial / school / church / municipal; still scored,
--                            but excluded from the digest, the Job Board export and mail drops
--   unknown                  no evidence or genuinely mixed; stays eligible
-- NULL means "not classified yet" and is treated like unknown by every consumer, so applying this
-- migration changes nothing until `scripts/backfill_use_class.py` (property-lead-scorer-full) runs.
--
-- Additive and idempotent: one nullable column and one CHECK constraint, no default, no rewrite of
-- existing rows. RLS is untouched (the column inherits the table's policy).
alter table parcels add column if not exists use_class text;

do $$
begin
    if not exists (select 1 from pg_constraint where conname = 'parcels_use_class_check') then
        alter table parcels
            add constraint parcels_use_class_check
            check (use_class in ('residential', 'farm_forest_residential', 'non_residential', 'unknown'));
    end if;
end
$$;

comment on column parcels.use_class is
    'residential | farm_forest_residential | non_residential | unknown; NULL = not classified yet. Derived by extscorer.normalize.use_class.';
