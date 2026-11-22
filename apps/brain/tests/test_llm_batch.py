"""Unit tests for OpenAI native batch submission & ID reconciliation (#607 step 2.4).

Covers:
- Successful 3-round batch execution with ``cached_tokens`` accounting
- Partial per-item failures inside a completed batch (error file / non-200)
- Expired batch handling and clean fallback to synchronous extraction
- <=30-minute poll deadline cap and best-effort cancellation on timeout
- Missing, duplicate, and foreign ``custom_id`` rejection (§9a ``test_result_id_mismatch_rejected``)
- Missing ``OPENAI_API_KEY`` warning and fallback to synchronous ``_process_window``
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from brain import llm_batch
from brain.config import Settings, get_settings
from brain.extract import relations as rel_mod
from brain.llm_batch import (
    MAX_POLL_DEADLINE_SECONDS,
    BatchError,
    BatchExpiredError,
    BatchItem,
    BatchResult,
    BatchTimeoutError,
    build_responses_batch_jsonl,
    reconcile_batch_results,
    submit_and_wait_batch,
)


class _FakeHttpResp:
    def __init__(
        self,
        body: dict[str, Any] | bytes,
        status_code: int = 200,
    ) -> None:
        self.status_code = status_code
        if isinstance(body, bytes):
            self.content = body
            self.text = body.decode("utf-8", errors="replace")
            self._json: dict[str, Any] | None = None
        else:
            self._json = body
            self.text = json.dumps(body)
            self.content = self.text.encode("utf-8")

    def json(self) -> dict[str, Any]:
        if self._json is None:
            return json.loads(self.text)
        return self._json


def _responses_line(
    custom_id: str,
    payload: dict[str, Any] | str,
    *,
    status_code: int = 200,
    body_status: str = "completed",
    input_tokens: int = 500,
    cached_tokens: int = 128,
    output_tokens: int = 200,
) -> dict[str, Any]:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return {
        "id": f"batch_req_{custom_id}",
        "custom_id": custom_id,
        "response": {
            "status_code": status_code,
            "body": {
                "status": body_status,
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": text}],
                    }
                ],
                "usage": {
                    "input_tokens": input_tokens,
                    "input_tokens_details": {"cached_tokens": cached_tokens},
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                },
            },
        },
        "error": None,
    }


def test_build_jsonl_appends_json_hint_and_strips_prefix() -> None:
    raw = build_responses_batch_jsonl(
        "openai/gpt-6-luna",
        [
            BatchItem(custom_id="p1", prompt="Extract operational facts."),
            BatchItem(custom_id="p2", prompt="Return JSON only for this passage."),
        ],
    )
    rows = [json.loads(line) for line in raw.splitlines()]
    assert [r["custom_id"] for r in rows] == ["p1", "p2"]
    assert rows[0]["body"]["model"] == "gpt-6-luna"
    assert rows[0]["url"] == "/v1/responses"
    assert "json" in rows[0]["body"]["input"][0]["content"].lower()
    assert rows[1]["body"]["input"][0]["content"] == "Return JSON only for this passage."


def test_result_id_mismatch_rejected() -> None:
    """§9a adversarial gate: missing, duplicate, or foreign passage ids raise BatchError."""
    valid_a = _responses_line("chunk-a", {"relations": [], "new_mentions": []})
    valid_b = _responses_line("chunk-b", {"relations": [], "new_mentions": []})
    foreign = _responses_line("chunk-foreign", {"relations": [], "new_mentions": []})

    # 1. Foreign passage ID in output
    with pytest.raises(BatchError, match="foreign custom_id"):
        reconcile_batch_results(
            ["chunk-a"],
            [valid_a, foreign],
            parse=rel_mod.parse_relations_json,
        )

    # 2. Foreign passage ID in error file
    with pytest.raises(BatchError, match="foreign custom_id"):
        reconcile_batch_results(
            ["chunk-a"],
            [valid_a],
            [{"custom_id": "chunk-intruder", "error": {"message": "boom"}}],
            parse=rel_mod.parse_relations_json,
        )

    # 3. Duplicate passage ID in output
    with pytest.raises(BatchError, match="duplicate custom_id"):
        reconcile_batch_results(
            ["chunk-a", "chunk-b"],
            [valid_a, valid_a, valid_b],
            parse=rel_mod.parse_relations_json,
        )

    # 4. Duplicate passage ID across output and error files
    with pytest.raises(BatchError, match="duplicate custom_id"):
        reconcile_batch_results(
            ["chunk-a"],
            [valid_a],
            [{"custom_id": "chunk-a", "error": {"message": "dup"}}],
            parse=rel_mod.parse_relations_json,
        )

    # 5. Missing requested passage ID
    with pytest.raises(BatchError, match="missing 1 requested custom_id"):
        reconcile_batch_results(
            ["chunk-a", "chunk-b"],
            [valid_a],
            parse=rel_mod.parse_relations_json,
        )


def test_submit_and_wait_batch_success_partial_failure_and_file_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mocked OpenAI /v1/batches: polls through validating -> completed, preserves
    healthy items on partial failure, records cached_tokens, and deletes temp files."""
    deleted_files: list[str] = []
    polls = [0]

    out_jsonl = (
        json.dumps(
            _responses_line(
                "c-ok",
                {"relations": [{"from": "m1", "to": "m2"}], "new_mentions": []},
                input_tokens=600,
                cached_tokens=256,
                output_tokens=140,
            )
        )
        + "\n"
    ).encode("utf-8")
    err_jsonl = (
        json.dumps({"custom_id": "c-err", "error": {"message": "rate_limit_exceeded"}})
        + "\n"
    ).encode("utf-8")

    def fake_post(url: str, **kw: Any) -> _FakeHttpResp:
        if url.endswith("/files"):
            assert kw["data"] == {"purpose": "batch"}
            return _FakeHttpResp({"id": "file_in_123"}, 200)
        if url.endswith("/batches"):
            assert kw["json"]["input_file_id"] == "file_in_123"
            assert kw["json"]["endpoint"] == "/v1/responses"
            return _FakeHttpResp({"id": "batch_abc_123", "status": "validating"}, 200)
        raise AssertionError(f"unexpected POST {url}")

    def fake_get(url: str, **kw: Any) -> _FakeHttpResp:
        del kw
        if url.endswith("/batches/batch_abc_123"):
            polls[0] += 1
            if polls[0] == 1:
                return _FakeHttpResp(
                    {"id": "batch_abc_123", "status": "in_progress"}, 200
                )
            return _FakeHttpResp(
                {
                    "id": "batch_abc_123",
                    "status": "completed",
                    "output_file_id": "file_out_456",
                    "error_file_id": "file_err_789",
                },
                200,
            )
        if url.endswith("/files/file_out_456/content"):
            return _FakeHttpResp(out_jsonl, 200)
        if url.endswith("/files/file_err_789/content"):
            return _FakeHttpResp(err_jsonl, 200)
        raise AssertionError(f"unexpected GET {url}")

    def fake_delete(url: str, **kw: Any) -> _FakeHttpResp:
        del kw
        deleted_files.append(url.rsplit("/", 1)[-1])
        return _FakeHttpResp({"deleted": True}, 200)

    monkeypatch.setattr(llm_batch.httpx, "post", fake_post)
    monkeypatch.setattr(llm_batch.httpx, "get", fake_get)
    monkeypatch.setattr(llm_batch.httpx, "delete", fake_delete)

    res = submit_and_wait_batch(
        "openai/gpt-6-luna",
        [
            BatchItem(custom_id="c-ok", prompt="Return JSON."),
            BatchItem(custom_id="c-err", prompt="Return JSON."),
        ],
        settings=Settings(openai_api_key="sk-test"),
        parse=rel_mod.parse_relations_json,
        sleep_fn=lambda _s: None,
    )
    assert res["c-ok"].status == "ok"
    assert res["c-ok"].payload == {
        "relations": [{"from": "m1", "to": "m2"}],
        "new_mentions": [],
    }
    assert res["c-ok"].usage == {
        "prompt_tokens": 600,
        "completion_tokens": 140,
        "cached_tokens": 256,
        "total_tokens": 740,
    }
    assert res["c-err"].status == "error"
    assert res["c-err"].payload is None
    assert set(deleted_files) == {"file_in_123", "file_out_456", "file_err_789"}


