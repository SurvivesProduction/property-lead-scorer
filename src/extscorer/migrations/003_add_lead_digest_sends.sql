-- Tracks which specific parcels have already appeared in a sent lead
-- digest email, per client. Unlike Elite Electric's own `digest_runs`
-- table (a coarse per-run count, keyed on data-freshness via
-- `first_seen_at`), Tool 4's leads come from a one-time-built, static
-- dataset with no recurring re-crawl -- there's no "new since last run"
-- signal to key dedup off. Instead, dedup is per-PARCEL: a future send
-- (whenever a recurring schedule exists) selects the next-best leads NOT
-- already in this table for the client, rather than repeating an address
-- Darren has already been shown.
--
-- A row is inserted only AFTER a successful send (see
-- property-lead-scorer-full's send_lead_digest.py) -- a failed send must
-- not falsely mark a lead as delivered, same discipline Tool 1's
-- `digest_runs` already follows.

create table if not exists lead_digest_sends (
    id uuid primary key default gen_random_uuid(),
    client_id text not null,
    parcel_id uuid not null references parcels(id) on delete cascade,
    sent_at timestamptz not null default now()
);

alter table lead_digest_sends enable row level security;

create index if not exists idx_lead_digest_sends_client_parcel
    on lead_digest_sends (client_id, parcel_id);
