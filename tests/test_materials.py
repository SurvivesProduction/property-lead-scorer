"""Tests for `extscorer.normalize.materials` -- the board's siding/roof
material-family classification (Prompt W follow-up, 2026-10-29).
"""
from __future__ import annotations

from extscorer.normalize.materials import (
    FAMILY_DURABLE,
    FAMILY_OTHER,
    FAMILY_VINYL,
    ROOF_ASBESTOS,
    ROOF_ASPHALT,
    ROOF_CONCRETE,
    ROOF_METAL,
    ROOF_OTHER,
    ROOF_RUBBER_ROLLED,
    ROOF_SLATE,
    ROOF_TAR_GRAVEL,
    ROOF_TILE,
    ROOF_WOOD,
    classify_roof_material,
    wall_material_families,
)
from extscorer.scoring.basic import _classify_wall_material


def test_wall_material_families_vinyl_only() -> None:
    assert wall_material_families("Vinyl Siding") == [FAMILY_VINYL]


def test_wall_material_families_durable_only() -> None:
    assert wall_material_families("Clapboard") == [FAMILY_DURABLE]


def test_wall_material_families_composite_matches_both() -> None:
    # The exact real-data case that motivated this function: a composite
    # string must be findable under EITHER filter chip, unlike
    # `_classify_wall_material`'s single-family scoring dispatch.
    assert wall_material_families("Vinyl Siding/Clapboards") == [FAMILY_VINYL, FAMILY_DURABLE]


def test_wall_material_families_other_when_neither_keyword_matches() -> None:
    assert wall_material_families("Glass/Thermo.") == [FAMILY_OTHER]  # ("Comp./Wall Brd" has its own family since 2026-11-16)


def test_wall_material_families_empty_for_missing_text() -> None:
    assert wall_material_families(None) == []
    assert wall_material_families("") == []


def test_wall_material_families_agrees_with_scoring_dispatch_on_single_family_cases() -> None:
    # For any non-composite raw value, the family list's content must
    # still agree with what `_classify_wall_material` would dispatch to
    # -- they should never silently classify the same plain text two
    # different ways.
    for raw, expected in [("Vinyl Siding", FAMILY_VINYL), ("Clapboard", FAMILY_DURABLE), ("Glass/Thermo.", FAMILY_OTHER)]:
        families = wall_material_families(raw)
        assert len(families) == 1
        assert families[0] == expected == _classify_wall_material(raw)


def test_wall_material_families_vinyl_takes_scoring_priority_but_filter_sees_both() -> None:
    # `_classify_wall_material` prioritizes vinyl (shorter real-world
    # lifespan is the dominant signal for THAT parcel's score) --
    # `wall_material_families` must still surface durable too, for the filter.
    assert _classify_wall_material("Vinyl Siding/Clapboards") == FAMILY_VINYL
    assert set(wall_material_families("Vinyl Siding/Clapboards")) == {FAMILY_VINYL, FAMILY_DURABLE}


# --- classify_roof_material: every real distinct value on file, 2026-10-29 ---


def test_classify_roof_material_asphalt_family() -> None:
    for raw in ["Asphalt Shingl", "Asph/F Gls/Cmp", "Asphalt", "Arch. Shingles", "Arch Shing", "Arch Shingles"]:
        assert classify_roof_material(raw) == ROOF_ASPHALT, raw


def test_classify_roof_material_metal_family() -> None:
    for raw in ["Metal/Tin", "Enam Mtl Shing", "Metal", "Enamel Metal Shingle", "Metal Shingles", "Mtl Shngl/Seam"]:
        assert classify_roof_material(raw) == ROOF_METAL, raw


def test_classify_roof_material_tar_gravel_family() -> None:
    for raw in ["Tar and Gravel", "Tar & Gravel"]:
        assert classify_roof_material(raw) == ROOF_TAR_GRAVEL, raw


def test_classify_roof_material_rubber_rolled_family() -> None:
    for raw in ["Rolled Compos", "Rolled/Rubber", "Rubber", "Roll Roofing"]:
        assert classify_roof_material(raw) == ROOF_RUBBER_ROLLED, raw


def test_classify_roof_material_wood_family() -> None:
    for raw in ["Wood Shingle", "Wood"]:
        assert classify_roof_material(raw) == ROOF_WOOD, raw


def test_classify_roof_material_slate_and_concrete() -> None:
    assert classify_roof_material("Slate") == ROOF_SLATE
    assert classify_roof_material("Concrete Tile") == ROOF_CONCRETE


def test_classify_roof_material_other_for_unmapped_real_values() -> None:
    for raw in ["Vinyl - 50 yea", "Vinyl", "Fiber Panels", "Typical"]:
        assert classify_roof_material(raw) == ROOF_OTHER, raw


def test_classify_roof_material_asbestos_family() -> None:
    for raw in ["Asbestos Shing", "Asbestos", "Corrugated Asb", "Corrug Asb", "Corr. Asbestos"]:
        assert classify_roof_material(raw) == ROOF_ASBESTOS, raw


def test_classify_roof_material_tile_copper_fiberglass_membrane() -> None:
    assert classify_roof_material("Clay Tile") == ROOF_TILE
    assert classify_roof_material("Concrete Tile") == ROOF_CONCRETE  # still concrete, not tile
    assert classify_roof_material("Copper") == ROOF_METAL
    assert classify_roof_material("Fiberglass") == ROOF_ASPHALT
    assert classify_roof_material("Membrane") == ROOF_RUBBER_ROLLED
    assert classify_roof_material("Asphalt") == ROOF_ASPHALT  # asph is not caught by the asbestos keywords


def test_classify_roof_material_none_for_missing_text() -> None:
    assert classify_roof_material(None) is None
    assert classify_roof_material("") is None
