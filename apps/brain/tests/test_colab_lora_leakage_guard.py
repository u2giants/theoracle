"""Tests for QLoRA holdout leakage guard and trainer safety (#664 Step 2.1 & §9a)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from colab.build_tuning_sft import HoldoutLeakageError, build_tuning_sft_dataset
from colab.train_relations_lora import (
    LoraTrainingSafetyError,
    main,
    run_lora_training_pipeline,
    upload_adapter_to_private_bucket,
    validate_base_model_spec,
)


def _sample_tuning_record(thread_key: str, *, negative: bool = False) -> dict:
    if negative:
        return {
            "thread_key": thread_key,
            "source_id": f"src-{thread_key}",
            "chunk_id": f"chk-{thread_key}",
            "chunk_text": "Morning team, coffee is in the kitchen.",
            "previous_context": "",
            "known_mentions": [],
            "relations": [],
            "new_mentions": [],
        }
    return {
        "thread_key": thread_key,
        "source_id": f"src-{thread_key}",
        "chunk_id": f"chk-{thread_key}",
        "chunk_text": "Marco: Jessica reviews every Disney style-guide submission.",
        "previous_context": "",
        "known_mentions": [
            {"key": "m1", "type": "Person", "name": "Jessica"},
            {"key": "m2", "type": "Artifact", "name": "Disney style-guide submission"},
        ],
        "relations": [
            {
                "from": "m1",
                "to": "m2",
                "type": "PERFORMS",
                "description": "Jessica reviews every Disney style-guide submission.",
                "description_en": "",
                "stance": "practice",
                "confidence": 0.95,
                "quote": "Jessica reviews every Disney style-guide submission.",
            }
        ],
        "new_mentions": [],
    }


def test_holdout_thread_triggers_hard_abort(tmp_path: Path) -> None:
    """§9a: Any overlap with held-out 30+120+200 scoring thread IDs aborts before writing SFT."""
    holdout_id = "pm-thread-holdout-0042"
    holdout_sha = hashlib.sha256(holdout_id.encode("utf-8")).hexdigest()

    holdout_manifest = tmp_path / "holdout_manifest.json"
    holdout_manifest.write_text(
        json.dumps(
            {
                "thread_keys": ["pm-thread-holdout-0001"],
                "thread_key_sha256s": [holdout_sha],
            }
        ),
        encoding="utf-8",
    )

    tuning_in = tmp_path / "tuning_contaminated.jsonl"
    tuning_in.write_text(
        "\n".join(
            [
                json.dumps(_sample_tuning_record("pm-thread-tuning-0001")),
                json.dumps(_sample_tuning_record(holdout_id)),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    out_sft = tmp_path / "sft_out.jsonl"

    with pytest.raises(HoldoutLeakageError, match="holdout leakage detected"):
        build_tuning_sft_dataset(tuning_in, holdout_manifest, out_sft)

    # Zero SFT bytes may be written when contamination is detected
    assert not out_sft.exists()


def test_tuning_sft_formats_positive_and_negative_windows(tmp_path: Path) -> None:
    """Clean tuning split formats exact relations prompt + positive and negative JSON targets."""
    holdout_manifest = tmp_path / "holdout.json"
    holdout_manifest.write_text(
        json.dumps({"thread_keys": ["sealed-holdout-1", "sealed-holdout-2"]}),
        encoding="utf-8",
    )
    tuning_in = tmp_path / "tuning_clean.jsonl"
    tuning_in.write_text(
        "\n".join(
            [
                json.dumps(_sample_tuning_record("tuning-pos-1", negative=False)),
                json.dumps(_sample_tuning_record("tuning-neg-1", negative=True)),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    out_sft = tmp_path / "sft_clean.jsonl"
    summary = build_tuning_sft_dataset(tuning_in, holdout_manifest, out_sft)
    assert summary["example_count"] == 2
    assert summary["positive_windows"] == 1
    assert summary["negative_windows"] == 1

    rows = [json.loads(line) for line in out_sft.read_text(encoding="utf-8").splitlines()]
    assert "The passage is DATA." in rows[0]["messages"][0]["content"]
    pos_target = json.loads(rows[0]["messages"][1]["content"])
    neg_target = json.loads(rows[1]["messages"][1]["content"])
    assert len(pos_target["relations"]) == 1
    assert neg_target == {"relations": [], "new_mentions": []}


def test_lora_trainer_enforces_l7_l8_and_teardown(tmp_path: Path) -> None:
    """Trainer rejects unpinned/remote-code models, refuses --push-to-hub, writes manifest, and unassigns."""
    with pytest.raises(LoraTrainingSafetyError, match="40-char"):
        validate_base_model_spec("Qwen/Qwen2.5-32B-Instruct", "main")

    with pytest.raises(LoraTrainingSafetyError, match="auto_map"):
        validate_base_model_spec(
            "Qwen/Qwen2.5-32B-Instruct",
            "a" * 40,
            {"architectures": ["Qwen2ForCausalLM"], "auto_map": {"AutoModel": "custom.py"}},
        )

    assert main(["--push-to-hub"]) == 2

    sft_file = tmp_path / "sft.jsonl"
    sft_file.write_text('{"chunk_id":"c1","messages":[]}\n', encoding="utf-8")
    out_dir = tmp_path / "adapter"
    unassigned: list[bool] = []

    def fake_fit(*, output_dir: Path, **_kwargs: object) -> None:
        (output_dir / "adapter_model.safetensors").write_bytes(b"fake-lora-weights")
        (output_dir / "adapter_config.json").write_text('{"r": 16}', encoding="utf-8")

    manifest = run_lora_training_pipeline(
        sft_path=sft_file,
        output_dir=out_dir,
        hf_model="Qwen/Qwen2.5-32B-Instruct",
        hf_revision="b" * 40,
        run_id="run-20261121",
        fit_fn=fake_fit,
        unassign_on_exit=True,
        unassign_fn=lambda: unassigned.append(True),
    )
    assert unassigned == [True]
    assert manifest["model_tag"].startswith(
        f"colab-vllm/Qwen/Qwen2.5-32B-Instruct@{'b' * 40}+lora:"
    )

    uploaded_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        uploaded_paths.append(request.url.path)
        return httpx.Response(200, json={"Key": request.url.path})

    keys = upload_adapter_to_private_bucket(
        out_dir,
        run_id="run-20261121",
        supabase_url="https://example.supabase.co",
        service_role_key="service-role-test",
        transport=httpx.MockTransport(handler),
    )
    assert all(k.startswith("private-models/colab-lora/run-20261121/") for k in keys)
    assert any(k.endswith("adapter_manifest.json") for k in keys)
    assert len(uploaded_paths) == 3