def test_submit_and_wait_batch_expiry_and_thirty_minute_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expired batches raise BatchExpiredError; deadlines >30m are rejected;
    timeouts cancel the remote batch and raise BatchTimeoutError."""
    with pytest.raises(ValueError, match="poll_deadline_seconds"):
        submit_and_wait_batch(
            "openai/gpt-6-luna",
            [BatchItem(custom_id="c1", prompt="Return JSON.")],
            settings=Settings(openai_api_key="sk-test"),
            parse=rel_mod.parse_relations_json,
            poll_deadline_seconds=MAX_POLL_DEADLINE_SECONDS + 1.0,
        )

    monkeypatch.setattr(
        llm_batch.httpx,
        "post",
        lambda url, **_kw: _FakeHttpResp(
            {"id": "file_in_exp"} if url.endswith("/files") else {"id": "batch_exp", "status": "expired"},
            200,
        ),
    )
    monkeypatch.setattr(
        llm_batch.httpx, "delete", lambda *_a, **_kw: _FakeHttpResp({"deleted": True}, 200)
    )
    with pytest.raises(BatchExpiredError, match="expired"):
        submit_and_wait_batch(
            "openai/gpt-6-luna",
            [BatchItem(custom_id="c1", prompt="Return JSON.")],
            settings=Settings(openai_api_key="sk-test"),
            parse=rel_mod.parse_relations_json,
            sleep_fn=lambda _s: None,
        )

    cancelled: list[str] = []

    def post_timeout(url: str, **_kw: Any) -> _FakeHttpResp:
        if url.endswith("/files"):
            return _FakeHttpResp({"id": "file_in_to"}, 200)
        if url.endswith("/batches"):
            return _FakeHttpResp({"id": "batch_to", "status": "in_progress"}, 200)
        if url.endswith("/batches/batch_to/cancel"):
            cancelled.append("batch_to")
            return _FakeHttpResp({"id": "batch_to", "status": "cancelling"}, 200)
        raise AssertionError(url)

    clock = [0.0]

    def fake_clock() -> float:
        val = clock[0]
        clock[0] += 10.0
        return val

    monkeypatch.setattr(llm_batch.httpx, "post", post_timeout)
    monkeypatch.setattr(
        llm_batch.httpx,
        "get",
        lambda *_a, **_kw: _FakeHttpResp({"id": "batch_to", "status": "in_progress"}, 200),
    )
    with pytest.raises(BatchTimeoutError, match="deadline"):
        submit_and_wait_batch(
            "openai/gpt-6-luna",
            [BatchItem(custom_id="c1", prompt="Return JSON.")],
            settings=Settings(openai_api_key="sk-test"),
            parse=rel_mod.parse_relations_json,
            poll_deadline_seconds=15.0,
            sleep_fn=lambda _s: None,
            clock_fn=fake_clock,
        )
    assert cancelled == ["batch_to"]


def test_handle_relations_message_batch_three_rounds_and_missing_key_fallback(
    db: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """handle_relations uses 3 batch rounds when OPENAI_API_KEY is set on an
    openai/* message seat, and logs a warning + falls back to sync when unset."""
    from psycopg.types.json import Json

    from tests.conftest import fake_embeddings

    fake_embeddings(monkeypatch)
    monkeypatch.setattr(rel_mod, "after_source_relations", lambda _sid: None)
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "test/frontier")
    monkeypatch.setenv("BRAIN_MESSAGE_RELATIONS_MODEL", "openai/gpt-6-luna")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("BRAIN_OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()

    sid = db.execute(
        "INSERT INTO cmap.source (kind, title, storage_path, sha256, bytes, origin) "
        "VALUES ('transcript', 'Batch msg test', 'cmap/b/1', 'sha-b1', 40, 'teams_chat') "
        "RETURNING id::text"
    ).fetchone()[0]
    passage = "Dana: Send the Fall mug spec before Friday."
    db.execute(
        "INSERT INTO cmap.chunk (source_id, ordinal, locator, text, token_count) "
        "VALUES (%s, 0, %s, %s, 12)",
        (sid, Json({"turn": 1, "speaker": "Dana"}), passage),
    )
    db.commit()

    sync_calls: list[int] = []
    valid_payload = {
        "relations": [
            {
                "from": "x1",
                "to": "x2",
                "type": "APPLIES_TO",
                "description": "Dana asked to send the Fall mug spec before Friday.",
                "stance": "report",
                "confidence": 0.9,
                "quote": "Send the Fall mug spec before Friday.",
            }
        ],
        "new_mentions": [
            {
                "key": "x1",
                "type": "Artifact",
                "name": "Fall mug spec",
                "quote": "Send the Fall mug spec before Friday.",
            },
            {
                "key": "x2",
                "type": "Product",
                "name": "Fall mug",
                "quote": "Send the Fall mug spec before Friday.",
            },
        ],
    }

    def fake_sync_post(
        messages: list[dict[str, Any]], settings: Any, max_tokens: int = 8000
    ) -> dict[str, Any]:
        del messages, settings, max_tokens
        sync_calls.append(1)
        return {
            "choices": [{"message": {"content": json.dumps(valid_payload)}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
        }

    monkeypatch.setattr(rel_mod, "_post_chat", fake_sync_post)

    with caplog.at_level(logging.WARNING):
        rel_mod.handle_relations({"payload": {"source_id": sid}})
    assert len(sync_calls) == 3
    assert any("OPENAI_API_KEY is not set" in rec.message for rec in caplog.records)

    # Reset extraction and run with OPENAI_API_KEY set -> 3 native batch rounds, 0 sync calls
    db.execute("DELETE FROM cmap.extraction WHERE stage = 'relations'")
    db.execute("DELETE FROM cmap.relation")
    db.commit()
    sync_calls.clear()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-batch-live-test")
    get_settings.cache_clear()

    batch_rounds: list[list[str]] = []

    def fake_submit_batch(
        model: str,
        items: list[BatchItem],
        *,
        settings: Settings,
        parse: Any,
        **_kw: Any,
    ) -> dict[str, BatchResult]:
        del settings, parse
        assert model == "openai/gpt-6-luna"
        batch_rounds.append([it.custom_id for it in items])
        return {
            it.custom_id: BatchResult(
                custom_id=it.custom_id,
                status="ok",
                payload=valid_payload,
                usage={
                    "prompt_tokens": 200,
                    "completion_tokens": 80,
                    "cached_tokens": 64,
                    "total_tokens": 280,
                },
            )
            for it in items
        }

    monkeypatch.setattr(rel_mod, "submit_and_wait_batch", fake_submit_batch)
    job_id = db.execute(
        "INSERT INTO cmap.job (kind, payload, state) "
        "VALUES ('relations', %s, 'running') RETURNING id",
        (Json({"source_id": sid}),),
    ).fetchone()[0]
    db.commit()

    rel_mod.handle_relations({"id": job_id, "payload": {"source_id": sid}})
    get_settings.cache_clear()

    assert len(batch_rounds) == 3, "Pass 1, Pass 2, and Pass 3 each ran as a batch round"
    assert sync_calls == []
    stored_rels = db.execute(
        "SELECT rel_type, quote FROM cmap.relation r JOIN cmap.chunk c ON c.id = r.chunk_id "
        "WHERE c.source_id = %s",
        (sid,),
    ).fetchall()
    assert stored_rels == [("APPLIES_TO", "Send the Fall mug spec before Friday.")]
    usage = db.execute(
        "SELECT payload->'usage' FROM cmap.job WHERE id = %s", (job_id,)
    ).fetchone()[0]
    assert usage["batch_rounds"] == 3
    assert usage["frontier_cached_tokens"] == 192


def test_submit_and_wait_batch_salvages_stalled_tail_via_flex(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When /v1/batches stalls on tail items, salvage_with_flex cancels the batch,
    harvests completed output_file_id rows, and completes remaining items on flex."""
    cancelled: list[str] = []
    flex_seen: list[str] = []
    polls = [0]

    out_jsonl = (
        json.dumps(
            _responses_line(
                "c-done",
                {"relations": [], "new_mentions": []},
                input_tokens=300,
                cached_tokens=64,
                output_tokens=50,
            )
        )
        + "\n"
    ).encode("utf-8")

    def fake_post(url: str, **kw: Any) -> _FakeHttpResp:
        if url.endswith("/files"):
            return _FakeHttpResp({"id": "file_in_s"}, 200)
        if url.endswith("/batches"):
            return _FakeHttpResp(
                {
                    "id": "batch_stall",
                    "status": "in_progress",
                    "request_counts": {"total": 2, "completed": 1, "failed": 0},
                },
                200,
            )
        if url.endswith("/batches/batch_stall/cancel"):
            cancelled.append("batch_stall")
            return _FakeHttpResp({"id": "batch_stall", "status": "cancelling"}, 200)
        if url.endswith("/responses"):
            assert kw["json"]["service_tier"] == "flex"
            flex_seen.append(kw["json"]["model"])
            return _FakeHttpResp(
                {
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": '{"relations": [{"from": "m1", "to": "m2"}], "new_mentions": []}',
                                }
                            ],
                        }
                    ],
                    "usage": {
                        "input_tokens": 310,
                        "input_tokens_details": {"cached_tokens": 0},
                        "output_tokens": 60,
                        "total_tokens": 370,
                    },
                },
                200,
            )
        raise AssertionError(url)

    def fake_get(url: str, **_kw: Any) -> _FakeHttpResp:
        if url.endswith("/batches/batch_stall"):
            polls[0] += 1
            if cancelled:
                return _FakeHttpResp(
                    {
                        "id": "batch_stall",
                        "status": "cancelled",
                        "output_file_id": "file_out_partial",
                    },
                    200,
                )
            return _FakeHttpResp(
                {
                    "id": "batch_stall",
                    "status": "in_progress",
                    "request_counts": {"total": 2, "completed": 1, "failed": 0},
                },
                200,
            )
        if url.endswith("/files/file_out_partial/content"):
            return _FakeHttpResp(out_jsonl, 200)
        raise AssertionError(url)

    clock = [0.0]

    def fake_clock() -> float:
        val = clock[0]
        clock[0] += 5.0
        return val

    monkeypatch.setattr(llm_batch.httpx, "post", fake_post)
    monkeypatch.setattr(llm_batch.httpx, "get", fake_get)
    monkeypatch.setattr(
        llm_batch.httpx, "delete", lambda *_a, **_kw: _FakeHttpResp({"deleted": True}, 200)
    )

    out = submit_and_wait_batch(
        "openai/gpt-6-luna",
        [
            BatchItem(custom_id="c-done", prompt="Return JSON."),
            BatchItem(custom_id="c-tail", prompt="Return JSON."),
        ],
        settings=Settings(openai_api_key="sk-test"),
        parse=rel_mod.parse_relations_json,
        salvage_with_flex=True,
        stall_salvage_seconds=5.0,
        sleep_fn=lambda _s: None,
        clock_fn=fake_clock,
    )
    assert cancelled == ["batch_stall"]
    assert flex_seen == ["gpt-6-luna"]
    assert out["c-done"].status == "ok"
    assert out["c-tail"].status == "ok"
    assert len(out["c-tail"].payload["relations"]) == 1


def test_handle_relations_coalesces_queued_message_jobs_into_three_batch_rounds(
    db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Multiple queued message-source relations jobs coalesce into 3 batch rounds total."""
    from psycopg.types.json import Json

    from tests.conftest import fake_embeddings

    fake_embeddings(monkeypatch)
    monkeypatch.setattr(rel_mod, "after_source_relations", lambda _sid: None)
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "test/frontier")
    monkeypatch.setenv("BRAIN_MESSAGE_RELATIONS_MODEL", "openai/gpt-6-luna")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-coalesce")
    get_settings.cache_clear()

    sids: list[str] = []
    jids: list[Any] = []
    for idx in range(3):
        sid = db.execute(
            "INSERT INTO cmap.source (kind, title, storage_path, sha256, bytes, origin, read_state) "
            "VALUES ('transcript', %s, %s, %s, 30, 'email', 'extracting') RETURNING id::text",
            (f"Thread {idx}", f"cmap/c/{idx}", f"sha-coal-{idx}"),
        ).fetchone()[0]
        db.execute(
            "INSERT INTO cmap.chunk (source_id, ordinal, locator, text, token_count) "
            "VALUES (%s, 0, %s, %s, 10)",
            (sid, Json({"turn": 1}), f"Alex: Approve tooling spec {idx}."),
        )
        state = "running" if idx == 0 else "queued"
        jid = db.execute(
            "INSERT INTO cmap.job (kind, payload, state) "
            "VALUES ('relations', %s, %s) RETURNING id",
            (Json({"source_id": sid}), state),
        ).fetchone()[0]
        sids.append(str(sid))
        jids.append(jid)
    db.commit()

    rounds: list[int] = []

    def fake_submit_batch(
        model: str,
        items: list[BatchItem],
        **_kw: Any,
    ) -> dict[str, BatchResult]:
        assert model == "openai/gpt-6-luna"
        rounds.append(len(items))
        out: dict[str, BatchResult] = {}
        for item in items:
            m_idx = 0
            for k in range(3):
                if f"tooling spec {k}." in item.prompt:
                    m_idx = k
                    break
            quote = f"Approve tooling spec {m_idx}."
            out[item.custom_id] = BatchResult(
                custom_id=item.custom_id,
                status="ok",
                payload={
                    "relations": [
                        {
                            "from": "x1",
                            "to": "x2",
                            "type": "APPLIES_TO",
                            "description": f"Alex asked to approve tooling spec {m_idx}.",
                            "stance": "report",
                            "confidence": 0.9,
                            "quote": quote,
                        }
                    ],
                    "new_mentions": [
                        {"key": "x1", "type": "Decision", "name": f"approval {m_idx}", "quote": quote},
                        {"key": "x2", "type": "Artifact", "name": f"tooling spec {m_idx}", "quote": quote},
                    ],
                },
                usage={"prompt_tokens": 100, "completion_tokens": 40, "cached_tokens": 0, "total_tokens": 140},
            )
        return out

    monkeypatch.setattr(rel_mod, "submit_and_wait_batch", fake_submit_batch)
    rel_mod.handle_relations({"id": jids[0], "payload": {"source_id": sids[0]}})
    get_settings.cache_clear()

    assert rounds == [3, 3, 3], "all 3 sources ran together in 3 batch rounds total"
    sibling_states = db.execute(
        "SELECT state FROM cmap.job WHERE id = ANY(%s) ORDER BY id",
        ([jids[1], jids[2]],),
    ).fetchall()
    assert sibling_states == [("done",), ("done",)]
    source_states = db.execute(
        "SELECT read_state FROM cmap.source WHERE id::text = ANY(%s)", (sids,)
    ).fetchall()
    assert source_states == [("read",), ("read",), ("read",)]
