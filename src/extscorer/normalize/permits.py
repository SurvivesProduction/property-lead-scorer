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
