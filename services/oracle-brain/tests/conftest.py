from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest


@pytest.fixture(scope="session")
def admin_url() -> str:
    url = os.environ.get("ORACLE2_TEST_ADMIN_URL", "")
    if not url:
        pytest.fail("real local Postgres URL required for S02 store tests")
    with psycopg.connect(url) as connection:
        connection.execute("SELECT 1")
    # Ensure pilot tables exist (002_pilot.sql is idempotent).
    sql_dir = Path(__file__).resolve().parents[1] / "sql"
    for sql_file in ("001_foundation.sql", "002_pilot.sql"):
        path = sql_dir / sql_file
        if path.is_file():
            with psycopg.connect(url, autocommit=True) as conn:
                conn.execute(path.read_text())
    return url


@pytest.fixture(scope="session")
def candidate_url() -> str:
    url = os.environ.get("ORACLE2_TEST_CANDIDATE_URL", "")
    if not url:
        pytest.fail("real local candidate FalkorDB URL required")
    return url


@pytest.fixture(scope="session")
def confirmed_url() -> str:
    url = os.environ.get("ORACLE2_TEST_CONFIRMED_URL", "")
    if not url:
        pytest.fail("real local confirmed FalkorDB URL required")
    return url
