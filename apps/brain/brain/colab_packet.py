"""Deterministic JSONL packet exporter and validated importer for Colab vLLM (#664 Step 1.1).

Exports pending ``relations`` windows from ``cmap`` into a SHA-256-manifested
JSONL packet + strict JSON Schema derived from ``relations.py``, and imports
Colab model replies through the exact same ``parse_relations_json``,
``validate_response``, ``_embed_new_mentions``, and ``_write_result`` pipeline
as ``handle_relations``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from psycopg.types.json import Json

from brain import db as db_mod
from brain.config import Settings, get_settings
from brain.contradictions import after_source_relations
from brain.embed import vector_literal
from brain.extract.flat import ENTITY_TYPES
from brain.extract.relations import (
    DROP_REASONS,
    REL_TYPES,
    STANCES,
    ChunkResult,
    KnownMention,
    NewMention,
    Relation,
    RelationsError,
    WindowEntry,
    _Counters,
    _embed_new_mentions,
    _enqueue_resolve,
    _IdentityIndex,
    _load_chunks,
    _load_done,
    _load_mentions,
    _mention_identity,
    _relation_identity,
    _resolve_interview_answer,
    build_prompt,
    known_mentions,
    parse_relations_json,
    relations_prompt_hash,
    validate_response,
    window_indices,
)
from brain.interview.conversation import source_chain_ended
from brain.read.state import clear_chunk_failure, finish_source, with_retries

PACKET_VERSION = 1
DEFAULT_PACKET_MAX_TOKENS = 2000
MODEL_TAG_RE = re.compile(r"^colab-vllm/[A-Za-z0-9._/@:+-]{3,120}$")


class ColabPacketError(RuntimeError):
    """Raised when a Colab JSONL packet, manifest, or result file fails validation."""


@dataclass(frozen=True)
class WindowSpec:
    """Server-constructed prompt window for one pending anchor chunk."""

    source_id: str
    chunk_id: str
    window: list[WindowEntry]
    known: list[KnownMention]
    prompt: str


@dataclass
class ValidatedChunkItem:
    """Validated result for one chunk prior to or after DB persistence."""

    source_id: str
    chunk_id: str
    model: str
    known: dict[str, KnownMention]
    payload: dict[str, Any]
    relations: list[Relation]
    new_mentions: list[NewMention]
    drops: dict[str, int]
    truncated: bool


@dataclass
class PacketImportSummary:
    """Aggregate outcome of ``import_relations_results``."""

    chunk_count: int
    relation_count: int
    new_mention_count: int
    truncation_count: int
    drops: dict[str, int] = field(default_factory=lambda: dict.fromkeys(DROP_REASONS, 0))
    completed_sources: list[str] = field(default_factory=list)
    items: list[ValidatedChunkItem] = field(default_factory=list)


def normalize_colab_model_tag(raw_tag: str, *, require_prefix: bool = False) -> str:
    """Validate and canonicalize a ``colab-vllm/<repo>@<rev>`` provenance string."""
    if not isinstance(raw_tag, str) or not raw_tag:
        raise ColabPacketError("model_tag must be a non-empty string")
    if raw_tag.startswith("colab-vllm/"):
        candidate = raw_tag
    elif require_prefix:
        raise ColabPacketError(f"model_tag must start with 'colab-vllm/': {raw_tag!r}")
    else:
        candidate = f"colab-vllm/{raw_tag}"
    if MODEL_TAG_RE.fullmatch(candidate) is None:
        raise ColabPacketError(f"invalid model_tag {candidate!r}")
    return candidate


def export_relations_schema() -> dict[str, Any]:
    """Return a strict JSON Schema matching ``relations.validate_response``."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["relations", "new_mentions"],
        "properties": {
            "relations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "from",
                        "to",
                        "type",
                        "description",
                        "description_en",
                        "stance",
                        "confidence",
                        "quote",
                    ],
                    "properties": {
                        "from": {"type": "string", "minLength": 1},
                        "to": {"type": "string", "minLength": 1},
                        "type": {"type": "string", "enum": list(REL_TYPES)},
                        "description": {"type": "string", "minLength": 1},
                        "description_en": {"type": "string"},
                        "stance": {"type": "string", "enum": list(STANCES)},
                        "confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                        },
                        "quote": {"type": "string", "minLength": 1},
                    },
                },
            },
            "new_mentions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["key", "type", "name", "quote"],
                    "properties": {
                        "key": {"type": "string", "minLength": 1},
                        "type": {"type": "string", "enum": list(ENTITY_TYPES.keys())},
                        "name": {"type": "string", "minLength": 1},
                        "quote": {"type": "string", "minLength": 1},
                    },
                },
            },
        },
    }


