#!/usr/bin/env python3
"""Install canonical ledger prerequisites and checkpoint grants in local CI."""

from __future__ import annotations

import os
import sys
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from verify_workflow_integrity import ROOT, SYNTHETIC_MIGRATIONS
sys.path.insert(0, str(ROOT))
from dev.oracle2.test_tls_bootstrap import postgres_uri, owned_postgres_fixture


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
    details = owned_postgres_fixture(os.environ.get("ORACLE2_SYNTHETIC_POSTGRES_CONTAINER", ""), url)
    project = os.environ.get("COMPOSE_PROJECT_NAME", "")
    labels = details["Config"].get("Labels", {})
    qualification_path = os.environ.get("ORACLE2_TEST_TLS_QUALIFICATION", "")
    if not qualification_path:
        raise PermissionError("owned TLS qualification required")
    qualification = json.loads(Path(qualification_path).read_text())
    if (not re.fullmatch(r"oracle2-(?:ci|synthetic)-[a-z0-9-]{1,80}", project)
            or labels.get("com.docker.compose.project") != project
            or labels.get("com.docker.compose.service") != "postgres"
            or qualification.get("container_id") != details["Id"]
            or qualification.get("synthetic_only") is not True
            or qualification.get("tls_verify_full") is not True
            or qualification.get("plaintext_refused") is not True
            or qualification.get("wrong_password_refused") is not True
            or qualification.get("ca_sha256") != hashlib.sha256(
                Path(dict(query)["sslrootcert"]).read_bytes()).hexdigest()):
        raise PermissionError("owned synthetic target and TLS qualification differ")
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
