-- 017_add_parcel_holds.sql
-- Adds `parcel_holds`: a manual, per-parcel "keep this home out of outreach" record. A parcel is HELD while it has at
-- least one row with `released_at IS NULL`; releasing a hold sets `released_at` (the row stays, so the history of who held
-- what and why is kept), and a parcel can carry more than one active hold at a time.
--
--   kind         why, in one word: 'shown_to_crew' (already shown to a crew), 'data_review' (the data is in doubt, e.g. a
--                stale year pending a Street View check), 'other'
--   reason       free text, required
--   held_by      who placed it; held_at when
--   released_at  NULL while the hold is active; released_by who released it
--
-- This is a separate table, not a column on `parcels`, on purpose: no scraper or load upserts this table, so a re-scrape
-- can never wipe a hold. Every selection path reads the active holds through `parcels_for_client`, which annotates each
-- parcel (`on_hold`, `holds`); `extscorer.digest.selection.is_held` is the predicate.
--
-- parcel_uuid is a real foreign key (unlike parcel_load_log): a held parcel cannot be deleted out from under its hold. No code
-- deletes parcels today. client_id is repeated here so a hold can be read without joining.
--
-- Row level security is on with no policy, like every other table here, so the Data API cannot read it.
-- Additive and idempotent (this runner replays every migration): the table and indexes are `if not exists`. Nothing in
-- `parcels` changes.
create table if not exists parcel_holds (
    id           bigint generated always as identity primary key,
    client_id    text        not null,
    parcel_uuid  uuid        not null references parcels (id),
    kind         text        not null check (kind in ('shown_to_crew', 'data_review', 'other')),
    reason       text        not null check (length(btrim(reason)) > 0),
    held_by      text        not null check (length(btrim(held_by)) > 0),
    held_at      timestamptz not null default now(),
    released_at  timestamptz,
    released_by  text,
    check (released_at is null or released_at >= held_at),
    check ((released_at is null) = (released_by is null))
);

alter table parcel_holds enable row level security;

create index if not exists idx_parcel_holds_active_parcel on parcel_holds (parcel_uuid) where released_at is null;
create index if not exists idx_parcel_holds_active_client on parcel_holds (client_id) where released_at is null;