def _build_window_spec(
    source_id: str,
    source_kind: str,
    chunks: list[tuple[str, str, str | None]],
    mentions: dict[str, list[tuple[str, str, str, str]]],
    index: int,
) -> WindowSpec:
    chunk_id = chunks[index][0]
    window: list[WindowEntry] = []
    for at in window_indices(source_kind, index):
        other_id, other_text, _kind = chunks[at]
        window.append((other_id, other_text, mentions.get(other_id, [])))
    anchor_text = window[-1][1]
    known = known_mentions(window)
    previous_context = "\n\n".join(text for _cid, text, _m in window[:-1])
    prompt = build_prompt(anchor_text, known, previous_context)
    return WindowSpec(
        source_id=source_id,
        chunk_id=chunk_id,
        window=window,
        known=known,
        prompt=prompt,
    )


def load_source_windows(
    source_id: str,
    prompt_hash: str,
    *,
    only_pending: bool = True,
) -> tuple[bool, dict[str, WindowSpec], list[WindowSpec]]:
    """Return ``(has_done_rows, all_eligible_by_chunk, pending_in_order)``."""
    source_kind, chunks = _load_chunks(source_id)
    if not source_kind and not chunks:
        raise ColabPacketError(f"unknown or empty source_id: {source_id}")
    mentions = _load_mentions(source_id)
    done = _load_done(source_id, prompt_hash)
    eligible_by_id: dict[str, WindowSpec] = {}
    pending: list[WindowSpec] = []
    for index, (chunk_id, _text, passage_kind) in enumerate(chunks):
        chunk_mentions = mentions.get(chunk_id, [])
        if passage_kind == "chatter" and not chunk_mentions:
            continue
        spec = _build_window_spec(source_id, source_kind, chunks, mentions, index)
        eligible_by_id[chunk_id] = spec
        if not only_pending or chunk_id not in done:
            pending.append(spec)
    return bool(done), eligible_by_id, pending


def manifest_path_for(packet_path: str | Path) -> Path:
    """Companion manifest path ``<packet_path>.manifest.json``."""
    p = Path(packet_path)
    return p.with_name(f"{p.name}.manifest.json")


