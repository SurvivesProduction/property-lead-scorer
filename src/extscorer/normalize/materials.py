"""Shared material-family classification for the interactive slider Lead
Board's siding/roof-cover filters (Prompt W follow-up, 2026-10-29).

`wall_material_families` reuses `extscorer.scoring.basic`'s own private
`_DURABLE_MATERIAL_KEYWORDS` constant -- the SAME keyword list/`"vinyl"`
substring rule `_classify_wall_material`/`siding_score` already use for
scoring -- so the board's filter and the real score dispatch can never
silently diverge into two different classifications of the same raw
text. Deliberately a DIFFERENT shape than `_classify_wall_material`
though: that function returns the single family SCORING should dispatch
on (vinyl takes priority the moment it's present, even in a composite
string like "Vinyl Siding/Clapboards" -- vinyl's shorter real-world
lifespan is the dominant physical signal for that parcel's redo-year
estimate). The board's filter has a different job: a viewer filtering by
"Durable" should still find a "Vinyl Siding/Clapboards" parcel, since it
genuinely has durable material on it too -- so this function returns
EVERY matching family, not just the one scoring would pick.

`classify_roof_material` has no scoring equivalent to reuse --
`roof_cover_material` isn't a scoring input anywhere in this project --
so it's a new, roof-only classifier, kept here (one place) rather than
duplicated in the board's export/build scripts.
"""
from __future__ import annotations

from extscorer.scoring.basic import _DURABLE_MATERIAL_KEYWORDS

FAMILY_VINYL = "vinyl"
FAMILY_DURABLE = "durable_original"
FAMILY_OTHER = "other"


def wall_material_families(exterior_wall_text: str | None) -> list[str]:
    """Every material family a raw `exterior_wall_1`/`exterior_wall_2`
    string touches, for the board's siding-material filter -- NOT the
    single family `extscorer.scoring.basic._classify_wall_material`
    would dispatch scoring to (see this module's own docstring for why
    they differ).

    Returns `[]` for missing/blank text (the caller treats that as the
    "Unknown" bucket, same "don't fabricate" convention the scoring
    module's own missing-data handling already uses) -- `['other']` when
    text is present but matches neither `vinyl` nor any durable keyword.
    """
    if not exterior_wall_text:
        return []
    text = exterior_wall_text.lower()
    families = []
    if "vinyl" in text:
        families.append(FAMILY_VINYL)
    if any(keyword in text for keyword in _DURABLE_MATERIAL_KEYWORDS):
        families.append(FAMILY_DURABLE)
    if not families:
        families.append(FAMILY_OTHER)
    return families


# Roof-cover classification -- see module docstring: no existing scoring
# signal to reuse here, this is a new mapping, built and verified
# (2026-10-29) against the real 25 distinct `roof_cover_material` values
# on file at the time (see the Prompt W follow-up report for the exact
# counts and every raw value that landed in 'other'). Keyword-substring
# match, same style as `_DURABLE_MATERIAL_KEYWORDS`, case-insensitive.
ROOF_ASPHALT = "asphalt"
ROOF_METAL = "metal"
ROOF_SLATE = "slate"
ROOF_WOOD = "wood"
ROOF_RUBBER_ROLLED = "rubber_rolled"
ROOF_TAR_GRAVEL = "tar_gravel"
ROOF_CONCRETE = "concrete"
ROOF_OTHER = "other"

# "arch[itectural shingle]" is grouped under asphalt -- architectural
# shingles are a (dimensional/laminated) asphalt-shingle product, not a
# separate roofing material. Checked in this fixed order; real data has
# no raw value matching more than one group, so order hasn't mattered in
# practice, but a fixed order keeps this deterministic if that changes.
_ROOF_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (ROOF_ASPHALT, ("asph", "arch")),
    (ROOF_METAL, ("metal", "mtl")),
    (ROOF_SLATE, ("slate",)),
    (ROOF_WOOD, ("wood",)),
    (ROOF_RUBBER_ROLLED, ("rubber", "roll")),
    (ROOF_TAR_GRAVEL, ("tar", "gravel")),
    (ROOF_CONCRETE, ("concrete",)),
)


def classify_roof_material(raw: str | None) -> str | None:
    """One of `ROOF_ASPHALT`/`_METAL`/`_SLATE`/`_WOOD`/`_RUBBER_ROLLED`/
    `_TAR_GRAVEL`/`_CONCRETE`/`ROOF_OTHER`, or `None` for missing/blank
    text (the caller treats that as the "Unknown" bucket).
    """
    if not raw:
        return None
    text = raw.lower()
    for family, keywords in _ROOF_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return family
    return ROOF_OTHER
