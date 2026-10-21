#!/usr/bin/env python3
"""Install canonical ledger prerequisites and checkpoint grants in local CI."""

from __future__ import annotations

import os
import sys
from urllib.parse import parse_qsl, urlsplit

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from verify_workflow_integrity import ROOT, SYNTHETIC_MIGRATIONS
sys.path.insert(0, str(ROOT))
from dev.oracle2.test_tls_bootstrap import postgres_uri


def main() -> None:
    if any(name.startswith("PG") for name in os.environ):
        raise PermissionError("libpq environment overrides forbidden for synthetic bootstrap")
    url = os.environ.get("ORACLE2_TEST_ADMIN_URL", "")
    parsed = urlsplit(url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    keys = [key for key, _ in query]
    if (parsed.scheme not in {"postgresql", "postgres"}
            or parsed.hostname != "127.0.0.1"
            or parsed.fragment or len(keys) != len(set(keys))
            or set(keys) != {"sslmode", "sslrootcert"}
            or dict(query)["sslmode"] != "verify-full"
            or not dict(query)["sslrootcert"]):
        raise PermissionError("checkpoint bootstrap requires isolated loopback Postgres")
    # The TLS fixture's canonicalizer rejects libpq routing indirection and
    # pins explicit host/port/database/user. Use only its normalized URI below.
    url = postgres_uri(url, sslrootcert=dict(query)["sslrootcert"])
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