def export_relations_packet(
    source_ids: Sequence[str],
    output_path: str | Path,
    *,
    max_tokens: int = DEFAULT_PACKET_MAX_TOKENS,
) -> dict[str, Any]:
    """Export pending ``relations`` windows for ``source_ids`` to JSONL + manifest."""
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    prompt_hash = relations_prompt_hash()

    ordered_sources = list(dict.fromkeys(str(sid) for sid in source_ids))
    lines: list[str] = []
    seen_chunks: set[str] = set()
    for source_id in ordered_sources:
        _done, _eligible, pending = load_source_windows(
            source_id, prompt_hash, only_pending=True
        )
        for spec in pending:
            if spec.chunk_id in seen_chunks:
                continue
            seen_chunks.add(spec.chunk_id)
            record = {
                "packet_version": PACKET_VERSION,
                "source_id": spec.source_id,
                "chunk_id": spec.chunk_id,
                "prompt_hash": prompt_hash,
                "max_tokens": max_tokens,
                "known_keys": [item.key for item in spec.known],
                "prompt": spec.prompt,
            }
            lines.append(json.dumps(record, ensure_ascii=False, sort_keys=False))

    payload_bytes = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    out.write_bytes(payload_bytes)
    digest = hashlib.sha256(payload_bytes).hexdigest()
    manifest = {
        "packet_version": PACKET_VERSION,
        "sha256": digest,
        "item_count": len(lines),
        "prompt_hash": prompt_hash,
        "source_ids": ordered_sources,
        "relations_schema": export_relations_schema(),
    }
    mpath = manifest_path_for(out)
    mpath.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def _parse_jsonl_strict(path: Path, label: str) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ColabPacketError(f"{label} does not exist: {path}")
    raw_text = path.read_text(encoding="utf-8")
    if not raw_text:
        return []
    items: list[dict[str, Any]] = []
    for lineno, raw_line in enumerate(raw_text.splitlines(), start=1):
        if not raw_line.strip():
            raise ColabPacketError(f"{label}:{lineno}: blank JSONL line is not allowed")
        try:
            obj = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ColabPacketError(f"{label}:{lineno}: invalid or truncated JSON: {exc}") from exc
        if not isinstance(obj, dict):
            raise ColabPacketError(f"{label}:{lineno}: expected JSON object")
        items.append(obj)
    return items


def validate_chunk_submission(
    spec: WindowSpec,
    *,
    raw_content: str,
    finish_reason: str | None,
    model_full: str,
) -> ValidatedChunkItem:
    """Parse and validate one untrusted model reply against ``spec``."""
    if not isinstance(raw_content, str) or not raw_content.strip():
        raise ColabPacketError(f"empty raw_content for chunk {spec.chunk_id}")
    try:
        payload = parse_relations_json(raw_content)
    except RelationsError as exc:
        raise ColabPacketError(f"chunk {spec.chunk_id}: {exc}") from exc

    by_key = {item.key: item for item in spec.known}
    rels, new_mentions, drops = validate_response(
        [(cid, text) for cid, text, _m in spec.window],
        by_key,
        payload,
    )
    truncated = bool(
        finish_reason == "length"
        or payload.get("truncated")
        or drops.get("truncation", 0) > 0
    )
    return ValidatedChunkItem(
        source_id=spec.source_id,
        chunk_id=spec.chunk_id,
        model=model_full,
        known=by_key,
        payload=payload,
        relations=rels,
        new_mentions=new_mentions,
        drops=drops,
        truncated=truncated,
    )


def _load_identity_index_on(conn: Any, source_id: str) -> _IdentityIndex:
    """Seed the dedupe index on an open transaction connection."""
    seen: set[tuple[str, ...]] = set()
    for row in conn.execute(
        "SELECT fm.entity_type, fm.normalized_name, tm.entity_type, tm.normalized_name, "
        "r.rel_type, r.quote "
        "FROM cmap.relation r JOIN cmap.chunk c ON c.id = r.chunk_id "
        "JOIN cmap.mention fm ON fm.id = r.from_mention_id "
        "JOIN cmap.mention tm ON tm.id = r.to_mention_id "
        "WHERE c.source_id = %s",
        (source_id,),
    ).fetchall():
        seen.add(tuple(str(value) for value in row))
    for row in conn.execute(
        "SELECT m.chunk_id, m.entity_type, m.normalized_name, m.quote "
        "FROM cmap.mention m JOIN cmap.chunk c ON c.id = m.chunk_id "
        "WHERE c.source_id = %s",
        (source_id,),
    ).fetchall():
        seen.add(tuple(str(value) for value in row))
    return _IdentityIndex(seen)


