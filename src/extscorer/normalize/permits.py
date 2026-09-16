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

EXTERIOR_PERMIT_KEYWORDS = (
    "siding",
    "side",
    "reshingle",
    "re-shingle",
    "shingle",
    "roof",
    "exterior",
    "window",
    "gutter",
    "clapboard",
)


def is_exterior_permit(permit_type: str | None, description: str | None) -> bool:
    """True if either the permit type or its free-text description
    (a "Reason" on propertyrecordcards.com, a "Work Description" on
    PermitLink) mentions exterior-relevant work, by keyword match.
    """
    text = f"{permit_type or ''} {description or ''}".lower()
    return any(keyword in text for keyword in EXTERIOR_PERMIT_KEYWORDS)
