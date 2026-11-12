-- 015_add_warren_building_fields.sql
-- Adds three building fields that a town's Warren Group (Vision CAMA) extract carries and `parcels` had no column for:
--   style_code      the Vision style CODE as text, leading zeros kept ('01', not 1). The extract has only the code, no
--                   description; what a code means is a per-town table nobody has sent yet, so nothing decodes it here.
--   roof_structure  the roof shape as the town spells it ('Gable', 'Gambrel', 'Hip', 'Salt Box', 'Shed', 'Flat').
--   stories         the numeric Stories field (1, 1.5, 1.75, 2, ...), not the sparse description text.
-- Written only by `refresh_town_from_warren.py` (property-lead-scorer-full), blank never overwrites. NULL means "not loaded".
-- NOTHING SELECTS ON THESE COLUMNS YET and the Job Board export does not carry them.
--
-- Additive and idempotent: three nullable columns, no default, no rewrite of existing rows. RLS is untouched.
alter table parcels add column if not exists style_code text;
alter table parcels add column if not exists roof_structure text;
alter table parcels add column if not exists stories numeric(4, 2);