def _write_result_on(
    conn: Any,
    result: ChunkResult,
    prompt_hash: str,
    model: str,
    claimed: _IdentityIndex,
) -> None:
    """Write one window's new mentions, relations, and extraction on ``conn``."""
    ids = {key: item.mention_id for key, item in result.known.items()}
    by_key: dict[str, Any] = dict(result.known)
    covered = result.covered_chunk_ids or (result.chunk_id,)
    for cid in covered:
        conn.execute(
            "DELETE FROM cmap.extraction WHERE chunk_id = %s AND stage = 'relations' "
            "AND prompt_hash <> %s",
            (cid, prompt_hash),
        )
    for mention in result.new_mentions:
        by_key[mention.key] = mention
        if claimed.claim(_mention_identity(mention)):
            row = conn.execute(
                "INSERT INTO cmap.mention "
                "(chunk_id, entity_type, surface_name, normalized_name, quote, embedding) "
                "VALUES (%s, %s, %s, %s, %s, %s::vector) RETURNING id",
                (
                    mention.quote_chunk_id,
                    mention.entity_type,
                    mention.surface_name,
                    mention.normalized_name,
                    mention.quote,
                    vector_literal(mention.vector)
                    if mention.vector is not None
                    else None,
                ),
            ).fetchone()
            ids[mention.key] = str(row[0])
        else:
            existing = conn.execute(
                "SELECT id FROM cmap.mention WHERE chunk_id = %s AND entity_type = %s "
                "AND normalized_name = %s AND quote = %s",
                (
                    mention.quote_chunk_id,
                    mention.entity_type,
                    mention.normalized_name,
                    mention.quote,
                ),
            ).fetchone()
            ids[mention.key] = str(existing[0]) if existing else None
    for relation in result.relations:
        from_id = ids.get(relation.from_key)
        to_id = ids.get(relation.to_key)
        if from_id is None or to_id is None:
            continue
        if not claimed.claim(_relation_identity(by_key, relation)):
            continue
        conn.execute(
            "INSERT INTO cmap.relation "
            "(chunk_id, from_mention_id, to_mention_id, rel_type, description, "
            "stance, confidence, quote) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                relation.quote_chunk_id,
                from_id,
                to_id,
                relation.rel_type,
                relation.description,
                relation.stance,
                relation.confidence,
                relation.quote,
            ),
        )
    for cid in covered:
        clear_chunk_failure(conn, cid, "relations")
        marker_payload = (
            result.payload
            if cid == result.chunk_id
            else {"grouped_into": result.chunk_id}
        )
        conn.execute(
            "INSERT INTO cmap.extraction (chunk_id, stage, prompt_hash, model, payload) "
            "VALUES (%s, 'relations', %s, %s, %s) "
            "ON CONFLICT (chunk_id, stage, prompt_hash) DO NOTHING",
            (cid, prompt_hash, model, Json(marker_payload)),
        )


def _record_drop_reasons_on(
    conn: Any, source_id: str, drops: dict[str, int], resuming: bool
) -> None:
    """Update ``cmap.source.read_notes->'drop_reasons'`` inside the source lock."""
    row = conn.execute(
        "SELECT read_notes FROM cmap.source WHERE id = %s", (source_id,)
    ).fetchone()
    notes = dict(row[0] or {}) if row else {}
    previous = notes.get("drop_reasons") or {}
    counts: dict[str, int] = {}
    for reason in DROP_REASONS:
        prior = int(previous.get(reason) or 0) if resuming else 0
        counts[reason] = prior + int(drops.get(reason) or 0)
    notes["drop_reasons"] = counts
    conn.execute(
        "UPDATE cmap.source SET read_notes = %s WHERE id = %s",
        (Json(notes), source_id),
    )


