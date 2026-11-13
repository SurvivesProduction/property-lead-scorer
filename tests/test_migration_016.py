"""Migration 016: the append-only parcel_load_log. Text checks only (this runner replays every migration, so it must be idempotent)."""
from __future__ import annotations

from pathlib import Path

SQL = (Path(__file__).resolve().parent.parent / "src" / "extscorer" / "migrations" / "016_add_parcel_load_log.sql").read_text()
BODY = " ".join(" ".join(ln for ln in SQL.splitlines() if not ln.strip().startswith("--")).lower().split())


def test_table_has_the_logged_columns_and_rls_on() -> None:
    for col in ("parcel_uuid uuid", "load_key text", "run_id uuid", "field text", "before_value jsonb", "after_value jsonb",
                "written_at timestamptz", "source text", "meta jsonb"):
        assert col in BODY
    assert "alter table parcel_load_log enable row level security" in BODY
    assert "policy" not in BODY


def test_no_foreign_key_so_deleting_a_parcel_cannot_delete_its_history() -> None:
    assert "references" not in BODY


def test_update_delete_and_truncate_are_blocked_by_triggers() -> None:
    assert "before update or delete on parcel_load_log" in BODY and "before truncate on parcel_load_log" in BODY
    assert "raise exception" in BODY


def test_replaying_the_migration_is_safe() -> None:
    assert "create table if not exists parcel_load_log" in BODY
    assert BODY.count("create index if not exists") + BODY.count("create unique index if not exists") == 3
    assert "create or replace function parcel_load_log_append_only" in BODY
    assert BODY.count("drop trigger if exists") == 2 and BODY.count("create trigger") == 2


def test_the_migration_copy_cannot_double_insert() -> None:
    assert "unique index if not exists uq_parcel_load_log_migration_copy" in BODY and "where source = 'migration'" in BODY


def test_nothing_in_parcels_is_touched() -> None:
    for word in ("alter table parcels", "update parcels", "delete from parcels", "drop table", "drop column"):
        assert word not in BODY
