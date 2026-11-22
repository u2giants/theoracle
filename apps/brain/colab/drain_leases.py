"""Headless pull-loop Google Colab worker for ``/colab/lease`` and ``/colab/submit`` (#664 Step 3.3).

Zero GPU libraries (``vllm``, ``torch``, ``transformers``, ``peft``, ``trl``,
``bitsandbytes``) are imported at module top level so CPU CI can import and
test this module without GPU dependencies installed.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import socket
import sys
import time
import traceback
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

import httpx

from colab.run_vllm_batch import (
    DEFAULT_MAX_MODEL_LEN,
    DEFAULT_MAX_TOKENS,
    TRUNCATION_RETRY_MAX_TOKENS,
    ConfigLoader,
    VllmBatchError,
    _build_lora_request,
    _generate_batch,
    _unassign_colab_runtime,
    build_sampling_params,
    build_vllm_engine,
    compute_model_tag,
    load_model_config_and_files,
    validate_hf_model,
    validate_hf_revision,
    validate_model_config,
)

DEFAULT_MAX_ITEMS = 64
MAX_LEASE_ITEMS = 256
DEFAULT_MAX_WALL_MINUTES = 110.0
DEFAULT_HTTP_TIMEOUT_SECONDS = 60.0

MAX_CONSECUTIVE_HTTP_ERRORS = 3
INITIAL_BACKOFF_SECONDS = 5.0
MAX_BACKOFF_SECONDS = 30.0
MAX_TOTAL_RETRY_WAIT_SECONDS = 120.0

_FORBIDDEN_TOKEN_FLAGS = ("--token", "--worker-token")
_BEARER_PATTERN = re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=:-]+", re.IGNORECASE)

logger = logging.getLogger(__name__)


class DrainWorkerError(VllmBatchError):
    """Raised when the Colab drain worker aborts due to config, auth, API, or retry cap."""


@dataclass(frozen=True)
class DrainRunSummary:
    """Summary returned by :func:`drain_leases`."""

    batches_completed: int
    chunks_submitted: int
    retried_items: int
    model_tag: str
    stop_reason: str


class TokenRedactingFilter(logging.Filter):
    """Logging filter that redacts ``Bearer <secret>`` and raw worker tokens."""

    def __init__(self, tokens: Sequence[str] = ()) -> None:
        super().__init__()
        self._tokens: set[str] = {tok for tok in tokens if tok}

    def add_token(self, token: str | None) -> None:
        if token:
            self._tokens.add(token)

    def redact(self, text: str) -> str:
        if not text:
            return text
        redacted = text
        for token in sorted(self._tokens, key=len, reverse=True):
            bearer_re = re.compile(rf"\bbearer\s+{re.escape(token)}", re.IGNORECASE)
            redacted = bearer_re.sub("Bearer [REDACTED]", redacted)
            redacted = redacted.replace(token, "[REDACTED]")
        redacted = _BEARER_PATTERN.sub("Bearer [REDACTED]", redacted)
        return redacted

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
        except Exception:
            rendered = str(record.msg)
        record.msg = self.redact(rendered)
        record.args = None

        if record.exc_info is not None:
            formatted_exc = "".join(traceback.format_exception(*record.exc_info)).rstrip("\n")
            record.exc_text = self.redact(formatted_exc)
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = self.redact(record.exc_text)
        return True


_SHARED_REDACTION_FILTER = TokenRedactingFilter()


def install_token_redaction_filter(token: str | None = None) -> TokenRedactingFilter:
    """Attach :class:`TokenRedactingFilter` to worker, ``httpx``, and root handlers."""
    _SHARED_REDACTION_FILTER.add_token(token)
    for name in ("", "colab", "colab.drain_leases", __name__, "httpx", "httpcore"):
        target_logger = logging.getLogger(name)
        if _SHARED_REDACTION_FILTER not in target_logger.filters:
            target_logger.addFilter(_SHARED_REDACTION_FILTER)
    for handler in logging.getLogger().handlers:
        if _SHARED_REDACTION_FILTER not in handler.filters:
            handler.addFilter(_SHARED_REDACTION_FILTER)
    return _SHARED_REDACTION_FILTER


install_token_redaction_filter()


def _default_worker_id() -> str:
    host = socket.gethostname() or "colab"
    raw = f"colab-{host}-{os.getpid()}"
    return raw[:128]


def _validate_api_url(api_url: str) -> str:
    cleaned = api_url.strip().rstrip("/")
    if not cleaned or not (cleaned.startswith("http://") or cleaned.startswith("https://")):
        raise DrainWorkerError(
            "BRAIN_COLAB_API_URL must be set to an http:// or https:// base URL"
        )
    return cleaned


def _validate_worker_token(worker_token: str) -> str:
    cleaned = worker_token.strip()
    if not cleaned:
        raise DrainWorkerError(
            "BRAIN_COLAB_WORKER_TOKEN is missing or empty; set env var or pass --token-stdin"
        )
    return cleaned


def _post_with_retry(
    client: httpx.Client,
    path: str,
    payload: dict[str, Any],
    *,
    max_consecutive_errors: int,
    initial_backoff_seconds: float,
    max_backoff_seconds: float,
    max_total_retry_wait_seconds: float,
    sleep_fn: Callable[[float], None],
    time_fn: Callable[[], float],
    deadline: float,
    error_state: dict[str, float | int],
) -> dict[str, Any]:
    """POST JSON to ``path`` with bounded exponential backoff capped at 3 consecutive errors."""
    while True:
        try:
            response = client.post(path, json=payload)
        except httpx.TransportError as exc:
            err_desc = _SHARED_REDACTION_FILTER.redact(f"{type(exc).__name__}: {exc}")
            retryable = True
            status_code: int | None = None
        else:
            status_code = response.status_code
            if 200 <= status_code < 300:
                error_state["consecutive_errors"] = 0
                error_state["streak_retry_wait"] = 0.0
                try:
                    data = response.json()
                except ValueError as exc:
                    raise DrainWorkerError(
                        f"POST {path} returned invalid JSON body: {exc}"
                    ) from exc
                if not isinstance(data, dict):
                    raise DrainWorkerError(f"POST {path} expected JSON object response")
                return data

            body_preview = _SHARED_REDACTION_FILTER.redact(response.text[:300])
            err_desc = f"HTTP {status_code}: {body_preview}"
            retryable = status_code == 429 or status_code >= 500

        if not retryable:
            raise DrainWorkerError(f"POST {path} failed with non-retryable {err_desc}")

        consecutive = int(error_state["consecutive_errors"]) + 1
        error_state["consecutive_errors"] = consecutive
        logger.warning(
            "POST %s transient error (%d/%d): %s",
            path,
            consecutive,
            max_consecutive_errors,
            err_desc,
        )

        if consecutive >= max_consecutive_errors:
            raise DrainWorkerError(
                f"stopping cleanly after {consecutive} consecutive HTTP/transport errors "
                f"on POST {path}: {err_desc}"
            )

        delay = min(
            max_backoff_seconds,
            initial_backoff_seconds * (2 ** (consecutive - 1)),
        )
        streak_wait = float(error_state["streak_retry_wait"])
        remaining_budget = max_total_retry_wait_seconds - streak_wait
        remaining_wall = deadline - time_fn()
        if remaining_budget <= 0 or remaining_wall <= 0:
            raise DrainWorkerError(
                f"stopping cleanly before retry on POST {path}: retry/wall budget exhausted"
            )
        actual_delay = min(delay, remaining_wall)
        if streak_wait + actual_delay >= max_total_retry_wait_seconds:
            raise DrainWorkerError(
                f"stopping cleanly on POST {path}: retry backoff would reach "
                f"{max_total_retry_wait_seconds:.0f}s limit"
            )
        error_state["streak_retry_wait"] = streak_wait + actual_delay
        sleep_fn(actual_delay)


def drain_leases(
    *,
    api_url: str,
    worker_token: str,
    hf_model: str,
    hf_revision: str,
    lora_path: Path | None = None,
    max_model_len: int = DEFAULT_MAX_MODEL_LEN,
    max_items: int = DEFAULT_MAX_ITEMS,
    worker_id: str | None = None,
    max_wall_minutes: float = DEFAULT_MAX_WALL_MINUTES,
    max_batches: int | None = None,
    config_loader: ConfigLoader | None = None,
    engine_factory: Callable[..., Any] | None = None,
    transport: httpx.BaseTransport | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    unassign_fn: Callable[[], None] | None = None,
    time_fn: Callable[[], float] | None = None,
) -> DrainRunSummary:
    """Load the vLLM model once and drain ``/colab/lease`` until empty, capped, or errored.

    Always invokes ``unassign_fn`` (default :func:`_unassign_colab_runtime`) in ``finally``.
    """
    client: httpx.Client | None = None
    teardown = unassign_fn if unassign_fn is not None else _unassign_colab_runtime
    try:
        token = _validate_worker_token(worker_token)
        install_token_redaction_filter(token)
        base_url = _validate_api_url(api_url)

        if max_items < 1 or max_items > MAX_LEASE_ITEMS:
            raise DrainWorkerError(
                f"max_items must be between 1 and {MAX_LEASE_ITEMS}, got {max_items}"
            )
        if max_wall_minutes <= 0:
            raise DrainWorkerError(f"max_wall_minutes must be > 0, got {max_wall_minutes}")
        if max_batches is not None and max_batches <= 0:
            raise DrainWorkerError(f"max_batches must be > 0, got {max_batches}")
        if max_model_len <= 0:
            raise DrainWorkerError(f"max_model_len must be > 0, got {max_model_len}")

        resolved_worker_id = (worker_id if worker_id is not None else _default_worker_id()).strip()
        if not resolved_worker_id or len(resolved_worker_id) > 128:
            raise DrainWorkerError("worker_id must be 1..128 non-whitespace characters")

        model_id = validate_hf_model(hf_model)
        revision = validate_hf_revision(hf_revision)
        loader = config_loader if config_loader is not None else load_model_config_and_files
        config, repo_files = loader(model_id, revision)
        validate_model_config(config, repo_files=repo_files)

        model_tag = f"colab-vllm/{compute_model_tag(model_id, revision, lora_path)}"
        allow_fallback = engine_factory is not None
        llm = build_vllm_engine(
            hf_model=model_id,
            hf_revision=revision,
            max_model_len=max_model_len,
            lora_path=lora_path,
            engine_factory=engine_factory,
        )
        lora_request = _build_lora_request(lora_path, allow_fallback=allow_fallback)

        clock = time_fn if time_fn is not None else time.monotonic
        sleeper = sleep_fn if sleep_fn is not None else time.sleep
        start_time = clock()
        deadline = start_time + (max_wall_minutes * 60.0)

        client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}"},
            transport=transport,
            timeout=DEFAULT_HTTP_TIMEOUT_SECONDS,
        )

        batches_completed = 0
        chunks_submitted = 0
        retried_items = 0
        stop_reason = "empty"
        error_state: dict[str, float | int] = {
            "consecutive_errors": 0,
            "streak_retry_wait": 0.0,
        }

        while True:
            if max_batches is not None and batches_completed >= max_batches:
                stop_reason = "max_batches"
                break
            if clock() >= deadline:
                stop_reason = "max_wall_minutes"
                break

            lease_data = _post_with_retry(
                client,
                "/colab/lease",
                {"worker_id": resolved_worker_id, "max_items": max_items},
                max_consecutive_errors=MAX_CONSECUTIVE_HTTP_ERRORS,
                initial_backoff_seconds=INITIAL_BACKOFF_SECONDS,
                max_backoff_seconds=MAX_BACKOFF_SECONDS,
                max_total_retry_wait_seconds=MAX_TOTAL_RETRY_WAIT_SECONDS,
                sleep_fn=sleeper,
                time_fn=clock,
                deadline=deadline,
                error_state=error_state,
            )

            items = lease_data.get("items") or []
            if not items:
                stop_reason = "empty"
                break

            lease_id = lease_data.get("lease_id")
            prompt_hash = lease_data.get("prompt_hash")
            relations_schema = lease_data.get("relations_schema")
            if not lease_id or not prompt_hash or not isinstance(relations_schema, dict):
                raise DrainWorkerError(
                    "POST /colab/lease returned items without lease_id, prompt_hash, or relations_schema"
                )

            prompts = [str(item["prompt"]) for item in items]
            params_list = [
                build_sampling_params(
                    relations_schema,
                    int(item.get("max_tokens", DEFAULT_MAX_TOKENS)),
                    allow_fallback=allow_fallback,
                )
                for item in items
            ]
            gen_results = _generate_batch(
                llm,
                prompts,
                params_list,
                lora_request=lora_request,
            )

            retry_indices = [
                idx for idx, res in enumerate(gen_results) if res.finish_reason == "length"
            ]
            if retry_indices:
                retry_prompts = [prompts[idx] for idx in retry_indices]
                retry_params = [
                    build_sampling_params(
                        relations_schema,
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
                    retry_res.elapsed_ms += gen_results[orig_idx].elapsed_ms
                    gen_results[orig_idx] = retry_res
                retried_items += len(retry_indices)

            submit_payload = {
                "lease_id": lease_id,
                "prompt_hash": prompt_hash,
                "model_tag": model_tag,
                "results": [
                    {
                        "chunk_id": item["chunk_id"],
                        "raw_content": res.raw_content,
                        "finish_reason": res.finish_reason,
                    }
                    for item, res in zip(items, gen_results, strict=True)
                ],
            }
            _post_with_retry(
                client,
                "/colab/submit",
                submit_payload,
                max_consecutive_errors=MAX_CONSECUTIVE_HTTP_ERRORS,
                initial_backoff_seconds=INITIAL_BACKOFF_SECONDS,
                max_backoff_seconds=MAX_BACKOFF_SECONDS,
                max_total_retry_wait_seconds=MAX_TOTAL_RETRY_WAIT_SECONDS,
                sleep_fn=sleeper,
                time_fn=clock,
                deadline=deadline,
                error_state=error_state,
            )

            batches_completed += 1
            chunks_submitted += len(items)

        return DrainRunSummary(
            batches_completed=batches_completed,
            chunks_submitted=chunks_submitted,
            retried_items=retried_items,
            model_tag=model_tag,
            stop_reason=stop_reason,
        )
    finally:
        if client is not None:
            client.close()
        teardown()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m colab.drain_leases",
        description=(
            "Headless pull-loop Colab worker for /colab/lease and /colab/submit. "
            "Reads BRAIN_COLAB_API_URL and BRAIN_COLAB_WORKER_TOKEN from env (or --token-stdin)."
        ),
    )
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
        "--max-items",
        type=int,
        default=DEFAULT_MAX_ITEMS,
        help=f"Maximum chunks requested per /colab/lease call (default {DEFAULT_MAX_ITEMS}).",
    )
    parser.add_argument(
        "--worker-id",
        type=str,
        default=None,
        help="Optional worker_id sent to /colab/lease.",
    )
    parser.add_argument(
        "--max-wall-minutes",
        type=float,
        default=DEFAULT_MAX_WALL_MINUTES,
        help=f"Soft wall-clock limit in minutes (default {DEFAULT_MAX_WALL_MINUTES}).",
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=None,
        help="Optional cap on number of leased batches before stopping cleanly.",
    )
    parser.add_argument(
        "--token-stdin",
        action="store_true",
        help="Read BRAIN_COLAB_WORKER_TOKEN from stdin instead of environment.",
    )
    return parser


def _reject_forbidden_cli_token_flags(
    parser: argparse.ArgumentParser,
    argv: Sequence[str] | None,
) -> None:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    for arg in raw_args:
        for flag in _FORBIDDEN_TOKEN_FLAGS:
            if arg == flag or arg.startswith(f"{flag}="):
                parser.error(
                    f"{flag} is forbidden on CLI argv (secrets appear in ps/logs); "
                    "pass BRAIN_COLAB_WORKER_TOKEN via environment or --token-stdin"
                )


def _read_worker_token_from_env_or_stdin(
    *,
    token_stdin: bool,
    stdin_stream: TextIO | None = None,
) -> str:
    if token_stdin:
        stream = stdin_stream if stdin_stream is not None else sys.stdin
        return stream.read().strip()
    return os.environ.get("BRAIN_COLAB_WORKER_TOKEN", "").strip()


def main(
    argv: Sequence[str] | None = None,
    *,
    config_loader: ConfigLoader | None = None,
    engine_factory: Callable[..., Any] | None = None,
    transport: httpx.BaseTransport | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    unassign_fn: Callable[[], None] | None = None,
    time_fn: Callable[[], float] | None = None,
    stdin_stream: TextIO | None = None,
) -> int:
    import json

    parser = _build_parser()
    _reject_forbidden_cli_token_flags(parser, argv)
    ns = parser.parse_args(argv)

    api_url = os.environ.get("BRAIN_COLAB_API_URL", "")
    worker_token = _read_worker_token_from_env_or_stdin(
        token_stdin=bool(ns.token_stdin),
        stdin_stream=stdin_stream,
    )
    install_token_redaction_filter(worker_token)

    try:
        summary = drain_leases(
            api_url=api_url,
            worker_token=worker_token,
            hf_model=ns.hf_model,
            hf_revision=ns.hf_revision,
            lora_path=ns.lora_path,
            max_model_len=ns.max_model_len,
            max_items=ns.max_items,
            worker_id=ns.worker_id,
            max_wall_minutes=ns.max_wall_minutes,
            max_batches=ns.max_batches,
            config_loader=config_loader,
            engine_factory=engine_factory,
            transport=transport,
            sleep_fn=sleep_fn,
            unassign_fn=unassign_fn,
            time_fn=time_fn,
        )
    except VllmBatchError as exc:
        redacted_msg = _SHARED_REDACTION_FILTER.redact(str(exc))
        logger.error("drain_leases failed: %s", redacted_msg)
        print(f"drain_leases error: {redacted_msg}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "batches_completed": summary.batches_completed,
                "chunks_submitted": summary.chunks_submitted,
                "retried_items": summary.retried_items,
                "model_tag": summary.model_tag,
                "stop_reason": summary.stop_reason,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