def persist_validated_items(
    validated_items: Sequence[ValidatedChunkItem],
    *,
    prompt_hash: str,
    settings: Settings | None = None,
) -> list[str]:
    """Embed new mentions, write ``cmap.extraction``/``mention``/``relation``, and finish completed sources."""
    cfg = settings if settings is not None else get_settings()
    counters = _Counters(cfg)
    by_source: dict[str, list[ValidatedChunkItem]] = {}
    for item in validated_items:
        by_source.setdefault(item.source_id, []).append(item)

    completed_sources: list[str] = []
    for source_id, source_items in by_source.items():
        # Compute mention embeddings BEFORE taking the source row lock so network I/O never holds FOR UPDATE.
        prepared: list[tuple[ValidatedChunkItem, ChunkResult]] = []
        source_drops = dict.fromkeys(DROP_REASONS, 0)
        for item in source_items:
            chunk_result = ChunkResult(
                chunk_id=item.chunk_id,
                known=item.known,
                payload=item.payload,
                relations=item.relations,
                new_mentions=item.new_mentions,
            )
            with_retries(
                lambda cr=chunk_result, cid=item.chunk_id: _embed_new_mentions(cr, counters),
                f"embedding new mentions of chunk {item.chunk_id}",
            )
            prepared.append((item, chunk_result))
            for reason, count in item.drops.items():
                source_drops[reason] = source_drops.get(reason, 0) + count

        with db_mod.get_pool().connection() as conn:
            conn.execute(
                "SELECT id FROM cmap.source WHERE id = %s FOR UPDATE",
                (source_id,),
            ).fetchone()
            done_rows = conn.execute(
                "SELECT e.chunk_id FROM cmap.extraction e "
                "JOIN cmap.chunk c ON c.id = e.chunk_id "
                "WHERE c.source_id = %s AND e.stage = 'relations' AND e.prompt_hash = %s",
                (source_id, prompt_hash),
            ).fetchall()
            done_before = bool(done_rows)
            if not done_before:
                conn.execute(
                    "DELETE FROM cmap.relation WHERE chunk_id IN "
                    "(SELECT id FROM cmap.chunk WHERE source_id = %s)",
                    (source_id,),
                )
            claimed = _load_identity_index_on(conn, source_id)
            for item, chunk_result in prepared:
                _write_result_on(conn, chunk_result, prompt_hash, item.model, claimed)
            _record_drop_reasons_on(conn, source_id, source_drops, resuming=done_before)
            conn.commit()

        _has_done, _eligible, remaining = load_source_windows(
            source_id, prompt_hash, only_pending=True
        )
        if not remaining:
            finish_source(source_id)
            source_chain_ended(
                source_id,
                failed=False,
                resolve=_resolve_interview_answer(source_id),
            )
            _enqueue_resolve()
            after_source_relations(source_id)
            completed_sources.append(source_id)

    return completed_sources


