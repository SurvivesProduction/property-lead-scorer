"""Shared owner-mailing-address-vs-property-address comparison (2026-09-15,
Prompt U's vacancy/occupancy signal).

Both real sources this tool builds against expose an owner-of-record
mailing address on the parcel's own card (VGSI: `#MainContent_lblGenOwner`
/`#MainContent_lblAddr1`, e.g. "SMITH JOHN & JANE" / "20 MAPLE
DR<br>ANYTOWN, CT 06331"; propertyrecordcards.com: the "Owner's
Information" table's single cell, e.g. "DOE MARY<br>32 OAK ST<br>
OTHERTOWN, CT 06239<br>") -- same shape on
both platforms (name, then a `<br>`-joined mailing address), so the
comparison logic lives here once rather than being duplicated per source
module, matching this package's existing "generic engine, thin per-
platform wiring" split.

A mismatch between the owner's mailing street and the property's own
street is treated as a real absentee-owner signal (the client explicitly
asked for exactly this check) -- NOT proof of vacancy on its own (a
landlord who owns several local properties, or an owner using a PO box,
both mail elsewhere while still actively living in or actively managing
the property), which is why this is a deprioritization/exclusion signal
at the digest-selection layer (see `extscorer.digest.selection
.is_likely_unreachable_owner`), not a claim of certainty baked any deeper
into the schema than a plain boolean.
"""
from __future__ import annotations

import hashlib
import re
from typing import NamedTuple

_STREET_TYPE_ABBREVIATIONS = {
    "STREET": "ST",
    "ROAD": "RD",
    "DRIVE": "DR",
    "AVENUE": "AVE",
    "LANE": "LN",
    "COURT": "CT",
    "CIRCLE": "CIR",
    "PLACE": "PL",
    "BOULEVARD": "BLVD",
    "TERRACE": "TER",
    "HIGHWAY": "HWY",
    "TURNPIKE": "TPKE",
    "EXTENSION": "EXT",
}

