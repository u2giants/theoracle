"""Relationship extraction with the frontier model (plan step 5).

Job ``relations`` runs per source. Every non-chatter chunk goes to the
frontier model once with ``prompts/relations.md``, together with the mentions
step 4 already found in it (so the model links known things rather than
inventing names) and the last two sentences of the previous chunk as context.
The call uses JSON mode, ``temperature=0`` and ``max_tokens=2000``; the model
id comes from the environment only.

Validation drops a relation whose quote is not an exact substring of the
chunk, whose type is outside the ontology, or whose keys do not resolve.
Accepted relations become ``cmap.relation`` rows, accepted ``new_mentions``
become ``cmap.mention`` rows, and the raw response is stored in
``cmap.extraction(stage='relations')``. Each chunk is written in its own
transaction, so a job stopped by ``BRAIN_MAX_FRONTIER_CALLS_PER_JOB`` resumes
by skipping chunks that already have a row for the current prompt hash.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from psycopg.types.json import Json

from brain.config import Settings, get_settings
from brain.db import get_pool
from brain.embed import embed_texts, vector_literal
from brain.extract.flat import (
    ENTITY_TYPES,
    OPENROUTER_BASE_URL,
    FlatError,
    parse_model_json,
)
from brain.extract.normalize import normalize_name

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "relations.md"

CONCURRENCY = 8
MAX_TOKENS = 2000
DEFAULT_MAX_FRONTIER_CALLS = 5000
INFERENCE_MAX_CONFIDENCE = 0.6
CONTEXT_SENTENCES = 2

REL_TYPES: tuple[str, ...] = (
    "PERFORMS",
    "OWNS",
    "PART_OF",
    "PRECEDES",
    "HANDS_OFF_TO",
    "DEPENDS_ON",
    "USES",
    "PRODUCES",
    "APPLIES_TO",
    "EXCEPT_WHEN",
    "CAUSES",
    "BLOCKED_BY",
    "CONTRADICTS",
    "MENTIONS",
)
STANCES: tuple[str, ...] = ("policy", "practice", "report", "inference")

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


class RelationsError(RuntimeError):
    """Raised when the relations stage cannot finish a chunk."""


@dataclass
class KnownMention:
    """One mention handed to the model under a short key."""

    key: str
    mention_id: str | None
    entity_type: str
    name: str


@dataclass
class NewMention:
    """One ``new_mentions`` item accepted for insertion."""

    key: str
    entity_type: str
    surface_name: str
    normalized_name: str
    quote: str
    vector: list[float] | None = None
    mention_id: str | None = None


@dataclass
class Relation:
    """One validated relation, keyed by prompt keys until written."""

    from_key: str
    to_key: str
    rel_type: str
    description: str
    stance: str
    confidence: float
    quote: str


@dataclass
class ChunkResult:
    """What one chunk contributed to the relations stage."""

    chunk_id: str
    known: dict[str, KnownMention]
    payload: dict[str, Any]
    relations: list[Relation] = field(default_factory=list)
    new_mentions: list[NewMention] = field(default_factory=list)


def load_relations_prompt() -> str:
    """Return the runtime prompt text (plan §8: prompts live in Markdown)."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def relations_prompt_hash() -> str:
    """Hash of the prompt file, recorded on every extraction row."""
    prompt_sha = hashlib.sha256(load_relations_prompt().encode("utf-8")).hexdigest()
    return hashlib.sha256(f"relations:{prompt_sha}".encode()).hexdigest()


def last_sentences(text: str, count: int = CONTEXT_SENTENCES) -> str:
    """Return the last ``count`` sentences of ``text``."""
    parts = [part.strip() for part in _SENTENCE_END.split(text.strip()) if part.strip()]
    return " ".join(parts[-count:])


def build_prompt(
    chunk_text: str,
    known: list[KnownMention],
    previous_context: str,
) -> str:
    """Fill ``prompts/relations.md`` for one chunk."""
    mentions_json = json.dumps(
        [{"key": item.key, "type": item.entity_type, "name": item.name} for item in known],
        ensure_ascii=False,
    )
    return (
        load_relations_prompt()
        .replace("{{mentions_json}}", mentions_json)
        .replace("{{previous_context}}", previous_context)
        .replace("{{chunk_text}}", chunk_text)
    )