def import_relations_results(
    packet_path: str | Path,
    results_path: str | Path,
    *,
    dry_run: bool = False,
    settings: Settings | None = None,
) -> PacketImportSummary:
    """Verify packet manifest & results JSONL, validate quotes/types, and optionally persist."""
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

    current_hash = relations_prompt_hash()
    manifest_hash = str(manifest.get("prompt_hash") or "")
    if manifest_hash != current_hash:
        raise ColabPacketError(
            f"packet prompt_hash {manifest_hash!r} does not match current {current_hash!r}"
        )

    packet_rows = _parse_jsonl_strict(pkt, "packet")
    if len(packet_rows) != int(manifest.get("item_count", -1)):
        raise ColabPacketError(
            f"packet item_count mismatch: manifest={manifest.get('item_count')}, lines={len(packet_rows)}"
        )

    packet_by_chunk: dict[str, dict[str, Any]] = {}
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

    result_rows = _parse_jsonl_strict(res, "results")
    parsed_results: list[tuple[str, str, str | None, str]] = []
    seen_result_chunks: set[str] = set()
    for idx, row in enumerate(result_rows, start=1):
        cid = str(row.get("chunk_id") or "")
        if not cid:
            raise ColabPacketError(f"results:{idx}: missing chunk_id")
        if cid in seen_result_chunks:
            raise ColabPacketError(f"results:{idx}: duplicate chunk_id {cid}")
        if cid not in packet_by_chunk:
            raise ColabPacketError(f"results:{idx}: unknown/foreign chunk_id {cid}")
        if str(row.get("prompt_hash") or "") != current_hash:
            raise ColabPacketError(f"results:{idx}: prompt_hash mismatch for chunk {cid}")
        model_full = normalize_colab_model_tag(str(row.get("model_tag") or ""))
        raw_content = row.get("raw_content")
        if not isinstance(raw_content, str) or not raw_content.strip():
            raise ColabPacketError(f"results:{idx}: missing raw_content for chunk {cid}")
        finish_reason = (
            str(row["finish_reason"]) if row.get("finish_reason") is not None else None
        )
        seen_result_chunks.add(cid)
        parsed_results.append((cid, raw_content, finish_reason, model_full))

    # Load authoritative windows per source from DB only after all file/manifest checks pass.
    needed_sources = list(
        dict.fromkeys(str(packet_by_chunk[cid]["source_id"]) for cid, *_ in parsed_results)
    )
    windows_by_chunk: dict[str, WindowSpec] = {}
    for source_id in needed_sources:
        _done, eligible_by_id, _pending = load_source_windows(
            source_id, current_hash, only_pending=False
        )
        windows_by_chunk.update(eligible_by_id)

    summary = PacketImportSummary(chunk_count=len(parsed_results), relation_count=0, new_mention_count=0, truncation_count=0)
    for cid, raw_content, finish_reason, model_full in parsed_results:
        spec = windows_by_chunk.get(cid)
        if spec is None:
            raise ColabPacketError(f"chunk {cid} is no longer an eligible window in cmap")
        item = validate_chunk_submission(
            spec,
            raw_content=raw_content,
            finish_reason=finish_reason,
            model_full=model_full,
        )
        summary.items.append(item)
        summary.relation_count += len(item.relations)
        summary.new_mention_count += len(item.new_mentions)
        if item.truncated:
            summary.truncation_count += 1
        for reason, count in item.drops.items():
            summary.drops[reason] = summary.drops.get(reason, 0) + count

    if not dry_run and summary.items:
        summary.completed_sources = persist_validated_items(
            summary.items,
            prompt_hash=current_hash,
            settings=settings,
        )
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m brain.colab_packet")
    sub = parser.add_subparsers(dest="command", required=True)

    exp = sub.add_parser("export", help="Export pending relations prompts to JSONL + manifest.")
    exp.add_argument("--output", type=Path, required=True)
    exp.add_argument("--max-tokens", type=int, default=DEFAULT_PACKET_MAX_TOKENS)
    exp.add_argument("source_ids", nargs="+")

    sch = sub.add_parser("schema", help="Write strict guided-decoding JSON Schema.")
    sch.add_argument("--output", type=Path, required=True)

    imp = sub.add_parser("import", help="Validate and import Colab vLLM JSONL results.")
    imp.add_argument("--packet", type=Path, required=True)
    imp.add_argument("--results", type=Path, required=True)
    imp.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    ns = _build_parser().parse_args(argv)
    try:
        if ns.command == "export":
            manifest = export_relations_packet(
                ns.source_ids,
                ns.output,
                max_tokens=ns.max_tokens,
            )
            print(
                json.dumps(
                    {
                        "item_count": manifest["item_count"],
                        "sha256": manifest["sha256"],
                        "prompt_hash": manifest["prompt_hash"],
                    }
                )
            )
            return 0
        if ns.command == "schema":
            ns.output.parent.mkdir(parents=True, exist_ok=True)
            ns.output.write_text(
                json.dumps(export_relations_schema(), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            return 0
        if ns.command == "import":
            summary = import_relations_results(
                ns.packet,
                ns.results,
                dry_run=ns.dry_run,
            )
            print(
                json.dumps(
                    {
                        "chunk_count": summary.chunk_count,
                        "relation_count": summary.relation_count,
                        "new_mention_count": summary.new_mention_count,
                        "truncation_count": summary.truncation_count,
                        "drops": summary.drops,
                        "completed_sources": summary.completed_sources,
                        "dry_run": ns.dry_run,
                    }
                )
            )
            return 0
    except ColabPacketError as exc:
        print(f"colab_packet error: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