_NON_ALNUM_RE = re.compile(r"[^A-Z0-9 ]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_street_address(value: str | None) -> str | None:
    """Uppercase, punctuation-stripped, whitespace-collapsed, common-
    street-type-abbreviated form of a street address line (no city/state/
    zip) -- good enough to catch the same real street written two ways
    ("20 MAPLE DR" vs "20 MAPLE DRIVE") without being a full USPS-grade
    address normalizer, which this comparison doesn't need: it only has
    to agree with itself on both sides of the same real record.

    Returns `None` for `None`/blank input so a caller can tell "nothing to
    compare" apart from "compared and empty."
    """
    if not value:
        return None
    cleaned = _NON_ALNUM_RE.sub(" ", value.upper())
    words = [_STREET_TYPE_ABBREVIATIONS.get(word, word) for word in cleaned.split()]
    normalized = _WHITESPACE_RE.sub(" ", " ".join(words)).strip()
    return normalized or None


class OwnerMailingBlock(NamedTuple):
    """An owner mailing block split into its parts. `care_of` keeps any `C/O`/`ATTN` name on its
    own, so it is never mistaken for the street (and is not thrown away)."""

    care_of: str | None
    street: str | None
    city_state_zip: str | None


_CITY_STATE_ZIP_RE = re.compile(r"\b[A-Z]{2}\s+\d{5}(?:-\d{4})?$")
_CARE_OF_RE = re.compile(r"^(?:C/O\b|C\\O\b|ATTN\b|ATT:|CARE OF\b|%)", re.I)
# A street line is "number word..." (not a date such as a trust date "01/01/2000") or a PO box / route.
_STREET_LINE_RE = re.compile(r"^(?:\d+[A-Za-z]?(?:-\d+)?\s+[A-Za-z]|P\.?\s?O\.?\s*BOX\b|BOX\b|RR\b|RT\b|ROUTE\b)", re.I)


def parse_owner_mailing_block(raw_lines: list[str]) -> OwnerMailingBlock:
    """Split a mailing block (owner name already removed) into care-of, street and city/state/zip.

    Real cards put a `C/O NAME` or `ATTN:` line before the street, so "first line is the street, second is the city" misread the
    care-of line as the street and the street as the city. The owner cell can also carry a second
    name line (a co-owner, a trust, "% NAME"), which was likewise read as the street and made a
    resident owner look absentee. The street is the street-shaped line
    closest to the city/state/zip line instead. When the block has a care-of line and a city line but nothing
    between (`C/O TOWN HALL` then the city line), `street` is None.
    """
    lines = [line.strip() for line in raw_lines if line and line.strip()]
    city_index = next((i for i in range(len(lines) - 1, -1, -1) if _CITY_STATE_ZIP_RE.search(lines[i].upper())), None)
    before = lines[:city_index] if city_index is not None else lines
    care_of_lines = [line for line in before if _CARE_OF_RE.match(line)]
    address_lines = [line for line in before if not _CARE_OF_RE.match(line)]
    street = None
    if address_lines:
        numbered = [line for line in address_lines if _STREET_LINE_RE.match(line)]
        street = numbered[-1] if numbered else address_lines[-1]
    if city_index is not None:
        city = lines[city_index]
    else:
        # No recognisable city/state/zip: the line after the street, as before.
        later = [line for line in address_lines if line != street]
        city = later[0] if later else None
    return OwnerMailingBlock(" ".join(care_of_lines) or None, street, city)


def split_owner_mailing_address(raw_lines: list[str]) -> tuple[str | None, str | None]:
    """`(street_line, city_state_zip_line)` of a mailing block; see `parse_owner_mailing_block`.

    Identical to the old behaviour for the usual two-line block; a `C/O`/`ATTN` line no longer
    becomes the street.
    """
    block = parse_owner_mailing_block(raw_lines)
    return block.street, block.city_state_zip


def format_owner_mailing_address(street_line: str | None, city_state_zip_line: str | None) -> str | None:
    """Join a split owner mailing address back into one storable/
    displayable string ("STREET, CITY, STATE ZIP") -- the DB column and
    digest copy both want one string, not a pair.
    """
    parts = [part for part in (street_line, city_state_zip_line) if part]
    return ", ".join(parts) or None


def is_owner_address_mismatch(property_address: str | None, owner_mailing_street: str | None) -> bool:
    """True if the owner's own mailing street doesn't match this parcel's
    own street address -- the real absentee-owner signal the client asked
    for ("check owner mailing address against property address on every
    parcel — a mismatch is a real absentee-owner signal").

    Deliberately compares STREET LINES ONLY, not city/state/zip: this
    tool's own `address` field never carries city/state/zip either (see
    `extscorer_full.sources.vgsi`'s module docstring -- VGSI's own card
    never includes them), so there's nothing on the property side to
    compare a mailing city against without re-deriving it from `town`,
    which is redundant with a direct street-to-street comparison and adds
    a second place a normalization mismatch (e.g. "Killingly" vs
    "KILLINGLY CT") could produce a false mismatch.

    Returns `False` (not absentee) when either side is missing -- an
    absence of data is not evidence of a mismatch, same "unknown must not
    be treated as confirmed" discipline `is_likely_unreachable_owner`
    documents for its own two input signals.
    """
    normalized_property = normalize_street_address(property_address)
    normalized_owner = normalize_street_address(owner_mailing_street)
    if normalized_property is None or normalized_owner is None:
        return False
    return normalized_property != normalized_owner


def mint_address_town_parcel_id(town: str, address: str) -> str:
    """Deterministic fallback `parcel_id` for a row that has no native
    scraper id (e.g. a state-layer-only parcel, which has no VGSI `pid` or
    propertyrecordcards.com `uniqueid` of its own) -- 2026-10-28, the state
    CAMA FeatureServer merge.

    No address+town hash minting scheme existed anywhere in this codebase
    before this (checked: `lead_pipeline.lead_key` builds `"{town}:
    {parcel_id}"` from an ALREADY-EXISTING `parcel_id`, it doesn't mint
    one). `parcels`' own `unique (client_id, town, parcel_id)` constraint
    still needs *some* value, and it needs to be the SAME value every time
    this function is called for the same real parcel (an idempotent merge
    script re-run must not insert a second row for a row it already
    inserted) -- a `sha256` of the normalized street address is
    deterministic and collision-resistant enough for this project's real
    scale (tens of thousands of parcels, not millions). Hashes the
    NORMALIZED address (`normalize_street_address`), not the raw string, so
    "20 Maple Dr" and "20 MAPLE DRIVE" mint the same id. Town is included
    in the hash input (not just relied on as a separate DB column) so two
    different towns' same-named street can never collide on `parcel_id`
    alone, matching how VGSI/propertyrecordcards.com ids are already only
    unique within a town, never globally.

    Prefixed `state-` so a human glancing at a `parcel_id` column can tell
    at a glance this is a minted id, not a real platform id (VGSI's are
    bare small integers, propertyrecordcards.com's are `uniqueid` strings
    like `"G0156900"` -- neither looks like a hex hash).
    """
    normalized = normalize_street_address(address) or ""
    digest = hashlib.sha256(f"{town.strip().upper()}|{normalized}".encode("utf-8")).hexdigest()
    return f"state-{digest[:16]}"
