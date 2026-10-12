-- 008_add_lead_pipeline.sql
-- Shared Google Sheet working-pipeline (Prompt V). Replaces
-- `lead_digest_sends` as the dedup source digest selection checks: that
-- table now means only "was in a sent email" (still written, as a sent
-- log, after a real send -- see `scripts/send_lead_digest.py`),
-- `lead_pipeline` means "a lead that's been surfaced to the team at all,
-- and what's happened to it since" -- worked leads stay visible on the
-- shared Sheet with their status and are never re-surfaced as new.
--
-- `lead_key` is "{town}:{parcel_id}", not a minted hash: `parcels`'
-- own `unique (client_id, town, parcel_id)` constraint (001_init_schema.sql)
-- already guarantees `(town, parcel_id)` uniquely identifies a parcel row
-- within one client -- verified live (2026-10-12) against the real
-- 1,600-row NECC population: zero duplicate `(town, parcel_id)` pairs,
-- 1,600 distinct keys for 1,600 rows. `lead_pipeline` itself is additionally
-- scoped by `client_id` (`unique (client_id, lead_key)`), so two different
-- clients could in theory mint the same lead_key string with no collision.
--
-- `status`/`owner`/`notes` are human-owned fields: the shared Google Sheet
-- (Master tab) is the source of truth for them, and a pull step mirrors the
-- Sheet's current values into this table before each digest cycle's
-- selection runs (see `extscorer_full`'s sheets sync module) -- this table
-- is never the place a human edits those fields directly.

create table if not exists lead_pipeline (
    id uuid primary key default gen_random_uuid(),
    client_id text not null,
    lead_key text not null,
    parcel_id uuid not null references parcels(id) on delete cascade,
    date_added date not null default current_date,
    status text not null default 'new',
    owner text,
    notes text,
    last_updated timestamptz not null default now(),
    unique (client_id, lead_key)
);

alter table lead_pipeline enable row level security;

create index if not exists idx_lead_pipeline_client_lead_key
    on lead_pipeline (client_id, lead_key);
