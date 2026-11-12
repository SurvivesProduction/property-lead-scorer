"""Migration 015: three nullable building columns, additive and idempotent."""
from __future__ import annotations

from pathlib import Path

SQL = (Path(__file__).resolve().parent.parent / "src" / "extscorer" / "migrations" / "015_add_warren_building_fields.sql").read_text()
STATEMENTS = [ln.strip() for ln in SQL.splitlines() if ln.strip() and not ln.strip().startswith("--")]


def test_adds_exactly_the_three_columns_with_the_right_types():
    assert STATEMENTS == [
        "alter table parcels add column if not exists style_code text;",
        "alter table parcels add column if not exists roof_structure text;",
        "alter table parcels add column if not exists stories numeric(4, 2);",
    ]


def test_is_additive_nothing_dropped_defaulted_or_rls_touched():
    body = " ".join(STATEMENTS).lower()
    for word in ("drop ", "default", "not null", "row level security", "policy", "update ", "delete "):
        assert word not in body


def test_style_code_is_text_so_leading_zeros_survive():
    assert "style_code text" in SQL and "style_code integer" not in SQL
