"""Pure lead-selection logic for a client-facing lead digest email.

Deliberately NOT Tool 1's `first_seen_at`-since-last-run model -- see
`extscorer.migrations.003_add_lead_digest_sends`'s docstring for why a
per-parcel send log fits a once-built, statically-scraped dataset (Tool
4's real shape) better than a data-freshness cutoff does.
"""
from __future__ import annotations

from typing import Any

from extscorer.lead_pipeline import lead_key

DEFAULT_LEADS_PER_DIGEST = 20
"""Widened from 10 (2026-09-15, Prompt U, explicit client request) now
that likely-vacant/absentee-owned properties are filtered out of the
digest entirely (see `is_likely_unreachable_owner` below) -- with real
leads removed from candidacy, a longer list keeps the digest as useful
per-send as the original 10-lead default was. Still NOT 25 (Prompt N's
full review export size) -- Darren runs a small, word-of-mouth-driven
crew on a 3-weeks-on/3-weeks-off cycle; a real, deliberate number in real
code, not final."""


def filter_sold_territory(
    parcels: list[dict[str, Any]], sold_towns: list[str] | None
) -> list[dict[str, Any]]:
    """Restrict `parcels` to rows whose `town` is in `sold_towns` -- the
    gate that keeps an unsold/not-yet-contracted town's data (added to the
    DB for scoring/export/dashboard purposes, e.g. a spike or a new-town
    build in progress) out of a client's digest/Sheet pipeline specifically.

    `sold_towns=None` means "no restriction" (every existing client's
    default, same as `load_scoring_overrides`'s "config doesn't set it ->
    no override" convention) -- a client with no `sold_towns:` key in its
    config.yaml sees no behavior change at all. Comparison is
    case-insensitive on the stored `town` string (`parcel["town"]`), since
    that's a source module's own hardcoded display-case constant (e.g.
    `CanterburyVgsiSource.town = "Canterbury"`), not a normalized key.

    This is deliberately NOT applied inside `rank_candidates`/
    `score_property` itself, and NOT applied in `scripts/
    generate_lead_dashboard.py` or `scripts/backfill_lead_scores.py` --
    an unsold town's parcels still get scored and still show up in the
    internal, Noah-facing dashboard/export (useful for exactly the kind
    of "is this town worth building" evaluation a new-town build/spike is
    for). The gate is applied at exactly one choke point:
    `extscorer_full.sheets.sync.run_sync_cycle`'s own parcel fetch, which
    is what both the Sheet push and the digest email derive their
    candidate list from.
    """
    if sold_towns is None:
        return parcels
    allowed = {town.strip().lower() for town in sold_towns}
    return [parcel for parcel in parcels if (parcel.get("town") or "").strip().lower() in allowed]


def is_likely_unreachable_owner(parcel: dict[str, Any]) -> bool:
    """True if this parcel should be excluded from the digest as a likely
    vacant or absentee-owned property -- a real property records show is
    old/exposed/under-maintained is a much weaker lead if there's no
    owner actually living there to pitch, or the town shows the taxes
    aren't being kept current (both real signals a property may be
    vacant, in an estate, or otherwise not a live sales conversation).

    Checks two independent real signals, either one triggers exclusion:
    `is_absentee_owner` (the owner's own mailing address doesn't match
    the property's address -- computed at scrape/enrichment time, see
    `extscorer.sources.vgsi.normalize_vgsi_parcel`/
    `extscorer_full.sources.propertyrecordcards.normalize_prc_parcel`)
    and `has_tax_delinquency` (a real outstanding balance on file with
    the town, from `extscorer_full`'s mytaxbill.org backfill). Both
    default to `False`/absent when not yet computed for a parcel (an
    older row from before this signal existed, or one whose enrichment
    pass hasn't run yet) -- deliberately NOT excluded in that case, since
    "unknown" must not be treated as "confirmed vacant."
    """
    return bool(parcel.get("is_absentee_owner")) or bool(parcel.get("has_tax_delinquency"))


