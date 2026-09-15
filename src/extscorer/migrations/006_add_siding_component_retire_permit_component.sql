-- Retires the standalone `score_permit_component` column: as of 2026-09-15
-- (Prompt S) permit history is no longer a separately-weighted top-level
-- signal -- its information is folded into the new unified siding signal
-- (`extscorer.scoring.basic.real_siding_age_score`, dispatched to by
-- `siding_score()`), which persists to `score_siding_component` instead.
-- `permit_data_available`/`permit_history`/`exterior_permit_count`/
-- `most_recent_exterior_permit_date`/`most_recent_exterior_permit_type`
-- are all unchanged -- they're still real input DATA the new siding
-- signal reads directly; only the separate SCORE OUTPUT column is
-- retired, since keeping it around unwritten would just leave a
-- permanently-stale value once backfill_lead_scores.py stops writing it.
--
-- Safe to rerun: `add column if not exists` / `drop column if exists`
-- are both idempotent.

alter table parcels
    add column if not exists score_siding_component numeric;

alter table parcels
    drop column if exists score_permit_component;
