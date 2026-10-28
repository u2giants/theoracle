"""Apply the cmap schema migrations: ``python -m brain.migrate``."""

from __future__ import annotations

from pathlib import Path

from brain.db import run_sql

SQL_DIR = Path(__file__).resolve().parent / "sql"


def migrate() -> None:
    """Apply every SQL file in ``brain/sql`` in filename order.

    Each file is idempotent, so running this repeatedly is safe.
    """
    for path in sorted(SQL_DIR.glob("*.sql")):
        run_sql(path)


def main() -> None:
    """Apply the schema and report success."""
    migrate()
    print("cmap schema applied")


if __name__ == "__main__":
    main()
