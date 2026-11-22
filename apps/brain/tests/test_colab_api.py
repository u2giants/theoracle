"""API & adversarial tests for /colab/lease, /colab/submit, /colab/status (#664 Step 3.2 & §9a)."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from conftest import TEST_TOKEN, fake_embeddings
from fastapi.testclient import TestClient
from psycopg.types.json import Json

from brain.api.colab import MAX_SUBMIT_BYTES
from brain.config import get_settings
from brain.extract.relations import relations_prompt_hash

WORKER_TOKEN = "colab-worker-secret-token-distinct-664"
VALID_MODEL_TAG = (
    "colab-vllm/Qwen/Qwen2.5-32B-Instruct@0123456789abcdef0123456789abcdef01234567"
)


@pytest.fixture()
def colab_enabled_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BRAIN_COLAB_LEASE_ENABLED", "true")
    monkeypatch.setenv("BRAIN_COLAB_WORKER_TOKEN", WORKER_TOKEN)
    monkeypatch.setenv("BRAIN_COLAB_LEASE_TTL_SECONDS", "900")
    monkeypatch.setenv("BRAIN_COLAB_MAX_BATCH_SIZE", "64")
    get_settings.cache_clear()
    fake_embeddings(monkeypatch)
    yield
    get_settings.cache_clear()


def _worker_headers(token: str = WORKER_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_source_with_chunks(
    db: Any,
    *,
    tag: str,
    passages: list[str],
    colab_offload: bool = True,
) -> tuple[str, list[str]]:
    srow = db.execute(
        "INSERT INTO cmap.source (kind, title, storage_path, sha256, bytes, read_state, colab_offload) "
        "VALUES ('text', %s, %s, %s, 200, 'extracting', %s) RETURNING id::text",
        (f"api-{tag}", f"test/{tag}", f"sha-api-{tag}", colab_offload),
    ).fetchone()
    source_id = str(srow[0])
    chunk_ids: list[str] = []
    for idx, text in enumerate(passages):
        crow = db.execute(
            "INSERT INTO cmap.chunk (source_id, ordinal, locator, text, token_count, passage_kind) "
            "VALUES (%s, %s, %s, %s, 30, 'process') RETURNING id::text",
            (source_id, idx, Json({"page": idx + 1}), text),
        ).fetchone()
        cid = str(crow[0])
        chunk_ids.append(cid)
        db.execute(
            "INSERT INTO cmap.mention (chunk_id, entity_type, surface_name, normalized_name, quote) "
            "VALUES (%s, 'Person', 'Jessica', 'jessica', %s), "
            "(%s, 'Role', 'Licensing Manager', 'licensing manager', %s)",
            (cid, text, cid, text),
        )
    db.commit()
    return source_id, chunk_ids


def test_colab_auth_rejects_missing_wrong_and_shared_token(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    colab_enabled_env,
) -> None:
    """§9a: Missing, wrong bearer token, or BRAIN_SHARED_TOKEN rejected with 401; identical tokens -> 503."""
    # 1. Missing header -> 401
    r_missing = client.post("/colab/lease", json={"worker_id": "w1", "max_items": 4})
    assert r_missing.status_code == 401

    # 2. Wrong bearer token -> 401
    r_wrong = client.post(
        "/colab/lease",
        headers=_worker_headers("wrong-secret"),
        json={"worker_id": "w1", "max_items": 4},
    )
    assert r_wrong.status_code == 401

    # 3. Caller passes BRAIN_SHARED_TOKEN instead of BRAIN_COLAB_WORKER_TOKEN -> 401
    r_shared = client.post(
        "/colab/lease",
        headers=_worker_headers(TEST_TOKEN),
        json={"worker_id": "w1", "max_items": 4},
    )
    assert r_shared.status_code == 401

    # 4. Misconfigured environment where BRAIN_COLAB_WORKER_TOKEN == BRAIN_SHARED_TOKEN -> 503
    monkeypatch.setenv("BRAIN_COLAB_WORKER_TOKEN", TEST_TOKEN)
    get_settings.cache_clear()
    r_conflated = client.post(
        "/colab/lease",
        headers=_worker_headers(TEST_TOKEN),
        json={"worker_id": "w1", "max_items": 4},
    )
    assert r_conflated.status_code == 503

    # 5. Disabled flag -> 503
    monkeypatch.setenv("BRAIN_COLAB_WORKER_TOKEN", WORKER_TOKEN)
    monkeypatch.setenv("BRAIN_COLAB_LEASE_ENABLED", "false")
    get_settings.cache_clear()
    r_disabled = client.post(
        "/colab/lease",
        headers=_worker_headers(WORKER_TOKEN),
        json={"worker_id": "w1", "max_items": 4},
    )
    assert r_disabled.status_code == 503


def test_submit_rejects_foreign_or_unknown_chunk_id(
    client: TestClient, db: Any, colab_enabled_env
) -> None:
    """§9a: Submitting foreign/non-offload/unknown chunk_id returns 400 with zero DB writes."""
    _offload_src, _offload_chunks = _seed_source_with_chunks(
        db,
        tag="leased",
        passages=["Jessica is the Licensing Manager for POP Creations."],
        colab_offload=True,
    )
    _non_offload_src, non_offload_chunks = _seed_source_with_chunks(
        db,
        tag="non-offload",
        passages=["Jessica is the Licensing Manager for Spruce Line."],
        colab_offload=False,
    )

    lease_resp = client.post(
        "/colab/lease",
        headers=_worker_headers(),
        json={"worker_id": "w1", "max_items": 10},
    )
    assert lease_resp.status_code == 200
    lease_data = lease_resp.json()
    assert len(lease_data["items"]) == 1

    # Submit non-offload chunk_id and random nonexistent UUID
    for bad_cid in (non_offload_chunks[0], str(uuid.uuid4())):
        sub = client.post(
            "/colab/submit",
            headers=_worker_headers(),
            json={
                "lease_id": lease_data["lease_id"],
                "prompt_hash": lease_data["prompt_hash"],
                "model_tag": VALID_MODEL_TAG,
                "results": [
                    {
                        "chunk_id": bad_cid,
                        "raw_content": '{"relations": [], "new_mentions": []}',
                        "finish_reason": "stop",
                    }
                ],
            },
        )
        assert sub.status_code == 400

    ext_count = db.execute("SELECT count(*) FROM cmap.extraction").fetchone()[0]
    rel_count = db.execute("SELECT count(*) FROM cmap.relation").fetchone()[0]
    assert ext_count == 0 and rel_count == 0


def test_expired_lease_submit_rejected_without_clobber(
    client: TestClient, db: Any, colab_enabled_env
) -> None:
    """§9a: Submitting after 15-min expiry & re-lease returns 409; second worker's lease stays intact."""
    _src, chunks = _seed_source_with_chunks(
        db,
        tag="expiry-race",
        passages=["Jessica is the Licensing Manager who approves proofs."],
    )
    l1 = client.post(
        "/colab/lease",
        headers=_worker_headers(),
        json={"worker_id": "slow-worker", "max_items": 4},
    ).json()
    lease_1_id = l1["lease_id"]

    # Expire lease 1 in DB
    db.execute(
        "UPDATE cmap.colab_lease SET leased_at = now() - interval '20 minutes', "
        "expires_at = now() - interval '5 minutes' WHERE id = %s",
        (lease_1_id,),
    )
    db.commit()

    # Worker 2 leases the same chunk cleanly
    l2 = client.post(
        "/colab/lease",
        headers=_worker_headers(),
        json={"worker_id": "fast-worker", "max_items": 4},
    ).json()
    lease_2_id = l2["lease_id"]
    assert lease_2_id != lease_1_id
    assert [i["chunk_id"] for i in l2["items"]] == chunks

    # Late Worker 1 tries to submit -> 409 Conflict
    late_sub = client.post(
        "/colab/submit",
        headers=_worker_headers(),
        json={
            "lease_id": lease_1_id,
            "prompt_hash": l1["prompt_hash"],
            "model_tag": VALID_MODEL_TAG,
            "results": [
                {
                    "chunk_id": chunks[0],
                    "raw_content": '{"relations": [], "new_mentions": []}',
                }
            ],
        },
    )
    assert late_sub.status_code == 409

    # Worker 2's lease is untouched and succeeds cleanly
    good_reply = {
        "relations": [
            {
                "from": "m1",
                "to": "m2",
                "type": "PERFORMS",
                "description": "Jessica serves as Licensing Manager.",
                "description_en": "",
                "stance": "practice",
                "confidence": 0.9,
                "quote": "Jessica is the Licensing Manager who approves proofs.",
            }
        ],
        "new_mentions": [],
    }
    w2_sub = client.post(
        "/colab/submit",
        headers=_worker_headers(),
        json={
            "lease_id": lease_2_id,
            "prompt_hash": l2["prompt_hash"],
            "model_tag": VALID_MODEL_TAG,
            "results": [
                {
                    "chunk_id": chunks[0],
                    "raw_content": json.dumps(good_reply),
                }
            ],
        },
    )
    assert w2_sub.status_code == 200
    assert w2_sub.json()["relations_written"] == 1


