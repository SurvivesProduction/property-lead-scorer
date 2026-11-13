-- 016_add_parcel_load_log.sql
-- Adds `parcel_load_log`: an append-only record of every value a load, backfill or re-scrape changed on `parcels`
-- (the field, its value before, its value after, which load and run wrote it). It replaces the per-load "rollback
-- blob" in parcels.raw_data, which a later write to the same key or a re-scrape could overwrite.
--
--   load_key   names the load ('town_assessor_2026_11', 'warren_canterbury_2026_11_12', 'scrape:run_client' ...)
--   run_id     one uuid per script invocation, so a whole run can be found and undone together
--   field      a `parcels` column, or '__insert__' for a row a load created
--   before/after_value  jsonb; a JSON null is a blank. 'after' of a row copied from an old rollback blob is the value
--              stored when it was copied (source = 'migration', see meta)
--   parcel_uuid has NO foreign key on purpose: deleting a parcel must never delete its history.
--
-- Append-only: UPDATE, DELETE and TRUNCATE raise for every role, the owner included. Row level security is on with no
-- policy, like every other table here, so the Data API cannot read it either.
--
-- Additive and idempotent (this runner replays every migration): the table and indexes are `if not exists`, the
-- function is `create or replace`, the triggers are dropped and recreated. Nothing in `parcels` changes.
create table if not exists parcel_load_log (
    id           bigint generated always as identity primary key,
    client_id    text        not null,
    parcel_uuid  uuid        not null,
    town         text        not null,
    parcel_key   text        not null,
    load_key     text        not null,
    run_id       uuid        not null,
    script       text        not null,
    field        text        not null,
    before_value jsonb,
    after_value  jsonb,
    source       text        not null default 'live' check (source in ('live', 'migration')),
    meta         jsonb,
    written_at   timestamptz not null default now()
);

alter table parcel_load_log enable row level security;

create index if not exists idx_parcel_load_log_parcel_field on parcel_load_log (parcel_uuid, field, id desc);
create index if not exists idx_parcel_load_log_load_run on parcel_load_log (load_key, run_id);
create unique index if not exists uq_parcel_load_log_migration_copy
    on parcel_load_log (parcel_uuid, load_key, field) where source = 'migration';

create or replace function parcel_load_log_append_only() returns trigger language plpgsql as $$
begin
    raise exception 'parcel_load_log is append-only: % is not allowed', tg_op;
end;
$$;

drop trigger if exists parcel_load_log_no_update_delete on parcel_load_log;
create trigger parcel_load_log_no_update_delete
    before update or delete on parcel_load_log
    for each row execute function parcel_load_log_append_only();

drop trigger if exists parcel_load_log_no_truncate on parcel_load_log;
create trigger parcel_load_log_no_truncate
    before truncate on parcel_load_log
    for each statement execute function parcel_load_log_append_only();
