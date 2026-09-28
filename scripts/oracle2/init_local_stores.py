#!/usr/bin/env python3
"""Install LangGraph tables and minimum extractor grants in local CI only."""

from __future__ import annotations

import os
from urllib.parse import urlparse

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver


def main() -> None:
    url = os.environ.get("ORACLE2_TEST_ADMIN_URL", "")
    if urlparse(url).hostname not in {"localhost", "127.0.0.1"}:
        raise PermissionError("checkpoint bootstrap requires isolated loopback Postgres")
    with PostgresSaver.from_conn_string(url) as saver:
        saver.setup()
    with psycopg.connect(url) as connection:
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            connection.execute(f"GRANT SELECT,INSERT,UPDATE,DELETE ON public.{table} TO oracle2_extract")


if __name__ == "__main__":
    main()