def test_prompt_hash_drift_rejected(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    db: Any,
    colab_enabled_env,
) -> None:
    """§9a: Prompt change while Colab batch is in flight returns 409 and frees chunk for new hash."""
    _src, chunks = _seed_source_with_chunks(
        db,
        tag="hash-drift",
        passages=["Jessica is the Licensing Manager on duty."],
    )
    l1 = client.post(
        "/colab/lease",
        headers=_worker_headers(),
        json={"worker_id": "w1", "max_items": 4},
    ).json()

    # Simulate relations.md prompt edit changing relations_prompt_hash()
    from brain.api import colab as colab_api_mod

    new_hash = "f" * 64
    monkeypatch.setattr(colab_api_mod, "relations_prompt_hash", lambda: new_hash)

    drift_sub = client.post(
        "/colab/submit",
        headers=_worker_headers(),
        json={
            "lease_id": l1["lease_id"],
            "prompt_hash": l1["prompt_hash"],
            "model_tag": VALID_MODEL_TAG,
            "results": [
                {
                    "chunk_id": chunks[0],
                    "raw_content": '{"relations": [], "new_mentions": []}',
                }
            ],
        },
    )
    assert drift_sub.status_code == 409

    # Chunk is immediately re-leaseable under the new prompt_hash!
    l2 = client.post(
        "/colab/lease",
        headers=_worker_headers(),
        json={"worker_id": "w2", "max_items": 4},
    ).json()
    assert l2["prompt_hash"] == new_hash
    assert [i["chunk_id"] for i in l2["items"]] == chunks


