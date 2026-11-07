-- 013_add_roof_only_candidate.sql
-- Adds `parcels.roof_only_candidate`: a masonry-only exterior (brick, stone, stucco, concrete, block) with no siding
-- permit on file. Such a house cannot be re-sided, so it is not a siding lead; it can still need a roof. The scorer
-- (`masonry_siding_zero`) gives it a siding component of 0 and sets this flag. NOTHING SELECTS ON THIS FLAG YET: it is
-- stored so a roof campaign can use it later.
-- NULL means "not computed yet", treated like false by every consumer.
--
-- Additive and idempotent: one nullable boolean column, no default, no rewrite of existing rows. RLS is untouched.
alter table parcels add column if not exists roof_only_candidate boolean;