def _post_chat(messages: list[dict[str, Any]], settings: Settings) -> dict[str, Any]:
    """POST one frontier chat-completions request in JSON mode."""
    if settings.openrouter_api_key is None:
        raise RelationsError("OPENROUTER_API_KEY is not set")
    if settings.brain_frontier_model is None:
        raise RelationsError("BRAIN_FRONTIER_MODEL is not set")
    response = httpx.post(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
        json={
            "model": settings.brain_frontier_model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": MAX_TOKENS,
            "response_format": {"type": "json_object"},
        },
        timeout=180.0,
    )
    if response.status_code != 200:
        raise RelationsError(
            f"frontier relations call failed: {response.status_code} {response.text[:200]}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise RelationsError("frontier relations response is not JSON") from exc


def _confidence(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return min(1.0, max(0.0, number))


def validate_response(
    chunk_text: str,
    known: dict[str, KnownMention],
    payload: dict[str, Any],
) -> tuple[list[Relation], list[NewMention]]:
    """Keep only relations and new mentions the plan's rules allow."""
    new_mentions: list[NewMention] = []
    keys = set(known)
    for item in payload.get("new_mentions") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "")
        entity_type = str(item.get("type") or "")
        name = str(item.get("name") or "").strip()
        quote = str(item.get("quote") or "")
        if not key or key in keys or entity_type not in ENTITY_TYPES or not name:
            continue
        if not quote or quote not in chunk_text:
            continue
        keys.add(key)
        new_mentions.append(
            NewMention(
                key=key,
                entity_type=entity_type,
                surface_name=name,
                normalized_name=normalize_name(name, entity_type),
                quote=quote,
            )
        )

    relations: list[Relation] = []
    for item in payload.get("relations") or []:
        if not isinstance(item, dict):
            continue
        from_key = str(item.get("from") or "")
        to_key = str(item.get("to") or "")
        rel_type = str(item.get("type") or "")
        stance = str(item.get("stance") or "")
        quote = str(item.get("quote") or "")
        description = str(item.get("description") or "").strip()
        confidence = _confidence(item.get("confidence"))
        if rel_type not in REL_TYPES or stance not in STANCES:
            continue
        if from_key not in keys or to_key not in keys or from_key == to_key:
            continue
        if not quote or quote not in chunk_text:
            continue
        if confidence is None or not description:
            continue
        if stance == "inference":
            confidence = min(confidence, INFERENCE_MAX_CONFIDENCE)
        relations.append(
            Relation(
                from_key=from_key,
                to_key=to_key,
                rel_type=rel_type,
                description=description,
                stance=stance,
                confidence=confidence,
                quote=quote,
            )
        )
    return relations, new_mentions


class _Counters:
    """Thread-safe usage counters and the per-job frontier cap (plan §11)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.lock = threading.Lock()
        self.usage: dict[str, int] = {}

    def bump(self, key: str, amount: int = 1) -> None:
        with self.lock:
            self.usage[key] = self.usage.get(key, 0) + amount

    def take_frontier_call(self) -> None:
        cap = self.settings.brain_max_frontier_calls_per_job
        if cap is None:
            cap = DEFAULT_MAX_FRONTIER_CALLS
        with self.lock:
            used = self.usage.get("frontier_calls", 0)
            if used >= cap:
                raise RelationsError(
                    f"BRAIN_MAX_FRONTIER_CALLS_PER_JOB cap of {cap} reached; "
                    "rerun the relations job to resume (finished chunks are skipped)"
                )
            self.usage["frontier_calls"] = used + 1


def _call_model(prompt: str, counters: _Counters) -> dict[str, Any]:
    """Run one relations prompt and return the parsed JSON object."""
    counters.take_frontier_call()
    body = _post_chat([{"role": "user", "content": prompt}], counters.settings)
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RelationsError("frontier relations response has no message content") from exc
    if not isinstance(content, str):
        raise RelationsError("frontier relations message content is not text")
    finish = (body.get("choices") or [{}])[0].get("finish_reason")
    if finish == "length":
        counters.bump("frontier_truncated")
    reported = body.get("usage") or {}
    for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = reported.get(name)
        if isinstance(value, int):
            counters.bump(f"frontier_{name}" if name != "total_tokens" else "frontier_tokens", value)
    return parse_relations_json(content)


def parse_relations_json(content: str) -> dict[str, Any]:
    """Parse the model's JSON object, tolerating prose, a fence or truncation.

    A response cut off at ``max_tokens`` keeps every relation and new mention
    that arrived complete; the cut-off tail is dropped.
    """
    try:
        return parse_model_json(content)
    except FlatError:
        pass
    start, end = content.find("{"), content.rfind("}")
    if 0 <= start < end:
        try:
            return parse_model_json(content[start : end + 1])
        except FlatError:
            pass
    salvaged = {
        "relations": _complete_items(content, "relations"),
        "new_mentions": _complete_items(content, "new_mentions"),
        "truncated": True,
    }
    if not salvaged["relations"] and not salvaged["new_mentions"]:
        raise RelationsError(f"relations response is not JSON: {content[:300]!r}")
    return salvaged


def _complete_items(content: str, name: str) -> list[Any]:
    """Return the complete objects of array ``name`` in possibly cut-off JSON."""
    match = re.search(rf'"{name}"\s*:\s*\[', content)
    if match is None:
        return []
    decoder = json.JSONDecoder()
    items: list[Any] = []
    index = match.end()
    while True:
        while index < len(content) and content[index] in " \t\r\n,":
            index += 1
        if index >= len(content) or content[index] != "{":
            return items
        try:
            item, index = decoder.raw_decode(content, index)
        except json.JSONDecodeError:
            return items
        items.append(item)


def _process_chunk(
    chunk_id: str,
    text: str,
    previous_text: str,
    mentions: list[tuple[str, str, str]],
    counters: _Counters,
) -> ChunkResult:
    """Ask the model for one chunk's relations and validate them."""
    known = known_mentions(text, mentions)
    prompt = build_prompt(text, known, last_sentences(previous_text))
    payload = _call_model(prompt, counters)
    by_key = {item.key: item for item in known}
    relations, new_mentions = validate_response(text, by_key, payload)
    return ChunkResult(
        chunk_id=chunk_id,
        known=by_key,
        payload=payload,
        relations=relations,
        new_mentions=new_mentions,
    )


def known_mentions(text: str, mentions: list[tuple[str, str, str]]) -> list[KnownMention]:
    """Key a chunk's mentions ``m1..mN`` in reading order, one per distinct name.

    ``mentions`` holds ``(mention_id, entity_type, surface_name)``. Order is by
    first position in the chunk, so the same chunk always yields the same keys
    (and the same prompt) across runs.
    """
    folded = text.casefold()
    seen: set[tuple[str, str]] = set()
    unique: list[tuple[int, str, str, str]] = []
    for mention_id, entity_type, surface in mentions:
        marker = (entity_type, surface.casefold())
        if marker in seen:
            continue
        seen.add(marker)
        at = folded.find(surface.casefold())
        unique.append((at if at >= 0 else len(text), entity_type, surface, mention_id))
    unique.sort()
    return [
        KnownMention(key=f"m{index}", mention_id=mention_id, entity_type=entity_type, name=surface)
        for index, (_, entity_type, surface, mention_id) in enumerate(unique, start=1)
    ]


def _load_chunks(source_id: str) -> list[tuple[str, str, str | None]]:
    """Return ``(chunk_id, text, passage_kind)`` for one source in order."""
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT id, text, passage_kind FROM cmap.chunk "
            "WHERE source_id = %s ORDER BY ordinal",
            (source_id,),
        ).fetchall()
    return [(str(row[0]), str(row[1]), row[2]) for row in rows]


