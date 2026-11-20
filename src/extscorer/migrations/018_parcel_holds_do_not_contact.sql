-- 018_parcel_holds_do_not_contact.sql
-- Adds the hold kind 'do_not_contact' to `parcel_holds`: a PERMANENT hold (a home the owner or the town has said stays out of outreach),
-- unlike 'data_review' / 'shown_to_crew', which are temporary and expected to be cleared by a review. Code that clears holds in bulk
-- (`release_parcel_holds`) skips permanent kinds unless it is told, in so many words, to include them.
--
-- Only the CHECK on `kind` changes. Idempotent (this runner replays every migration): the constraint is dropped if present and re-added
-- with the wider list; every existing row already satisfies it. 017 names nothing explicitly, so Postgres called it parcel_holds_kind_check.
alter table parcel_holds drop constraint if exists parcel_holds_kind_check;
alter table parcel_holds add constraint parcel_holds_kind_check check (kind in ('shown_to_crew', 'data_review', 'other', 'do_not_contact'));
