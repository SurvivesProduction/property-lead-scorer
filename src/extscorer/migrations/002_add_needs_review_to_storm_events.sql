-- Adds needs_review/review_reason to storm_events, matching the same
-- discipline `parcels` already has (and the same discipline Tool 3's
-- OpportunityRecord adopted after the fact) -- a storm-event row with an
-- unparseable date or missing critical field gets flagged for a human,
-- never silently dropped or guessed at. Prompt A's original schema
-- predated this requirement; this migration catches storm_events up to
-- it before the NOAA fetcher (which needs it) is built.
--
-- `event_date` is relaxed to nullable for the same reason: a raw NOAA row
-- with a genuinely unparseable BEGIN_DATE_TIME still gets persisted
-- (flagged, not dropped) so a human can see and fix it, rather than
-- vanishing from the pipeline invisibly -- there's no sensible non-null
-- placeholder date the way `parcels.address` can fall back to `''`.
--
-- Safe to rerun: `add column if not exists` and dropping a constraint
-- that's already gone are both idempotent.

alter table storm_events
    add column if not exists needs_review boolean not null default false,
    add column if not exists review_reason text;

alter table storm_events
    alter column event_date drop not null;