def test_untrusted_model_reply_filtered_by_validate_response(
    client: TestClient, db: Any, admin_headers: dict[str, str], colab_enabled_env
) -> None:
    """§9a: Hallucinated quote, unknown rel_type, and truncated JSON are filtered; source completes & queues resolve."""
    src_id, chunks = _seed_source_with_chunks(
        db,
        tag="untrusted-reply",
        passages=[
            "Jessica is the Licensing Manager for Disney approvals.",
            "Jessica reviews artwork before submission.",
        ],
    )
    lease = client.post(
        "/colab/lease",
        headers=_worker_headers(),
        json={"worker_id": "w1", "max_items": 10},
    ).json()
    assert len(lease["items"]) == 2

    # Chunk 0: 1 valid relation + 1 hallucinated quote + 1 invalid rel_type
    mixed_reply = {
        "relations": [
            {
                "from": "m1",
                "to": "m2",
                "type": "PERFORMS",
                "description": "Jessica acts as Licensing Manager.",
                "description_en": "",
                "stance": "policy",
                "confidence": 0.95,
                "quote": "Jessica is the Licensing Manager for Disney approvals.",
            },
            {
                "from": "m1",
                "to": "m2",
                "type": "OWNS",
                "description": "Hallucinated relation.",
                "description_en": "",
                "stance": "policy",
                "confidence": 0.9,
                "quote": "THIS QUOTE DOES NOT EXIST IN THE PASSAGE.",
            },
            {
                "from": "m1",
                "to": "m2",
                "type": "INVENTED_REL_TYPE",
                "description": "Invalid type.",
                "description_en": "",
                "stance": "policy",
                "confidence": 0.9,
                "quote": "Jessica is the Licensing Manager for Disney approvals.",
            },
        ],
        "new_mentions": [],
    }
    # Chunk 1: truncated JSON mid-second-item (parse_relations_json salvages complete first item!)
    truncated_raw = (
        '{"relations": [{"from": "m1", "to": "m2", "type": "PERFORMS", '
        '"description": "Jessica reviews artwork.", "description_en": "", '
        '"stance": "practice", "confidence": 0.85, '
        '"quote": "Jessica reviews artwork before submission."}, '
        '{"from": "m1", "to": "m2", "type": "OWNS"'
    )

    sub = client.post(
        "/colab/submit",
        headers=_worker_headers(),
        json={
            "lease_id": lease["lease_id"],
            "prompt_hash": lease["prompt_hash"],
            "model_tag": VALID_MODEL_TAG,
            "results": [
                {"chunk_id": chunks[0], "raw_content": json.dumps(mixed_reply)},
                {"chunk_id": chunks[1], "raw_content": truncated_raw, "finish_reason": "length"},
            ],
        },
    )
    assert sub.status_code == 200
    body = sub.json()
    assert body["relations_written"] == 2
    assert body["drops"]["quote_mismatch"] == 1
    assert body["drops"]["unknown_type"] == 1
    assert body["completed_sources"] == [src_id]

    # Source finished as 'read' and queued a 'resolve' job!
    read_state = db.execute(
        "SELECT read_state FROM cmap.source WHERE id = %s", (src_id,)
    ).fetchone()[0]
    assert read_state == "read"
    resolve_queued = db.execute(
        "SELECT count(*) FROM cmap.job WHERE kind = 'resolve' AND state = 'queued'"
    ).fetchone()[0]
    assert resolve_queued == 1

    # Verify GET /colab/status reflects completed chunks and drop reasons
    st = client.get("/colab/status", headers=admin_headers)
    assert st.status_code == 200
    st_json = st.json()
    assert st_json["pending_chunks"] == 0
    assert st_json["active_leases"] == 0
    assert st_json["completed_chunks_24h"] == 2
    assert st_json["drop_reasons"]["quote_mismatch"] == 1
    assert st_json["drop_reasons"]["unknown_type"] == 1


