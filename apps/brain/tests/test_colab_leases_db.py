"""Database integration tests for 039_colab_leases.sql and FOR UPDATE SKIP LOCKED (#664 Step 3.1)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import errors as pg_errors
from psycopg.types.json import Json

from brain.api.colab import claim_lease_batch, sweep_expired_leases
from brain.config import get_settings
from brain.extract.relations import handle_relations, relations_prompt_hash

SQL_039 = Path(__file__).resolve().parents[1] / "brain" / "sql" / "039_colab_leases.sql"


def _seed_offload_source(
    conn: Any,
    *,
    tag: str,
    chunk_count: int = 4,
    colab_offload: bool = True,
    passage_kind: str = "process",
) -> tuple[str, list[str]]:
    row = conn.execute(
        "INSERT INTO cmap.source (kind, title, storage_path, sha256, bytes, read_state, colab_offload) "
        "VALUES ('text', %s, %s, %s, 100, 'extracting', %s) RETURNING id::text",
        (f"colab-db-{tag}", f"test/{tag}", f"sha-{tag}", colab_offload),
    ).fetchone()
    source_id = str(row[0])
    chunk_ids: list[str] = []
    for ordinal in range(chunk_count):
        crow = conn.execute(
            "INSERT INTO cmap.chunk (source_id, ordinal, locator, text, token_count, passage_kind) "
            "VALUES (%s, %s, %s, %s, 20, %s) RETURNING id::text",
            (
                source_id,
                ordinal,
                Json({"turn": ordinal}),
                f"Jessica reviews submission {ordinal}.",
                passage_kind,
            ),
        ).fetchone()
        cid = str(crow[0])
        chunk_ids.append(cid)
        conn.execute(
            "INSERT INTO cmap.mention (chunk_id, entity_type, surface_name, normalized_name, quote) "
            "VALUES (%s, 'Person', 'Jessica', 'jessica', %s)",
            (cid, f"Jessica reviews submission {ordinal}."),
        )
    conn.commit()
    return source_id, chunk_ids


def test_039_colab_leases_sql_idempotent(db: Any) -> None:
    """Applying 039_colab_leases.sql twice in a row succeeds with zero errors."""
    sql_text = SQL_039.read_text(encoding="utf-8")
    db.execute(sql_text)
    db.commit()
    db.execute(sql_text)
    db.commit()


def test_db_check_rejects_lease_exceeding_30_minutes(db: Any) -> None:
    """DB CHECK constraint hard-blocks any lease TTL > 30 minutes (standing rule)."""
    with pytest.raises(pg_errors.CheckViolation):
        db.execute(
            "INSERT INTO cmap.colab_lease (worker_id, prompt_hash, leased_at, expires_at, chunk_count) "
            "VALUES ('w1', 'hash', now(), now() + interval '31 minutes', 1)"
        )
    db.rollback()

    # Exactly 30 minutes is accepted
    row = db.execute(
        "INSERT INTO cmap.colab_lease (worker_id, prompt_hash, leased_at, expires_at, chunk_count) "
        "VALUES ('w1', 'hash', now(), now() + interval '30 minutes', 1) RETURNING id::text"
    ).fetchone()
    assert row is not None
    db.commit()


def test_concurrent_skip_locked_claims_never_overlap(db: Any) -> None:
    """Two concurrent transactions claiming batches never receive overlapping chunk_ids."""
    _source_id, all_chunks = _seed_offload_source(db, tag="concurrent", chunk_count=10)
    prompt_hash = relations_prompt_hash()
    db_url = get_settings().database_url
    assert db_url is not None

    def _worker_claim(worker_name: str) -> list[str]:
        with psycopg.connect(db_url, connect_timeout=5) as conn:
            _lease_id, _exp, claimed = claim_lease_batch(
                conn,
                worker_id=worker_name,
                limit=6,
                prompt_hash=prompt_hash,
                ttl_seconds=900,
            )
            return [cid for cid, _sid in claimed]

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_worker_claim, "colab-gpu-1")
        f2 = pool.submit(_worker_claim, "colab-gpu-2")
        c1 = f1.result()
        c2 = f2.result()

    assert set(c1).isdisjoint(set(c2))
    assert sorted(c1 + c2) == sorted(all_chunks)


def test_expired_lease_sweep_releases_chunks_and_awaits_reply_excluded(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """Expired leases release chunks for re-lease; live interview sources are never leased."""
    offload_src, offload_chunks = _seed_offload_source(db, tag="expirable", chunk_count=2)
    interview_src, _interview_chunks = _seed_offload_source(db, tag="live-interview", chunk_count=2)

    # Wire interview_src as an active awaits_reply conversation source (#604 L4)
    conv_row = db.execute(
        "INSERT INTO cmap.interview_conversation (employee_id, state, processing_since) "
        "VALUES ('00000000-0000-4000-8000-0000000000b1', 'processing', now()) RETURNING id::text"
    ).fetchone()
    db.execute(
        "INSERT INTO cmap.interview_turn (conversation_id, seq, direction, kind, text, source_id) "
        "VALUES (%s, 1, 'in', 'answer', 'reply', %s)",
        (conv_row[0], interview_src),
    )
    db.commit()

    prompt_hash = relations_prompt_hash()
    lease_1, _exp1, claimed_1 = claim_lease_batch(
        db,
        worker_id="worker-a",
        limit=10,
        prompt_hash=prompt_hash,
        ttl_seconds=900,
    )
    assert lease_1 is not None
    # Only offload_src chunks were claimed; live interview_src was strictly excluded!
    assert [cid for cid, _ in claimed_1] == offload_chunks

    # Backdate lease_1 so it is expired
    db.execute(
        "UPDATE cmap.colab_lease SET leased_at = now() - interval '20 minutes', "
        "expires_at = now() - interval '5 minutes' WHERE id = %s",
        (lease_1,),
    )
    db.commit()

    lease_2, _exp2, claimed_2 = claim_lease_batch(
        db,
        worker_id="worker-b",
        limit=10,
        prompt_hash=prompt_hash,
        ttl_seconds=900,
    )
    assert lease_2 is not None and lease_2 != lease_1
    assert [cid for cid, _ in claimed_2] == offload_chunks

    old_state = db.execute(
        "SELECT state FROM cmap.colab_lease WHERE id = %s", (lease_1,)
    ).fetchone()[0]
    assert old_state == "expired"
    assert sweep_expired_leases(db) == 0

    # Also verify handle_relations defers offload_src when enabled without needing frontier model
    monkeypatch.setenv("BRAIN_COLAB_LEASE_ENABLED", "true")
    monkeypatch.delenv("BRAIN_FRONTIER_MODEL", raising=False)
    get_settings.cache_clear()
    try:
        handle_relations({"payload": {"source_id": offload_src}})
        state_after = db.execute(
            "SELECT read_state FROM cmap.source WHERE id = %s", (offload_src,)
        ).fetchone()[0]
        assert state_after == "extracting"
    finally:
        get_settings.cache_clear()
