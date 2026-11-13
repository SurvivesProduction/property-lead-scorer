"""The one place a load, backfill or re-scrape writes a changed `parcels` value *and* records what it replaced.

`parcel_load_log` (migration 016) is append-only: every changed field is one row (before, after, which load, which run).
`logged_update` / `logged_update_many` read the old row `for update`, write only what differs, and append the log rows in
the same transaction. They never commit: the caller does, so a failed log insert rolls the write back with it.

Not logged here: `raw_data` (a whole source record; rollback info does not belong in it any more) and the identity
columns. Passing either raises, so no script can slip a rollback blob back into `raw_data` through this path.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

INSERT_FIELD = "__insert__"
# Columns that name the row or hold the source record; never written through the logged helpers.
FORBIDDEN_FIELDS = frozenset({"id", "client_id", "town", "parcel_id", "raw_data", "created_at", "updated_at", "first_seen_at", "last_seen_at"})


@dataclass(frozen=True)
class LoadContext:
    """Who is writing: a load name, the script, and one run id for the whole invocation."""

    client_id: str
    load_key: str
    script: str
    run_id: uuid.UUID = field(default_factory=uuid.uuid4)
    source: str = "live"  # 'migration' only for the one-time copy of old rollback blobs


@dataclass(frozen=True)
class FieldChange:
    field: str
    before: Any
    after: Any
    meta: Mapping[str, Any] | None = None


def to_json_value(value: Any) -> Any:
    """A column value as JSON: dates as ISO text, numerics as numbers, containers recursively. None stays None."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): to_json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_value(v) for v in value]
    return str(value)


def _same(before: Any, after: Any) -> bool:
    return to_json_value(before) == to_json_value(after)


def check_fields(fields: Iterable[str]) -> None:
    for name in fields:
        if name in FORBIDDEN_FIELDS:
            raise ValueError(f"{name!r} cannot be written through the logged helpers")
        if not name.replace("_", "").isalnum() or name != name.lower():
            raise ValueError(f"not a plain column name: {name!r}")


def diff_fields(before: Mapping[str, Any], new_values: Mapping[str, Any]) -> list[FieldChange]:
    """The fields of `new_values` whose value differs from `before`, in the order given."""
    check_fields(new_values)
    return [FieldChange(f, before.get(f), v) for f, v in new_values.items() if not _same(before.get(f), v)]


def _log_params(ctx: LoadContext, parcel: Mapping[str, Any], change: FieldChange, meta: Mapping[str, Any] | None) -> tuple:
    merged = {**(meta or {}), **(change.meta or {})}
    return (
        ctx.client_id, parcel["id"], parcel["town"], str(parcel["parcel_id"]), ctx.load_key, ctx.run_id, ctx.script,
        change.field, Jsonb(to_json_value(change.before)), Jsonb(to_json_value(change.after)), ctx.source,
        Jsonb(to_json_value(merged)) if merged else None,
    )


_INSERT_LOG = """
    insert into parcel_load_log (client_id, parcel_uuid, town, parcel_key, load_key, run_id, script, field,
                                 before_value, after_value, source, meta)
    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


# The one-time copy of old rollback blobs can be re-run: the partial unique index on source = 'migration' skips repeats.
_INSERT_LOG_ONCE = _INSERT_LOG + " on conflict (parcel_uuid, load_key, field) where source = 'migration' do nothing"


def append_log(conn, ctx: LoadContext, parcel: Mapping[str, Any], changes: Sequence[FieldChange], meta: Mapping[str, Any] | None = None) -> int:
    """Append one log row per change. Does not commit. For `source = 'migration'` a repeated (parcel, load, field) is skipped."""
    if not changes:
        return 0
    query = _INSERT_LOG_ONCE if ctx.source == "migration" else _INSERT_LOG
    with conn.cursor() as cur:
        cur.executemany(query, [_log_params(ctx, parcel, c, meta) for c in changes])
    return len(changes)


def log_insert(conn, ctx: LoadContext, parcel: Mapping[str, Any], meta: Mapping[str, Any] | None = None) -> int:
    """Record that a load created this row (field `__insert__`, no before-value)."""
    return append_log(conn, ctx, parcel, [FieldChange(INSERT_FIELD, None, True)], meta)


def _fetch_old(conn, parcel_uuids: Sequence[Any], columns: Sequence[str]) -> dict[Any, dict[str, Any]]:
    query = sql.SQL("select id, town, parcel_id, {cols} from parcels where id = any(%s) for update").format(
        cols=sql.SQL(", ").join(sql.Identifier(c) for c in columns))
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, (list(parcel_uuids),))
        return {row["id"]: row for row in cur.fetchall()}


def logged_update_many(conn, ctx: LoadContext, assignments: Sequence[tuple[Any, Mapping[str, Any]]], meta: Mapping[str, Any] | None = None,
                       touch_updated_at: bool = True) -> dict[Any, list[FieldChange]]:
    """`assignments` = [(parcel uuid, {column: new value})]. Writes only the columns whose value differs, bumps
    `updated_at` on rows that changed, and logs every change. Returns {parcel uuid: [changes]} for the rows that changed.
    A parcel missing from the table raises. Does not commit."""
    if not assignments:
        return {}
    columns = sorted({c for _, values in assignments for c in values})
    check_fields(columns)
    old = _fetch_old(conn, [pid for pid, _ in assignments], columns)
    changed: dict[Any, list[FieldChange]] = {}
    with conn.cursor() as cur:
        for pid, values in assignments:
            if pid not in old:
                raise LookupError(f"parcel {pid} not found")
            changes = diff_fields(old[pid], values)
            if not changes:
                continue
            sets = [sql.SQL("{} = %s").format(sql.Identifier(c.field)) for c in changes]
            if touch_updated_at:
                sets.append(sql.SQL("updated_at = now()"))
            cur.execute(sql.SQL("update parcels set {sets} where id = %s").format(sets=sql.SQL(", ").join(sets)),
                        [_adapt(c.after) for c in changes] + [pid])
            changed[pid] = changes
    for pid, changes in changed.items():
        append_log(conn, ctx, old[pid], changes, meta)
    return changed


def logged_update(conn, ctx: LoadContext, parcel_uuid: Any, new_values: Mapping[str, Any], meta: Mapping[str, Any] | None = None,
                  touch_updated_at: bool = True) -> list[FieldChange]:
    return logged_update_many(conn, ctx, [(parcel_uuid, new_values)], meta, touch_updated_at).get(parcel_uuid, [])


def _adapt(value: Any) -> Any:
    """Dicts and lists go to jsonb columns (permit_history, state_parcel_ref); everything else is passed through."""
    return Jsonb(value) if isinstance(value, (dict, list)) else value
