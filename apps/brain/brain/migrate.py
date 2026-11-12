"""Apply the cmap schema migrations: ``python -m brain.migrate``."""

from __future__ import annotations

import logging
from pathlib import Path

from brain.corrections import migrate_review_flags
from brain.db import get_pool, run_sql

logger = logging.getLogger(__name__)

SQL_DIR = Path(__file__).resolve().parent / "sql"


def migrate() -> None:
    """Apply every SQL file in ``brain/sql`` in filename order, then data steps.

    Each file is idempotent, so running this repeatedly is safe. The
    review-flag backfill (G1) runs after the SQL so its content keys come from
    the one shared Python normaliser; it is idempotent too and logs counts.
    """
    for path in sorted(SQL_DIR.glob("*.sql")):
        run_sql(path)
    with get_pool().connection() as conn:
        counts = migrate_review_flags(conn)
    logger.info("migrate data steps: review_flag→correction %s", counts)


def main() -> None:
    """Apply the schema and report success."""
    migrate()
    print("cmap schema applied")


if __name__ == "__main__":
    main()
