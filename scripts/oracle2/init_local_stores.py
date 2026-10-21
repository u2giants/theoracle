#!/usr/bin/env python3
"""Install canonical ledger prerequisites and checkpoint grants in local CI."""

from __future__ import annotations

import os
from urllib.parse import urlparse

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from verify_workflow_integrity import ROOT, SYNTHETIC_MIGRATIONS


def main() -> None:
    url = os.environ.get("ORACLE2_TEST_ADMIN_URL", "")
    if urlparse(url).hostname not in {"localhost", "127.0.0.1"}:
        raise PermissionError("checkpoint bootstrap requires isolated loopback Postgres")
    # W10 owns separate temporary databases. S03 uses this Compose database,
    # which must independently have the same canonical host prerequisites.
    # Execute unchanged migrations in order; their owner/role checks still gate
    # installation. No runtime admissions or source grants are issued here.
    with psycopg.connect(url) as connection:
        for migration in SYNTHETIC_MIGRATIONS:
            connection.execute((ROOT / "services/oracle-brain/sql" / migration).read_text())
    with PostgresSaver.from_conn_string(url) as saver:
        saver.setup()
    with psycopg.connect(url) as connection:
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            connection.execute(f"GRANT SELECT,INSERT,UPDATE,DELETE ON public.{table} TO oracle2_checkpoint")


if __name__ == "__main__":
    main()
