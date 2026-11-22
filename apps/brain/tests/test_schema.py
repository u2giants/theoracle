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
    "model_seat",
    "employee_flags",
    "resolve_decision",  # added by step 6 (sql/002_resolve.sql)
    "teams_conversation",  # added by step 12 (sql/003_interviews.sql)
    "interview_setting",  # added by step 12 (sql/003_interviews.sql)
    "interview_send",  # added by step 12 (sql/003_interviews.sql)
    "teams_intake",  # added by Teams build-out phase 1 (sql/006_teams_intake.sql)
    "review_flag",  # added by the Map review gate (sql/010_review_flags.sql)
    "translation",  # added by the zh translation sidecar (sql/011_translation.sql)
    "function",  # added by repair step C1 (sql/022_functions.sql)
    "source_function",  # added by repair step C2 (sql/024_function_assignment.sql)
    "chunk_function",  # added by repair step C2 (sql/024_function_assignment.sql)
    "entity_function",  # added by repair step C2 (sql/024_function_assignment.sql)
    "correction",  # added by repair step G1 (sql/026_corrections.sql)
    "source_version",  # added by repair step D2 (sql/028_source_versions.sql)
    "process_flow",  # added by repair step E2 (sql/033_process_flows.sql)
    "flow_step",  # added by repair step E2 (sql/033_process_flows.sql)
    "contradiction",  # added by repair step D3 (sql/032_contradictions.sql)
    "interview_conversation",  # added by #604 (sql/034_interview_conversation.sql)
    "interview_turn",  # added by #604 (sql/034_interview_conversation.sql)
    "intake_item",  # added by #607 (sql/036_message_intake.sql)
    "intake_thread",  # added by #607 (sql/036_message_intake.sql)
    "colab_lease",  # added by #664 (sql/039_colab_leases.sql)
    "colab_lease_item",  # added by #664 (sql/039_colab_leases.sql)
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


def test_migrate_replays_cleanly_with_widened_constraint_rows() -> None:
    """Re-running ``migrate`` must not narrow CHECK constraints broadened in later files."""
    run_migrate()
    settings = get_settings()
    src_id = "00000000-0000-4000-8000-000000000777"
    chk_id = "00000000-0000-4000-8000-000000000778"
    with psycopg.connect(settings.database_url, connect_timeout=5) as conn:
        conn.execute(
            "INSERT INTO cmap.source "
            "(id, kind, title, original_filename, storage_path, sha256, bytes, read_state, origin, date_origin) "
            "VALUES (%s, 'transcript', 't', 't.json', 'cmap/t.json', 'sha', 10, 'read', 'email', 'message_record')",
            (src_id,),
        )
        conn.execute(
            "INSERT INTO cmap.chunk (id, source_id, ordinal, text, token_count) "
            "VALUES (%s, %s, 0, 'body', 1)",
            (chk_id, src_id),
        )
        conn.execute(
            "INSERT INTO cmap.extraction (chunk_id, stage, prompt_hash, model, payload) "
            "VALUES (%s, 'contradiction', 'h1', 'm1', '{}'::jsonb)",
            (chk_id,),
        )
        conn.execute(
            "INSERT INTO cmap.model_seat (stage, model) "
            "VALUES ('relations_messages', 'openai/gpt-6-luna') "
            "ON CONFLICT (stage) DO UPDATE SET model = EXCLUDED.model"
        )
        conn.commit()
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


def test_service_start_applies_schema_before_worker(monkeypatch) -> None:
    """The service applies the schema first; a failure stops the start-up."""
    import pytest

    from brain import __main__ as entry

    order: list[str] = []
    monkeypatch.setattr(entry, "migrate", lambda: order.append("migrate"))
    monkeypatch.setattr(entry, "run_worker", lambda stop: order.append("worker"))
    monkeypatch.setattr(entry.uvicorn, "run", lambda *a, **k: order.append("serve"))
    entry.main()
    assert order[0] == "migrate" and "serve" in order

    def _boom() -> None:
        raise RuntimeError("database unreachable")

    order.clear()
    monkeypatch.setattr(entry, "migrate", _boom)
    with pytest.raises(RuntimeError):
        entry.main()
    assert order == []