def test_submit_oversized_payload_rejected(
    client: TestClient, colab_enabled_env
) -> None:
    """§9a: >10 MB payload on POST /colab/submit is rejected with 413 before JSON parsing."""
    oversized = b'{"padding":"' + (b"x" * (MAX_SUBMIT_BYTES + 1024)) + b'"}'
    resp = client.post(
        "/colab/submit",
        headers={**_worker_headers(), "Content-Type": "application/json"},
        content=oversized,
    )
    assert resp.status_code == 413


def test_model_tag_validation(client: TestClient, colab_enabled_env) -> None:
    """§9a: Injection strings, newlines, missing prefix, or huge model_tag rejected with 422."""
    p_hash = relations_prompt_hash()
    for bad_tag in (
        "Qwen/Qwen2.5-32B",  # missing colab-vllm/ prefix
        "colab-vllm/bad\ninjection",
        "colab-vllm/bad space",
        "colab-vllm/" + ("a" * 200),
        "colab-vllm/; DROP TABLE cmap.relation;--",
    ):
        resp = client.post(
            "/colab/submit",
            headers=_worker_headers(),
            json={
                "lease_id": str(uuid.uuid4()),
                "prompt_hash": p_hash,
                "model_tag": bad_tag,
                "results": [
                    {
                        "chunk_id": str(uuid.uuid4()),
                        "raw_content": '{"relations": [], "new_mentions": []}',
                    }
                ],
            },
        )
        assert resp.status_code == 422, f"expected 422 for {bad_tag!r}, got {resp.status_code}"


