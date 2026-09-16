"""Pure lead-selection logic for a client-facing lead digest email.

Deliberately NOT Tool 1's `first_seen_at`-since-last-run model -- see
`extscorer.migrations.003_add_lead_digest_sends`'s docstring for why a
per-parcel send log fits a once-built, statically-scraped dataset (Tool
4's real shape) better than a data-freshness cutoff does.
"""
from __future__ import annotations

from typing import Any

DEFAULT_LEADS_PER_DIGEST = 20
"""Widened from 10 (2026-09-15, Prompt U, explicit client request) now
that likely-vacant/absentee-owned properties are filtered out of the
digest entirely (see `is_likely_unreachable_owner` below) -- with real
leads removed from candidacy, a longer list keeps the digest as useful
per-send as the original 10-lead default was. Still NOT 25 (Prompt N's
full review export size) -- Darren runs a small, word-of-mouth-driven
crew on a 3-weeks-on/3-weeks-off cycle; a real, deliberate number in real
code, not final."""


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
    """
    selected = []
    for lead, parcel in ranked_leads_with_parcels:
        if parcel["id"] in already_sent_parcel_row_ids:
            continue
        if is_likely_unreachable_owner(parcel):
            continue
        selected.append((lead, parcel))
        if len(selected) >= limit:
            break
    return selected
