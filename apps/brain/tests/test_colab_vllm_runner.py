"""Unit and adversarial tests for apps/brain/colab/run_vllm_batch.py (#664 Step 1.2 & §9a)."""

from __future__ import annotations

import ast
import importlib
import json
import os
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from brain.colab_packet import export_relations_schema, normalize_colab_model_tag
from colab import run_vllm_batch as runner_mod
from colab.run_vllm_batch import (
    ALLOWED_ARCHITECTURES,
    TRUNCATION_RETRY_MAX_TOKENS,
    ModelPolicyError,
    VllmBatchError,
    compute_model_tag,
    main,
    run_batch,
)

BRAIN_DIR = Path(__file__).resolve().parents[1]
BRAIN_PKG_DIR = BRAIN_DIR / "brain"
RUNNER_PATH = BRAIN_DIR / "colab" / "run_vllm_batch.py"

VALID_REVISION = "a" * 40
ALT_REVISION = "0123456789abcdef0123456789abcdef01234567"
FORBIDDEN_BRAIN_IMPORTS = frozenset({"vllm", "torch", "peft", "trl", "bitsandbytes"})
FORBIDDEN_TOP_LEVEL_RUNNER_IMPORTS = FORBIDDEN_BRAIN_IMPORTS | frozenset(
    {"transformers", "accelerate", "datasets"}
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


def _write_schema(tmp_path: Path) -> Path:
    schema_path = tmp_path / "relations_schema.json"
    schema_path.write_text(
        json.dumps(export_relations_schema()),
        encoding="utf-8",
    )
    return schema_path


def _write_packet(
    tmp_path: Path,
    count: int = 2,
    *,
    omit_max_tokens: bool = False,
    custom_max_tokens: int | None = None,
) -> Path:
    packet_path = tmp_path / "packet.jsonl"
    lines: list[str] = []
    for idx in range(count):
        item: dict[str, Any] = {
            "packet_version": 1,
            "source_id": f"src-{idx // 10}",
            "chunk_id": f"chunk-{idx:04d}",
            "prompt_hash": "hash-abc123",
            "prompt": f"Extract relations from passage {idx}.",
        }
        if not omit_max_tokens:
            item["max_tokens"] = custom_max_tokens if custom_max_tokens is not None else 2000
        lines.append(json.dumps(item))
    packet_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return packet_path


def _write_local_model_dir(
    tmp_path: Path,
    *,
    name: str = "local-model",
    config: dict[str, Any] | None = None,
    extra_files: dict[str, str] | None = None,
) -> Path:
    model_dir = tmp_path / name
    model_dir.mkdir(parents=True, exist_ok=True)
    cfg = config if config is not None else {"architectures": ["Qwen2ForCausalLM"]}
    (model_dir / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    for rel, content in (extra_files or {}).items():
        target = model_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return model_dir


def _install_fake_vllm(
    monkeypatch: pytest.MonkeyPatch,
    *,
    use_structured_outputs: bool = False,
    generate_fn: Any = None,
) -> dict[str, Any]:
    """Register a minimal fake ``vllm`` package in ``sys.modules`` and capture calls."""
    recorded: dict[str, Any] = {"llm_kwargs": [], "generate_calls": []}

    class FakeGuidedDecodingParams:
        def __init__(self, *, json: dict[str, Any]) -> None:
            self.json = json

    class FakeStructuredOutputsParams:
        def __init__(self, *, json: dict[str, Any]) -> None:
            self.json = json

    class FakeSamplingParams:
        def __init__(
            self,
            *,
            temperature: float,
            max_tokens: int,
            guided_decoding: Any = None,
            structured_outputs: Any = None,
        ) -> None:
            if use_structured_outputs and guided_decoding is not None:
                raise TypeError("guided_decoding is removed")
            self.temperature = temperature
            self.max_tokens = max_tokens
            self.guided_decoding = guided_decoding
            self.structured_outputs = structured_outputs

    class FakeLoRARequest:
        def __init__(self, lora_name: str, lora_int_id: int, lora_path: str) -> None:
            self.lora_name = lora_name
            self.lora_int_id = lora_int_id
            self.lora_path = lora_path

    class FakeLLM:
        def __init__(self, **kwargs: Any) -> None:
            recorded["llm_kwargs"].append(kwargs)

        def generate(
            self,
            prompts: list[str],
            sampling_params: list[Any],
            **kwargs: Any,
        ) -> list[_FakeRequestOutput]:
            recorded["generate_calls"].append(
                {
                    "prompts": list(prompts),
                    "sampling_params": list(sampling_params),
                    "kwargs": dict(kwargs),
                }
            )
            if generate_fn is not None:
                return generate_fn(prompts, sampling_params, **kwargs)
            return [
                _FakeRequestOutput(
                    prompt_token_ids=[1, 2, 3, 4],
                    outputs=[
                        _FakeCompletionOutput(
                            text='{"relations": [], "new_mentions": []}',
                            finish_reason="stop",
                            token_ids=[10, 11, 12],
                        )
                    ],
                )
                for _ in prompts
            ]

    vllm_pkg = types.ModuleType("vllm")
    vllm_pkg.LLM = FakeLLM  # type: ignore[attr-defined]
    vllm_pkg.SamplingParams = FakeSamplingParams  # type: ignore[attr-defined]

    sampling_mod = types.ModuleType("vllm.sampling_params")
    if use_structured_outputs:
        sampling_mod.StructuredOutputsParams = FakeStructuredOutputsParams  # type: ignore[attr-defined]
    else:
        sampling_mod.GuidedDecodingParams = FakeGuidedDecodingParams  # type: ignore[attr-defined]

    lora_pkg = types.ModuleType("vllm.lora")
    lora_req_mod = types.ModuleType("vllm.lora.request")
    lora_req_mod.LoRARequest = FakeLoRARequest  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "vllm", vllm_pkg)
    monkeypatch.setitem(sys.modules, "vllm.sampling_params", sampling_mod)
    monkeypatch.setitem(sys.modules, "vllm.lora", lora_pkg)
    monkeypatch.setitem(sys.modules, "vllm.lora.request", lora_req_mod)
    return recorded


def test_rejects_remote_code_and_unpinned_revision(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """§9a: Reject floating refs, short SHAs, auto_map, modeling_*.py, and non-allowlisted arches; enforce trust_remote_code=False."""
    schema_path = _write_schema(tmp_path)
    packet_path = _write_packet(tmp_path, count=1)
    output_path = tmp_path / "results.jsonl"
    recorded = _install_fake_vllm(monkeypatch)

    # 1. Floating branch or non-40-hex revision must fail before touching engine.
    for bad_rev in ("main", "HEAD", "v1.0.0", "abcdef1234", "A" * 40, "g" * 40):
        with pytest.raises(ModelPolicyError, match="40-char"):
            run_batch(
                input_path=packet_path,
                schema_path=schema_path,
                output_path=output_path,
                hf_model="Qwen/Qwen2.5-32B-Instruct",
                hf_revision=bad_rev,
                config_loader=lambda _m, _r: ({"architectures": ["Qwen2ForCausalLM"]}, []),
            )
    assert recorded["llm_kwargs"] == []

    # 2. Custom auto_map hook in config.json must fail before loading weights.
    with pytest.raises(ModelPolicyError, match="auto_map"):
        run_batch(
            input_path=packet_path,
            schema_path=schema_path,
            output_path=output_path,
            hf_model="evil/custom-model",
            hf_revision=VALID_REVISION,
            config_loader=lambda _m, _r: (
                {
                    "architectures": ["Qwen2ForCausalLM"],
                    "auto_map": {"AutoModelForCausalLM": "modeling_evil.EvilForCausalLM"},
                },
                ["config.json"],
            ),
        )
    assert recorded["llm_kwargs"] == []

    # 3. Custom modeling_*.py file in local model directory must fail even if config claims allowed arch.
    evil_dir = _write_local_model_dir(
        tmp_path,
        name="evil-local",
        config={"architectures": ["Qwen2ForCausalLM"]},
        extra_files={"modeling_custom.py": "print('remote code')\n"},
    )
    with pytest.raises(ModelPolicyError, match="modeling_"):
        run_batch(
            input_path=packet_path,
            schema_path=schema_path,
            output_path=output_path,
            hf_model=str(evil_dir),
            hf_revision=VALID_REVISION,
        )
    assert recorded["llm_kwargs"] == []

    # 4. Non-allowlisted architecture must fail before loading weights.
    for bad_arch_cfg in (
        {"architectures": ["CustomForCausalLM"]},
        {"architectures": ["MistralForCausalLM"]},
        {"architectures": ["Qwen2ForCausalLM", "CustomMixin"]},
        {"architectures": []},
        {},
    ):
        with pytest.raises(ModelPolicyError, match="ALLOWED_ARCHITECTURES"):
            run_batch(
                input_path=packet_path,
                schema_path=schema_path,
                output_path=output_path,
                hf_model="someone/other-model",
                hf_revision=VALID_REVISION,
                config_loader=lambda _m, _r, cfg=bad_arch_cfg: (cfg, ["config.json"]),
            )
    assert recorded["llm_kwargs"] == []

    # 5. Every allowlisted architecture succeeds and passes trust_remote_code=False to vllm.LLM.
    for idx, arch in enumerate(sorted(ALLOWED_ARCHITECTURES)):
        out_file = tmp_path / f"ok_{idx}.jsonl"
        summary = run_batch(
            input_path=packet_path,
            schema_path=schema_path,
            output_path=out_file,
            hf_model=f"org/model-{arch}",
            hf_revision=ALT_REVISION,
            config_loader=lambda _m, _r, a=arch: ({"architectures": [a]}, ["config.json"]),
        )
        assert summary.processed_items == 1
        assert recorded["llm_kwargs"][-1]["trust_remote_code"] is False
        assert recorded["llm_kwargs"][-1]["revision"] == ALT_REVISION


@pytest.mark.parametrize("use_structured_outputs", [False, True])
def test_batch_execution_guided_json_and_lora_model_tag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    use_structured_outputs: bool,
) -> None:
    """Verify temperature=0, default 2000 max_tokens, guided JSON (0.8.x + structured fallback), and LoRA tag."""
    schema_path = _write_schema(tmp_path)
    packet_path = _write_packet(tmp_path, count=2, omit_max_tokens=True)
    output_path = tmp_path / "results.jsonl"

    lora_dir = tmp_path / "adapter"
    lora_dir.mkdir()
    (lora_dir / "adapter_config.json").write_text('{"r": 16}', encoding="utf-8")
    (lora_dir / "adapter_model.safetensors").write_bytes(b"fake-weights-bytes")

    recorded = _install_fake_vllm(
        monkeypatch, use_structured_outputs=use_structured_outputs
    )
    model_dir = _write_local_model_dir(
        tmp_path, name="qwen-local", config={"architectures": ["Qwen3ForCausalLM"]}
    )

    rc = main(
        [
            "--input",
            str(packet_path),
            "--schema",
            str(schema_path),
            "--output",
            str(output_path),
            "--hf-model",
            str(model_dir),
            "--hf-revision",
            VALID_REVISION,
            "--lora-path",
            str(lora_dir),
            "--max-model-len",
            "4096",
        ]
    )
    assert rc == 0
    printed_summary = json.loads(capsys.readouterr().out.strip())
    assert printed_summary["first_truncated_items"] == 0

    llm_kw = recorded["llm_kwargs"][0]
    assert llm_kw["trust_remote_code"] is False
    assert llm_kw["max_model_len"] == 4096
    assert llm_kw["enable_lora"] is True

    gen_call = recorded["generate_calls"][0]
    assert gen_call["kwargs"]["lora_request"].lora_path == str(lora_dir)
    for sp in gen_call["sampling_params"]:
        assert sp.temperature == 0.0
        assert sp.max_tokens == 2000
        if use_structured_outputs:
            assert sp.structured_outputs.json == json.loads(schema_path.read_text(encoding="utf-8"))
        else:
            assert sp.guided_decoding.json == json.loads(schema_path.read_text(encoding="utf-8"))

    expected_tag = compute_model_tag(str(model_dir), VALID_REVISION, lora_dir)
    assert expected_tag.startswith(f"{model_dir}@{VALID_REVISION}+lora:")
    # Deterministic tag across repeated computations
    assert expected_tag == compute_model_tag(str(model_dir), VALID_REVISION, lora_dir)
    # Compatible with colab_packet provenance tag validator when repo-shaped
    assert normalize_colab_model_tag(
        compute_model_tag("Qwen/Qwen2.5-32B-Instruct", ALT_REVISION, lora_dir)
    ).startswith("colab-vllm/Qwen/Qwen2.5-32B-Instruct@")

    rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert set(rows[0].keys()) == {
        "chunk_id",
        "prompt_hash",
        "model_tag",
        "raw_content",
        "finish_reason",
        "first_finish_reason",
        "retried",
        "prompt_tokens",
        "completion_tokens",
        "elapsed_ms",
    }
    assert rows[0]["chunk_id"] == "chunk-0000"
    assert rows[0]["model_tag"] == expected_tag
    assert rows[0]["finish_reason"] == "stop"
    assert rows[0]["first_finish_reason"] == "stop"
    assert rows[0]["retried"] is False
    assert rows[0]["prompt_tokens"] == 4
    assert rows[0]["completion_tokens"] == 3
    assert isinstance(rows[0]["elapsed_ms"], (int, float))


def test_checkpoint_64_and_resume_skips_completed_chunks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify 64-item checkpointing (flush + fsync) and resume skipping already-written chunk_ids."""
    schema_path = _write_schema(tmp_path)
    packet_path = _write_packet(tmp_path, count=130)
    output_path = tmp_path / "results.jsonl"
    model_dir = _write_local_model_dir(tmp_path)

    fsync_calls = 0
    real_fsync = os.fsync

    def counting_fsync(fd: int) -> None:
        nonlocal fsync_calls
        fsync_calls += 1
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", counting_fsync)

    # First run: succeed on batch 1 (64 items), crash on batch 2.
    batch_counter = 0

    def crash_on_second_batch(
        prompts: list[str], _sp: list[Any], **_kw: Any
    ) -> list[_FakeRequestOutput]:
        nonlocal batch_counter
        batch_counter += 1
        if batch_counter == 2:
            raise RuntimeError("simulated Colab VM preemption")
        return [
            _FakeRequestOutput(
                prompt_token_ids=[1, 2],
                outputs=[_FakeCompletionOutput(text='{"relations": [], "new_mentions": []}', token_ids=[5])],
            )
            for _ in prompts
        ]

    _install_fake_vllm(monkeypatch, generate_fn=crash_on_second_batch)
    with pytest.raises(RuntimeError, match="simulated Colab VM preemption"):
        run_batch(
            input_path=packet_path,
            schema_path=schema_path,
            output_path=output_path,
            hf_model=str(model_dir),
            hf_revision=VALID_REVISION,
            checkpoint_every=64,
        )

    assert fsync_calls == 1
    first_lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(first_lines) == 64

    # Simulate a truncated partial JSON line left by a mid-write kill.
    with output_path.open("a", encoding="utf-8") as fh:
        fh.write('{"chunk_id": "chunk-0064", "partial": ')

    # Resume: must skip the 64 completed chunks, repair the trailing corrupt line, and process 66 remaining.
    recorded_resume = _install_fake_vllm(monkeypatch)
    summary = run_batch(
        input_path=packet_path,
        schema_path=schema_path,
        output_path=output_path,
        hf_model=str(model_dir),
        hf_revision=VALID_REVISION,
        checkpoint_every=64,
    )
    assert summary.total_items == 130
    assert summary.skipped_items == 64
    assert summary.processed_items == 66

    # Remaining 66 items run as 2 batches: 64 + 2
    batch_sizes = [len(call["prompts"]) for call in recorded_resume["generate_calls"]]
    assert batch_sizes == [64, 2]

    final_rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert len(final_rows) == 130
    assert [row["chunk_id"] for row in final_rows] == [f"chunk-{i:04d}" for i in range(130)]


def test_finish_reason_length_retries_once_at_4000_tokens(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Chunks hitting finish_reason=='length' retry exactly once at TRUNCATION_RETRY_MAX_TOKENS (4000)."""
    assert TRUNCATION_RETRY_MAX_TOKENS == 4000
    schema_path = _write_schema(tmp_path)
    packet_path = _write_packet(tmp_path, count=3, custom_max_tokens=1500)
    output_path = tmp_path / "results.jsonl"
    model_dir = _write_local_model_dir(tmp_path)

    def truncating_generate(
        prompts: list[str], sampling_params: list[Any], **_kw: Any
    ) -> list[_FakeRequestOutput]:
        outs: list[_FakeRequestOutput] = []
        for prompt, sp in zip(prompts, sampling_params, strict=True):
            # Item 0 succeeds on first pass; Item 1 truncates then succeeds at 4000;
            # Item 2 truncates on both passes (must NOT retry a second time).
            if "passage 0" in prompt:
                outs.append(
                    _FakeRequestOutput(
                        [1], [_FakeCompletionOutput('{"relations": [], "new_mentions": []}', "stop", [2])]
                    )
                )
            elif "passage 1" in prompt:
                if sp.max_tokens == 1500:
                    outs.append(
                        _FakeRequestOutput([1], [_FakeCompletionOutput('{"relations": [', "length", [2, 3])])
                    )
                else:
                    outs.append(
                        _FakeRequestOutput(
                            [1], [_FakeCompletionOutput('{"relations": [], "new_mentions": []}', "stop", [2, 3, 4])]
                        )
                    )
            else:
                outs.append(
                    _FakeRequestOutput([1], [_FakeCompletionOutput('{"relations": [', "length", [2, 3])])
                )
        return outs

    recorded = _install_fake_vllm(monkeypatch, generate_fn=truncating_generate)
    summary = run_batch(
        input_path=packet_path,
        schema_path=schema_path,
        output_path=output_path,
        hf_model=str(model_dir),
        hf_revision=VALID_REVISION,
    )

    assert summary.processed_items == 3
    assert summary.retried_items == 2
    assert summary.first_truncated_items == 2
    assert len(recorded["generate_calls"]) == 2
    retry_call = recorded["generate_calls"][1]
    assert len(retry_call["prompts"]) == 2
    assert all(sp.max_tokens == 4000 for sp in retry_call["sampling_params"])

    rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["finish_reason"] == "stop"
    assert rows[0]["first_finish_reason"] == "stop"
    assert rows[0]["retried"] is False
    assert rows[1]["finish_reason"] == "stop"
    assert rows[1]["first_finish_reason"] == "length"
    assert rows[1]["retried"] is True
    assert rows[1]["raw_content"] == '{"relations": [], "new_mentions": []}'
    assert rows[2]["finish_reason"] == "length"
    assert rows[2]["first_finish_reason"] == "length"
    assert rows[2]["retried"] is True

    cli_output = tmp_path / "cli_results.jsonl"
    rc = main(
        [
            "--input",
            str(packet_path),
            "--schema",
            str(schema_path),
            "--output",
            str(cli_output),
            "--hf-model",
            str(model_dir),
            "--hf-revision",
            VALID_REVISION,
        ]
    )
    assert rc == 0
    cli_summary = json.loads(capsys.readouterr().out.strip())
    assert cli_summary["retried_items"] == 2
    assert cli_summary["first_truncated_items"] == 2


def test_unassign_on_exit_fires_even_on_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """--unassign-on-exit calls google.colab.runtime.unassign() in finally on success and failure."""
    unassign_calls = 0

    def fake_unassign() -> None:
        nonlocal unassign_calls
        unassign_calls += 1

    google_pkg = types.ModuleType("google")
    colab_pkg = types.ModuleType("google.colab")
    runtime_mod = types.ModuleType("google.colab.runtime")
    runtime_mod.unassign = fake_unassign  # type: ignore[attr-defined]
    colab_pkg.runtime = runtime_mod  # type: ignore[attr-defined]
    google_pkg.colab = colab_pkg  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "google", google_pkg)
    monkeypatch.setitem(sys.modules, "google.colab", colab_pkg)
    monkeypatch.setitem(sys.modules, "google.colab.runtime", runtime_mod)

    schema_path = _write_schema(tmp_path)
    packet_path = _write_packet(tmp_path, count=1)
    model_dir = _write_local_model_dir(tmp_path)

    # 1. Flag omitted -> unassign must NOT fire.
    _install_fake_vllm(monkeypatch)
    rc = main(
        [
            "--input",
            str(packet_path),
            "--schema",
            str(schema_path),
            "--output",
            str(tmp_path / "no_unassign.jsonl"),
            "--hf-model",
            str(model_dir),
            "--hf-revision",
            VALID_REVISION,
        ]
    )
    assert rc == 0
    assert unassign_calls == 0

    # 2. Normal exit with --unassign-on-exit -> fires once.
    rc = main(
        [
            "--input",
            str(packet_path),
            "--schema",
            str(schema_path),
            "--output",
            str(tmp_path / "ok_unassign.jsonl"),
            "--hf-model",
            str(model_dir),
            "--hf-revision",
            VALID_REVISION,
            "--unassign-on-exit",
        ]
    )
    assert rc == 0
    assert unassign_calls == 1

    # 3. Runtime crash during inference -> unassign still fires.
    def exploding_generate(*_args: Any, **_kwargs: Any) -> list[Any]:
        raise RuntimeError("cuda OOM")

    _install_fake_vllm(monkeypatch, generate_fn=exploding_generate)
    with pytest.raises(RuntimeError, match="cuda OOM"):
        main(
            [
                "--input",
                str(packet_path),
                "--schema",
                str(schema_path),
                "--output",
                str(tmp_path / "err_unassign.jsonl"),
                "--hf-model",
                str(model_dir),
                "--hf-revision",
                VALID_REVISION,
                "--unassign-on-exit",
            ]
        )
    assert unassign_calls == 2

    # 4. Policy validation failure -> unassign still fires.
    rc_bad = main(
        [
            "--input",
            str(packet_path),
            "--schema",
            str(schema_path),
            "--output",
            str(tmp_path / "bad_rev.jsonl"),
            "--hf-model",
            str(model_dir),
            "--hf-revision",
            "main",
            "--unassign-on-exit",
        ]
    )
    assert rc_bad == 1
    assert unassign_calls == 3


