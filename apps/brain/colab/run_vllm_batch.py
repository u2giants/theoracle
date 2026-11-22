"""Offline vLLM guided-JSON batch runner for ephemeral Colab GPUs (#664 Step 1.2).

Zero GPU libraries (``vllm``, ``torch``, ``transformers``, ``peft``, ``trl``,
``bitsandbytes``) are imported at module top level so CPU CI can import and
test this module without GPU dependencies installed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ALLOWED_ARCHITECTURES: frozenset[str] = frozenset(
    {
        "Qwen2ForCausalLM",
        "Qwen3ForCausalLM",
        "Gemma3ForCausalLM",
        "LlamaForCausalLM",
    }
)
REVISION_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DEFAULT_MAX_TOKENS = 2000
TRUNCATION_RETRY_MAX_TOKENS = 4000
DEFAULT_MAX_MODEL_LEN = 8192
DEFAULT_CHECKPOINT_EVERY = 64


class VllmBatchError(RuntimeError):
    """Base error for offline vLLM batch runner validation and execution failures."""


class ModelPolicyError(VllmBatchError):
    """Raised when a model violates revision pinning or trust_remote_code=False policy."""


@dataclass(frozen=True)
class _FallbackGuidedSpec:
    json: dict[str, Any]


@dataclass(frozen=True)
class _FallbackSamplingParams:
    temperature: float
    max_tokens: int
    guided_decoding: _FallbackGuidedSpec


@dataclass(frozen=True)
class _FallbackLoRARequest:
    lora_name: str
    lora_int_id: int
    lora_path: str


@dataclass
class _GeneratedItem:
    raw_content: str
    finish_reason: str | None
    prompt_tokens: int
    completion_tokens: int
    elapsed_ms: float


@dataclass(frozen=True)
class BatchRunSummary:
    """Summary returned by :func:`run_batch`."""

    total_items: int
    skipped_items: int
    processed_items: int
    retried_items: int
    model_tag: str
    output_path: Path
    first_truncated_items: int = 0


ConfigLoader = Callable[[str, str], tuple[dict[str, Any], Sequence[str] | None]]


def validate_hf_model(hf_model: str) -> str:
    """Ensure ``--hf-model`` is a non-empty model repo ID or local path."""
    if not isinstance(hf_model, str) or not hf_model.strip():
        raise ModelPolicyError("hf_model is required and must be a non-empty string")
    return hf_model.strip()


def validate_hf_revision(hf_revision: str) -> str:
    """Enforce a pinned 40-char lowercase hex commit SHA (no floating branches)."""
    if not isinstance(hf_revision, str) or REVISION_SHA_RE.fullmatch(hf_revision) is None:
        raise ModelPolicyError(
            f"hf_revision must be a 40-char lowercase hex commit SHA, got {hf_revision!r}"
        )
    return hf_revision


def validate_model_config(
    config: Mapping[str, Any],
    *,
    repo_files: Sequence[str] | None = None,
) -> list[str]:
    """Validate ``config.json`` and repo files against L7 ``trust_remote_code=False`` policy."""
    if not isinstance(config, Mapping):
        raise ModelPolicyError("model config.json must be a JSON object")

    if "auto_map" in config and config["auto_map"] is not None:
        raise ModelPolicyError(
            "refusing model with custom auto_map remote-code hook (L7 requires trust_remote_code=False)"
        )
    if config.get("custom_pipelines"):
        raise ModelPolicyError(
            "refusing model with custom_pipelines remote-code hook (L7 requires trust_remote_code=False)"
        )

    if repo_files is not None:
        modeling_files = [
            f
            for f in repo_files
            if Path(f).name.lower().startswith("modeling_") and f.lower().endswith(".py")
        ]
        if modeling_files:
            raise ModelPolicyError(
                f"refusing model with custom modeling_*.py remote-code hook(s): {modeling_files}"
            )

    architectures = config.get("architectures")
    if (
        not isinstance(architectures, list)
        or not architectures
        or not all(isinstance(arch, str) and arch in ALLOWED_ARCHITECTURES for arch in architectures)
    ):
        raise ModelPolicyError(
            f"model architectures {architectures!r} not in ALLOWED_ARCHITECTURES "
            f"{sorted(ALLOWED_ARCHITECTURES)}"
        )
    return list(architectures)


def load_model_config_and_files(
    hf_model: str,
    hf_revision: str,
) -> tuple[dict[str, Any], list[str] | None]:
    """Load ``config.json`` (and repo file listing when available) prior to weight loading."""
    model_id = validate_hf_model(hf_model)
    revision = validate_hf_revision(hf_revision)

    local_dir = Path(model_id)
    if local_dir.is_dir():
        cfg_file = local_dir / "config.json"
        if not cfg_file.is_file():
            raise ModelPolicyError(f"local model directory missing config.json: {local_dir}")
        try:
            config = json.loads(cfg_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ModelPolicyError(f"failed to read local config.json: {exc}") from exc
        repo_files = sorted(
            p.relative_to(local_dir).as_posix() for p in local_dir.rglob("*") if p.is_file()
        )
        return config, repo_files

    try:
        from huggingface_hub import hf_hub_download, list_repo_files  # type: ignore[import-not-found]
    except ImportError:
        hf_hub_download = None
        list_repo_files = None

    if hf_hub_download is not None:
        try:
            cfg_path = hf_hub_download(
                repo_id=model_id,
                filename="config.json",
                revision=revision,
            )
            config = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
            repo_files = (
                list(list_repo_files(repo_id=model_id, revision=revision))
                if list_repo_files is not None
                else None
            )
            return config, repo_files
        except Exception as exc:
            raise ModelPolicyError(
                f"failed to load config.json for {model_id}@{revision}: {exc}"
            ) from exc

    import httpx

    headers: dict[str, str] = {}
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    cfg_url = f"https://huggingface.co/{model_id}/resolve/{revision}/config.json"
    try:
        resp = httpx.get(cfg_url, headers=headers, follow_redirects=True, timeout=30.0)
        resp.raise_for_status()
        config = resp.json()
    except Exception as exc:
        raise ModelPolicyError(
            f"failed to fetch config.json from {cfg_url}: {exc}"
        ) from exc

    repo_files: list[str] | None = None
    tree_url = f"https://huggingface.co/api/models/{model_id}/revision/{revision}"
    try:
        tree_resp = httpx.get(tree_url, headers=headers, follow_redirects=True, timeout=30.0)
        if tree_resp.is_success:
            siblings = tree_resp.json().get("siblings") or []
            repo_files = [
                str(item["rfilename"])
                for item in siblings
                if isinstance(item, dict) and item.get("rfilename")
            ]
    except Exception:
        repo_files = None

    return config, repo_files


def hash_lora_adapter(lora_path: str | Path) -> str:
    """Compute a deterministic SHA-256 hex digest over all files in ``lora_path``."""
    root = Path(lora_path)
    if not root.is_dir():
        raise VllmBatchError(f"lora_path does not exist or is not a directory: {root}")
    files = sorted(
        (p for p in root.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(root).as_posix(),
    )
    if not files:
        raise VllmBatchError(f"lora_path contains no adapter files: {root}")

    digest = hashlib.sha256()
    for path in files:
        rel = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(rel)
        digest.update(b"\0")
        digest.update(str(path.stat().st_size).encode("ascii"))
        digest.update(b"\0")
        with path.open("rb") as fh:
            while chunk := fh.read(65536):
                digest.update(chunk)
    return digest.hexdigest()


def compute_model_tag(
    hf_model: str,
    hf_revision: str,
    lora_path: str | Path | None = None,
) -> str:
    """Format ``<hf_model>@<hf_revision>[+lora:<sha256[:12]>]``."""
    base = f"{hf_model}@{hf_revision}"
    if lora_path is None:
        return base
    adapter_sha = hash_lora_adapter(lora_path)
    return f"{base}+lora:{adapter_sha[:12]}"


def load_schema(schema_path: Path) -> dict[str, Any]:
    """Load the strict guided-JSON schema dict from disk."""
    if not schema_path.is_file():
        raise VllmBatchError(f"schema file does not exist: {schema_path}")
    try:
        parsed = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VllmBatchError(f"invalid schema JSON at {schema_path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise VllmBatchError(f"schema JSON root must be an object: {schema_path}")
    return parsed


def load_packet_items(input_path: Path) -> list[dict[str, Any]]:
    """Load and validate JSONL packet records from ``input_path``."""
    if not input_path.is_file():
        raise VllmBatchError(f"input packet file does not exist: {input_path}")
    raw_text = input_path.read_text(encoding="utf-8")
    if not raw_text:
        return []

    items: list[dict[str, Any]] = []
    seen_chunks: set[str] = set()
    for lineno, raw_line in enumerate(raw_text.splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            obj = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise VllmBatchError(f"input:{lineno}: invalid JSON: {exc}") from exc
        if not isinstance(obj, dict):
            raise VllmBatchError(f"input:{lineno}: expected JSON object")

        chunk_id = obj.get("chunk_id")
        prompt = obj.get("prompt")
        prompt_hash = obj.get("prompt_hash")
        if not isinstance(chunk_id, str) or not chunk_id:
            raise VllmBatchError(f"input:{lineno}: missing chunk_id")
        if chunk_id in seen_chunks:
            raise VllmBatchError(f"input:{lineno}: duplicate chunk_id {chunk_id}")
        if not isinstance(prompt, str) or not prompt:
            raise VllmBatchError(f"input:{lineno}: missing prompt for chunk {chunk_id}")
        if not isinstance(prompt_hash, str) or not prompt_hash:
            raise VllmBatchError(f"input:{lineno}: missing prompt_hash for chunk {chunk_id}")

        max_tokens = obj.get("max_tokens", DEFAULT_MAX_TOKENS)
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
            raise VllmBatchError(
                f"input:{lineno}: invalid max_tokens {max_tokens!r} for chunk {chunk_id}"
            )

        seen_chunks.add(chunk_id)
        items.append(
            {
                "chunk_id": chunk_id,
                "prompt": prompt,
                "prompt_hash": prompt_hash,
                "max_tokens": max_tokens,
            }
        )
    return items


def _load_completed_chunk_ids(
    output_path: Path,
    expected_hashes: Mapping[str, str],
) -> set[str]:
    """Read already-written valid ``chunk_id``s from ``output_path`` for crash resume."""
    if not output_path.exists():
        return set()

    raw_text = output_path.read_text(encoding="utf-8")
    if not raw_text:
        return set()

    lines = raw_text.splitlines()
    valid_lines: list[str] = []
    completed: set[str] = set()
    needs_rewrite = False

    for idx, raw_line in enumerate(lines):
        if not raw_line.strip():
            needs_rewrite = True
            continue
        is_last = idx == len(lines) - 1
        try:
            obj = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            if is_last:
                needs_rewrite = True
                break
            raise VllmBatchError(
                f"existing output corrupted at line {idx + 1}: {exc}"
            ) from exc

        if not isinstance(obj, dict):
            if is_last:
                needs_rewrite = True
                break
            raise VllmBatchError(f"existing output line {idx + 1} is not a JSON object")

        cid = obj.get("chunk_id")
        raw_content = obj.get("raw_content")
        if not isinstance(cid, str) or not cid or not isinstance(raw_content, str) or raw_content == "":
            if is_last:
                needs_rewrite = True
                break
            raise VllmBatchError(
                f"existing output line {idx + 1} missing valid chunk_id or raw_content"
            )

        if cid in expected_hashes and obj.get("prompt_hash") != expected_hashes[cid]:
            raise VllmBatchError(
                f"existing output chunk {cid} has prompt_hash {obj.get('prompt_hash')!r}, "
                f"expected {expected_hashes[cid]!r}"
            )

        valid_lines.append(raw_line)
        completed.add(cid)

    if needs_rewrite:
        with output_path.open("w", encoding="utf-8") as fh:
            if valid_lines:
                fh.write("\n".join(valid_lines) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    return completed


def build_sampling_params(
    schema: dict[str, Any],
    max_tokens: int,
    *,
    allow_fallback: bool = False,
) -> Any:
    """Build vLLM ``SamplingParams`` with guided JSON (0.8.x or structured_outputs fallback)."""
    try:
        from vllm import SamplingParams  # type: ignore[import-not-found]
    except ImportError as exc:
        if allow_fallback:
            return _FallbackSamplingParams(
                temperature=0.0,
                max_tokens=max_tokens,
                guided_decoding=_FallbackGuidedSpec(json=schema),
            )
        raise VllmBatchError(
            "vllm is not installed; install apps/brain/colab/requirements-colab.txt in Colab"
        ) from exc

    guided_cls = None
    structured_cls = None
    try:
        from vllm.sampling_params import GuidedDecodingParams  # type: ignore[import-not-found]

        guided_cls = GuidedDecodingParams
    except ImportError:
        pass
    try:
        from vllm.sampling_params import StructuredOutputsParams  # type: ignore[import-not-found]

        structured_cls = StructuredOutputsParams
    except ImportError:
        pass

    if guided_cls is not None:
        try:
            return SamplingParams(
                temperature=0.0,
                max_tokens=max_tokens,
                guided_decoding=guided_cls(json=schema),
            )
        except TypeError:
            if structured_cls is None:
                raise

    if structured_cls is not None:
        return SamplingParams(
            temperature=0.0,
            max_tokens=max_tokens,
            structured_outputs=structured_cls(json=schema),
        )

    raise VllmBatchError("vllm exposes neither GuidedDecodingParams nor StructuredOutputsParams")


def build_vllm_engine(
    *,
    hf_model: str,
    hf_revision: str,
    max_model_len: int,
    lora_path: Path | None = None,
    engine_factory: Callable[..., Any] | None = None,
) -> Any:
    """Instantiate ``vllm.LLM`` (or ``engine_factory``) with ``trust_remote_code=False``."""
    kwargs: dict[str, Any] = {
        "model": hf_model,
        "revision": hf_revision,
        "trust_remote_code": False,
        "max_model_len": max_model_len,
    }
    if lora_path is not None:
        kwargs["enable_lora"] = True

    if engine_factory is not None:
        return engine_factory(**kwargs)

    try:
        from vllm import LLM  # type: ignore[import-not-found]
    except ImportError as exc:
        raise VllmBatchError(
            "vllm is not installed; install apps/brain/colab/requirements-colab.txt in Colab"
        ) from exc
    return LLM(**kwargs)


def _build_lora_request(lora_path: Path | None, *, allow_fallback: bool) -> Any:
    if lora_path is None:
        return None
    try:
        from vllm.lora.request import LoRARequest  # type: ignore[import-not-found]

        return LoRARequest("relations_adapter", 1, str(lora_path))
    except ImportError as exc:
        if allow_fallback:
            return _FallbackLoRARequest(
                lora_name="relations_adapter",
                lora_int_id=1,
                lora_path=str(lora_path),
            )
        raise VllmBatchError("vllm.lora.request.LoRARequest is unavailable") from exc


def _extract_output(req_out: Any, elapsed_ms: float) -> _GeneratedItem:
    outputs = getattr(req_out, "outputs", None)
    if not outputs:
        raise VllmBatchError("vLLM returned request output with empty outputs list")
    first = outputs[0]

    prompt_tokens = getattr(req_out, "prompt_tokens", None)
    if prompt_tokens is None:
        prompt_token_ids = getattr(req_out, "prompt_token_ids", None)
        prompt_tokens = len(prompt_token_ids) if prompt_token_ids is not None else 0

    completion_tokens = getattr(first, "completion_tokens", None)
    if completion_tokens is None:
        token_ids = getattr(first, "token_ids", None)
        completion_tokens = len(token_ids) if token_ids is not None else 0

    return _GeneratedItem(
        raw_content=str(getattr(first, "text", "")),
        finish_reason=getattr(first, "finish_reason", None),
        prompt_tokens=int(prompt_tokens),
        completion_tokens=int(completion_tokens),
        elapsed_ms=elapsed_ms,
    )


def _generate_batch(
    llm: Any,
    prompts: list[str],
    sampling_params: list[Any],
    *,
    lora_request: Any = None,
) -> list[_GeneratedItem]:
    t0 = time.monotonic()
    if lora_request is not None:
        raw_outputs = llm.generate(prompts, sampling_params, lora_request=lora_request)
    else:
        raw_outputs = llm.generate(prompts, sampling_params)
    elapsed_ms = (time.monotonic() - t0) * 1000.0
    if len(raw_outputs) != len(prompts):
        raise VllmBatchError(
            f"vLLM returned {len(raw_outputs)} outputs for {len(prompts)} prompts"
        )
    per_item_ms = elapsed_ms / len(prompts) if prompts else 0.0
    return [_extract_output(out, per_item_ms) for out in raw_outputs]


def _unassign_colab_runtime() -> None:
    """Best-effort Colab runtime teardown when ``--unassign-on-exit`` is set."""
    try:
        from google.colab import runtime  # type: ignore[import-not-found]
    except ImportError:
        return
    try:
        runtime.unassign()
    except Exception as exc:  # pragma: no cover - defensive teardown
        print(f"warning: google.colab.runtime.unassign() failed: {exc}", file=sys.stderr)


def run_batch(
    *,
    input_path: Path,
    schema_path: Path,
    output_path: Path,
    hf_model: str,
    hf_revision: str,
    lora_path: Path | None = None,
    max_model_len: int = DEFAULT_MAX_MODEL_LEN,
    checkpoint_every: int = DEFAULT_CHECKPOINT_EVERY,
    unassign_on_exit: bool = False,
    config_loader: ConfigLoader | None = None,
    engine_factory: Callable[..., Any] | None = None,
) -> BatchRunSummary:
    """Validate policy, run guided-JSON vLLM inference with checkpointing, and tear down."""
    try:
        model_id = validate_hf_model(hf_model)
        revision = validate_hf_revision(hf_revision)
        if max_model_len <= 0:
            raise VllmBatchError(f"max_model_len must be > 0, got {max_model_len}")
        if checkpoint_every <= 0:
            raise VllmBatchError(f"checkpoint_every must be > 0, got {checkpoint_every}")

        schema = load_schema(schema_path)
        items = load_packet_items(input_path)
        model_tag = compute_model_tag(model_id, revision, lora_path)

        loader = config_loader if config_loader is not None else load_model_config_and_files
        config, repo_files = loader(model_id, revision)
        validate_model_config(config, repo_files=repo_files)

        expected_hashes = {item["chunk_id"]: item["prompt_hash"] for item in items}
        completed_ids = _load_completed_chunk_ids(output_path, expected_hashes)
        pending = [item for item in items if item["chunk_id"] not in completed_ids]
        skipped = len(items) - len(pending)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not pending:
            if not output_path.exists():
                output_path.write_text("", encoding="utf-8")
            return BatchRunSummary(
                total_items=len(items),
                skipped_items=skipped,
                processed_items=0,
                retried_items=0,
                model_tag=model_tag,
                output_path=output_path,
                first_truncated_items=0,
            )

        allow_fallback = engine_factory is not None
        llm = build_vllm_engine(
            hf_model=model_id,
            hf_revision=revision,
            max_model_len=max_model_len,
            lora_path=lora_path,
            engine_factory=engine_factory,
        )
        lora_request = _build_lora_request(lora_path, allow_fallback=allow_fallback)

        processed = 0
        retried = 0
        first_truncated = 0
        with output_path.open("a", encoding="utf-8") as fh:
            for start in range(0, len(pending), checkpoint_every):
                batch = pending[start : start + checkpoint_every]
                prompts = [item["prompt"] for item in batch]
                params_list = [
                    build_sampling_params(
                        schema,
                        item["max_tokens"],
                        allow_fallback=allow_fallback,
                    )
                    for item in batch
                ]
                results = _generate_batch(
                    llm,
                    prompts,
                    params_list,
                    lora_request=lora_request,
                )

                first_finish_reasons = [res.finish_reason for res in results]
                retry_indices = [
                    idx
                    for idx, reason in enumerate(first_finish_reasons)
                    if reason == "length"
                ]
                retry_set = set(retry_indices)
                first_truncated += len(retry_indices)
                if retry_indices:
                    retry_prompts = [batch[idx]["prompt"] for idx in retry_indices]
                    retry_params = [
                        build_sampling_params(
                            schema,
                            TRUNCATION_RETRY_MAX_TOKENS,
                            allow_fallback=allow_fallback,
                        )
                        for _ in retry_indices
                    ]
                    retry_results = _generate_batch(
                        llm,
                        retry_prompts,
                        retry_params,
                        lora_request=lora_request,
                    )
                    for orig_idx, retry_res in zip(retry_indices, retry_results, strict=True):
                        retry_res.elapsed_ms += results[orig_idx].elapsed_ms
                        results[orig_idx] = retry_res
                    retried += len(retry_indices)

                for idx, (item, res) in enumerate(zip(batch, results, strict=True)):
                    record = {
                        "chunk_id": item["chunk_id"],
                        "prompt_hash": item["prompt_hash"],
                        "model_tag": model_tag,
                        "raw_content": res.raw_content,
                        "finish_reason": res.finish_reason,
                        "first_finish_reason": first_finish_reasons[idx],
                        "retried": idx in retry_set,
                        "prompt_tokens": res.prompt_tokens,
                        "completion_tokens": res.completion_tokens,
                        "elapsed_ms": round(res.elapsed_ms, 2),
                    }
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
                processed += len(batch)

        return BatchRunSummary(
            total_items=len(items),
            skipped_items=skipped,
            processed_items=processed,
            retried_items=retried,
            model_tag=model_tag,
            output_path=output_path,
            first_truncated_items=first_truncated,
        )
    finally:
        if unassign_on_exit:
            _unassign_colab_runtime()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m colab.run_vllm_batch",
        description="Run offline vLLM guided-JSON inference over an exported relations packet.",
    )
    parser.add_argument("--input", type=Path, required=True, help="Input JSONL packet path.")
    parser.add_argument("--schema", type=Path, required=True, help="Guided JSON Schema file path.")
    parser.add_argument("--output", type=Path, required=True, help="Output JSONL results path.")
    parser.add_argument(
        "--hf-model",
        type=str,
        required=True,
        help="Hugging Face repo ID or local model directory (required; never defaulted).",
    )
    parser.add_argument(
        "--hf-revision",
        type=str,
        required=True,
        help="Pinned 40-char lowercase hex commit SHA.",
    )
    parser.add_argument(
        "--lora-path",
        type=Path,
        default=None,
        help="Optional local QLoRA adapter directory.",
    )
    parser.add_argument(
        "--max-model-len",
        type=int,
        default=DEFAULT_MAX_MODEL_LEN,
        help=f"Maximum context length passed to vLLM (default {DEFAULT_MAX_MODEL_LEN}).",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=DEFAULT_CHECKPOINT_EVERY,
        help=f"Flush + fsync output every N chunks (default {DEFAULT_CHECKPOINT_EVERY}).",
    )
    parser.add_argument(
        "--unassign-on-exit",
        action="store_true",
        help="Call google.colab.runtime.unassign() in finally block on exit.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    ns = _build_parser().parse_args(argv)
    try:
        summary = run_batch(
            input_path=ns.input,
            schema_path=ns.schema,
            output_path=ns.output,
            hf_model=ns.hf_model,
            hf_revision=ns.hf_revision,
            lora_path=ns.lora_path,
            max_model_len=ns.max_model_len,
            checkpoint_every=ns.checkpoint_every,
            unassign_on_exit=ns.unassign_on_exit,
        )
    except VllmBatchError as exc:
        print(f"run_vllm_batch error: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "total_items": summary.total_items,
                "skipped_items": summary.skipped_items,
                "processed_items": summary.processed_items,
                "retried_items": summary.retried_items,
                "first_truncated_items": summary.first_truncated_items,
                "model_tag": summary.model_tag,
                "output_path": str(summary.output_path),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
