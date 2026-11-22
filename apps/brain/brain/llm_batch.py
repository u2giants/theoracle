"""OpenAI native Batch API client for relationship extraction (#607 step 2.4).

Submits a job's pending prompts as one ``/v1/responses`` JSONL batch on
``https://api.openai.com/v1/batches``, polls from the worker with bounded
exponential backoff (never exceeding the 30-minute standing ceiling), reconciles
results strictly by ``custom_id``, and deletes temporary batch files on exit so
no source text lingers in provider file storage.

When ``OPENAI_API_KEY`` / ``BRAIN_OPENAI_API_KEY`` is unset, callers log a
warning and fall back cleanly to the synchronous OpenRouter path.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import httpx

from brain.config import Settings, openai_api_key

logger = logging.getLogger(__name__)

OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENAI_RESPONSES_ENDPOINT = "/v1/responses"
# Standing operating rule: never design or build an automated hold, wait,
# retry delay, or timeout longer than 30 minutes (1,800 seconds).
MAX_POLL_DEADLINE_SECONDS = 1800.0
DEFAULT_POLL_DEADLINE_SECONDS = 1800.0
DEFAULT_STALL_SALVAGE_SECONDS = 180.0
DEFAULT_CANCEL_GRACE_SECONDS = 300.0
DEFAULT_INITIAL_BACKOFF_SECONDS = 2.0
DEFAULT_MAX_BACKOFF_SECONDS = 30.0
DEFAULT_HTTP_TIMEOUT_SECONDS = 60.0
FLEX_CONCURRENCY = 8

_OPENAI_PREFIXES: tuple[str, ...] = ("openai-api/", "openai/")
_VALID_REMOTE_ID = re.compile(r"^[A-Za-z0-9_-]{3,200}$")


class BatchError(RuntimeError):
    """Raised on batch protocol violations, expiry, timeout, or ID mismatches."""


class BatchExpiredError(BatchError):
    """Raised when the provider batch expires before completing."""


class BatchTimeoutError(BatchError):
    """Raised when polling reaches the <=30-minute deadline."""


@dataclass(frozen=True)
class BatchItem:
    """One prompt submitted inside a ``/v1/responses`` batch."""

    custom_id: str
    prompt: str
    max_output_tokens: int = 16000
    reasoning_effort: str | None = "medium"


@dataclass(frozen=True)
class BatchResult:
    """Reconciled outcome for one ``custom_id``."""

    custom_id: str
    status: str  # "ok" | "truncated" | "malformed" | "error"
    payload: dict[str, Any] | None
    usage: dict[str, int] = field(default_factory=dict)
    error: str | None = None


def openai_batch_key(settings: Settings) -> str | None:
    """Return the direct OpenAI API key configured for native batch calls."""
    return openai_api_key(settings)


def is_openai_batch_model(model: str | None) -> bool:
    """True when ``model`` names an OpenAI model eligible for ``/v1/batches``."""
    if not model:
        return False
    return any(model.startswith(prefix) for prefix in _OPENAI_PREFIXES)


def openai_model_name(model: str) -> str:
    """Strip ``openai/`` or ``openai-api/`` so OpenAI's API sees its bare model id."""
    for prefix in _OPENAI_PREFIXES:
        if model.startswith(prefix):
            bare = model[len(prefix) :].strip()
            if not bare:
                raise BatchError(f"empty OpenAI model identifier in {model!r}")
            return bare
    return model.strip()


