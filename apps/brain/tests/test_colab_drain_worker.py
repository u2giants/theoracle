"""Unit, E2E, and §9a adversarial tests for apps/brain/colab/drain_leases.py (#664 Step 3.3)."""

from __future__ import annotations

import ast
import importlib
import io
import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from conftest import fake_embeddings
from fastapi.testclient import TestClient
from psycopg.types.json import Json

from brain.config import get_settings
from colab import drain_leases as drain_mod
from colab.drain_leases import (
    DrainWorkerError,
    drain_leases,
    install_token_redaction_filter,
    main,
)
from colab.run_vllm_batch import TRUNCATION_RETRY_MAX_TOKENS

BRAIN_DIR = Path(__file__).resolve().parents[1]
DRAIN_PATH = BRAIN_DIR / "colab" / "drain_leases.py"
VALID_MODEL = "Qwen/Qwen2.5-32B-Instruct"
VALID_REVISION = "0123456789abcdef0123456789abcdef01234567"
WORKER_TOKEN = "colab-worker-secret-token-drain-664"
FORBIDDEN_TOP_LEVEL_IMPORTS = frozenset(
    {"vllm", "torch", "peft", "trl", "bitsandbytes", "transformers", "accelerate", "datasets"}
)


@dataclass
class _FakeCompletionOutput:
    text: str
    finish_reason: str | None = "stop"
    token_ids: list[int] | None = None


@dataclass
class _FakeRequestOutput:
    prompt_token_ids: list[int]
    outputs: list[_FakeCompletionOutput]


def _ok_config_loader(hf_model: str, hf_revision: str) -> tuple[dict[str, Any], list[str]]:
    del hf_model, hf_revision
    return {"architectures": ["Qwen2ForCausalLM"]}, ["config.json", "model.safetensors"]


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