def is_unverified_state_only(parcel: dict[str, Any]) -> bool:
    """True if this parcel has never been independently scraped -- it only
    exists because the state CAMA layer's full-town coverage added it
    (2026-10-28, see property-lead-scorer-full's docs/state-featureserver-
    audit-2026-10-28.md). Excluded from the digest/Sheet pipeline entirely,
    same treatment as `is_likely_unreachable_owner`: it still scores and
    still shows on the internal dashboard (useful for picking a Phase 2
    enrichment candidate list), it just never reaches Darren until a real
    VGSI/propertyrecordcards.com scrape (plus permits/mytaxbill) confirms
    it -- no stable per-parcel card URL, no real siding/roof data, no
    permit visibility to back up a `state_only` row's score yet.

    Defaults to `False` (not excluded) for any parcel predating this
    column -- `enrichment_status` itself defaults to `'scraped'` at the
    schema level (migration `010_add_state_enrichment_fields.sql`), so
    this only ever actually triggers for a genuine state-only row, never
    as a side effect of an older row simply not having the column
    computed yet (unlike `is_absentee_owner`/`has_tax_delinquency`, there
    is no "unknown" state here to worry about conflating with "excluded").
    """
    return parcel.get("enrichment_status") == "state_only"


def select_unsent_leads(
    ranked_leads_with_parcels: list[tuple[Any, dict[str, Any]]],
    already_sent_parcel_row_ids: set[Any],
    limit: int = DEFAULT_LEADS_PER_DIGEST,
) -> list[tuple[Any, dict[str, Any]]]:
    """Filter an already-ranked list of `(LeadScore, raw_parcel_dict)`
    pairs -- `rank_candidates`'s own deterministic order, tiebreak
    included, zipped against each lead's own source parcel row -- down to
    the top `limit` pairs whose `raw_parcel_dict["id"]` (the real
    `parcels.id` primary key) is NOT already in `already_sent_parcel_row_ids`,
    and which aren't flagged `is_likely_unreachable_owner` (2026-09-15,
    Prompt U -- excluded from the digest entirely, not merely
    deprioritized, since a likely-vacant/absentee property is a much
    weaker lead regardless of how it otherwise scored; it still stays in
    `rank_candidates`'s own output and the internal dashboard, which
    intentionally shows everything for debugging).

    Pairs, not a `LeadScore`-only list, specifically so this stays a pure
    function with no dependency on `extscorer.scoring.basic.LeadScore`'s
    own shape (that dataclass carries the town-scoped `parcel_id` string,
    not the row's real primary key, and isn't touched by this digest
    work -- scoring changes are out of scope here).

    `limit <= 0` returns `[]` immediately -- without this guard the loop
    below still appends exactly one lead before its own `break` check
    fires, since the check runs after the append (2026-10-13, found while
    building Tool 4's backlog-cap feature, which legitimately calls this
    with `limit=0` whenever the open-"new" backlog is already full).
    """
    if limit <= 0:
        return []
    selected = []
    for lead, parcel in ranked_leads_with_parcels:
        if parcel["id"] in already_sent_parcel_row_ids:
            continue
        if is_likely_unreachable_owner(parcel):
            continue
        if is_unverified_state_only(parcel):
            continue
        selected.append((lead, parcel))
        if len(selected) >= limit:
            break
    return selected


def select_new_leads_for_pipeline(
    ranked_leads_with_parcels: list[tuple[Any, dict[str, Any]]],
    existing_pipeline_lead_keys: set[str],
    limit: int = DEFAULT_LEADS_PER_DIGEST,
) -> list[tuple[Any, dict[str, Any]]]:
    """Prompt V's replacement for `select_unsent_leads`'s dedup source.

    Same ranked-pairs shape and same `is_likely_unreachable_owner`
    exclusion as `select_unsent_leads`, but the dedup check is now "is
    this lead's `lead_key` already in `lead_pipeline`" (regardless of
    that row's `status` -- a lead marked `dead` or `won` is still a lead
    that's been surfaced, and must never come back as new) rather than
    "is this parcel's row id already in `lead_digest_sends`". The shared
    Google Sheet's Master tab mirrors `lead_pipeline` 1:1 (see
    `extscorer_full`'s sheets sync module), so this is equivalently "skip
    every lead already on Master or in lead_pipeline" per the prompt's own
    phrasing -- `lead_pipeline` is checked directly here since the Sheet
    itself was already pulled into it earlier in the same digest cycle.

    `lead_digest_sends` is untouched by this function -- it keeps meaning
    "was in a sent email" (see that table's own migration docstring),
    recorded only after a real, non-review send, independent of this
    pipeline-based selection.

    `limit <= 0` returns `[]` immediately -- same guard and reason as
    `select_unsent_leads` above.
    """
    if limit <= 0:
        return []
    selected = []
    for lead, parcel in ranked_leads_with_parcels:
        if lead_key(parcel["town"], parcel["parcel_id"]) in existing_pipeline_lead_keys:
            continue
        if is_likely_unreachable_owner(parcel):
            continue
        if is_unverified_state_only(parcel):
            continue
        selected.append((lead, parcel))
        if len(selected) >= limit:
            break
    return selected
