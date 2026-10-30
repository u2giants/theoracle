"""Step 1 gate: the cmap schema applies twice cleanly and holds 15 tables."""

from __future__ import annotations

import subprocess
import sys

import psycopg

from brain.config import get_settings

EXPECTED_TABLES = {
    "source",
    "chunk",
    "extraction",
    "mention",
    "entity",
    "entity_alias",
    "relation",
    "community",
    "job",
    "graph_version",
    "open_question",
    "eval_question",
    "eval_run",
    "recommendation",
    "employee_flags",
    "resolve_decision",  # added by step 6 (sql/002_resolve.sql)
    "teams_conversation",  # added by step 12 (sql/003_interviews.sql)
    "interview_setting",  # added by step 12 (sql/003_interviews.sql)
    "interview_send",  # added by step 12 (sql/003_interviews.sql)
}


def run_migrate() -> None:
    """Run ``python -m brain.migrate`` as its own process and require success."""
    result = subprocess.run(
        [sys.executable, "-m", "brain.migrate"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_migrate_runs_twice_without_error() -> None:
    """``python -m brain.migrate`` succeeds on a fresh database and again."""
    run_migrate()
    run_migrate()


def test_all_tables_exist() -> None:
    """information_schema lists exactly the cmap tables (15 from step 1, plus step 6's resolve_decision and step 12's interview tables)."""
    run_migrate()
    settings = get_settings()
    with psycopg.connect(settings.database_url, connect_timeout=5) as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'cmap' AND table_type = 'BASE TABLE'"
        ).fetchall()
    found = {name for (name,) in rows}
    assert found == EXPECTED_TABLES