def _seed_offload_source(
    db: Any,
    *,
    tag: str,
    passages: list[str],
) -> tuple[str, list[str]]:
    srow = db.execute(
        "INSERT INTO cmap.source (kind, title, storage_path, sha256, bytes, read_state, colab_offload) "
        "VALUES ('text', %s, %s, %s, 200, 'extracting', true) RETURNING id::text",
        (f"drain-{tag}", f"test/drain-{tag}", f"sha-drain-{tag}"),
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


def _empty_queue_transport(expected_token: str) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") == f"Bearer {expected_token}"
        assert request.url.path == "/colab/lease"
        return httpx.Response(
            200,
            json={
                "lease_id": None,
                "expires_at": None,
                "prompt_hash": "a" * 64,
                "relations_schema": {"type": "object"},
                "items": [],
            },
        )

    return httpx.MockTransport(handler)


def _dummy_engine_factory(**kwargs: Any) -> Any:
    del kwargs

    class _DummyEngine:
        def generate(
            self,
            prompts: list[str],
            sampling_params: list[Any],
            **kwargs: Any,
        ) -> list[_FakeRequestOutput]:
            del sampling_params, kwargs
            return [
                _FakeRequestOutput(
                    [1, 2],
                    [_FakeCompletionOutput('{"relations": [], "new_mentions": []}', "stop", [3])],
                )
                for _ in prompts
            ]

    return _DummyEngine()


def test_worker_token_never_in_argv_or_logs(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """§9a: CLI rejects --token/--worker-token with exit 2; env/stdin works; logs redact Bearer."""
    secret = "super-secret-colab-token-9a-check"
    monkeypatch.setenv("BRAIN_COLAB_API_URL", "http://brain.test")
    monkeypatch.delenv("BRAIN_COLAB_WORKER_TOKEN", raising=False)

    # 1. Passing --token or --worker-token in any form fails with exit code 2 without echoing secret.
    bad_invocations = [
        ["--hf-model", VALID_MODEL, "--hf-revision", VALID_REVISION, "--token", secret],
        ["--hf-model", VALID_MODEL, "--hf-revision", VALID_REVISION, f"--token={secret}"],
        ["--hf-model", VALID_MODEL, "--hf-revision", VALID_REVISION, "--worker-token", secret],
        ["--hf-model", VALID_MODEL, "--hf-revision", VALID_REVISION, f"--worker-token={secret}"],
    ]
    for argv in bad_invocations:
        with pytest.raises(SystemExit) as exc_info:
            main(argv)
        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        assert secret not in captured.out
        assert secret not in captured.err

    # 2. Reading token from BRAIN_COLAB_WORKER_TOKEN environment variable works cleanly.
    monkeypatch.setenv("BRAIN_COLAB_WORKER_TOKEN", secret)
    unassign_calls = 0

    def count_unassign() -> None:
        nonlocal unassign_calls
        unassign_calls += 1

    rc_env = main(
        ["--hf-model", VALID_MODEL, "--hf-revision", VALID_REVISION],
        config_loader=_ok_config_loader,
        engine_factory=_dummy_engine_factory,
        transport=_empty_queue_transport(secret),
        unassign_fn=count_unassign,
    )
    assert rc_env == 0
    assert unassign_calls == 1
    env_out = capsys.readouterr()
    assert secret not in env_out.out
    assert secret not in env_out.err

    # 3. Reading token from stdin with --token-stdin works when env var is unset.
    monkeypatch.delenv("BRAIN_COLAB_WORKER_TOKEN", raising=False)
    stdin_secret = "stdin-secret-colab-token-664"
    rc_stdin = main(
        ["--hf-model", VALID_MODEL, "--hf-revision", VALID_REVISION, "--token-stdin"],
        config_loader=_ok_config_loader,
        engine_factory=_dummy_engine_factory,
        transport=_empty_queue_transport(stdin_secret),
        unassign_fn=count_unassign,
        stdin_stream=io.StringIO(f"  {stdin_secret}\n"),
    )
    assert rc_stdin == 0
    assert unassign_calls == 2

    # 4. Logging filter redacts Bearer <token> and raw token on worker, httpx, httpcore, & tracebacks.
    caplog.set_level(logging.DEBUG)
    install_token_redaction_filter(stdin_secret)

    logging.getLogger("httpx").debug(
        "HTTP Request headers=%s",
        {"Authorization": f"Bearer {stdin_secret}", "Accept": "application/json"},
    )
    logging.getLogger("httpcore").debug(
        "send_request_headers.started headers=[(b'authorization', b'Bearer %s')]",
        stdin_secret,
    )
    try:
        raise RuntimeError(f"upstream rejected Authorization: Bearer {stdin_secret}")
    except RuntimeError:
        logging.getLogger("colab.drain_leases").error("submit crashed", exc_info=True)

    assert stdin_secret not in caplog.text
    assert secret not in caplog.text
    assert "Bearer [REDACTED]" in caplog.text


def test_e2e_multi_batch_drain_against_fastapi_app(
    client: TestClient,
    db: Any,
    admin_headers: dict[str, str],
    colab_enabled_env,
) -> None:
    """Drain 2 batches against real FastAPI brain.main.app until items==[], finishing source."""
    passages = [
        "Jessica is the Licensing Manager for Disney approvals.",
        "Jessica reviews packaging proofs before submission.",
        "Jessica tracks Disney royalty deadlines each Friday.",
    ]
    source_id, chunk_ids = _seed_offload_source(db, tag="e2e-multi", passages=passages)

    engine_builds = 0
    generate_calls: list[dict[str, Any]] = []
    seen_first_length_retry = False

    class FakeVllmEngine:
        def generate(
            self,
            prompts: list[str],
            sampling_params: list[Any],
            **kwargs: Any,
        ) -> list[_FakeRequestOutput]:
            nonlocal seen_first_length_retry
            generate_calls.append(
                {
                    "count": len(prompts),
                    "max_tokens": [sp.max_tokens for sp in sampling_params],
                    "schema": sampling_params[0].guided_decoding.json,
                    "kwargs": kwargs,
                }
            )
            outputs: list[_FakeRequestOutput] = []
            for idx, prompt in enumerate(prompts):
                # {{chunk_text}} appears after {{previous_context}}, so rfind selects the anchor passage.
                matched_quote = max(
                    (prompt.rfind(p), p) for p in passages if p in prompt
                )[1]
                mention_keys = re.findall(r'"key":\s*"(m\d+)"', prompt)
                from_key, to_key = mention_keys[-2], mention_keys[-1]
                # Force a truncation retry on the very first prompt call to prove retry at 4000.
                if not seen_first_length_retry and idx == 0:
                    seen_first_length_retry = True
                    outputs.append(
                        _FakeRequestOutput(
                            prompt_token_ids=[1, 2, 3],
                            outputs=[
                                _FakeCompletionOutput(
                                    text='{"relations": [{"from": "m1"',
                                    finish_reason="length",
                                    token_ids=[10, 11],
                                )
                            ],
                        )
                    )
                    continue
                payload = {
                    "relations": [
                        {
                            "from": from_key,
                            "to": to_key,
                            "type": "PERFORMS",
                            "description": "Jessica works as Licensing Manager.",
                            "description_en": "",
                            "stance": "practice",
                            "confidence": 0.92,
                            "quote": matched_quote,
                        }
                    ],
                    "new_mentions": [],
                }
                outputs.append(
                    _FakeRequestOutput(
                        prompt_token_ids=[1, 2, 3],
                        outputs=[
                            _FakeCompletionOutput(
                                text=json.dumps(payload),
                                finish_reason="stop",
                                token_ids=[10, 11, 12],
                            )
                        ],
                    )
                )
            return outputs

    def engine_factory(**kwargs: Any) -> FakeVllmEngine:
        nonlocal engine_builds
        engine_builds += 1
        assert kwargs["trust_remote_code"] is False
        assert kwargs["model"] == VALID_MODEL
        assert kwargs["revision"] == VALID_REVISION
        return FakeVllmEngine()

    unassign_calls = 0

    def count_unassign() -> None:
        nonlocal unassign_calls
        unassign_calls += 1

    summary = drain_leases(
        api_url="http://testserver",
        worker_token=WORKER_TOKEN,
        hf_model=VALID_MODEL,
        hf_revision=VALID_REVISION,
        max_items=2,
        worker_id="colab-e2e-worker",
        config_loader=_ok_config_loader,
        engine_factory=engine_factory,
        transport=client._transport,
        unassign_fn=count_unassign,
    )

    assert engine_builds == 1
    assert summary.batches_completed == 2
    assert summary.chunks_submitted == len(chunk_ids)
    assert summary.retried_items == 1
    assert summary.stop_reason == "empty"
    assert summary.model_tag == f"colab-vllm/{VALID_MODEL}@{VALID_REVISION}"
    assert unassign_calls == 1

    # Verify the length retry used TRUNCATION_RETRY_MAX_TOKENS (4000) and guided schema.
    assert any(
        call["max_tokens"] == [TRUNCATION_RETRY_MAX_TOKENS]
        for call in generate_calls
    )
    assert "relations" in generate_calls[0]["schema"]["properties"]

    # Source must finish as 'read', all 3 extractions carry model_tag, and 3 relations persisted.
    read_state = db.execute(
        "SELECT read_state FROM cmap.source WHERE id = %s", (source_id,)
    ).fetchone()[0]
    assert read_state == "read"

    models = db.execute(
        "SELECT DISTINCT model FROM cmap.extraction WHERE stage = 'relations'"
    ).fetchall()
    assert models == [(summary.model_tag,)]

    rel_count = db.execute("SELECT count(*) FROM cmap.relation").fetchone()[0]
    assert rel_count == 3

    status_resp = client.get("/colab/status", headers=admin_headers)
    assert status_resp.status_code == 200
    status_json = status_resp.json()
    assert status_json["pending_chunks"] == 0
    assert status_json["active_leases"] == 0
    assert status_json["completed_chunks_24h"] == 3


def test_three_consecutive_http_errors_stop_with_bounded_backoff_and_unassign(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stop cleanly after 3 consecutive 5xx/transport errors with total backoff < 120s & unassign."""
    # 1. Three consecutive 503 HTTP responses
    attempts = 0
    sleeps: list[float] = []
    unassign_calls = 0

    def fail_503(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, text="brain unavailable")

    def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    def count_unassign() -> None:
        nonlocal unassign_calls
        unassign_calls += 1

    monkeypatch.setenv("BRAIN_COLAB_API_URL", "http://brain.test")
    monkeypatch.setenv("BRAIN_COLAB_WORKER_TOKEN", WORKER_TOKEN)
    rc = main(
        ["--hf-model", VALID_MODEL, "--hf-revision", VALID_REVISION],
        config_loader=_ok_config_loader,
        engine_factory=_dummy_engine_factory,
        transport=httpx.MockTransport(fail_503),
        sleep_fn=record_sleep,
        unassign_fn=count_unassign,
    )
    assert rc == 1
    assert attempts == 3
    assert len(sleeps) == 2
    assert all(0 < s <= 30.0 for s in sleeps)
    assert sum(sleeps) < 120.0
    assert unassign_calls == 1

    # 2. Three consecutive transport errors (ConnectError)
    transport_attempts = 0
    transport_sleeps: list[float] = []

    def fail_transport(request: httpx.Request) -> httpx.Response:
        nonlocal transport_attempts
        transport_attempts += 1
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(DrainWorkerError, match="3 consecutive"):
        drain_leases(
            api_url="http://brain.test",
            worker_token=WORKER_TOKEN,
            hf_model=VALID_MODEL,
            hf_revision=VALID_REVISION,
            config_loader=_ok_config_loader,
            engine_factory=_dummy_engine_factory,
            transport=httpx.MockTransport(fail_transport),
            sleep_fn=transport_sleeps.append,
            unassign_fn=count_unassign,
        )
    assert transport_attempts == 3
    assert len(transport_sleeps) == 2
    assert sum(transport_sleeps) < 120.0
    assert unassign_calls == 2

    # 3. Transient 2 errors -> 1 success resets consecutive streak -> 2 errors -> empty queue ok
    call_idx = 0
    reset_sleeps: list[float] = []

    def flaky_then_empty(_request: httpx.Request) -> httpx.Response:
        nonlocal call_idx
        call_idx += 1
        if call_idx in (1, 2, 4, 5):
            return httpx.Response(502, text="bad gateway")
        if call_idx == 3:
            return httpx.Response(
                200,
                json={
                    "lease_id": "00000000-0000-4000-8000-000000000001",
                    "expires_at": "2026-11-22T03:00:00+00:00",
                    "prompt_hash": "a" * 64,
                    "relations_schema": {"type": "object"},
                    "items": [
                        {
                            "chunk_id": "00000000-0000-4000-8000-000000000010",
                            "source_id": "00000000-0000-4000-8000-000000000020",
                            "max_tokens": 2000,
                            "prompt": "Passage",
                        }
                    ],
                },
            )
        if call_idx == 6:
            return httpx.Response(200, json={"accepted_chunks": 1})
        return httpx.Response(
            200,
            json={
                "lease_id": None,
                "expires_at": None,
                "prompt_hash": "a" * 64,
                "relations_schema": {"type": "object"},
                "items": [],
            },
        )

    summary = drain_leases(
        api_url="http://brain.test",
        worker_token=WORKER_TOKEN,
        hf_model=VALID_MODEL,
        hf_revision=VALID_REVISION,
        config_loader=_ok_config_loader,
        engine_factory=_dummy_engine_factory,
        transport=httpx.MockTransport(flaky_then_empty),
        sleep_fn=reset_sleeps.append,
        unassign_fn=count_unassign,
    )
    assert summary.batches_completed == 1
    assert summary.stop_reason == "empty"
    assert len(reset_sleeps) == 4
    assert unassign_calls == 3


def test_max_batches_wall_limit_lora_tag_and_no_top_level_gpu_imports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify --max-batches, --max-wall-minutes, LoRA model_tag format, and AST GPU-free guard."""
    # 1. AST & reload guard: zero top-level GPU imports in drain_leases.py
    tree = ast.parse(DRAIN_PATH.read_text(encoding="utf-8"), filename=str(DRAIN_PATH))
    top_level_gpu: list[str] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                if alias.name.split(".")[0] in FORBIDDEN_TOP_LEVEL_IMPORTS:
                    top_level_gpu.append(alias.name)
        elif isinstance(stmt, ast.ImportFrom) and stmt.module:
            if stmt.module.split(".")[0] in FORBIDDEN_TOP_LEVEL_IMPORTS:
                top_level_gpu.append(stmt.module)
    assert not top_level_gpu, f"Top-level GPU imports in drain_leases.py: {top_level_gpu}"

    for pkg in FORBIDDEN_TOP_LEVEL_IMPORTS:
        monkeypatch.setitem(sys.modules, pkg, None)
    reloaded = importlib.reload(drain_mod)
    assert hasattr(reloaded, "drain_leases")

    # 2. LoRA adapter directory + --max-batches=1 + --max-wall-minutes
    lora_dir = tmp_path / "lora_adapter"
    lora_dir.mkdir()
    (lora_dir / "adapter_model.safetensors").write_bytes(b"weights")

    unassign_calls = 0

    def count_unassign() -> None:
        nonlocal unassign_calls
        unassign_calls += 1

    def always_one_item(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/colab/lease":
            return httpx.Response(
                200,
                json={
                    "lease_id": "00000000-0000-4000-8000-000000000002",
                    "expires_at": "2026-11-22T03:00:00+00:00",
                    "prompt_hash": "b" * 64,
                    "relations_schema": {"type": "object"},
                    "items": [
                        {
                            "chunk_id": "00000000-0000-4000-8000-000000000011",
                            "source_id": "00000000-0000-4000-8000-000000000021",
                            "max_tokens": 2000,
                            "prompt": "Passage",
                        }
                    ],
                },
            )
        return httpx.Response(200, json={"accepted_chunks": 1})

    seen_engine_kwargs: dict[str, Any] = {}

    def lora_engine_factory(**kwargs: Any) -> Any:
        seen_engine_kwargs.update(kwargs)
        return _dummy_engine_factory(**kwargs)

    summary_batches = drain_leases(
        api_url="http://brain.test",
        worker_token=WORKER_TOKEN,
        hf_model=VALID_MODEL,
        hf_revision=VALID_REVISION,
        lora_path=lora_dir,
        max_batches=1,
        config_loader=_ok_config_loader,
        engine_factory=lora_engine_factory,
        transport=httpx.MockTransport(always_one_item),
        unassign_fn=count_unassign,
    )
    assert seen_engine_kwargs["enable_lora"] is True
    assert summary_batches.batches_completed == 1
    assert summary_batches.stop_reason == "max_batches"
    assert re.fullmatch(
        rf"^colab-vllm/{re.escape(VALID_MODEL)}@{VALID_REVISION}\+lora:[0-9a-f]{{12}}$",
        summary_batches.model_tag,
    )
    assert unassign_calls == 1

    # 3. Wall-clock limit stops after clock advances past deadline
    ticks = iter([100.0, 100.0, 200.0])  # start=100, check1=100 (<160), check2=200 (>=160)
    summary_wall = drain_leases(
        api_url="http://brain.test",
        worker_token=WORKER_TOKEN,
        hf_model=VALID_MODEL,
        hf_revision=VALID_REVISION,
        max_wall_minutes=1.0,
        config_loader=_ok_config_loader,
        engine_factory=_dummy_engine_factory,
        transport=httpx.MockTransport(always_one_item),
        unassign_fn=count_unassign,
        time_fn=lambda: next(ticks),
    )
    assert summary_wall.batches_completed == 1
    assert summary_wall.stop_reason == "max_wall_minutes"
    assert unassign_calls == 2
