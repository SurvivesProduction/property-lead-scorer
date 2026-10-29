-- 011_add_mail_drops.sql
-- Mail-drop tracking (2026-10-29 follow-up to the first NECC mail-list
-- export, see property-lead-scorer-full's docs/TOOL4_OPEN_ITEMS.md item
-- 1) -- so a parcel that's already queued for (or confirmed sent on) a
-- physical mailing doesn't also get re-surfaced as a brand-new digest/
-- Sheet lead, and so rolling enrichment's own per-town pool count
-- doesn't treat a mailed parcel as still available to enrich. Two
-- tables, same client_id-scoped + RLS-at-creation pattern every other
-- table here already uses.
--
-- `mail_drops` is one row per physical mailing batch ("NECC drop 1",
-- "NECC drop 2", ...). `status` starts 'planned' (export written, cards
-- not yet in the mail) and moves to 'sent' once the user confirms the
-- drop actually went out (see scripts/mark_mail_drop_sent.py in the full
-- repo). BOTH states exclude a parcel from new-lead selection (see
-- extscorer.digest.selection.is_on_active_mail_drop) -- a lead already
-- queued for a physical mailing shouldn't also show up as a brand-new
-- digest pick, whether or not the postcard has physically shipped yet.
--
-- `mail_drop_parcels` is one row per parcel on a given drop.
-- `parcel_id` (same confusingly-reused name `lead_pipeline.parcel_id`
-- already established, see that migration's own comment) is
-- `parcels.id`, the real UUID primary key -- NOT `parcels.parcel_id`,
-- that table's own scraper-native text id. `address_snapshot`/
-- `recipient_line` freeze what was actually printed on the mailer at
-- export time, independent of whatever `parcels.address` says later (a
-- correction, a re-scrape) -- this table is a record of what was
-- mailed, not a live view of the parcel.
--
-- Safe to rerun: every statement uses an `if not exists` guard.

create table if not exists mail_drops (
    id uuid primary key default gen_random_uuid(),
    client_id text not null,
    drop_name text not null,
    status text not null default 'planned',
    planned_at timestamptz not null default now(),
    sent_at timestamptz,
    unique (client_id, drop_name)
);

do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'mail_drops_status_check'
    ) then
        alter table mail_drops
            add constraint mail_drops_status_check
                check (status in ('planned', 'sent'));
    end if;
end $$;

alter table mail_drops enable row level security;

create index if not exists idx_mail_drops_client on mail_drops (client_id);

create table if not exists mail_drop_parcels (
    id uuid primary key default gen_random_uuid(),
    drop_id uuid not null references mail_drops(id) on delete cascade,
    parcel_id uuid not null references parcels(id) on delete cascade,
    address_snapshot text not null,
    recipient_line text not null,
    created_at timestamptz not null default now(),
    unique (drop_id, parcel_id)
);

alter table mail_drop_parcels enable row level security;

create index if not exists idx_mail_drop_parcels_drop on mail_drop_parcels (drop_id);
create index if not exists idx_mail_drop_parcels_parcel on mail_drop_parcels (parcel_id);
