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

import re

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


def split_owner_mailing_address(raw_lines: list[str]) -> tuple[str | None, str | None]:
    """Split a `<br>`-joined owner mailing address (already split into
    lines by the caller, e.g. `soup.find(...).get_text(separator="\\n")
    .splitlines()`) into `(street_line, city_state_zip_line)`.

    Confirmed live shape on both platforms is exactly two meaningful lines
    after the owner name is dropped (VGSI's `#MainContent_lblAddr1` IS the
    address only, name lives in a separate `#MainContent_lblGenOwner`
    span; propertyrecordcards.com's single cell has name as its own first
    line instead, hence `raw_lines` here is expected to already have any
    leading name line stripped by the caller, which knows its own
    platform's shape). A blank trailing line (both platforms' HTML ends
    the cell with a trailing `<br>`) is dropped rather than treated as a
    real third field.
    """
    lines = [line.strip() for line in raw_lines if line.strip()]
    street_line = lines[0] if len(lines) >= 1 else None
    city_state_zip_line = lines[1] if len(lines) >= 2 else None
    return street_line, city_state_zip_line


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
