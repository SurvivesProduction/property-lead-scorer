"""The logged write helpers: what they read, what they write, what they log. A fake connection; no database."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from extscorer.db import load_log as ll

P1, P2 = uuid.uuid4(), uuid.uuid4()
CTX = ll.LoadContext(client_id="c1", load_key="town_file_2026_11", script="loader.py", run_id=uuid.UUID(int=7))


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        text = query.as_string(None) if hasattr(query, "as_string") else str(query)
        self.conn.statements.append((text, params))
        self._rows = self.conn.old_rows if text.lstrip().startswith("select") else []

    def executemany(self, query, seq):
        text = query.as_string(None) if hasattr(query, "as_string") else str(query)
        for params in seq:
            self.conn.statements.append((text, params))

    def fetchall(self):
        return self._rows


class FakeConn:
    def __init__(self, old_rows):
        self.old_rows = old_rows
        self.statements = []
        self.commits = 0

    def cursor(self, row_factory=None):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1


def _old(pid, **cols):
    return {"id": pid, "town": "Testville", "parcel_id": "state-abc", **cols}


def _kinds(conn):
    return [s.split()[0] + " " + s.split()[1] for s, _ in conn.statements]


def test_only_changed_fields_are_written_and_logged() -> None:
    conn = FakeConn([_old(P1, exterior_wall_1="Wood Frame", year_built=1950)])
    changes = ll.logged_update(conn, CTX, P1, {"exterior_wall_1": "Vinyl Siding", "year_built": 1950})
    assert [(c.field, c.before, c.after) for c in changes] == [("exterior_wall_1", "Wood Frame", "Vinyl Siding")]
    update = [(s, p) for s, p in conn.statements if s.startswith("update parcels")]
    assert len(update) == 1 and '"exterior_wall_1" = %s' in update[0][0] and "year_built" not in update[0][0]
    assert "updated_at = now()" in update[0][0]
    logs = [p for s, p in conn.statements if "insert into parcel_load_log" in s]
    assert len(logs) == 1 and logs[0][:8] == ("c1", P1, "Testville", "state-abc", "town_file_2026_11", uuid.UUID(int=7), "loader.py", "exterior_wall_1")
    assert logs[0][8].obj == "Wood Frame" and logs[0][9].obj == "Vinyl Siding" and logs[0][10] == "live"


def test_nothing_is_written_or_logged_when_nothing_differs() -> None:
    conn = FakeConn([_old(P1, year_built=1950, stories=Decimal("1.50"))])
    assert ll.logged_update(conn, CTX, P1, {"year_built": 1950, "stories": 1.5}) == []
    assert _kinds(conn) == ["select id,"]


def test_the_select_locks_the_rows_and_the_helper_never_commits() -> None:
    conn = FakeConn([_old(P1, year_built=1)])
    ll.logged_update(conn, CTX, P1, {"year_built": 2})
    assert "for update" in conn.statements[0][0] and conn.commits == 0


def test_many_parcels_one_select_and_a_log_row_per_changed_field() -> None:
    conn = FakeConn([_old(P1, use_class="unknown"), _old(P2, use_class="residential")])
    changed = ll.logged_update_many(conn, CTX, [(P1, {"use_class": "residential"}), (P2, {"use_class": "residential"})])
    assert list(changed) == [P1]
    assert sum(1 for s, _ in conn.statements if s.startswith("select")) == 1
    assert sum(1 for s, _ in conn.statements if "insert into parcel_load_log" in s) == 1


def test_a_blank_replacing_a_value_is_a_logged_change() -> None:
    conn = FakeConn([_old(P1, owner_name="DOE JANE")])
    (change,) = ll.logged_update(conn, CTX, P1, {"owner_name": None})
    assert (change.before, change.after) == ("DOE JANE", None)


def test_dates_decimals_and_dicts_are_stored_as_json() -> None:
    assert ll.to_json_value(date(2026, 11, 12)) == "2026-11-12"
    assert ll.to_json_value(Decimal("1.50")) == 1.5 and ll.to_json_value(Decimal("2.00")) == 2
    assert ll.to_json_value({"a": [Decimal("1.25"), date(2020, 1, 2)]}) == {"a": [1.25, "2020-01-02"]}
    assert ll.to_json_value(None) is None


@pytest.mark.parametrize("name", ["raw_data", "id", "parcel_id", "town", "client_id", "updated_at"])
def test_identity_raw_data_and_timestamp_columns_cannot_be_written(name) -> None:
    with pytest.raises(ValueError):
        ll.logged_update(FakeConn([_old(P1)]), CTX, P1, {name: "x"})


@pytest.mark.parametrize("name", ["year_built; drop table parcels", "Year", "a-b", ""])
def test_only_plain_lowercase_column_names_are_accepted(name) -> None:
    with pytest.raises(ValueError):
        ll.check_fields([name])


def test_a_missing_parcel_raises_instead_of_silently_skipping() -> None:
    with pytest.raises(LookupError):
        ll.logged_update(FakeConn([]), CTX, P1, {"year_built": 1})


def test_log_insert_records_the_creation_with_no_before_value() -> None:
    conn = FakeConn([])
    ll.log_insert(conn, CTX, _old(P1), meta={"why": "new state row"})
    (_, params), = conn.statements
    assert params[7] == ll.INSERT_FIELD and params[8].obj is None and params[9].obj is True and params[11].obj == {"why": "new state row"}


def test_migration_rows_are_marked_as_such() -> None:
    ctx = ll.LoadContext("c1", "k", "copy.py", source="migration")
    conn = FakeConn([])
    ll.append_log(conn, ctx, _old(P1), [ll.FieldChange("year_built", 1, 2, {"after_is_current": True})])
    assert conn.statements[0][1][10] == "migration" and conn.statements[0][1][11].obj == {"after_is_current": True}


def test_migration_copies_are_idempotent_and_live_rows_are_not() -> None:
    migration = FakeConn([])
    ll.append_log(migration, ll.LoadContext("c1", "k", "copy.py", source="migration"), _old(P1), [ll.FieldChange("year_built", 1, 2)])
    assert "on conflict (parcel_uuid, load_key, field) where source = 'migration' do nothing" in migration.statements[0][0]
    live = FakeConn([])
    ll.append_log(live, CTX, _old(P1), [ll.FieldChange("year_built", 1, 2)])
    assert "on conflict" not in live.statements[0][0]


def test_upsert_parcel_can_leave_the_commit_to_the_caller() -> None:
    from extscorer.db import client
    from extscorer.normalize.schema import ParcelLeadRecord

    class Cur(FakeCursor):
        def fetchone(self):
            return {"id": P1}

    class Conn(FakeConn):
        def cursor(self, row_factory=None):
            return Cur(self)

    record = ParcelLeadRecord(client_id="c1", town="Testville", county="Windham", parcel_id="1", address="1 TEST RD", source_url="https://example.invalid/1")
    held, default = Conn([]), Conn([])
    client.upsert_parcel(held, record, commit=False)
    client.upsert_parcel(default, record)
    assert held.commits == 0 and default.commits == 1


def test_field_meta_rides_on_that_fields_log_row_only() -> None:
    conn = FakeConn([_old(P1, year_built=1950, living_area_sqft=1000)])
    ll.logged_update(conn, CTX, P1, {"year_built": 1960, "living_area_sqft": 1100}, meta={"run": "x"},
                     field_meta={"year_built": {"overrode_load_key": "warren_x"}})
    metas = {p[7]: p[11].obj for s, p in conn.statements if "insert into parcel_load_log" in s}
    assert metas == {"year_built": {"run": "x", "overrode_load_key": "warren_x"}, "living_area_sqft": {"run": "x"}}