def test_cli_requires_hf_model_and_revision(tmp_path: Path) -> None:
    """L10: --hf-model and --hf-revision must be explicitly required with no defaults."""
    schema_path = _write_schema(tmp_path)
    packet_path = _write_packet(tmp_path, count=1)
    output_path = tmp_path / "out.jsonl"

    with pytest.raises(SystemExit):
        main(
            [
                "--input",
                str(packet_path),
                "--schema",
                str(schema_path),
                "--output",
                str(output_path),
                "--hf-revision",
                VALID_REVISION,
            ]
        )

    with pytest.raises(SystemExit):
        main(
            [
                "--input",
                str(packet_path),
                "--schema",
                str(schema_path),
                "--output",
                str(output_path),
                "--hf-model",
                "Qwen/Qwen2.5-32B-Instruct",
            ]
        )


def test_brain_package_and_runner_have_no_top_level_gpu_imports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guard: zero files under apps/brain/brain/ import GPU packages, and run_vllm_batch imports cleanly without them."""
    offenders: list[str] = []
    for py_file in sorted(BRAIN_PKG_DIR.rglob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in FORBIDDEN_BRAIN_IMPORTS:
                        offenders.append(f"{py_file.relative_to(BRAIN_DIR)}:{node.lineno} import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".")[0]
                if top in FORBIDDEN_BRAIN_IMPORTS:
                    offenders.append(
                        f"{py_file.relative_to(BRAIN_DIR)}:{node.lineno} from {node.module}"
                    )
    assert not offenders, f"Forbidden GPU imports under apps/brain/brain/: {offenders}"

    # Verify run_vllm_batch.py has zero top-level GPU imports in AST and reloads cleanly when blocked.
    runner_tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"), filename=str(RUNNER_PATH))
    top_level_gpu: list[str] = []
    for stmt in runner_tree.body:
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                if alias.name.split(".")[0] in FORBIDDEN_TOP_LEVEL_RUNNER_IMPORTS:
                    top_level_gpu.append(alias.name)
        elif isinstance(stmt, ast.ImportFrom) and stmt.module:
            if stmt.module.split(".")[0] in FORBIDDEN_TOP_LEVEL_RUNNER_IMPORTS:
                top_level_gpu.append(stmt.module)
    assert not top_level_gpu, f"Top-level GPU imports found in run_vllm_batch.py: {top_level_gpu}"

    for pkg in FORBIDDEN_TOP_LEVEL_RUNNER_IMPORTS:
        monkeypatch.setitem(sys.modules, pkg, None)
    reloaded = importlib.reload(runner_mod)
    assert hasattr(reloaded, "run_batch")


def test_engine_factory_injection_works_without_vllm(tmp_path: Path) -> None:
    """Verify injected engine_factory works cleanly in CPU CI with zero vllm installed."""
    schema_path = _write_schema(tmp_path)
    packet_path = _write_packet(tmp_path, count=1)
    output_path = tmp_path / "injected.jsonl"
    model_dir = _write_local_model_dir(
        tmp_path, config={"architectures": ["LlamaForCausalLM"]}
    )

    seen_kwargs: dict[str, Any] = {}

    class InjectedEngine:
        def generate(self, prompts: list[str], sampling_params: list[Any]) -> list[_FakeRequestOutput]:
            assert sampling_params[0].temperature == 0.0
            assert sampling_params[0].max_tokens == 2000
            return [
                _FakeRequestOutput(
                    [1, 2],
                    [_FakeCompletionOutput('{"relations": [], "new_mentions": []}', "stop", [3])],
                )
                for _ in prompts
            ]

    def factory(**kwargs: Any) -> InjectedEngine:
        seen_kwargs.update(kwargs)
        return InjectedEngine()

    summary = run_batch(
        input_path=packet_path,
        schema_path=schema_path,
        output_path=output_path,
        hf_model=str(model_dir),
        hf_revision=VALID_REVISION,
        engine_factory=factory,
    )
    assert seen_kwargs["trust_remote_code"] is False
    assert summary.processed_items == 1
    assert VllmBatchError is not None


def test_chat_template_applied_when_tokenizer_present(tmp_path: Path) -> None:
    """When vLLM exposes a chat-templated tokenizer, prompts are formatted with enable_thinking=False."""
    from colab.run_vllm_batch import _format_prompts_for_llm

    seen_calls: list[dict[str, Any]] = []

    class FakeTokenizer:
        chat_template = "{{ messages }}"

        def apply_chat_template(
            self, messages: list[dict[str, str]], **kwargs: Any
        ) -> str:
            seen_calls.append({"messages": messages, "kwargs": kwargs})
            return f"<chat>{messages[0]['content']}</chat>"

    class FakeLLMWithTokenizer:
        def get_tokenizer(self) -> FakeTokenizer:
            return FakeTokenizer()

    out = _format_prompts_for_llm(FakeLLMWithTokenizer(), ["extract this"])
    assert out == ["<chat>extract this</chat>"]
    assert seen_calls[0]["kwargs"]["enable_thinking"] is False
    assert seen_calls[0]["kwargs"]["add_generation_prompt"] is True
    assert tmp_path is not None


def test_lora_tar_gz_archive_supported_and_unsafe_paths_rejected(tmp_path: Path) -> None:
    """Verify --lora-path accepts a safe .tar.gz adapter archive and rejects path traversal."""
    import io
    import tarfile

    from colab.run_vllm_batch import (
        VllmBatchError as RunnerBatchError,
    )
    from colab.run_vllm_batch import (
        compute_model_tag,
        resolved_lora_directory,
    )

    adapter_src = tmp_path / "lora_src"
    adapter_src.mkdir()
    (adapter_src / "adapter_config.json").write_text('{"r": 16}\n', encoding="utf-8")
    (adapter_src / "adapter_model.safetensors").write_bytes(b"weights-123")
    (adapter_src / "adapter_manifest.json").write_text(
        json.dumps({"adapter_sha256": "b" * 64}) + "\n",
        encoding="utf-8",
    )

    good_tar = tmp_path / "adapter.tar.gz"
    with tarfile.open(good_tar, "w:gz") as tf:
        for f in sorted(adapter_src.iterdir()):
            tf.add(f, arcname=f.name)

    tag = compute_model_tag("Qwen/Qwen2.5-14B-Instruct", VALID_REVISION, good_tar)
    assert tag == f"Qwen/Qwen2.5-14B-Instruct@{VALID_REVISION}+lora:{'b' * 12}"

    evil_tar = tmp_path / "evil.tar.gz"
    with tarfile.open(evil_tar, "w:gz") as tf:
        info = tarfile.TarInfo(name="../escape.txt")
        payload = b"bad"
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))

    with pytest.raises(RunnerBatchError, match="unsafe LoRA tar archive entry"):
        with resolved_lora_directory(evil_tar):
            pass