def _load_mentions(source_id: str) -> dict[str, list[tuple[str, str, str]]]:
    """Return each chunk's mentions as ``(mention_id, entity_type, surface_name)``."""
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT m.chunk_id, m.id, m.entity_type, m.surface_name "
            "FROM cmap.mention m JOIN cmap.chunk c ON c.id = m.chunk_id "
            "WHERE c.source_id = %s",
            (source_id,),
        ).fetchall()
    by_chunk: dict[str, list[tuple[str, str, str]]] = {}
    for chunk_id, mention_id, entity_type, surface in rows:
        by_chunk.setdefault(str(chunk_id), []).append(
            (str(mention_id), str(entity_type), str(surface))
        )
    return by_chunk


def _load_done(source_id: str, prompt_hash: str) -> set[str]:
    """Chunks that already have a relations row for the current prompt hash."""
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT e.chunk_id FROM cmap.extraction e "
            "JOIN cmap.chunk c ON c.id = e.chunk_id "
            "WHERE c.source_id = %s AND e.stage = 'relations' AND e.prompt_hash = %s",
            (source_id, prompt_hash),
        ).fetchall()
    return {str(row[0]) for row in rows}


def _write_result(result: ChunkResult, prompt_hash: str, model: str) -> None:
    """Write one chunk's new mentions, relations and raw response together."""
    ids = {key: item.mention_id for key, item in result.known.items()}
    with get_pool().connection() as conn:
        for mention in result.new_mentions:
            row = conn.execute(
                "INSERT INTO cmap.mention "
                "(chunk_id, entity_type, surface_name, normalized_name, quote, embedding) "
                "VALUES (%s, %s, %s, %s, %s, %s::vector) RETURNING id",
                (
                    result.chunk_id,
                    mention.entity_type,
                    mention.surface_name,
                    mention.normalized_name,
                    mention.quote,
                    vector_literal(mention.vector) if mention.vector is not None else None,
                ),
            ).fetchone()
            ids[mention.key] = str(row[0])
        for relation in result.relations:
            conn.execute(
                "INSERT INTO cmap.relation "
                "(chunk_id, from_mention_id, to_mention_id, rel_type, description, "
                "stance, confidence, quote) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    result.chunk_id,
                    ids[relation.from_key],
                    ids[relation.to_key],
                    relation.rel_type,
                    relation.description,
                    relation.stance,
                    relation.confidence,
                    relation.quote,
                ),
            )
        conn.execute(
            "INSERT INTO cmap.extraction (chunk_id, stage, prompt_hash, model, payload) "
            "VALUES (%s, 'relations', %s, %s, %s) "
            "ON CONFLICT (chunk_id, stage, prompt_hash) DO NOTHING",
            (result.chunk_id, prompt_hash, model, Json(result.payload)),
        )
        conn.commit()


