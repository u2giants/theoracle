"""QLoRA SFT dataset formatter with hard holdout leakage guard (#664 Step 2.1 & L5).

Builds supervised fine-tuning examples exclusively from ``#607``'s 50 tuning
threads using ``relations.build_prompt`` and ``relations.validate_response``.
Aborts with ``HoldoutLeakageError`` before writing a single byte if any record
matches the frozen held-out scoring manifest (raw ID or SHA-256 digest).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from brain.extract.normalize import normalize_name
from brain.extract.relations import KnownMention, build_prompt, validate_response


class HoldoutLeakageError(RuntimeError):
    """Raised when any held-out scoring thread or source appears in tuning input."""


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_holdout_identifiers(manifest: dict[str, Any]) -> tuple[set[str], set[str]]:
    """Return ``(raw_ids, sha256_ids)`` from a held-out scoring manifest."""
    raw_ids: set[str] = set()
    sha_ids: set[str] = set()

    for key in ("thread_keys", "source_ids", "holdout_ids"):
        for item in manifest.get(key) or []:
            val = str(item).strip()
            if val:
                raw_ids.add(val)
                sha_ids.add(_sha256_text(val))

    for key in ("thread_key_sha256s", "source_id_sha256s", "holdout_sha256s"):
        for item in manifest.get(key) or []:
            val = str(item).strip().lower()
            if val:
                sha_ids.add(val)

    for entry in manifest.get("threads") or []:
        if isinstance(entry, dict):
            for field_name in ("thread_key", "source_id", "id"):
                val = str(entry.get(field_name) or "").strip()
                if val:
                    raw_ids.add(val)
                    sha_ids.add(_sha256_text(val))
            for field_name in ("thread_key_sha256", "source_id_sha256", "sha256"):
                val = str(entry.get(field_name) or "").strip().lower()
                if val:
                    sha_ids.add(val)

    if not raw_ids and not sha_ids:
        raise ValueError("holdout manifest contains zero thread or source identifiers")
    return raw_ids, sha_ids


def assert_zero_holdout_overlap(
    records: Sequence[dict[str, Any]],
    holdout_manifest: dict[str, Any],
) -> None:
    """Verify zero records belong to the sealed held-out scoring split."""
    raw_holdouts, sha_holdouts = load_holdout_identifiers(holdout_manifest)
    for index, record in enumerate(records):
        thread_key = str(record.get("thread_key") or "").strip()
        source_id = str(record.get("source_id") or "").strip()
        if not thread_key and not source_id:
            raise HoldoutLeakageError(
                f"record {index} is missing both thread_key and source_id; cannot prove holdout isolation"
            )
        for label, identifier in (("thread_key", thread_key), ("source_id", source_id)):
            if not identifier:
                continue
            digest = _sha256_text(identifier)
            if (
                identifier in raw_holdouts
                or identifier.lower() in sha_holdouts
                or digest in sha_holdouts
            ):
                raise HoldoutLeakageError(
                    f"holdout leakage detected at record {index} ({label} sha256={digest[:16]})"
                )


def _format_one_record(record: dict[str, Any], index: int) -> tuple[dict[str, Any], bool]:
    chunk_id = str(record.get("chunk_id") or f"tuning-chunk-{index}")
    chunk_text = str(record.get("chunk_text") or "")
    if not chunk_text.strip():
        raise ValueError(f"record {index} has empty chunk_text")
    previous_context = str(record.get("previous_context") or "")

    known_list: list[KnownMention] = []
    for m_idx, raw_m in enumerate(record.get("known_mentions") or [], start=1):
        key = str(raw_m.get("key") or f"m{m_idx}")
        entity_type = str(raw_m["type"])
        surface = str(raw_m["name"])
        known_list.append(
            KnownMention(
                key=key,
                mention_id=str(raw_m.get("mention_id") or f"men-{index}-{m_idx}"),
                entity_type=entity_type,
                name=surface,
                normalized_name=normalize_name(surface, entity_type),
            )
        )

    prompt = build_prompt(chunk_text, known_list, previous_context)
    gold_payload = record.get("target") or {
        "relations": record.get("relations") or [],
        "new_mentions": record.get("new_mentions") or [],
    }

    window: list[tuple[str, str]] = []
    if previous_context:
        window.append((f"{chunk_id}-prev", previous_context))
    window.append((chunk_id, chunk_text))

    by_key = {item.key: item for item in known_list}
    valid_rels, valid_new_mentions, drops = validate_response(window, by_key, gold_payload)
    if any(drops.values()):
        raise ValueError(
            f"tuning gold record {index} ({chunk_id}) failed validate_response: {drops}"
        )

    canonical_target = {
        "relations": [
            {
                "from": rel.from_key,
                "to": rel.to_key,
                "type": rel.rel_type,
                "description": rel.description,
                "description_en": rel.description_en,
                "stance": rel.stance,
                "confidence": rel.confidence,
                "quote": rel.quote,
            }
            for rel in valid_rels
        ],
        "new_mentions": [
            {
                "key": nm.key,
                "type": nm.entity_type,
                "name": nm.surface_name,
                "quote": nm.quote,
            }
            for nm in valid_new_mentions
        ],
    }
    is_negative = not canonical_target["relations"] and not canonical_target["new_mentions"]
    sft_row = {
        "chunk_id": chunk_id,
        "messages": [
            {"role": "user", "content": prompt},
            {
                "role": "assistant",
                "content": json.dumps(canonical_target, ensure_ascii=False),
            },
        ],
    }
    return sft_row, is_negative


def build_tuning_sft_dataset(
    tuning_input_path: str | Path,
    holdout_manifest_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Validate zero holdout overlap and write formatted SFT JSONL + manifest."""
    in_path = Path(tuning_input_path)
    holdout_path = Path(holdout_manifest_path)
    out_path = Path(output_path)

    holdout_bytes = holdout_path.read_bytes()
    holdout_manifest = json.loads(holdout_bytes.decode("utf-8"))
    raw_lines = [
        line
        for line in in_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    records = [json.loads(line) for line in raw_lines]

    # Hard L5 gate BEFORE creating or touching output_path!
    assert_zero_holdout_overlap(records, holdout_manifest)

    formatted_lines: list[str] = []
    positive_count = 0
    negative_count = 0
    for idx, rec in enumerate(records):
        sft_row, is_negative = _format_one_record(rec, idx)
        if is_negative:
            negative_count += 1
        else:
            positive_count += 1
        formatted_lines.append(json.dumps(sft_row, ensure_ascii=False))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_bytes = ("\n".join(formatted_lines) + ("\n" if formatted_lines else "")).encode("utf-8")
    out_path.write_bytes(out_bytes)

    manifest = {
        "example_count": len(formatted_lines),
        "positive_windows": positive_count,
        "negative_windows": negative_count,
        "sft_sha256": hashlib.sha256(out_bytes).hexdigest(),
        "holdout_manifest_sha256": hashlib.sha256(holdout_bytes).hexdigest(),
    }
    manifest_out = out_path.with_name(f"{out_path.name}.manifest.json")
    manifest_out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m colab.build_tuning_sft")
    parser.add_argument("--tuning-input", type=Path, required=True)
    parser.add_argument("--holdout-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    ns = _build_parser().parse_args(argv)
    summary = build_tuning_sft_dataset(ns.tuning_input, ns.holdout_manifest, ns.output)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
