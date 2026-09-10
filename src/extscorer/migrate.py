"""Migration runner for extscorer's packaged SQL migrations.

Migrations live under `extscorer/migrations/*.sql` so they ship inside
the installed package and are reachable via `importlib.resources` -- both
from this repo's own `scripts/migrate.py` and from a downstream package
(e.g. the full/paid overlay) that installs `extscorer` as a dependency
and wants to run the same migrations without duplicating the SQL. Mirrors
`bidscraper.migrate` / `leadscorer.migrate` / `oppscanner.migrate` exactly.
"""
from __future__ import annotations

import sys
from importlib import resources

import psycopg
from dotenv import load_dotenv

from extscorer.config import DatabaseConfig


def iter_migration_sql() -> list[tuple[str, str]]:
    """Return (filename, sql_text) pairs for every packaged migration, sorted by name."""
    migrations_dir = resources.files("extscorer").joinpath("migrations")
    entries = sorted(
        (entry for entry in migrations_dir.iterdir() if entry.name.endswith(".sql")),
        key=lambda entry: entry.name,
    )
    return [(entry.name, entry.read_text(encoding="utf-8")) for entry in entries]


def run_migrations(dsn: str | None = None) -> None:
    """Apply every packaged migration, in filename order, to `dsn`.

    Falls back to `DatabaseConfig.from_env()` if `dsn` isn't given.
    Migrations use `if not exists` guards, so this is safe to rerun.
    """
    resolved_dsn = dsn or DatabaseConfig.from_env().dsn
    migrations = iter_migration_sql()
    if not migrations:
        raise RuntimeError("No migrations found in the extscorer package.")

    with psycopg.connect(resolved_dsn) as conn:
        for name, sql in migrations:
            print(f"Applying migration: {name}")
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
            print(f"Applied: {name}")

    print("All migrations applied successfully.")


def main() -> int:
    load_dotenv()
    try:
        run_migrations()
    except RuntimeError as exc:
        print(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
