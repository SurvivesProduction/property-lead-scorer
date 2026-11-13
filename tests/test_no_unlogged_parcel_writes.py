"""Ratchet: raw SQL that writes `parcels` may only shrink. New writes go through extscorer.db.load_log.

The allowlist is the set of raw statements that existed when the log was added; converting one lowers its number here.
A new file, or a higher count, fails the test.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERN = re.compile(r"\b(update|insert\s+into|delete\s+from)\s+parcels\b", re.IGNORECASE)
ALLOWED = {
    "src/extscorer/db/client.py": 13,  # upsert_parcel + the update_parcel_* helpers (one count is a docstring), to be moved onto load_log
    "src/extscorer/db/load_log.py": 1,  # the helper itself
}


def _counts() -> dict[str, int]:
    out = {}
    for base in ("src", "scripts"):
        for path in (ROOT / base).rglob("*.py"):
            n = len(PATTERN.findall(path.read_text(encoding="utf-8")))
            if n:
                out[str(path.relative_to(ROOT))] = n
    return out


def test_no_new_raw_parcel_writes() -> None:
    counts = _counts()
    new_files = sorted(set(counts) - set(ALLOWED))
    assert not new_files, f"raw parcel writes in {new_files}: use extscorer.db.load_log.logged_update"
    grown = {f: (n, ALLOWED[f]) for f, n in counts.items() if n > ALLOWED[f]}
    assert not grown, f"more raw parcel writes than allowed (found, allowed): {grown}"


def test_the_allowlist_is_tight() -> None:
    shrunk = {f: (counts, ALLOWED[f]) for f, counts in ((f, _counts().get(f, 0)) for f in ALLOWED) if counts < ALLOWED[f]}
    assert not shrunk, f"lower the allowlist to the new counts (found, allowed): {shrunk}"
