"""Unit tests for Colab deferral bounds in apps/brain/brain/chain.py (#668 d)."""

from __future__ import annotations

from typing import Any

import pytest
from test_flat import _seed_text

from brain.chain import MAX_COLAB_DEFER_SECONDS, run_ensure_chain
from brain.config import get_settings
from brain.function_assign import function_assign_prompt_hash


def _seed_colab_offload_extracting(
    db: Any, *, tag: str, job_age_minutes: int
) -> str:
    source_id = _seed_text(db, "Jessica manages licensing proofs.", tag)
    db.execute(
        "UPDATE cmap.source SET read_state = 'extracting', colab_offload = true "
        "WHERE id = %s",
        (source_id,),
    )
    db.execute(
        "INSERT INTO cmap.job (kind, payload, state, created_at, started_at, finished_at) "
        "VALUES ('relations', jsonb_build_object('source_id', %s::text), 'done', "
        "now() - make_interval(mins => %s), "
        "now() - make_interval(mins => %s), "
        "now() - make_interval(mins => %s))",
        (source_id, job_age_minutes + 1, job_age_minutes + 1, job_age_minutes),
    )
    db.commit()
    return source_id


def test_colab_offload_defers_within_30_minutes(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """#668 (d): Within MAX_COLAB_DEFER_SECONDS, ensure_chain defers without re-queueing."""
    assert MAX_COLAB_DEFER_SECONDS == 1800
    monkeypatch.setenv("BRAIN_COLAB_LEASE_ENABLED", "true")
    get_settings.cache_clear()
    try:
        source_id = _seed_colab_offload_extracting(
            db, tag="colab-defer-under-30m", job_age_minutes=10
        )
        stats = run_ensure_chain()
        assert not any(stats.values())

        db.commit()
        offload = db.execute(
            "SELECT colab_offload FROM cmap.source WHERE id = %s", (source_id,)
        ).fetchone()[0]
        assert offload is True
        queued = db.execute(
            "SELECT count(*) FROM cmap.job WHERE kind = 'relations' AND state = 'queued'"
        ).fetchone()[0]
        assert queued == 0
    finally:
        get_settings.cache_clear()


def test_colab_offload_defers_when_lease_is_active_or_recent(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """#668 (d): Active non-expired Colab lease keeps deferral even if relations job > 30m old."""
    monkeypatch.setenv("BRAIN_COLAB_LEASE_ENABLED", "true")
    get_settings.cache_clear()
    try:
        source_id = _seed_colab_offload_extracting(
            db, tag="colab-active-lease", job_age_minutes=45
        )
        chunk_id = db.execute(
            "SELECT id::text FROM cmap.chunk WHERE source_id = %s LIMIT 1",
            (source_id,),
        ).fetchone()[0]
        lease_id = db.execute(
            "INSERT INTO cmap.colab_lease "
            "(worker_id, prompt_hash, leased_at, expires_at, state, chunk_count) "
            "VALUES ('w1', 'hash', now() - interval '5 minutes', now() + interval '10 minutes', 'active', 1) "
            "RETURNING id::text"
        ).fetchone()[0]
        db.execute(
            "INSERT INTO cmap.colab_lease_item (lease_id, chunk_id, source_id, state) "
            "VALUES (%s, %s, %s, 'leased')",
            (lease_id, chunk_id, source_id),
        )
        db.commit()

        stats = run_ensure_chain()
        assert not any(stats.values())

        db.commit()
        offload = db.execute(
            "SELECT colab_offload FROM cmap.source WHERE id = %s", (source_id,)
        ).fetchone()[0]
        assert offload is True
        queued = db.execute(
            "SELECT count(*) FROM cmap.job WHERE kind = 'relations' AND state = 'queued'"
        ).fetchone()[0]
        assert queued == 0
    finally:
        get_settings.cache_clear()


def test_colab_offload_falls_back_to_cloud_after_30_minutes_idle(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """#668 (d): Idle Colab > 30m clears colab_offload and queues cloud relations job."""
    monkeypatch.setenv("BRAIN_COLAB_LEASE_ENABLED", "true")
    get_settings.cache_clear()
    try:
        stale_idle = _seed_colab_offload_extracting(
            db, tag="colab-stale-no-lease", job_age_minutes=45
        )
        stale_expired = _seed_colab_offload_extracting(
            db, tag="colab-stale-expired-lease", job_age_minutes=60
        )
        exp_chunk = db.execute(
            "SELECT id::text FROM cmap.chunk WHERE source_id = %s LIMIT 1",
            (stale_expired,),
        ).fetchone()[0]
        old_lease = db.execute(
            "INSERT INTO cmap.colab_lease "
            "(worker_id, prompt_hash, leased_at, expires_at, state, chunk_count) "
            "VALUES ('w-old', 'hash', now() - interval '50 minutes', "
            "now() - interval '35 minutes', 'expired', 1) RETURNING id::text"
        ).fetchone()[0]
        db.execute(
            "INSERT INTO cmap.colab_lease_item (lease_id, chunk_id, source_id, state) "
            "VALUES (%s, %s, %s, 'failed')",
            (old_lease, exp_chunk, stale_expired),
        )
        db.commit()

        stats = run_ensure_chain()
        assert stats["classify_extract"] == 2

        db.commit()
        for sid in (stale_idle, stale_expired):
            offload = db.execute(
                "SELECT colab_offload FROM cmap.source WHERE id = %s", (sid,)
            ).fetchone()[0]
            assert offload is False

        queued_rows = db.execute(
            "SELECT kind, payload->>'source_id' FROM cmap.job "
            "WHERE state = 'queued' ORDER BY payload->>'source_id'"
        ).fetchall()
        assert {(str(k), str(s)) for k, s in queued_rows} == {
            ("relations", stale_idle),
            ("relations", stale_expired),
        }

        # Second run does not duplicate queued jobs
        assert not any(run_ensure_chain().values())
    finally:
        get_settings.cache_clear()


def test_rag_only_source_queues_function_assign_and_never_classify_extract(
    db: Any,
) -> None:
    """Embedded RAG-only chunks need one completed classification per prompt."""
    source_id = _seed_text(db, "Routine status ping for ROSS SKU.", "rag-only-chain")
    db.execute(
        "UPDATE cmap.source SET read_state = 'read', ingest_tier = 'rag_only', "
        "map_eligible = false WHERE id = %s",
        (source_id,),
    )
    vec = "[" + ",".join(["0.0"] * 1024) + "]"
    db.execute(
        "UPDATE cmap.chunk SET embedding = %s::vector WHERE source_id = %s",
        (vec, source_id),
    )
    db.commit()

    stats = run_ensure_chain()
    assert stats["function_assign"] == 1
    assert stats["classify_extract"] == 0

    kinds = [
        r[0]
        for r in db.execute(
            "SELECT kind FROM cmap.job WHERE state = 'queued'"
        ).fetchall()
    ]
    assert kinds == ["function_assign"]
    # Second pass while function_assign is queued does not duplicate it.
    assert run_ensure_chain()["function_assign"] == 0
    db.execute("UPDATE cmap.job SET state = 'done' WHERE kind = 'function_assign'")
    db.execute(
        "INSERT INTO cmap.extraction (chunk_id, stage, prompt_hash, model, payload) "
        "SELECT id, 'function', %s, 'test', '{}'::jsonb "
        "FROM cmap.chunk WHERE source_id = %s",
        (function_assign_prompt_hash(), source_id),
    )
    db.commit()
    # An empty assignment still marks the chunk as processed.
    assert run_ensure_chain()["function_assign"] == 0
