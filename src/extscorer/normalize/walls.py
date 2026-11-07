"""Exterior-wall classification for the masonry rule (2026-11-07).

A brick, stone, stucco or concrete house cannot be re-sided, so it is not a siding lead; it can still need a roof.
`is_masonry_exterior` decides that from the raw wall text the assessor cards use ("Brick/Masonry", "Stucco on Mas.",
"Concr/Cinder", "Stone Veneer", ...).

Rules, from the real values on file:
- masonry word present: brick, stone, masonry (and the card abbreviations msnry / mas), stucco, concrete (concr),
  cinder, block;
- NOT masonry when a sidable material is named too ("Vinyl Siding/Brick Veneer", "Clapboards/Stone Veneer",
  "Pre-Finish Metal/Brick", "Log Cabin/Stone Veneer") or the text is a frame type with masonry ("Wood Frame/Masonry"):
  those are partly sidable, so they keep the normal siding score;
- fiber-cement board ("Cement Board", "Fbr cement") is a real siding product and is never masonry;
- a second wall (`exterior_wall_2`) that names a sidable material also keeps the normal score.
"""
from __future__ import annotations

import re
from typing import Any

_MASONRY = re.compile(r"brick|stone|masonry|msnry|stucco|concr|cinder|\bblock\b|\bmas\b")
_SIDABLE = re.compile(
    r"vinyl|alumin|\bal\b|al/|clapboard|shingle|shake|siding|metal|\blog\b|batten|pre-?fab|wood frame|wood on|"
    r"cedar|redwood|board|cement|hardi|asbest"
)
_WOOD = re.compile(r"\bwood\b")


def _names_sidable_material(text: str) -> bool:
    """A sidable material is named. Bare "wood" counts, except in "Stucco on Wood" (stucco over a wood frame is still stucco)."""
    if _SIDABLE.search(text):
        return True
    return bool(_WOOD.search(text)) and "stucco" not in text


def is_masonry_text(wall: str | None) -> bool:
    """True when the wall text names masonry and no sidable material."""
    text = (wall or "").lower()
    if not text or not _MASONRY.search(text):
        return False
    return not _names_sidable_material(text)


def is_masonry_exterior(parcel: dict[str, Any]) -> bool:
    """The parcel's primary wall is masonry-only and its second wall (if any) does not add a sidable material."""
    if not is_masonry_text(parcel.get("exterior_wall_1")):
        return False
    wall_2 = (parcel.get("exterior_wall_2") or "").lower().strip()
    return not wall_2 or is_masonry_text(wall_2) or not _names_sidable_material(wall_2)
