-- Adds the CT statewide Parcel+CAMA dataset's own fields that have no
-- existing equivalent column (2026-10-26, Windham build):
--
-- `effective_year_built` (CAMA's `eyb`) -- the assessor's own
-- condition-restated-as-a-year figure. Verified (Windham spike,
-- FINDINGS.md) to correlate -0.96 with CAMA's `depreciation`, i.e. it's
-- essentially `building_percent_good` restated as a year, not an
-- independent renovation date -- kept as its own column anyway (not
-- derived/dropped) since it's a real field a human reviewing a parcel
-- may want to see directly, and a future town/dataset could have it
-- diverge further from percent-good than Windham's did.
--
-- `cama_permit_count` -- CAMA's own `permit_count`, a coarse "N permits
-- of SOME kind, ever, no dates/types" count. Deliberately a SEPARATE
-- column from `exterior_permit_count` (which means "N real, dated,
-- exterior-relevant permits" from propertyrecordcards.com/PermitLink) --
-- conflating the two would silently overstate exterior-relevant permit
-- confidence for any CAMA-sourced parcel. See `extscorer.scoring.basic`'s
-- siding-signal dispatch for why this column is NOT read by
-- `permit_data_available`'s gate.
--
-- `outbuilding_count` -- CAMA's own count, no type/year/condition detail
-- (the barn-vs-shed distinction CAMA can't make -- see Windham
-- FINDINGS.md's Q2/Q3/Q5 section). Not yet consumed by any scoring
-- signal this migration -- a future "barn angle" pass, not this one.
--
-- `last_sale_date`/`last_sale_price` -- no existing column captured sale
-- data at all (checked: zero references anywhere in either Tool 4 repo)
-- even though CAMA (and, per the Windham spike, presumably other
-- assessor sources too) exposes it directly. Added here since the
-- Windham build's field-mapping needs it, not as a new scoring signal --
-- nothing reads these two columns yet.
--
-- `source_dataset_id`/`source_fetch_date` -- generic provenance fields
-- (not CAMA-specific by name, since any future bulk-dataset source could
-- use them the same way) recording which dataset a parcel's CAMA-sourced
-- fields came from and when they were fetched, so staleness (the CT CAMA
-- dataset is an annual valuation snapshot, not a live feed) is visible
-- on the row itself rather than only in a script's own console output.
-- `None` for any parcel from a non-dataset (per-page scrape) source.
--
-- Safe to rerun: `add column if not exists` is idempotent.

alter table parcels
    add column if not exists effective_year_built int;

alter table parcels
    add column if not exists cama_permit_count int;

alter table parcels
    add column if not exists outbuilding_count int;

alter table parcels
    add column if not exists last_sale_date date;

alter table parcels
    add column if not exists last_sale_price numeric;

alter table parcels
    add column if not exists source_dataset_id text;

alter table parcels
    add column if not exists source_fetch_date date;

-- `permit_history_since` -- the earliest date this parcel's town's REAL
-- permit source can actually attest to (NOT a CAMA field at all -- an
-- enrichment field written by whatever pass populates
-- `permit_data_available`/`permit_history`, e.g. Windham's PermitLink
-- crawl in permit-history-enrichment-full). `NULL` (the default, and
-- every pre-Windham permit-visible town's value) means "this source's
-- history is long/established enough that 'no permit on file' can be
-- trusted as a genuine never-redone signal" -- unchanged behavior for
-- Killingly/Ashford/Woodstock/Brooklyn/Pomfret/Thompson. A real date
-- (Windham: 2026-04-15, PermitLink's own portal launch) means the
-- opposite: `extscorer.scoring.basic.real_siding_age_score` must NOT
-- treat "no permit found" as "never redone since year_built" for a
-- parcel whose town's permit visibility only goes back a few months --
-- see that function's own docstring for the fallback-to-proxy fix.
alter table parcels
    add column if not exists permit_history_since date;