def test_submit_truncation_salvage_requires_length_finish_reason(
    client: TestClient, db: Any, colab_enabled_env
) -> None:
    """#668 (a): Only finish_reason=='length' salvages '{...'; malformed stop reply -> 400."""
    _src, chunks = _seed_source_with_chunks(
        db,
        tag="salvage-guard",
        passages=["Jessica is the Licensing Manager who approves proofs."],
    )
    lease = client.post(
        "/colab/lease",
        headers=_worker_headers(),
        json={"worker_id": "w1", "max_items": 4},
    ).json()
    assert len(lease["items"]) == 1

    # 1. Malformed '{broken' with finish_reason='stop' must return HTTP 400, NOT salvage
    bad_sub = client.post(
        "/colab/submit",
        headers=_worker_headers(),
        json={
            "lease_id": lease["lease_id"],
            "prompt_hash": lease["prompt_hash"],
            "model_tag": VALID_MODEL_TAG,
            "results": [
                {
                    "chunk_id": chunks[0],
                    "raw_content": "{broken",
                    "finish_reason": "stop",
                }
            ],
        },
    )
    assert bad_sub.status_code == 400
    assert db.execute("SELECT count(*) FROM cmap.extraction").fetchone()[0] == 0

    # 2. Cut-off '{broken' with finish_reason='length' salvages with truncation=1
    len_sub = client.post(
        "/colab/submit",
        headers=_worker_headers(),
        json={
            "lease_id": lease["lease_id"],
            "prompt_hash": lease["prompt_hash"],
            "model_tag": VALID_MODEL_TAG,
            "results": [
                {
                    "chunk_id": chunks[0],
                    "raw_content": "{broken",
                    "finish_reason": "length",
                }
            ],
        },
    )
    assert len_sub.status_code == 200
    body = len_sub.json()
    assert body["accepted_chunks"] == 1
    assert body["drops"]["truncation"] == 1


def test_lease_chunks_releases_skipped_windows_immediately(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    db: Any,
    colab_enabled_env,
) -> None:
    """#668 (b): Claimed chunks with WindowSpec is None are deleted from colab_lease_item immediately."""
    from brain.api import colab as colab_api_mod

    src_id, chunks = _seed_source_with_chunks(
        db,
        tag="skipped-window",
        passages=[
            "Jessica approves licensing proofs.",
            "Marco coordinates vendor schedules.",
        ],
    )
    real_load = colab_api_mod.load_source_windows

    # Case 1: One chunk skipped, one kept -> skipped chunk released, chunk_count updated to 1
    def _partial_load(source_id: str, prompt_hash: str, *, only_pending: bool = True):
        done, eligible, pending = real_load(
            source_id, prompt_hash, only_pending=only_pending
        )
        filtered = {k: v for k, v in eligible.items() if k != chunks[1]}
        return done, filtered, pending

    monkeypatch.setattr(colab_api_mod, "load_source_windows", _partial_load)
    resp_partial = client.post(
        "/colab/lease",
        headers=_worker_headers(),
        json={"worker_id": "w1", "max_items": 4},
    )
    assert resp_partial.status_code == 200
    partial_json = resp_partial.json()
    assert [i["chunk_id"] for i in partial_json["items"]] == [chunks[0]]

    db.commit()
    lease_items = db.execute(
        "SELECT chunk_id::text, state FROM cmap.colab_lease_item WHERE lease_id = %s",
        (partial_json["lease_id"],),
    ).fetchall()
    assert [(str(r[0]), str(r[1])) for r in lease_items] == [(chunks[0], "leased")]
    lease_count = db.execute(
        "SELECT chunk_count FROM cmap.colab_lease WHERE id = %s",
        (partial_json["lease_id"],),
    ).fetchone()[0]
    assert lease_count == 1

    # Case 2: All claimed chunks skipped -> lease & items deleted, returns lease_id=None
    def _empty_load(source_id: str, prompt_hash: str, *, only_pending: bool = True):
        done, _eligible, _pending = real_load(
            source_id, prompt_hash, only_pending=only_pending
        )
        return done, {}, []

    monkeypatch.setattr(colab_api_mod, "load_source_windows", _empty_load)
    resp_empty = client.post(
        "/colab/lease",
        headers=_worker_headers(),
        json={"worker_id": "w2", "max_items": 4},
    )
    assert resp_empty.status_code == 200
    empty_json = resp_empty.json()
    assert empty_json["lease_id"] is None
    assert empty_json["expires_at"] is None
    assert empty_json["items"] == []

    db.commit()
    # Only the first lease's kept chunk remains leased; chunk[1] was never held!
    remaining_for_skipped = db.execute(
        "SELECT count(*) FROM cmap.colab_lease_item WHERE chunk_id = %s",
        (chunks[1],),
    ).fetchone()[0]
    assert remaining_for_skipped == 0
    total_leases = db.execute(
        "SELECT count(*) FROM cmap.colab_lease WHERE worker_id = 'w2'"
    ).fetchone()[0]
    assert total_leases == 0
    assert src_id is not None
