"""Pure lead-selection logic for a client-facing lead digest email.

Deliberately NOT Tool 1's `first_seen_at`-since-last-run model -- see
`extscorer.migrations.003_add_lead_digest_sends`'s docstring for why a
per-parcel send log fits a once-built, statically-scraped dataset (Tool
4's real shape) better than a data-freshness cutoff does.
"""
from __future__ import annotations

from typing import Any

DEFAULT_LEADS_PER_DIGEST = 10
"""Real, deliberate default -- NOT 25 (Prompt N's full review export size).
Darren runs a small, word-of-mouth-driven crew on a 3-weeks-on/3-weeks-off
cycle; a short, high-conviction list he can actually act on beats a long
one he'll skim past. Same "real number in real code, not final" status as
every other proposed default in this project."""


def select_unsent_leads(
    ranked_leads_with_parcels: list[tuple[Any, dict[str, Any]]],
    already_sent_parcel_row_ids: set[Any],
    limit: int = DEFAULT_LEADS_PER_DIGEST,
) -> list[tuple[Any, dict[str, Any]]]:
    """Filter an already-ranked list of `(LeadScore, raw_parcel_dict)`
    pairs -- `rank_candidates`'s own deterministic order, tiebreak
    included, zipped against each lead's own source parcel row -- down to
    the top `limit` pairs whose `raw_parcel_dict["id"]` (the real
    `parcels.id` primary key) is NOT already in `already_sent_parcel_row_ids`.

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
        selected.append((lead, parcel))
        if len(selected) >= limit:
            break
    return selected
