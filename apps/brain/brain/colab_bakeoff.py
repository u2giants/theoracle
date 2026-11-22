"""Bridge between Colab JSONL packets/results (#664) and ``brain.intake.bakeoff`` (#607).

Converts ``colab_packet`` + ``run_vllm_batch`` outputs into ``PassageAttempt``
records for ``brain.intake.bakeoff.score_candidate`` / ``select_winner`` with:
- strict packet manifest SHA-256 and ``prompt_hash`` verification before parsing;
- exact preservation of first-attempt vs post-4000-retry truncation status
  (``first_finish_reason == 'length'`` -> ``first_status = 'truncated'``);
- zero database writes and zero raw text emitted in aggregate summaries; and
- Colab compute-unit economics (``ccu_per_1000_passages``) alongside ``$0.00``
  marginal API spend.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from brain.colab_packet import (
    PACKET_VERSION,
    ColabPacketError,
    WindowSpec,
    _parse_jsonl_strict,
    load_source_windows,
    manifest_path_for,
    normalize_colab_model_tag,
)
from brain.extract.relations import (
    RelationsError,
    parse_relations_json,
    relations_prompt_hash,
)
from brain.intake.bakeoff import PassageAttempt

# Keep in sync with apps/brain/colab/preflight.py without importing colab.* from brain.*.
COLAB_CCU_PER_HOUR: dict[str, float] = {
    "CPU": 0.2,
    "T4": 1.2,
    "L4": 2.0,
    "G4": 4.0,
    "A100": 15.0,
    "H100": 35.0,
}


@dataclass(frozen=True)
class ColabBakeoffConversion:
    """Converted ``PassageAttempt`` list and aggregate telemetry (zero source text)."""

    model_tag: str
    prompt_hash: str
    packet_sha256: str
    attempts: tuple[PassageAttempt, ...]
    total_elapsed_ms: float
    ccu_spent_estimate: float
    ccu_per_1000_passages: float


def compute_ccu_economics(
    *,
    gpu_tier: str,
    wall_seconds: float,
    passage_count: int,
) -> tuple[float, float]:
    """Return ``(ccu_spent, ccu_per_1000_passages)`` for ``gpu_tier`` and ``wall_seconds``."""
    tier = gpu_tier.upper()
    if tier not in COLAB_CCU_PER_HOUR:
        allowed = ", ".join(sorted(COLAB_CCU_PER_HOUR))
        raise ValueError(f"unsupported gpu_tier {gpu_tier!r}; allowed: {allowed}")
    if wall_seconds < 0:
        raise ValueError("wall_seconds must be >= 0")
    if passage_count < 0:
        raise ValueError("passage_count must be >= 0")
    ccu_spent = COLAB_CCU_PER_HOUR[tier] * (wall_seconds / 3600.0)
    per_1000 = (ccu_spent * 1000.0 / passage_count) if passage_count > 0 else 0.0
    return round(ccu_spent, 6), round(per_1000, 4)


def build_bakeoff_attempts_from_colab(
    packet_path: str | Path,
    results_path: str | Path,
    *,
    gpu_tier: str = "A100",
    wall_seconds: float | None = None,
    windows_by_chunk: Mapping[str, WindowSpec] | None = None,
    thread_id_by_source: Mapping[str, str] | None = None,
    expected_prompt_hash: str | None = None,
) -> ColabBakeoffConversion:
    """Convert verified Colab JSONL outputs into ``PassageAttempt`` records for ``score_candidate``."""
    pkt = Path(packet_path)
    res = Path(results_path)
    mpath = manifest_path_for(pkt)
    if not pkt.is_file():
        raise ColabPacketError(f"packet file does not exist: {pkt}")
    if not mpath.is_file():
        raise ColabPacketError(f"packet manifest does not exist: {mpath}")

    try:
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ColabPacketError(f"invalid manifest JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ColabPacketError("manifest root must be a JSON object")

    actual_sha = hashlib.sha256(pkt.read_bytes()).hexdigest()
    expected_sha = str(manifest.get("sha256") or "")
    if actual_sha != expected_sha:
        raise ColabPacketError(
            f"packet manifest sha256 mismatch: expected {expected_sha}, got {actual_sha}"
        )

    current_hash = expected_prompt_hash or relations_prompt_hash()
    manifest_hash = str(manifest.get("prompt_hash") or "")
    if manifest_hash != current_hash:
        raise ColabPacketError(
            f"packet prompt_hash {manifest_hash!r} does not match expected {current_hash!r}"
        )

    packet_rows = _parse_jsonl_strict(pkt, "packet")
    if len(packet_rows) != int(manifest.get("item_count", -1)):
        raise ColabPacketError(
            f"packet item_count mismatch: manifest={manifest.get('item_count')}, lines={len(packet_rows)}"
        )

    packet_by_chunk: dict[str, dict[str, Any]] = {}
    passage_ord_by_source: dict[str, int] = {}
    passage_index_by_chunk: dict[str, int] = {}
    for idx, row in enumerate(packet_rows, start=1):
        if row.get("packet_version") != PACKET_VERSION:
            raise ColabPacketError(f"packet:{idx}: unsupported packet_version {row.get('packet_version')!r}")
        cid = str(row.get("chunk_id") or "")
        sid = str(row.get("source_id") or "")
        ph = str(row.get("prompt_hash") or "")
        if not cid or not sid:
            raise ColabPacketError(f"packet:{idx}: missing chunk_id or source_id")
        if ph != current_hash:
            raise ColabPacketError(f"packet:{idx}: prompt_hash mismatch")
        if cid in packet_by_chunk:
            raise ColabPacketError(f"packet:{idx}: duplicate chunk_id {cid}")
        packet_by_chunk[cid] = row
        ord_idx = passage_ord_by_source.get(sid, 0)
        passage_index_by_chunk[cid] = ord_idx
        passage_ord_by_source[sid] = ord_idx + 1

    result_rows = _parse_jsonl_strict(res, "results")
    result_by_chunk: dict[str, dict[str, Any]] = {}
    canonical_models: set[str] = set()
    for idx, row in enumerate(result_rows, start=1):
        cid = str(row.get("chunk_id") or "")
        if not cid:
            raise ColabPacketError(f"results:{idx}: missing chunk_id")
        if cid in result_by_chunk:
            raise ColabPacketError(f"results:{idx}: duplicate chunk_id {cid}")
        if cid not in packet_by_chunk:
            raise ColabPacketError(f"results:{idx}: unknown/foreign chunk_id {cid}")
        if str(row.get("prompt_hash") or "") != current_hash:
            raise ColabPacketError(f"results:{idx}: prompt_hash mismatch for chunk {cid}")
        canonical_models.add(normalize_colab_model_tag(str(row.get("model_tag") or "")))
        result_by_chunk[cid] = row

    missing_chunks = [cid for cid in packet_by_chunk if cid not in result_by_chunk]
    if missing_chunks:
        raise ColabPacketError(
            f"results missing {len(missing_chunks)} packet chunk(s), e.g. {missing_chunks[0]}"
        )
    if len(canonical_models) > 1:
        raise ColabPacketError(f"mixed model_tag values in single bakeoff file: {sorted(canonical_models)}")
    model_tag = next(iter(canonical_models), "colab-vllm/empty")

    resolved_windows: dict[str, WindowSpec] = {}
    if windows_by_chunk is not None:
        resolved_windows.update(windows_by_chunk)
    else:
        needed_sources = list(
            dict.fromkeys(str(r["source_id"]) for r in packet_rows)
        )
        for source_id in needed_sources:
            _done, eligible_by_id, _pending = load_source_windows(
                source_id, current_hash, only_pending=False
            )
            resolved_windows.update(eligible_by_id)

    attempts: list[PassageAttempt] = []
    total_elapsed_ms = 0.0

    for cid, pkt_row in packet_by_chunk.items():
        spec = resolved_windows.get(cid)
        if spec is None:
            raise ColabPacketError(f"chunk {cid} missing from windows_by_chunk")
        res_row = result_by_chunk[cid]
        source_id = str(pkt_row["source_id"])
        thread_id = (
            str(thread_id_by_source[source_id])
            if thread_id_by_source is not None and source_id in thread_id_by_source
            else source_id
        )

        raw_content = res_row.get("raw_content")
        final_finish = (
            str(res_row["finish_reason"])
            if res_row.get("finish_reason") is not None
            else None
        )
        first_finish = (
            str(res_row["first_finish_reason"])
            if res_row.get("first_finish_reason") is not None
            else final_finish
        )
        retried = bool(res_row.get("retried", False))
        elapsed_ms = float(res_row.get("elapsed_ms") or 0.0)
        total_elapsed_ms += max(0.0, elapsed_ms)

        parsed_payload: dict[str, Any] | None = None
        malformed = False
        if not isinstance(raw_content, str) or not raw_content.strip():
            malformed = True
        else:
            try:
                parsed_payload = parse_relations_json(raw_content)
            except RelationsError:
                malformed = True

        payload_truncated = bool(parsed_payload and parsed_payload.get("truncated"))

        if first_finish == "length":
            first_status = "truncated"
        elif not retried and malformed:
            first_status = "malformed"
        else:
            first_status = "ok"

        if final_finish == "length" or payload_truncated:
            final_status = "truncated"
        elif malformed or parsed_payload is None:
            final_status = "malformed"
        else:
            final_status = "ok"

        attempts.append(
            PassageAttempt(
                thread_id=thread_id,
                passage_index=passage_index_by_chunk[cid],
                window=tuple((w_cid, w_text) for w_cid, w_text, _m in spec.window),
                known_mentions=tuple(spec.known),
                first_status=first_status,
                final_status=final_status,
                payload=parsed_payload if final_status == "ok" else None,
                cost_usd=0.0,
            )
        )

    measured_seconds = (
        wall_seconds if wall_seconds is not None else (total_elapsed_ms / 1000.0)
    )
    ccu_spent, ccu_per_1000 = compute_ccu_economics(
        gpu_tier=gpu_tier,
        wall_seconds=measured_seconds,
        passage_count=len(attempts),
    )

    return ColabBakeoffConversion(
        model_tag=model_tag,
        prompt_hash=current_hash,
        packet_sha256=actual_sha,
        attempts=tuple(attempts),
        total_elapsed_ms=round(total_elapsed_ms, 2),
        ccu_spent_estimate=ccu_spent,
        ccu_per_1000_passages=ccu_per_1000,
    )
