"""Manual per-parcel holds (migration 017): the table, the annotation `parcels_for_client` adds, and the two digest selectors.
A held parcel is left out; releasing the hold brings it back. Text checks on the migration (this runner replays every migration)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from extscorer.db import client
from extscorer.digest.selection import is_held, select_new_leads_for_pipeline, select_unsent_leads

SQL = (Path(__file__).resolve().parent.parent / "src" / "extscorer" / "migrations" / "017_add_parcel_holds.sql").read_text()
BODY = " ".join(" ".join(ln for ln in SQL.splitlines() if not ln.strip().startswith("--")).lower().split())


# --- the migration -----------------------------------------------------------------------------------------------

def test_table_has_the_columns_and_rls_on_with_no_policy() -> None:
    for col in ("client_id text not null", "parcel_uuid uuid not null references parcels (id)", "kind text not null", "reason text not null",
                "held_by text not null", "held_at timestamptz not null default now()", "released_at timestamptz", "released_by text"):
        assert col in BODY
    assert "alter table parcel_holds enable row level security" in BODY
    assert "policy" not in BODY


def test_kind_is_limited_and_reason_cannot_be_blank() -> None:
    assert "check (kind in ('shown_to_crew', 'data_review', 'other'))" in BODY
    assert "check (length(btrim(reason)) > 0)" in BODY
    assert tuple(client.HOLD_KINDS) == ("shown_to_crew", "data_review", "other")


def test_a_release_names_who_released_it_and_cannot_predate_the_hold() -> None:
    assert "check (released_at is null or released_at >= held_at)" in BODY
    assert "check ((released_at is null) = (released_by is null))" in BODY


def test_active_holds_are_indexed_and_a_parcel_may_carry_several() -> None:
    assert BODY.count("create index if not exists") == 2 and "where released_at is null" in BODY
    assert "unique" not in BODY  # more than one active hold per parcel is allowed


def test_replaying_is_safe_and_parcels_is_untouched() -> None:
    assert "create table if not exists parcel_holds" in BODY
    for word in ("alter table parcels", "update parcels", "delete from parcels", "drop table", "drop column"):
        assert word not in BODY


# --- the predicate and the two selectors -------------------------------------------------------------------------

class _Lead:
    def __init__(self, parcel_id: str) -> None:
        self.parcel_id = parcel_id


def _pairs(*held: str) -> list[tuple[_Lead, dict]]:
    """Three otherwise-eligible parcels A, B, C in rank order; those named in `held` carry the annotation."""
    return [(_Lead(i), {"id": f"row-{i}", "town": "Killingly", "parcel_id": i, "on_hold": i in held}) for i in "ABC"]


def test_is_held_reads_the_annotation_and_defaults_to_false() -> None:
    assert is_held({"on_hold": True}) is True
    assert is_held({"on_hold": False}) is False
    assert is_held({}) is False  # an un-annotated dict is not a held parcel


@pytest.mark.parametrize("select", ["unsent", "pipeline"])
def test_a_held_parcel_is_not_selected_for_the_digest_or_the_sheet(select: str) -> None:
    def run(pairs):
        if select == "unsent":
            return select_unsent_leads(pairs, already_sent_parcel_row_ids=set(), limit=10)
        return select_new_leads_for_pipeline(pairs, existing_pipeline_lead_keys=set(), limit=10)

    assert [p["parcel_id"] for _, p in run(_pairs("B"))] == ["A", "C"]


@pytest.mark.parametrize("select", ["unsent", "pipeline"])
def test_releasing_the_hold_brings_the_parcel_back(select: str) -> None:
    def run(pairs):
        if select == "unsent":
            return select_unsent_leads(pairs, already_sent_parcel_row_ids=set(), limit=10)
        return select_new_leads_for_pipeline(pairs, existing_pipeline_lead_keys=set(), limit=10)

    assert [p["parcel_id"] for _, p in run(_pairs("B"))] == ["A", "C"]
    assert [p["parcel_id"] for _, p in run(_pairs())] == ["A", "B", "C"]  # the hold released: no annotation


def test_a_held_parcel_does_not_use_up_a_slot() -> None:
    selected = select_new_leads_for_pipeline(_pairs("A"), existing_pipeline_lead_keys=set(), limit=2)
    assert [p["parcel_id"] for _, p in selected] == ["B", "C"]


# --- the annotation and the helpers (a fake connection records the SQL) ------------------------------------------

class _Cursor:
    def __init__(self, conn: "_Conn") -> None:
        self.conn = conn
        self.rowcount = 0

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *exc) -> None:
        return None

    def execute(self, sql: str, params: dict | None = None) -> None:
        self.conn.calls.append((" ".join(sql.split()), params))
        self.sql = sql
        self.rowcount = 1

    def fetchall(self) -> list[dict]:
        return self.conn.holds if "from parcel_holds" in self.sql else self.conn.parcels

    def fetchone(self) -> tuple:
        return (41,)


class _Conn:
    def __init__(self, parcels: list[dict], holds: list[dict]) -> None:
        self.parcels, self.holds, self.calls = parcels, holds, []

    def cursor(self, row_factory=None) -> _Cursor:
        return _Cursor(self)


def _hold(parcel_uuid: str, **kw) -> dict:
    row = {"id": 1, "parcel_uuid": parcel_uuid, "kind": "shown_to_crew", "reason": "shown to a crew", "held_by": "noah",
           "held_at": datetime(2026, 11, 18, tzinfo=timezone.utc)}
    row.update(kw)
    return row


def test_parcels_for_client_annotates_held_and_unheld_parcels() -> None:
    conn = _Conn([{"id": "u1"}, {"id": "u2"}], [_hold("u1"), _hold("u1", id=2, kind="data_review", reason="year stale")])
    parcels = client.parcels_for_client(conn, "c")
    by = {p["id"]: p for p in parcels}
    assert by["u1"]["on_hold"] is True and [h["kind"] for h in by["u1"]["holds"]] == ["shown_to_crew", "data_review"]
    assert by["u2"]["on_hold"] is False and by["u2"]["holds"] == []
    assert len(parcels) == 2  # a held parcel is still returned: scoring and the internal views show everything
    hold_sql = next(sql for sql, _ in conn.calls if "from parcel_holds" in sql)
    assert "released_at is null" in hold_sql  # only ACTIVE holds are read


def test_only_active_holds_reach_a_parcel_so_a_released_one_is_gone() -> None:
    # `released_at is null` is in the query; a released hold is never returned by it, so the next load has no annotation
    conn = _Conn([{"id": "u1"}], [])
    assert client.parcels_for_client(conn, "c")[0]["on_hold"] is False


def test_add_hold_validates_before_it_writes() -> None:
    conn = _Conn([], [])
    assert client.add_parcel_hold(conn, "c", "u1", "data_review", "  year stale  ", "noah") == 41
    sql, params = conn.calls[-1]
    assert sql.startswith("insert into parcel_holds") and params["reason"] == "year stale" and params["kind"] == "data_review"
    for bad in (("nope", "r", "noah"), ("other", "  ", "noah"), ("other", "r", " ")):
        with pytest.raises(ValueError):
            client.add_parcel_hold(conn, "c", "u1", *bad)


def test_release_sets_released_at_and_skips_the_already_released() -> None:
    conn = _Conn([], [])
    assert client.release_parcel_holds(conn, "c", [3, 4], "noah") == 1  # the fake reports one row
    sql, params = conn.calls[-1]
    assert "set released_at = now(), released_by" in sql and "released_at is null" in sql and params["ids"] == [3, 4]
    assert client.release_parcel_holds(conn, "c", [], "noah") == 0
    with pytest.raises(ValueError):
        client.release_parcel_holds(conn, "c", [3], " ")


# --- end to end: a hold in the TABLE reaches the selectors through parcels_for_client -----------------------------

def _loaded(holds: list[dict]) -> list[tuple[_Lead, dict]]:
    """Three parcels loaded the real way (`parcels_for_client` over a fake connection) and paired with a lead each, in rank order."""
    conn = _Conn([{"id": f"u{i}", "town": "Killingly", "parcel_id": i} for i in "ABC"], holds)
    return [(_Lead(p["parcel_id"]), p) for p in client.parcels_for_client(conn, "c")]


@pytest.mark.parametrize("select", ["unsent", "pipeline"])
def test_a_hold_row_reaches_the_selectors_and_releasing_it_brings_the_parcel_back(select: str) -> None:
    def run(pairs):
        if select == "unsent":
            return select_unsent_leads(pairs, already_sent_parcel_row_ids=set(), limit=10)
        return select_new_leads_for_pipeline(pairs, existing_pipeline_lead_keys=set(), limit=10)

    assert [p["parcel_id"] for _, p in run(_loaded([_hold("uB")]))] == ["A", "C"]  # an active hold row on B
    assert [p["parcel_id"] for _, p in run(_loaded([]))] == ["A", "B", "C"]  # released: the query returns no row for it
