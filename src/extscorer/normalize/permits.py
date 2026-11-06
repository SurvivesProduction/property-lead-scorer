"""Shared exterior-relevant-permit classification (2026-09-16, Brooklyn's
real PermitLink source).

Centralized here for the same reason `extscorer.normalize.address` centralizes
owner-address comparison: two independent real platforms
(`extscorer_full.sources.propertyrecordcards`'s Permit Type/Reason columns,
`extscorer_full.sources.permitlink`'s Permit Type/Work Description columns)
both need the identical judgment call -- "does this permit's own text
describe exterior work" -- so the keyword list and classifier live in one
place rather than drifting apart across two source modules.

Type alone is insufficient on both platforms: a real Woodstock permit typed
"Miscellaneous" with reason text "STRIP/ RESHINGLE APPROX 1800 SF" is
exterior-relevant despite its type, and real Brooklyn PermitLink rows show
the same shape (e.g. a "Building" permit whose Work Description reads
"strip exsting siding, install house wrap and double 4 vinyl siding").
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

# Substring keywords: each is distinctive enough that a bare substring match
# is safe ("roofing", "windows", "shingles", "gutters" all SHOULD hit).
EXTERIOR_PERMIT_KEYWORDS = (
    "reshingle",
    "re-shingle",
    "shingle",
    "roof",
    "exterior",
    "window",
    "gutter",
    "clapboard",
)

# Whole-word keywords. These were substring keywords until 2026-11-05, which
# made "siding" and "side" hit unrelated words: "side" is inside "residential",
# "reside", "residence", "inside", "outside", "poolside", "alongside", and
# "siding" is inside "residing".
#
# The bare word "side" is deliberately NOT a keyword either. As a whole word it
# is almost always a location: "generator on the right side of the home",
# "propane tank on side of garage", "deck off the left side". Of 15,892 exterior
# flags across the PermitLink towns and propertyrecordcards samples, 683 (4.3%)
# rested only on it, and every one of 18 sampled was a location. What is kept:
#   siding, sided ("vinyl sided"), sidewall / sidewalls, the two words
#   "side wall", and the hyphenated "re-side" ("re-siding" matches via
#   "siding"). "re-side" needs its hyphen, so "reside" meaning "to live" and
#   "re side" do not match.
_EXTERIOR_WHOLE_WORD_PATTERN = re.compile(r"\b(?:siding|sided|sidewalls?|side wall|re-side)\b")

# A permit in one of these statuses was refused, abandoned, or voided: the
# work was never built, so it must not read as "recently redone" (which would
# push a home DOWN the list for work that never happened). Compared
# case-insensitively; PermitLink spells it "Canceled", other systems "Cancelled".
NOT_BUILT_PERMIT_STATUSES = frozenset({"canceled", "cancelled", "denied", "void", "voided", "withdrawn"})


def is_exterior_permit(
    permit_type: str | None,
    description: str | None,
    status: str | None = None,
) -> bool:
    """True if either the permit type or its free-text description
    (a "Reason" on propertyrecordcards.com, a "Work Description" on
    PermitLink) mentions exterior-relevant work, by keyword match.

    `status` is optional (propertyrecordcards.com's permit table has no
    status column; PermitLink's grid does). A Canceled/Denied/Void/Withdrawn
    permit is never exterior work, whatever its text says.
    """
    if status is not None and status.strip().lower() in NOT_BUILT_PERMIT_STATUSES:
        return False
    text = f"{permit_type or ''} {description or ''}".lower()
    if _EXTERIOR_WHOLE_WORD_PATTERN.search(text):
        return True
    return any(keyword in text for keyword in EXTERIOR_PERMIT_KEYWORDS)


# --- permit-history helpers (2026-11-05) -------------------------------------
#
# `parcels.permit_history` is a list of dicts (permit_number, permit_type,
# date_opened, reason, and -- for PermitLink sources -- status). The denormalized
# columns `exterior_permit_count` / `most_recent_exterior_permit_*` are derived
# from it. Both the recompute script in property-lead-scorer-full and the
# cross-source merge in permit-history-enrichment-full need that derivation, so
# it lives here once, next to the classifier it depends on.

_PLACEHOLDER_YEAR = 1900  # PermitLink "Historical" rows use 01/01/1900 for "no date"


def parse_permit_date(value: str | None) -> date | None:
    """MM/DD/YYYY -> date. Blank, malformed and the 01/01/1900 placeholder -> None."""
    if not value:
        return None
    try:
        parsed = datetime.strptime(value.strip(), "%m/%d/%Y").date()
    except ValueError:
        return None
    return None if parsed.year == _PLACEHOLDER_YEAR else parsed


def summarize_permit_history(permit_history: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive the exterior-permit columns from a stored `permit_history` list.

    Counts every dated permit the classifier calls exterior (a Canceled/Denied/
    Void/Withdrawn `status`, when the entry carries one, never counts). The most
    recent date and its type come from the entries whose date parses.
    """
    exterior = [
        entry
        for entry in permit_history
        if parse_permit_date(entry.get("date_opened"))
        and is_exterior_permit(entry.get("permit_type"), entry.get("reason"), entry.get("status"))
    ]
    most_recent: dict[str, Any] | None = None
    most_recent_date: date | None = None
    for entry in exterior:
        opened = parse_permit_date(entry.get("date_opened"))
        if opened is not None and (most_recent_date is None or opened > most_recent_date):
            most_recent_date, most_recent = opened, entry
    return {
        "exterior_permit_count": len(exterior),
        "most_recent_exterior_permit_date": most_recent_date,
        "most_recent_exterior_permit_type": most_recent.get("permit_type") if most_recent else None,
    }


def _permit_key(entry: dict[str, Any]) -> tuple[str, str]:
    number = re.sub(r"[^A-Z0-9]", "", (entry.get("permit_number") or "").upper())
    if number and number != "DRAFT":
        return number, (entry.get("date_opened") or "").strip()
    # No usable number: fall back to what the permit says it is.
    text = f"{entry.get('permit_type') or ''} {entry.get('reason') or ''}".lower()
    return " ".join(text.split()), (entry.get("date_opened") or "").strip()


def merge_permit_histories(*histories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Union of several `permit_history` lists from different sources, deduped on
    (permit number, date opened). The first occurrence wins, but a later duplicate
    fills in a field the first one lacks (e.g. a PermitLink `status`).
    """
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for history in histories:
        for entry in history or []:
            key = _permit_key(entry)
            if key in merged:
                for field, value in entry.items():
                    if merged[key].get(field) in (None, "") and value not in (None, ""):
                        merged[key][field] = value
            else:
                merged[key] = dict(entry)
    return list(merged.values())


# --- three classes of exterior work (scoring split, 2026-11-05) -------------------------------
#
# Re-siding a house resets the siding's age, re-roofing it resets the roof's age, and neither says
# anything about the other. A new deck, porch, door or window is not a reset of either, but it shows an
# owner who spends money on the exterior. So an exterior permit is classified into:
#
#   siding          siding, sided, sidewall(s), side wall, re-side, house wrap, clapboard
#                   -> resets the SIDING age
#   roof            roof, roofing, reroof / re-roof, shingle(s), reshingle
#                   -> resets the ROOF age only (it does not reset the siding)
#   other_exterior  windows, doors, decks, porches (and gutters, "exterior"); not fire or interior doors
#                   -> a small positive "willingness to spend" signal, no reset
#
# One permit can be several ("re-roof and new siding"). The legacy `is_exterior_permit` above is
# unchanged; this is the finer view used by the opt-in scoring switch `permit_class_split`.

SIDING = "siding"
ROOF = "roof"
OTHER_EXTERIOR = "other_exterior"

_SIDING_CLASS_PATTERN = re.compile(r"\b(?:siding|sided|sidewalls?|side wall|re-side|house ?wrap|clapboards?)\b")

# Roof wording. "roof", "roofing", "reroof" are whole words, so "waterproof" and "fireproof" are not roofs.
_ROOF_WORD_PATTERN = re.compile(r"\b(?:re-?)?roof(?:ing|s|ed)?\b")
# "17 sq" / "20 squares" is how a roof job is sized, even when the word "roof" is missing.
_ROOF_SQUARES_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s*(?:sq|sqs|squares?)\b")
_SHINGLE_PATTERN = re.compile(r"\b(?:re-?)?shingl(?:e|es|ed|ing)\b|\bshakes?\b")
# Text that says the work is on the WALLS: "walls", "wall shingles", "exterior walls", "front/side/back of house".
_NAMES_WALLS_PATTERN = re.compile(
    r"\bwalls?\b|\b(?:front|side|back|rear)(?:\s+and\s+(?:front|side|back|rear))*\s+of\s+(?:the\s+)?(?:house|home)\b"
)

_OTHER_EXTERIOR_PATTERN = re.compile(r"\b(?:windows?|doors?|decks?|porch(?:es)?|gutters?)\b")
_EXTERIOR_WORD_PATTERN = re.compile(r"\bexterior\b")
# Doors that are not exterior work: "fire door", "fire-rated door", "interior door", "int. door". They are
# removed from the text before the other-exterior match, so "exterior door" and "storm door" still count.
_NOT_EXTERIOR_DOOR_PATTERN = re.compile(r"\b(?:fire[- ](?:rated[- ])?|interior[- ]|int\.? )doors?\b")
# "roof deck" / "roof decking" is the roof's sheathing, not a deck.
_ROOF_DECK_PATTERN = re.compile(r"\broof[- ]deck(?:ing)?\b")
# Interior-room wording. A door or deck in a permit that talks about a bathroom or a kitchen is interior work
# unless the text also says it is an outside door ("storm", "entry", "front", "back", "garage", "porch",
# "exterior"). Windows are left out of this test: a window is in the building's shell wherever the room is.
_INTERIOR_ROOM_PATTERN = re.compile(r"\b(?:bath(?:room)?|shower|kitchen|basement|closet|cabinet|bedroom|interior)\b")
_EXPLICIT_EXTERIOR_PATTERN = re.compile(r"\b(?:storm|entry|front|back|rear|garage|patio|walk[- ]?out|porch(?:es)?|exterior)\b")
# A deck that is being built or sized is outside work even in a permit that also remodels a kitchen:
# "add 10x28 deck", "upgrade deck", "6x10 deck". "gas line under the deck" matches neither.
_DECK_BUILT_PATTERN = re.compile(
    r"\b(?:add|adding|new|build|construct|install|replace|upgrade|rebuild)\w*\s+(?:[\w']+\s+){0,3}deck\b"
    r"|\b\d+\s*(?:'|ft)?\s*x\s*\d+\S*\s+(?:\w+\s+)?deck\b"
)
_DOOR_OR_DECK_PATTERN = re.compile(r"\b(?:doors?|decks?)\b")
_WINDOW_PATTERN = re.compile(r"\bwindows?\b")
_ALWAYS_EXTERIOR_PATTERN = re.compile(r"\b(?:porch(?:es)?|gutters?)\b")


def _is_other_exterior(text: str, has_siding_or_roof: bool) -> bool:
    text = _NOT_EXTERIOR_DOOR_PATTERN.sub(" ", _ROOF_DECK_PATTERN.sub(" ", text))
    if _ALWAYS_EXTERIOR_PATTERN.search(text) or _WINDOW_PATTERN.search(text):
        return True
    if _DOOR_OR_DECK_PATTERN.search(text):
        if not _INTERIOR_ROOM_PATTERN.search(text):
            return True
        return bool(_EXPLICIT_EXTERIOR_PATTERN.search(text) or _DECK_BUILT_PATTERN.search(text))
    # The bare word "exterior" ("exterior painting") counts only when the permit is not already a siding or
    # roof job; "replace exterior siding" is a siding permit, not also an upgrade.
    return bool(_EXTERIOR_WORD_PATTERN.search(text)) and not has_siding_or_roof


def classify_exterior_permit(
    permit_type: str | None,
    description: str | None,
    status: str | None = None,
) -> frozenset[str]:
    """The set of exterior-work classes a permit belongs to (empty if it is not exterior work).

    A Canceled / Denied / Void / Withdrawn permit was never built, so it is in no class.

    Shingles are ambiguous: they cover roofs and also walls. A shingle (or shake) permit is SIDING when the
    text names the walls (walls, wall shingles, front/side/back of house) and nothing marks it as a roof job
    (the word "roof", or a size in "sq" / "squares"). Otherwise it stays ROOF, so "reshingle 17 sq" is a roof.
    """
    if status is not None and status.strip().lower() in NOT_BUILT_PERMIT_STATUSES:
        return frozenset()
    text = f"{permit_type or ''} {description or ''}".lower()
    classes = set()
    has_roof_word = bool(_ROOF_WORD_PATTERN.search(text))
    has_squares = bool(_ROOF_SQUARES_PATTERN.search(text))
    has_shingle = bool(_SHINGLE_PATTERN.search(text))
    wall_shingles = has_shingle and bool(_NAMES_WALLS_PATTERN.search(text)) and not has_roof_word and not has_squares

    if _SIDING_CLASS_PATTERN.search(text) or wall_shingles:
        classes.add(SIDING)
    if has_roof_word or has_squares or (has_shingle and not wall_shingles):
        classes.add(ROOF)
    if _is_other_exterior(text, has_siding_or_roof=bool(classes)):
        classes.add(OTHER_EXTERIOR)
    return frozenset(classes)


def dated_permits_by_class(permit_history: list[dict[str, Any]] | None) -> dict[str, list[date]]:
    """`{class: [dates, newest first]}` from a stored `permit_history`. Undated permits (drafts) are skipped."""
    out: dict[str, list[date]] = {SIDING: [], ROOF: [], OTHER_EXTERIOR: []}
    for entry in permit_history or []:
        opened = parse_permit_date(entry.get("date_opened"))
        if opened is None:
            continue
        for cls in classify_exterior_permit(entry.get("permit_type"), entry.get("reason"), entry.get("status")):
            out[cls].append(opened)
    for dates in out.values():
        dates.sort(reverse=True)
    return out