def _embed_new_mentions(result: ChunkResult, counters: _Counters) -> None:
    """Embed ``surface_name — quote`` for each new mention (as step 4 does)."""
    if not result.new_mentions:
        return
    texts = [f"{item.surface_name} — {item.quote}" for item in result.new_mentions]
    vectors = embed_texts(texts, counters.settings, counters.usage)
    for mention, vector in zip(result.new_mentions, vectors, strict=True):
        mention.vector = vector


def _record_usage(job_id: Any, usage: dict[str, int]) -> None:
    """Log the job's model usage into ``cmap.job.payload.usage`` (plan §11)."""
    if job_id is None or not usage:
        return
    with get_pool().connection() as conn:
        conn.execute(
            "UPDATE cmap.job SET payload = jsonb_set(payload, '{usage}', %s::jsonb) "
            "WHERE id = %s",
            (Json(usage), job_id),
        )
        conn.commit()


def handle_relations(job: dict[str, Any]) -> None:
    """Extract relations for every non-chatter chunk of one source."""
    payload = job.get("payload") or {}
    source_id = str(payload.get("source_id") or "")
    if not source_id:
        raise ValueError("relations job has no source_id")
    settings = get_settings()
    if settings.brain_frontier_model is None:
        raise RelationsError("BRAIN_FRONTIER_MODEL is not set")
    prompt_hash = relations_prompt_hash()
    chunks = _load_chunks(source_id)
    mentions = _load_mentions(source_id)
    done = _load_done(source_id, prompt_hash)
    counters = _Counters(settings)

    pending: list[tuple[str, str, str, list[tuple[str, str, str]]]] = []
    previous_text = ""
    for chunk_id, text, passage_kind in chunks:
        chunk_mentions = mentions.get(chunk_id, [])
        skip = chunk_id in done or (passage_kind == "chatter" and not chunk_mentions)
        if not skip:
            pending.append((chunk_id, text, previous_text, chunk_mentions))
        previous_text = text

    first_error: BaseException | None = None
    written = 0
    relation_count = 0
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = [pool.submit(_process_chunk, *item, counters) for item in pending]
        for future in as_completed(futures):
            try:
                result = future.result()
                _embed_new_mentions(result, counters)
                _write_result(result, prompt_hash, settings.brain_frontier_model)
            except Exception as exc:  # keep finished chunks; fail the job after
                if first_error is None:
                    first_error = exc
                continue
            written += 1
            relation_count += len(result.relations)
    _record_usage(job.get("id"), counters.usage)
    logger.info(
        "relations source=%s chunks=%d pending=%d written=%d relations=%d usage=%s",
        source_id,
        len(chunks),
        len(pending),
        written,
        relation_count,
        counters.usage,
    )
    if first_error is not None:
        raise first_error
