-- Adds exterior_wall_1/exterior_wall_2/building_percent_good to parcels,
-- for the siding-age lead signal (wall material + year built, with
-- Percent Good as a condition-proxy modifier).
--
-- Field audit (2026-09-10, live-sampled 90 real cards across all 6 towns)
-- found Exterior Wall 1/2 are already present in the same "Building
-- Attributes" table roof_cover_material/style already read (~100% fill on
-- real dwellings), and a separate "Building Percent Good" field (VGSI's
-- real equivalent of a depreciation percent -- no literal "Dep %" label
-- exists on VGSI) is present on 5 of 6 towns. Pomfret's card template
-- genuinely lacks the Percent Good block entirely -- expect a real,
-- permanent 0% fill rate there, not a bug. Year Remodeled/Remodel
-- Rating/Condition/Building Permit Record were also audited and found NOT
-- present on single-family cards (only on the rare Condo template) --
-- deliberately not added here.
--
-- Safe to rerun: `add column if not exists` is idempotent.

alter table parcels
    add column if not exists exterior_wall_1 text,
    add column if not exists exterior_wall_2 text,
    add column if not exists building_percent_good int;
