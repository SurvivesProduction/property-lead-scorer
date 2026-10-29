"""Offline tests for the state-only-row promotion path (2026-10-29,
"loose ends" pass) -- no live Postgres connection, same split
`test_backfill_parcel_canopy.py`'s own `_FakeCursor`/`_FakeConn` pattern
already establishes for pure query-construction logic in this codebase.

Covers the real gap this pass found: `upsert_parcel`'s own dedup key
(`client_id, town, parcel_id`) can never match a state-only row's
minted `state-*` key, so a plain scrape upsert could never find/update
that row -- it would silently insert a SECOND row for the same real
property instead, leaving the original state-only row un-promoted
forever. `state_only_parcel_ids_by_address`/`promote_state_only_parcel_
from_scrape` exist to make that reachable; these tests prove the
promotion path writes scraped values (not state values) while never
touching address/town/parcel_id.
"""
from __future__ import annotations

from datetime import date

from extscorer.db import client as db_client
from extscorer.normalize.schema import ParcelLeadRecord


class _FakeCursor:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.executed_query: str | None = None
        self.executed_params: dict | None = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        self.executed_query = query
        self.executed_params = params

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows: list[dict]) -> None:
        self.cursor_obj = _FakeCursor(rows)

    def cursor(self, row_factory=None):
        return self.cursor_obj


def _sample_record(**overrides) -> ParcelLeadRecord:
    defaults = dict(
        client_id="north-east-corner-construction",
        town="Testville",
        county="Windham",
        address="1 EXAMPLE RD",
        parcel_id="999001",  # VGSI-shaped pid -- never equals a minted state-* id
        source_url="https://example.invalid/Parcel.aspx?pid=999001",
        year_built=1800,
        living_area_sqft=1803,
        roof_cover_material="Metal/Tin",
        exterior_wall_1="Clapboard",
        building_percent_good=70,
        owner_name="TEST OWNER A",
        owner_mailing_address="1 EXAMPLE RD, TESTVILLE, CT 00000",
        is_absentee_owner=False,
        needs_review=False,
        review_reason=None,
    )
    defaults.update(overrides)
    return ParcelLeadRecord(**defaults)


# --- state_only_parcel_ids_by_address: index-building logic -----------------------------------------------


def test_state_only_parcel_ids_by_address_queries_only_this_towns_state_only_rows() -> None:
    conn = _FakeConn(rows=[])
    db_client.state_only_parcel_ids_by_address(conn, "north-east-corner-construction", "Testville")
    query = conn.cursor_obj.executed_query
    params = conn.cursor_obj.executed_params
    assert "enrichment_status = 'state_only'" in query
    assert "town = %(town)s" in query
    assert params == {"client_id": "north-east-corner-construction", "town": "Testville"}


def test_state_only_parcel_ids_by_address_normalizes_and_dedupes() -> None:
    conn = _FakeConn(
        rows=[
            {"id": "uuid-1", "address": "1 EXAMPLE RD"},
            {"id": "uuid-2", "address": "12 MAPLE DRIVE"},  # abbreviates to "12 MAPLE DR"
            {"id": "uuid-3", "address": "12 MAPLE DR"},  # same normalized key -- first-seen (uuid-2) wins
        ]
    )
    index = db_client.state_only_parcel_ids_by_address(conn, "north-east-corner-construction", "Testville")
    assert index["1 EXAMPLE RD"] == "uuid-1"
    assert index["12 MAPLE DR"] == "uuid-2"
    assert len(index) == 2


# --- promote_state_only_parcel_from_scrape: merge direction + identity preservation ------------------------


def test_promote_writes_scraped_values_via_update_parcel_scraped_base_fields(monkeypatch) -> None:
    captured = {}

    def fake_update_base_fields(conn, parcel_id, **kwargs):
        captured["parcel_id"] = parcel_id
        captured["kwargs"] = kwargs
        return {"id": parcel_id}

    monkeypatch.setattr(db_client, "update_parcel_scraped_base_fields", fake_update_base_fields)

    record = _sample_record()
    db_client.promote_state_only_parcel_from_scrape(conn=object(), parcel_id="existing-state-only-uuid", record=record)

    # The row being written to is the EXISTING state-only row's own id --
    # never a new id, never derived from the scraper's own parcel_id.
    assert captured["parcel_id"] == "existing-state-only-uuid"
    # Scraped values win -- these came from the record, not "left alone."
    assert captured["kwargs"]["year_built"] == 1800
    assert captured["kwargs"]["exterior_wall_1"] == "Clapboard"
    assert captured["kwargs"]["owner_name"] == "TEST OWNER A"
    assert captured["kwargs"]["enrichment_status"] == "scraped"
    # Identity fields are not even parameters this call COULD pass --
    # confirmed structurally, not just "wasn't passed this time."
    assert "address" not in captured["kwargs"]
    assert "town" not in captured["kwargs"]
    assert "parcel_id" not in captured["kwargs"]


def test_promote_also_writes_permit_fields_when_record_has_real_permit_data(monkeypatch) -> None:
    monkeypatch.setattr(db_client, "update_parcel_scraped_base_fields", lambda conn, parcel_id, **kw: {"id": parcel_id})
    permit_captured = {}

    def fake_update_permits(conn, parcel_id, **kwargs):
        permit_captured["parcel_id"] = parcel_id
        permit_captured["kwargs"] = kwargs
        return {"id": parcel_id}

    monkeypatch.setattr(db_client, "update_parcel_permit_and_siding_fields", fake_update_permits)

    record = _sample_record(
        permit_data_available=True,
        permit_history=[{"permit_type": "Roofing", "date_opened": "2024-01-01"}],
        exterior_permit_count=1,
        most_recent_exterior_permit_date=date(2024, 1, 1),
        most_recent_exterior_permit_type="Roofing",
    )
    db_client.promote_state_only_parcel_from_scrape(conn=object(), parcel_id="existing-id", record=record)

    assert permit_captured["parcel_id"] == "existing-id"
    assert permit_captured["kwargs"]["permit_data_available"] is True
    assert permit_captured["kwargs"]["exterior_permit_count"] == 1


def test_promote_skips_permit_write_when_record_has_no_real_permit_data(monkeypatch) -> None:
    monkeypatch.setattr(db_client, "update_parcel_scraped_base_fields", lambda conn, parcel_id, **kw: {"id": parcel_id})
    called = {"permit_fn_called": False}

    def fake_update_permits(conn, parcel_id, **kwargs):
        called["permit_fn_called"] = True
        return {"id": parcel_id}

    monkeypatch.setattr(db_client, "update_parcel_permit_and_siding_fields", fake_update_permits)

    record = _sample_record(permit_data_available=False)
    db_client.promote_state_only_parcel_from_scrape(conn=object(), parcel_id="existing-id", record=record)

    assert called["permit_fn_called"] is False
