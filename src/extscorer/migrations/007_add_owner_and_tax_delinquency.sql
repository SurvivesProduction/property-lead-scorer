-- Adds the vacancy/occupancy signal's real underlying columns (2026-09-15,
-- Prompt U): a mismatch between a parcel's own address and its owner's
-- mailing address, or a real outstanding tax balance on file with the
-- parcel's town, either one is grounds to exclude a lead from the
-- client-facing digest (see `extscorer.digest.selection
-- .is_likely_unreachable_owner`) even though it still scores and appears
-- on the internal dashboard.
--
-- `owner_name`/`owner_mailing_address`/`is_absentee_owner` are
-- scrape-native (both VGSI and propertyrecordcards.com expose a real
-- owner-of-record mailing address; `is_absentee_owner` is computed at
-- normalize time from the other two) -- blind-overwrite on upsert, same
-- treatment as every other scrape-native field.
--
-- `has_tax_delinquency`/`tax_outstanding_balance` are enrichment-only,
-- populated by `property-lead-scorer-full/scripts
-- /backfill_tax_delinquency.py` against mytaxbill.org well after the
-- initial scrape -- COALESCE-protected on upsert, same treatment as
-- `pct_tree_canopy_nearby`/`latitude`/`longitude`, so a re-scrape can
-- never silently wipe a real delinquency finding.
--
-- Safe to rerun: `add column if not exists` is idempotent.

alter table parcels
    add column if not exists owner_name text;

alter table parcels
    add column if not exists owner_mailing_address text;

alter table parcels
    add column if not exists is_absentee_owner boolean not null default false;

alter table parcels
    add column if not exists has_tax_delinquency boolean not null default false;

alter table parcels
    add column if not exists tax_outstanding_balance numeric;
