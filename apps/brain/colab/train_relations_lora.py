"""4-bit QLoRA adapter trainer for Colab A100 with private storage custody (#664 Step 2.1).

Trains a domain relations adapter strictly from ``build_tuning_sft.py`` output,
verifies pinned 40-char Hugging Face commit SHA and ``trust_remote_code=False``
(L7), writes ``adapter_manifest.json``, uploads weights ONLY to private storage
under ``private-models/colab-lora/<run_id>/`` (never GitHub or public HF Hub,
L8), and calls ``google.colab.runtime.unassign()`` in ``finally``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

ALLOWED_ARCHITECTURES: frozenset[str] = frozenset(
    {
        "Qwen2ForCausalLM",
        "Qwen3ForCausalLM",
        "Gemma3ForCausalLM",
        "LlamaForCausalLM",
    }
)
REVISION_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]{3,80}$")
PRIVATE_STORAGE_PREFIX = "private-models/colab-lora"


class LoraTrainingSafetyError(RuntimeError):
    """Raised when model provenance, architecture, or privacy boundaries are violated."""


@dataclass(frozen=True)
class LoraHyperparameters:
    """Locked Step 2.1 QLoRA configuration."""

    r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    target_modules: str = "all-linear"
    learning_rate: float = 2e-4
    lr_scheduler_type: str = "cosine"
    num_train_epochs: int = 3
    per_device_train_batch_size: int = 2
    gradient_accumulation_steps: int = 8
    max_seq_length: int = 8192
    seed: int = 42
    bf16: bool = True


def validate_base_model_spec(
    hf_model: str,
    hf_revision: str,
    model_config: dict[str, Any] | None = None,
) -> None:
    """Enforce L7 + L10: explicit repo, 40-char commit SHA, allowlisted arch, no remote code."""
    if not hf_model or not hf_model.strip():
        raise LoraTrainingSafetyError("--hf-model is required and never defaulted")
    if REVISION_SHA_RE.fullmatch(hf_revision) is None:
        raise LoraTrainingSafetyError(
            f"--hf-revision must be a 40-char lowercase hex commit SHA, got {hf_revision!r}"
        )
    if model_config is not None:
        if model_config.get("auto_map"):
            raise LoraTrainingSafetyError("model config defines auto_map (remote code forbidden)")
        archs = model_config.get("architectures") or []
        if not archs or any(arch not in ALLOWED_ARCHITECTURES for arch in archs):
            raise LoraTrainingSafetyError(
                f"model architectures {archs!r} not in allowlist {sorted(ALLOWED_ARCHITECTURES)}"
            )


def compute_directory_sha256(directory: Path) -> str:
    """Deterministic SHA-256 across all adapter files in ``directory``."""
    hasher = hashlib.sha256()
    files = sorted(p for p in directory.rglob("*") if p.is_file() and p.name != "adapter_manifest.json")
    if not files:
        raise LoraTrainingSafetyError(f"adapter directory {directory} contains no files")
    for path in files:
        rel = path.relative_to(directory).as_posix()
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def upload_adapter_to_private_bucket(
    adapter_dir: Path,
    *,
    run_id: str,
    supabase_url: str,
    service_role_key: str,
    bucket: str = "company_documents",
    transport: httpx.BaseTransport | None = None,
) -> list[str]:
    """Upload adapter files strictly to private Supabase Storage (L8)."""
    if RUN_ID_RE.fullmatch(run_id) is None:
        raise LoraTrainingSafetyError(f"invalid run_id {run_id!r}")
    if not supabase_url or not service_role_key:
        raise LoraTrainingSafetyError("private bucket upload requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")

    uploaded_keys: list[str] = []
    with httpx.Client(
        base_url=supabase_url.rstrip("/"),
        headers={"Authorization": f"Bearer {service_role_key}"},
        timeout=httpx.Timeout(180.0, connect=30.0),
        transport=transport,
    ) as client:
        for file_path in sorted(p for p in adapter_dir.rglob("*") if p.is_file()):
            rel = file_path.relative_to(adapter_dir).as_posix()
            key = f"{PRIVATE_STORAGE_PREFIX}/{run_id}/{rel}"
            ctype = "application/json" if file_path.suffix == ".json" else "application/octet-stream"
            resp = client.post(
                f"/storage/v1/object/{bucket}/{key}",
                content=file_path.read_bytes(),
                headers={"Content-Type": ctype},
            )
            if resp.status_code not in (200, 201):
                raise LoraTrainingSafetyError(
                    f"private storage upload failed for {key}: HTTP {resp.status_code}"
                )
            uploaded_keys.append(key)
    return uploaded_keys


def _default_qlora_fit(
    *,
    sft_path: Path,
    output_dir: Path,
    hf_model: str,
    hf_revision: str,
    hparams: LoraHyperparameters,
) -> None:
    """Run 4-bit QLoRA training inside a Colab A100 runtime (lazy GPU imports)."""
    import torch
    from datasets import load_dataset
    from peft import LoraConfig
    from transformers import (
        AutoConfig,
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
    )
    from trl import SFTConfig, SFTTrainer

    cfg_obj = AutoConfig.from_pretrained(
        hf_model,
        revision=hf_revision,
        trust_remote_code=False,
    )
    validate_base_model_spec(hf_model, hf_revision, cfg_obj.to_dict())

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(
        hf_model,
        revision=hf_revision,
        trust_remote_code=False,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        hf_model,
        revision=hf_revision,
        quantization_config=bnb_config,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=False,
    )
    lora_config = LoraConfig(
        r=hparams.r,
        lora_alpha=hparams.lora_alpha,
        lora_dropout=hparams.lora_dropout,
        target_modules=hparams.target_modules,
        bias="none",
        task_type="CAUSAL_LM",
    )
    dataset = load_dataset("json", data_files=str(sft_path), split="train")
    sft_args = SFTConfig(
        output_dir=str(output_dir / "checkpoints"),
        num_train_epochs=hparams.num_train_epochs,
        per_device_train_batch_size=hparams.per_device_train_batch_size,
        gradient_accumulation_steps=hparams.gradient_accumulation_steps,
        learning_rate=hparams.learning_rate,
        lr_scheduler_type=hparams.lr_scheduler_type,
        bf16=hparams.bf16,
        max_seq_length=hparams.max_seq_length,
        seed=hparams.seed,
        data_seed=hparams.seed,
        save_strategy="no",
        report_to=[],
        push_to_hub=False,
    )
    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=dataset,
        peft_config=lora_config,
        args=sft_args,
    )
    trainer.train()
    trainer.model.save_pretrained(str(output_dir), safe_serialization=True)
    tokenizer.save_pretrained(str(output_dir))


def run_lora_training_pipeline(
    *,
    sft_path: Path,
    output_dir: Path,
    hf_model: str,
    hf_revision: str,
    run_id: str,
    hparams: LoraHyperparameters | None = None,
    fit_fn: Callable[..., None] | None = None,
    upload_to_private_storage: bool = False,
    unassign_on_exit: bool = True,
    unassign_fn: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Execute QLoRA training, manifest generation, optional private upload, and teardown."""
    hp = hparams or LoraHyperparameters()
    try:
        validate_base_model_spec(hf_model, hf_revision)
        if not sft_path.is_file():
            raise FileNotFoundError(f"SFT dataset file not found: {sft_path}")
        if RUN_ID_RE.fullmatch(run_id) is None:
            raise LoraTrainingSafetyError(f"invalid run_id {run_id!r}")

        training_sha = hashlib.sha256(sft_path.read_bytes()).hexdigest()
        output_dir.mkdir(parents=True, exist_ok=True)

        runner = fit_fn or _default_qlora_fit
        runner(
            sft_path=sft_path,
            output_dir=output_dir,
            hf_model=hf_model,
            hf_revision=hf_revision,
            hparams=hp,
        )

        # Remove intermediate trainer checkpoints if present before hashing/uploading adapter
        ckpt_dir = output_dir / "checkpoints"
        if ckpt_dir.is_dir():
            import shutil

            shutil.rmtree(ckpt_dir)

        adapter_sha = compute_directory_sha256(output_dir)
        manifest = {
            "run_id": run_id,
            "base_model": hf_model,
            "base_revision": hf_revision,
            "training_data_sha256": training_sha,
            "adapter_sha256": adapter_sha,
            "model_tag": f"colab-vllm/{hf_model}@{hf_revision}+lora:{adapter_sha[:12]}",
            "hyperparameters": asdict(hp),
        }
        (output_dir / "adapter_manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )

        if upload_to_private_storage:
            uploaded = upload_adapter_to_private_bucket(
                output_dir,
                run_id=run_id,
                supabase_url=os.environ.get("SUPABASE_URL", ""),
                service_role_key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
            )
            manifest["uploaded_keys"] = uploaded
        return manifest
    finally:
        if unassign_on_exit:
            if unassign_fn is not None:
                unassign_fn()
            else:
                try:
                    from google.colab import runtime  # type: ignore[import-not-found]

                    runtime.unassign()
                except Exception:
                    pass


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m colab.train_relations_lora")
    parser.add_argument("--sft-input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--hf-model", required=True)
    parser.add_argument("--hf-revision", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--upload-private", action="store_true")
    parser.add_argument("--no-unassign", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if argv is not None and any(arg.startswith("--push-to-hub") for arg in argv):
        print("L8 violation: pushing private adapters to public Hub is forbidden", file=sys.stderr)
        return 2
    if any(arg.startswith("--push-to-hub") for arg in sys.argv[1:]):
        print("L8 violation: pushing private adapters to public Hub is forbidden", file=sys.stderr)
        return 2
    ns = _build_parser().parse_args(argv)
    hp = LoraHyperparameters(num_train_epochs=ns.epochs, seed=ns.seed)
    manifest = run_lora_training_pipeline(
        sft_path=ns.sft_input,
        output_dir=ns.output_dir,
        hf_model=ns.hf_model,
        hf_revision=ns.hf_revision,
        run_id=ns.run_id,
        hparams=hp,
        upload_to_private_storage=ns.upload_private,
        unassign_on_exit=not ns.no_unassign,
    )
    print(json.dumps({"run_id": manifest["run_id"], "model_tag": manifest["model_tag"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