def build_responses_batch_jsonl(model: str, items: Sequence[BatchItem]) -> bytes:
    """Serialize ``items`` into OpenAI ``/v1/responses`` batch JSONL bytes."""
    if not items:
        raise BatchError("cannot build an empty OpenAI batch")
    bare_model = openai_model_name(model)
    seen: set[str] = set()
    lines: list[bytes] = []
    for item in items:
        cid = (item.custom_id or "").strip()
        if not cid:
            raise BatchError("batch request item has an empty custom_id")
        if cid in seen:
            raise BatchError(f"duplicate request custom_id {cid!r}")
        seen.add(cid)
        content = item.prompt
        # OpenAI /v1/responses rejects json_object format with HTTP 400 unless
        # the literal word "json" appears in the input messages (#607 dead end).
        if "json" not in content.lower():
            content = f"{content}\n\nReturn JSON only."
        body: dict[str, Any] = {
            "model": bare_model,
            "input": [{"role": "user", "content": content}],
            "max_output_tokens": int(item.max_output_tokens),
            "text": {"format": {"type": "json_object"}},
            "store": False,
        }
        if item.reasoning_effort:
            body["reasoning"] = {"effort": item.reasoning_effort}
        record = {
            "custom_id": cid,
            "method": "POST",
            "url": OPENAI_RESPONSES_ENDPOINT,
            "body": body,
        }
        lines.append((json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"))
    return b"".join(lines)


def _extract_response_text(body: dict[str, Any]) -> str:
    """Extract assistant text from a ``/v1/responses`` (or chat) response body."""
    output = body.get("output")
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for block in item.get("content") or []:
                if isinstance(block, dict) and block.get("type") in {
                    "output_text",
                    "text",
                }:
                    parts.append(str(block.get("text") or ""))
        return "".join(parts).strip()
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        msg = first.get("message") if isinstance(first.get("message"), dict) else {}
        content = msg.get("content")
        if isinstance(content, str):
            return content.strip()
    return ""


def _extract_usage(body: dict[str, Any]) -> dict[str, int]:
    """Normalize token usage (including ``cached_tokens``) into integer counts."""
    raw = body.get("usage")
    if not isinstance(raw, dict):
        return {}
    prompt_tokens = int(raw.get("input_tokens") or raw.get("prompt_tokens") or 0)
    completion_tokens = int(
        raw.get("output_tokens") or raw.get("completion_tokens") or 0
    )
    details = (
        raw.get("input_tokens_details")
        or raw.get("prompt_tokens_details")
        or {}
    )
    cached_tokens = (
        int(details.get("cached_tokens") or 0) if isinstance(details, dict) else 0
    )
    total_tokens = int(raw.get("total_tokens") or (prompt_tokens + completion_tokens))
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cached_tokens": cached_tokens,
        "total_tokens": total_tokens,
    }


def reconcile_batch_results(
    expected_ids: Sequence[str],
    output_rows: Sequence[dict[str, Any]],
    error_rows: Sequence[dict[str, Any]] = (),
    *,
    parse: Callable[[str], dict[str, Any]],
) -> dict[str, BatchResult]:
    """Map batch JSONL output/error rows strictly onto ``expected_ids``.

    Rejects missing, duplicate, or foreign ``custom_id`` entries with
    ``BatchError`` (plan_pm_message_intake.md §9a ``test_result_id_mismatch_rejected``).
    Per-item HTTP or error-file failures become ``status='error'`` so healthy
    items in a partially failed batch are preserved while failed items retry.
    """
    expected = list(expected_ids)
    expected_set = set(expected)
    if len(expected_set) != len(expected):
        raise BatchError("expected_ids contains duplicate passage ids")

    results: dict[str, BatchResult] = {}

    def _claim_id(row: Any, source_label: str) -> str:
        if not isinstance(row, dict):
            raise BatchError(f"batch {source_label} line is not a JSON object")
        cid = row.get("custom_id")
        if not isinstance(cid, str) or not cid.strip():
            raise BatchError(f"batch {source_label} line has missing custom_id")
        if cid not in expected_set:
            raise BatchError(f"batch {source_label} contains foreign custom_id {cid!r}")
        if cid in results:
            raise BatchError(
                f"batch {source_label} contains duplicate custom_id {cid!r}"
            )
        return cid

    for row in output_rows:
        cid = _claim_id(row, "output")
        row_error = row.get("error")
        resp = row.get("response") if isinstance(row.get("response"), dict) else {}
        status_code = resp.get("status_code")
        body = resp.get("body") if isinstance(resp.get("body"), dict) else {}
        usage = _extract_usage(body)
        if row_error is not None or status_code != 200:
            err_msg = (
                str(row_error.get("message") or row_error)
                if isinstance(row_error, dict)
                else f"HTTP {status_code}"
            )
            results[cid] = BatchResult(
                custom_id=cid,
                status="error",
                payload=None,
                usage=usage,
                error=err_msg,
            )
            continue
        incomplete_reason = (
            (body.get("incomplete_details") or {}).get("reason")
            if isinstance(body.get("incomplete_details"), dict)
            else None
        )
        body_status = body.get("status")
        if (
            body_status == "incomplete"
            or incomplete_reason == "max_output_tokens"
            or (
                isinstance(body.get("choices"), list)
                and body["choices"]
                and isinstance(body["choices"][0], dict)
                and body["choices"][0].get("finish_reason") == "length"
            )
        ):
            results[cid] = BatchResult(
                custom_id=cid,
                status="truncated",
                payload=None,
                usage=usage,
                error="response incomplete (max_output_tokens)",
            )
            continue
        text = _extract_response_text(body)
        if not text:
            results[cid] = BatchResult(
                custom_id=cid,
                status="malformed",
                payload=None,
                usage=usage,
                error="empty response text",
            )
            continue
        try:
            parsed = parse(text)
        except Exception as exc:  # noqa: BLE001 - caller parser error class varies
            results[cid] = BatchResult(
                custom_id=cid,
                status="malformed",
                payload=None,
                usage=usage,
                error=str(exc),
            )
            continue
        if not isinstance(parsed, dict):
            results[cid] = BatchResult(
                custom_id=cid,
                status="malformed",
                payload=None,
                usage=usage,
                error="parsed response is not a JSON object",
            )
            continue
        results[cid] = BatchResult(
            custom_id=cid,
            status="ok",
            payload=parsed,
            usage=usage,
        )

    for row in error_rows:
        cid = _claim_id(row, "error")
        row_error = row.get("error")
        resp = row.get("response") if isinstance(row.get("response"), dict) else {}
        err_msg = (
            str(row_error.get("message") or row_error)
            if isinstance(row_error, dict)
            else f"HTTP {resp.get('status_code', 'error')}"
        )
        results[cid] = BatchResult(
            custom_id=cid,
            status="error",
            payload=None,
            usage={},
            error=err_msg,
        )

    missing = [cid for cid in expected if cid not in results]
    if missing:
        raise BatchError(
            f"batch output missing {len(missing)} requested custom_id(s): {missing[:5]}"
        )
    return results


def _validate_remote_id(value: Any, kind: str) -> str:
    if not isinstance(value, str) or not _VALID_REMOTE_ID.match(value):
        raise BatchError(f"invalid OpenAI {kind} identifier: {value!r}")
    return value


def _parse_jsonl_bytes(raw: bytes, label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(raw.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            item = json.loads(stripped)
        except ValueError as exc:
            raise BatchError(
                f"OpenAI batch {label} line {index} is not valid JSON"
            ) from exc
        if not isinstance(item, dict):
            raise BatchError(
                f"OpenAI batch {label} line {index} is not a JSON object"
            )
        rows.append(item)
    return rows


def _delete_remote_file(
    file_id: str | None, *, api_key: str, base_url: str, timeout: float
) -> None:
    if not file_id or not _VALID_REMOTE_ID.match(file_id):
        return
    try:
        httpx.delete(
            f"{base_url}/files/{file_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 - best-effort cleanup
        logger.debug("best-effort delete of batch file %s failed: %s", file_id, exc)


def _cancel_remote_batch(
    batch_id: str, *, api_key: str, base_url: str, timeout: float
) -> None:
    try:
        httpx.post(
            f"{base_url}/batches/{batch_id}/cancel",
            headers={"Authorization": f"Bearer {api_key}"},
            json={},
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 - best-effort cancellation
        logger.warning("failed to cancel timed-out batch %s: %s", batch_id, exc)


def _post_flex_response(
    model: str,
    item: BatchItem,
    *,
    api_key: str,
    base_url: str,
    parse: Callable[[str], dict[str, Any]],
    timeout: float,
) -> BatchResult:
    """Complete one stalled batch tail item via ``/v1/responses`` ``service_tier='flex'``."""
    bare_model = openai_model_name(model)
    content = item.prompt
    if "json" not in content.lower():
        content = f"{content}\n\nReturn JSON only."
    body: dict[str, Any] = {
        "model": bare_model,
        "input": [{"role": "user", "content": content}],
        "max_output_tokens": int(item.max_output_tokens),
        "text": {"format": {"type": "json_object"}},
        "service_tier": "flex",
        "store": False,
    }
    if item.reasoning_effort:
        body["reasoning"] = {"effort": item.reasoning_effort}
    resp = httpx.post(
        f"{base_url}/responses",
        headers={"Authorization": f"Bearer {api_key}"},
        json=body,
        timeout=max(timeout, 120.0),
    )
    if resp.status_code != 200:
        return BatchResult(
            custom_id=item.custom_id,
            status="error",
            payload=None,
            usage={},
            error=f"flex HTTP {resp.status_code}: {resp.text[:200]}",
        )
    try:
        data = resp.json()
    except ValueError:
        return BatchResult(
            custom_id=item.custom_id,
            status="malformed",
            payload=None,
            usage={},
            error="flex response is not JSON",
        )
    if not isinstance(data, dict):
        return BatchResult(
            custom_id=item.custom_id,
            status="malformed",
            payload=None,
            usage={},
            error="flex response is not a JSON object",
        )
    usage = _extract_usage(data)
    if data.get("status") == "incomplete":
        return BatchResult(
            custom_id=item.custom_id,
            status="truncated",
            payload=None,
            usage=usage,
            error="flex response incomplete (max_output_tokens)",
        )
    text = _extract_response_text(data)
    if not text:
        return BatchResult(
            custom_id=item.custom_id,
            status="malformed",
            payload=None,
            usage=usage,
            error="empty flex response text",
        )
    try:
        parsed = parse(text)
    except Exception as exc:  # noqa: BLE001
        return BatchResult(
            custom_id=item.custom_id,
            status="malformed",
            payload=None,
            usage=usage,
            error=str(exc),
        )
    if not isinstance(parsed, dict):
        return BatchResult(
            custom_id=item.custom_id,
            status="malformed",
            payload=None,
            usage=usage,
            error="flex parsed response is not a JSON object",
        )
    return BatchResult(
        custom_id=item.custom_id,
        status="ok",
        payload=parsed,
        usage=usage,
    )


def submit_and_wait_batch(
    model: str,
    items: Sequence[BatchItem],
    *,
    settings: Settings,
    parse: Callable[[str], dict[str, Any]],
    base_url: str = OPENAI_BASE_URL,
    poll_deadline_seconds: float = DEFAULT_POLL_DEADLINE_SECONDS,
    stall_salvage_seconds: float | None = None,
    salvage_with_flex: bool = False,
    initial_backoff_seconds: float = DEFAULT_INITIAL_BACKOFF_SECONDS,
    max_backoff_seconds: float = DEFAULT_MAX_BACKOFF_SECONDS,
    timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    sleep_fn: Callable[[float], None] = time.sleep,
    clock_fn: Callable[[], float] = time.monotonic,
) -> dict[str, BatchResult]:
    """Upload ``items`` as an OpenAI ``/v1/responses`` batch, poll, and reconcile."""
    if poll_deadline_seconds <= 0 or poll_deadline_seconds > MAX_POLL_DEADLINE_SECONDS:
        raise ValueError(
            f"poll_deadline_seconds must be in (0, {MAX_POLL_DEADLINE_SECONDS}]"
        )
    api_key = openai_batch_key(settings)
    if not api_key:
        raise BatchError("OPENAI_API_KEY is not set for OpenAI batch submission")

    jsonl_bytes = build_responses_batch_jsonl(model, items)
    expected_ids = [item.custom_id for item in items]
    item_by_id = {item.custom_id: item for item in items}
    auth_headers = {"Authorization": f"Bearer {api_key}"}

    input_file_id: str | None = None
    output_file_id: str | None = None
    error_file_id: str | None = None
    try:
        upload_resp = httpx.post(
            f"{base_url}/files",
            headers=auth_headers,
            data={"purpose": "batch"},
            files={
                "file": (
                    "oracle-relations-batch.jsonl",
                    jsonl_bytes,
                    "application/jsonl",
                )
            },
            timeout=timeout,
        )
        if upload_resp.status_code not in (200, 201):
            raise BatchError(
                f"OpenAI batch file upload failed: HTTP {upload_resp.status_code}: "
                f"{upload_resp.text[:200]}"
            )
        try:
            upload_data = upload_resp.json()
        except ValueError as exc:
            raise BatchError("OpenAI batch file upload returned non-JSON") from exc
        input_file_id = _validate_remote_id(
            upload_data.get("id") if isinstance(upload_data, dict) else None, "file"
        )

        create_resp = httpx.post(
            f"{base_url}/batches",
            headers=auth_headers,
            json={
                "input_file_id": input_file_id,
                "endpoint": OPENAI_RESPONSES_ENDPOINT,
                "completion_window": "24h",
            },
            timeout=timeout,
        )
        if create_resp.status_code not in (200, 201, 202):
            raise BatchError(
                f"OpenAI batch create failed: HTTP {create_resp.status_code}: "
                f"{create_resp.text[:200]}"
            )
        try:
            batch_data = create_resp.json()
        except ValueError as exc:
            raise BatchError("OpenAI batch create returned non-JSON") from exc
        batch_id = _validate_remote_id(
            batch_data.get("id") if isinstance(batch_data, dict) else None, "batch"
        )

        started = clock_fn()
        last_progress_at = started
        last_done_count = -1
        last_status = ""
        cancel_sent = False
        cancel_sent_at = 0.0
        salvaged_incomplete = False
        delay = max(0.01, initial_backoff_seconds)
        effective_stall = (
            stall_salvage_seconds
            if stall_salvage_seconds is not None
            else (DEFAULT_STALL_SALVAGE_SECONDS if salvage_with_flex else None)
        )

        while True:
            status_str = str(
                batch_data.get("status") if isinstance(batch_data, dict) else ""
            )
            counts = (
                batch_data.get("request_counts")
                if isinstance(batch_data, dict)
                and isinstance(batch_data.get("request_counts"), dict)
                else {}
            )
            done_count = int(counts.get("completed") or 0) + int(
                counts.get("failed") or 0
            )
            if done_count > last_done_count or (
                last_status == "validating" and status_str == "in_progress"
            ):
                last_done_count = max(last_done_count, done_count)
                last_progress_at = clock_fn()
            last_status = status_str

            if status_str == "completed":
                raw_out_id = batch_data.get("output_file_id")
                raw_err_id = batch_data.get("error_file_id")
                if raw_out_id:
                    output_file_id = _validate_remote_id(raw_out_id, "output_file")
                if raw_err_id:
                    error_file_id = _validate_remote_id(raw_err_id, "error_file")
                break
            if status_str == "expired":
                if not salvage_with_flex:
                    raise BatchExpiredError(
                        f"OpenAI batch {batch_id} expired before completing"
                    )
                salvaged_incomplete = True
                raw_out_id = batch_data.get("output_file_id")
                raw_err_id = batch_data.get("error_file_id")
                if raw_out_id:
                    output_file_id = _validate_remote_id(raw_out_id, "output_file")
                if raw_err_id:
                    error_file_id = _validate_remote_id(raw_err_id, "error_file")
                break
            if status_str == "cancelled" and cancel_sent and salvage_with_flex:
                salvaged_incomplete = True
                raw_out_id = batch_data.get("output_file_id")
                raw_err_id = batch_data.get("error_file_id")
                if raw_out_id:
                    output_file_id = _validate_remote_id(raw_out_id, "output_file")
                if raw_err_id:
                    error_file_id = _validate_remote_id(raw_err_id, "error_file")
                break
            if status_str in {"failed", "cancelled"} or (
                status_str == "cancelling" and not cancel_sent
            ):
                raise BatchError(
                    f"OpenAI batch {batch_id} ended in terminal status {status_str!r}"
                )

            now_val = clock_fn()
            if (
                cancel_sent
                and salvage_with_flex
                and status_str == "cancelling"
                and (now_val - cancel_sent_at) >= DEFAULT_CANCEL_GRACE_SECONDS
            ):
                salvaged_incomplete = True
                break
            elapsed = now_val - started
            remaining = poll_deadline_seconds - elapsed
            if (
                salvage_with_flex
                and effective_stall is not None
                and not cancel_sent
                and status_str in {"validating", "in_progress", "finalizing"}
                and (now_val - last_progress_at) >= effective_stall
            ):
                logger.info(
                    "OpenAI batch %s stalled at %d/%d for >=%.1fs; cancelling to "
                    "salvage completed items and finish tail via service_tier=flex",
                    batch_id,
                    max(0, last_done_count),
                    len(items),
                    effective_stall,
                )
                _cancel_remote_batch(
                    batch_id, api_key=api_key, base_url=base_url, timeout=timeout
                )
                cancel_sent = True
                cancel_sent_at = now_val

            if remaining <= 0:
                _cancel_remote_batch(
                    batch_id, api_key=api_key, base_url=base_url, timeout=timeout
                )
                if salvage_with_flex:
                    salvaged_incomplete = True
                    break
                raise BatchTimeoutError(
                    f"OpenAI batch {batch_id} exceeded {poll_deadline_seconds}s deadline"
                )
            sleep_fn(min(delay, remaining))
            delay = min(max_backoff_seconds, delay * 2.0)

            poll_resp = httpx.get(
                f"{base_url}/batches/{batch_id}",
                headers=auth_headers,
                timeout=timeout,
            )
            if poll_resp.status_code != 200:
                logger.warning(
                    "OpenAI batch %s poll returned HTTP %d; retrying",
                    batch_id,
                    poll_resp.status_code,
                )
                continue
            try:
                batch_data = poll_resp.json()
            except ValueError as exc:
                raise BatchError("OpenAI batch poll returned non-JSON") from exc

        output_rows: list[dict[str, Any]] = []
        if output_file_id is not None:
            out_resp = httpx.get(
                f"{base_url}/files/{output_file_id}/content",
                headers=auth_headers,
                timeout=timeout,
            )
            if out_resp.status_code != 200:
                raise BatchError(
                    f"OpenAI batch output download failed: HTTP {out_resp.status_code}"
                )
            output_rows = _parse_jsonl_bytes(out_resp.content, "output")

        error_rows: list[dict[str, Any]] = []
        if error_file_id is not None:
            err_resp = httpx.get(
                f"{base_url}/files/{error_file_id}/content",
                headers=auth_headers,
                timeout=timeout,
            )
            if err_resp.status_code != 200:
                raise BatchError(
                    f"OpenAI batch error download failed: HTTP {err_resp.status_code}"
                )
            error_rows = _parse_jsonl_bytes(err_resp.content, "error")

        if not salvaged_incomplete:
            return reconcile_batch_results(
                expected_ids, output_rows, error_rows, parse=parse
            )

        # Partial salvage: reconcile all present IDs strictly (still rejecting
        # duplicate or foreign IDs), then run missing IDs on service_tier="flex".
        present_ids: list[str] = []
        expected_set = set(expected_ids)
        for row in [*output_rows, *error_rows]:
            cid = row.get("custom_id") if isinstance(row, dict) else None
            if not isinstance(cid, str) or cid not in expected_set:
                raise BatchError(f"batch output contains foreign custom_id {cid!r}")
            present_ids.append(cid)
        if len(set(present_ids)) != len(present_ids):
            raise BatchError("batch output contains duplicate custom_id")

        partial = (
            reconcile_batch_results(
                present_ids, output_rows, error_rows, parse=parse
            )
            if present_ids
            else {}
        )
        missing_ids = [cid for cid in expected_ids if cid not in partial]
        if missing_ids:
            with ThreadPoolExecutor(
                max_workers=min(FLEX_CONCURRENCY, len(missing_ids))
            ) as pool:
                futs = [
                    pool.submit(
                        _post_flex_response,
                        model,
                        item_by_id[cid],
                        api_key=api_key,
                        base_url=base_url,
                        parse=parse,
                        timeout=timeout,
                    )
                    for cid in missing_ids
                ]
                for fut in futs:
                    res = fut.result()
                    partial[res.custom_id] = res
        return {cid: partial[cid] for cid in expected_ids}
    finally:
        for fid in (input_file_id, output_file_id, error_file_id):
            _delete_remote_file(fid, api_key=api_key, base_url=base_url, timeout=timeout)
