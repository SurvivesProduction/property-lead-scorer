"""The stable key identifying a lead across the digest, the shared Google
Sheet, and the `lead_pipeline` table (Prompt V).

Deliberately NOT a minted hash: `parcels`' own `unique (client_id, town,
parcel_id)` constraint (`migrations/001_init_schema.sql`) already
guarantees `(town, parcel_id)` uniquely identifies a parcel row within one
client, so the plain string `"{town}:{parcel_id}"` is already a safe key --
verified live (2026-10-12) against the real 1,600-row NECC population: zero
duplicate `(town, parcel_id)` pairs, 1,600 distinct keys for 1,600 rows.
"""
from __future__ import annotations


def lead_key(town: str, parcel_id: str) -> str:
    """Build the stable `lead_key` for a parcel: `"{town}:{parcel_id}"`.

    Both inputs are a parcel row's own `town`/`parcel_id` columns verbatim
    (not normalized or re-cased) -- the same two values already used by
    `parcels`' own `unique (client_id, town, parcel_id)` constraint, so a
    caller who already has a `parcels` row can build this key directly from
    it without guessing at normalization.
    """
    return f"{town}:{parcel_id}"
