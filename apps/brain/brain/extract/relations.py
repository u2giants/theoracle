"""Relationship extraction with the frontier model (plan step 5).

Job ``relations`` runs per source. Every non-chatter chunk goes to the
frontier model once with ``prompts/relations.md``, together with the mentions
step 4 already found in the window (so the model links known things rather
than inventing names) and the previous one or two passages **in full** as
quotable context (plan E1: a relation may span neighbouring passages — the
question and its reply, or two sides of a page break). The call uses JSON
mode, ``temperature=0`` and ``max_tokens=8000``; a reply still cut off at that
limit is retried once at ``max_tokens=16000`` (issue #365: dense chunks
truncated at 2,000). The model id comes from the environment only.

Validation drops a relation whose quote is not in the window (whitespace and
quote-mark normalised matching is tried first), whose type is outside the
ontology, or whose keys do not resolve. Accepted relations become
``cmap.relation`` rows with the quote's true chunk id (not the window's
anchor), accepted ``new_mentions`` become ``cmap.mention`` rows, and the raw
response is stored in ``cmap.extraction(stage='relations')``. Relations and
mentions found by two overlapping windows are stored once. Dropped items are
counted per source under ``cmap.source.read_notes->'drop_reasons'``. Each
anchor chunk is written in its own transaction, so a job stopped by
``BRAIN_MAX_FRONTIER_CALLS_PER_JOB`` resumes by skipping chunks that already
have a row for the current prompt hash.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from psycopg.types.json import Json

from brain.config import Settings, get_settings
from brain.db import get_pool
from brain.embed import embed_texts, vector_literal
from brain.extract.flat import ENTITY_TYPES
from brain.extract.normalize import normalize_name
from brain.llm import post_chat_with_rescue
from brain.read import pdf as pdf_read
from brain.read import state as read_state
from brain.read import transcript as transcript_read
from brain.read.state import (
    clear_chunk_failure,
    finish_source,
    record_chunk_failure,
    with_retries,
)
from brain.seats import stage_model

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "relations.md"

CONCURRENCY = 8
MAX_TOKENS = 8000
# One retry with this budget when a reply stops at MAX_TOKENS (issue #365).
TRUNCATION_RETRY_MAX_TOKENS = 16000
DEFAULT_MAX_FRONTIER_CALLS = 5000
INFERENCE_MAX_CONFIDENCE = 0.6
CALL_ATTEMPTS = 3
# Plan E1: the window is the anchor passage plus this many previous passages
# in full. Measured on the frozen fixture corpus (see the E1 PR): a window of
# two passages found every cross-boundary relation the corpus holds (a
# question/answer pair, a page-break pair) and a third passage added none, so
# the smaller window wins. Transcript windows are exchange pairs regardless
# (transcript_read.exchange_windows).
WINDOW_PREVIOUS = 1
# Drop reasons counted per source in ``read_notes`` (plan E1).
DROP_REASONS: tuple[str, ...] = ("quote_mismatch", "unknown_type", "truncation")
# Issue #415: hold the resolve→project→communities chain until sources stop
# arriving, so one burst pays for one chain run.
DEBOUNCE_SECONDS = 300.0
MAX_DELAY_SECONDS = 900.0

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

_QUOTE_FOLD = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\uff02": '"',
    }
)


class RelationsError(RuntimeError):
    """Raised when the relations stage cannot finish a chunk."""


class FrontierCapReached(RelationsError):
    """Raised when ``BRAIN_MAX_FRONTIER_CALLS_PER_JOB`` is used up."""


@dataclass
class KnownMention:
    """One mention handed to the model under a short key."""

    key: str
    mention_id: str | None
    entity_type: str
    name: str
    normalized_name: str


@dataclass
class NewMention:
    """One ``new_mentions`` item accepted for insertion."""

    key: str
    entity_type: str
    surface_name: str
    normalized_name: str
    quote: str
    quote_chunk_id: str = ""
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
    quote_chunk_id: str = ""
    description_en: str = ""


@dataclass
class ChunkResult:
    """What one window contributed to the relations stage."""

    chunk_id: str
    known: dict[str, KnownMention]
    payload: dict[str, Any]
    relations: list[Relation] = field(default_factory=list)
    new_mentions: list[NewMention] = field(default_factory=list)


# One entry of a window: ``(chunk_id, text, mentions)`` in reading order; the
# anchor chunk is last. ``mentions`` holds
# ``(mention_id, entity_type, surface_name, normalized_name)``.
WindowEntry = tuple[str, str, list[tuple[str, str, str, str]]]


def load_relations_prompt() -> str:
    """Return the runtime prompt text (plan §8: prompts live in Markdown)."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def relations_prompt_hash() -> str:
    """Hash of the prompt file, recorded on every extraction row."""
    prompt_sha = hashlib.sha256(load_relations_prompt().encode("utf-8")).hexdigest()
    return hashlib.sha256(f"relations:{prompt_sha}".encode()).hexdigest()


def window_indices(source_kind: str, anchor: int) -> tuple[int, ...]:
    """Indices (ascending) of the passages in ``anchor``'s window (plan E1).

    Transcripts window consecutive speaker turns of one exchange (question +
    reply), overlapping by one turn. Every other source windows the anchor
    plus the previous ``WINDOW_PREVIOUS`` passages in full; for PDFs the
    window may span a page break (the page chunks come from ``read_pdf``).
    """
    if source_kind == "transcript":
        return transcript_read.exchange_windows(anchor)
    return pdf_read.passage_windows(anchor, WINDOW_PREVIOUS)


def build_prompt(
    chunk_text: str,
    known: list[KnownMention],
    previous_context: str,
) -> str:
    """Fill ``prompts/relations.md`` for one window's anchor passage."""
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


def _post_chat(
    messages: list[dict[str, Any]], settings: Settings, max_tokens: int = MAX_TOKENS
) -> dict[str, Any]:
    """POST one frontier chat-completions request in JSON mode."""
    model = stage_model(settings, "relations")
    if model is None:
        raise RelationsError("BRAIN_FRONTIER_MODEL is not set")
    return post_chat_with_rescue(
        {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        },
        settings=settings,
        timeout=180.0,
        error_cls=RelationsError,
        label="frontier relations",
    )


def _confidence(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return min(1.0, max(0.0, number))


def _normalize_quote(text: str) -> str:
    """Fold whitespace runs and curly quote marks before quote matching."""
    return re.sub(r"\s+", " ", text.translate(_QUOTE_FOLD)).strip()


def find_quote(
    window: list[tuple[str, str]], quote: str
) -> str | None:
    """Return the id of the chunk holding ``quote``, or None if it is absent.

    An exact substring match is tried first; whitespace/quote-mark-normalised
    matching is tried before declaring a mismatch (plan E1). A quote that only
    matches the joined window (it straddles a chunk boundary) is attributed to
    the chunk where it starts.
    """
    if not quote:
        return None
    for chunk_id, text in window:
        if quote in text:
            return chunk_id
    normalized = _normalize_quote(quote)
    if not normalized:
        return None
    parts = [(chunk_id, _normalize_quote(text)) for chunk_id, text in window]
    for chunk_id, text in parts:
        if normalized in text:
            return chunk_id
    joined = " ".join(text for _chunk_id, text in parts)
    at = joined.find(normalized)
    if at < 0:
        return None
    cursor = 0
    for chunk_id, text in parts:
        if at < cursor + len(text):
            return chunk_id
        cursor += len(text) + 1
    return window[-1][0]


def validate_response(
    window: list[tuple[str, str]],
    known: dict[str, KnownMention],
    payload: dict[str, Any],
) -> tuple[list[Relation], list[NewMention], dict[str, int]]:
    """Keep only relations and new mentions the plan's rules allow.

    ``window`` is ``(chunk_id, text)`` in reading order. A dropped item is
    counted under one reason: ``unknown_type`` (outside the ontology),
    ``truncation`` (a required field is missing — the signature of a reply cut
    off mid-item) or ``quote_mismatch`` (the quote is not in the window).
    """
    drops = dict.fromkeys(DROP_REASONS, 0)
    new_mentions: list[NewMention] = []
    keys = set(known)
    for item in payload.get("new_mentions") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "")
        entity_type = str(item.get("type") or "")
        name = str(item.get("name") or "").strip()
        quote = str(item.get("quote") or "")
        if not key or key in keys:
            continue
        if entity_type not in ENTITY_TYPES:
            drops["unknown_type"] += 1
            continue
        if not name or not quote:
            drops["truncation"] += 1
            continue
        quote_chunk = find_quote(window, quote)
        if quote_chunk is None:
            drops["quote_mismatch"] += 1
            continue
        keys.add(key)
        new_mentions.append(
            NewMention(
                key=key,
                entity_type=entity_type,
                surface_name=name,
                normalized_name=normalize_name(name, entity_type),
                quote=quote,
                quote_chunk_id=quote_chunk,
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
        description_en = str(item.get("description_en") or "").strip()
        confidence = _confidence(item.get("confidence"))
        if rel_type not in REL_TYPES or stance not in STANCES:
            drops["unknown_type"] += 1
            continue
        if from_key not in keys or to_key not in keys or from_key == to_key:
            continue
        if not quote or confidence is None or not description:
            drops["truncation"] += 1
            continue
        quote_chunk = find_quote(window, quote)
        if quote_chunk is None:
            drops["quote_mismatch"] += 1
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
                quote_chunk_id=quote_chunk,
                description_en=description_en,
            )
        )
    return relations, new_mentions, drops


class _Counters:
    """Thread-safe usage counters and the per-job frontier cap (plan §11)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.lock = threading.Lock()
        self.usage: dict[str, int] = {}
        self.drops: dict[str, int] = dict.fromkeys(DROP_REASONS, 0)

    def bump(self, key: str, amount: int = 1) -> None:
        with self.lock:
            self.usage[key] = self.usage.get(key, 0) + amount

    def drop(self, reason: str, amount: int = 1) -> None:
        with self.lock:
            self.drops[reason] = self.drops.get(reason, 0) + amount

    def take_frontier_call(self) -> None:
        cap = self.settings.brain_max_frontier_calls_per_job
        if cap is None:
            cap = DEFAULT_MAX_FRONTIER_CALLS
        with self.lock:
            used = self.usage.get("frontier_calls", 0)
            if used >= cap:
                raise FrontierCapReached(
                    f"BRAIN_MAX_FRONTIER_CALLS_PER_JOB cap of {cap} reached; "
                    "rerun the relations job to resume (finished chunks are skipped)"
                )
            self.usage["frontier_calls"] = used + 1


class _IdentityIndex:
    """Identities already written, so overlapping windows never duplicate.

    Seeded from the database at job start (a resumed job must not re-find what
    an earlier run stored) and then claimed under a lock per write.
    """

    def __init__(self, seen: set[tuple]) -> None:
        self._lock = threading.Lock()
        self._seen = seen

    def claim(self, identity: tuple) -> bool:
        with self._lock:
            if identity in self._seen:
                return False
            self._seen.add(identity)
            return True


def _call_model(prompt: str, counters: _Counters) -> dict[str, Any]:
    """Run one relations prompt and return the parsed JSON object."""
    messages = [{"role": "user", "content": prompt}]
    counters.take_frontier_call()
    body = _post_chat(messages, counters.settings)
    if _finish_reason(body) == "length":
        # Dense chunks can need more than MAX_TOKENS; retry once with a larger
        # budget before falling back to item-wise salvage (issue #365).
        counters.bump("frontier_truncation_retries")
        counters.take_frontier_call()
        _bump_usage(body, counters)
        body = _post_chat(messages, counters.settings, TRUNCATION_RETRY_MAX_TOKENS)
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RelationsError("frontier relations response has no message content") from exc
    if isinstance(content, list):
        # Some providers return content as a list of text blocks.
        content = "".join(
            str(part.get("text", "")) for part in content if isinstance(part, dict)
        )
    if not isinstance(content, str) or not content:
        raise RelationsError("frontier relations message content is not text")
    if _finish_reason(body) == "length":
        counters.bump("frontier_truncated")
    _bump_usage(body, counters)
    return parse_relations_json(content)


def _finish_reason(body: dict[str, Any]) -> Any:
    choices = body.get("choices") or [{}]
    first = choices[0] if isinstance(choices[0], dict) else {}
    return first.get("finish_reason")


def _bump_usage(body: dict[str, Any], counters: _Counters) -> None:
    reported = body.get("usage") or {}
    for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = reported.get(name)
        if isinstance(value, int):
            counters.bump(f"frontier_{name}" if name != "total_tokens" else "frontier_tokens", value)


def parse_relations_json(content: str) -> dict[str, Any]:
    """Parse the model's JSON object, tolerating prose, a fence or truncation.

    A response cut off at ``max_tokens`` keeps every relation and new mention
    that arrived complete; the cut-off tail is dropped.
    """
    start, end = content.find("{"), content.rfind("}")
    if 0 <= start < end:
        try:
            # strict=False: quotes copied from spreadsheets carry raw tabs.
            value = json.loads(content[start : end + 1], strict=False)
        except json.JSONDecodeError:
            value = None
        if isinstance(value, dict):
            return value
    salvaged = {
        "relations": _complete_items(content, "relations"),
        "new_mentions": _complete_items(content, "new_mentions"),
        "truncated": True,
    }
    if not salvaged["relations"] and not salvaged["new_mentions"]:
        raise RelationsError(f"relations response is not JSON: {content[:300]!r}")
    return salvaged


def _complete_items(content: str, name: str) -> list[Any]:
    """Return the complete values of array ``name`` in possibly cut-off JSON."""
    match = re.search(rf'"{name}"\s*:\s*\[', content)
    if match is None:
        return []
    decoder = json.JSONDecoder(strict=False)
    items: list[Any] = []
    index = match.end()
    while True:
        while index < len(content) and content[index] in " \t\r\n,":
            index += 1
        if index >= len(content):
            return items
        try:
            item, index = decoder.raw_decode(content, index)
        except json.JSONDecodeError:
            return items
        items.append(item)


def known_mentions(window: list[WindowEntry]) -> list[KnownMention]:
    """Key a window's mentions ``m1..mN`` for the prompt.

    The anchor chunk (the window's last entry) is keyed first in reading order
    within its text, then the earlier chunks in reading order — so the anchor's
    own keys match a single-passage extraction and the earlier chunks' keys let
    both relation ends come from anywhere in the window. One key per distinct
    ``(entity_type, surface)``: the earliest entry in that key order keeps its
    mention row. ``mentions`` holds
    ``(mention_id, entity_type, surface_name, normalized_name)``.
    """
    result: list[KnownMention] = []
    seen: set[tuple[str, str]] = set()
    for chunk_id, text, mentions in [window[-1], *window[:-1]]:
        del chunk_id
        folded = text.casefold()
        positioned: list[tuple[int, str, str, str, str]] = []
        for mention_id, entity_type, surface, normalized in mentions:
            marker = (entity_type, surface.casefold())
            if marker in seen:
                continue
            at = folded.find(surface.casefold())
            positioned.append(
                (at if at >= 0 else len(text), entity_type, surface, normalized, mention_id)
            )
        positioned.sort()
        for _at, entity_type, surface, normalized, mention_id in positioned:
            marker = (entity_type, surface.casefold())
            if marker in seen:
                continue
            seen.add(marker)
            result.append(
                KnownMention(
                    key=f"m{len(result) + 1}",
                    mention_id=mention_id,
                    entity_type=entity_type,
                    name=surface,
                    normalized_name=normalized,
                )
            )
    return result


def _load_chunks(source_id: str) -> tuple[str, list[tuple[str, str, str | None]]]:
    """Return ``(source kind, (chunk_id, text, passage_kind) rows in order)``."""
    with get_pool().connection() as conn:
        source_row = conn.execute(
            "SELECT kind FROM cmap.source WHERE id = %s", (source_id,)
        ).fetchone()
        rows = conn.execute(
            "SELECT id, text, passage_kind FROM cmap.chunk "
            "WHERE source_id = %s ORDER BY ordinal",
            (source_id,),
        ).fetchall()
    kind = str(source_row[0]) if source_row else ""
    return kind, [(str(row[0]), str(row[1]), row[2]) for row in rows]


def _load_mentions(source_id: str) -> dict[str, list[tuple[str, str, str, str]]]:
    """Each chunk's mentions as ``(mention_id, entity_type, surface, normalized)``."""
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT m.chunk_id, m.id, m.entity_type, m.surface_name, m.normalized_name "
            "FROM cmap.mention m JOIN cmap.chunk c ON c.id = m.chunk_id "
            "WHERE c.source_id = %s",
            (source_id,),
        ).fetchall()
    by_chunk: dict[str, list[tuple[str, str, str, str]]] = {}
    for chunk_id, mention_id, entity_type, surface, normalized in rows:
        by_chunk.setdefault(str(chunk_id), []).append(
            (str(mention_id), str(entity_type), str(surface), str(normalized))
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


def _relation_identity(by_key: dict[str, Any], relation: Relation) -> tuple:
    """Stable identity of one relation finding, shared by overlapping windows.

    Two windows find the same relation when the same named things are linked
    with the same type and the same verbatim quote — regardless of which
    mention rows (the anchor's or a neighbour's) the keys resolved to.
    """
    frm = by_key[relation.from_key]
    to = by_key[relation.to_key]
    return (
        frm.entity_type,
        frm.normalized_name,
        to.entity_type,
        to.normalized_name,
        relation.rel_type,
        relation.quote,
    )


def _mention_identity(mention: NewMention) -> tuple:
    return (
        mention.quote_chunk_id,
        mention.entity_type,
        mention.normalized_name,
        mention.quote,
    )


def _load_identity_index(source_id: str) -> _IdentityIndex:
    """Seed the dedupe index with what this source already holds."""
    seen: set[tuple] = set()
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT fm.entity_type, fm.normalized_name, tm.entity_type, tm.normalized_name, "
            "r.rel_type, r.quote "
            "FROM cmap.relation r JOIN cmap.chunk c ON c.id = r.chunk_id "
            "JOIN cmap.mention fm ON fm.id = r.from_mention_id "
            "JOIN cmap.mention tm ON tm.id = r.to_mention_id "
            "WHERE c.source_id = %s",
            (source_id,),
        ).fetchall()
        for row in rows:
            seen.add(tuple(str(value) for value in row))
        rows = conn.execute(
            "SELECT m.chunk_id, m.entity_type, m.normalized_name, m.quote "
            "FROM cmap.mention m JOIN cmap.chunk c ON c.id = m.chunk_id "
            "WHERE c.source_id = %s",
            (source_id,),
        ).fetchall()
        for row in rows:
            seen.add(tuple(str(value) for value in row))
    return _IdentityIndex(seen)


def _clear_relations(source_id: str) -> None:
    """Drop every relation of a source before a fresh extraction (plan A8).

    A window is extracted again only when the prompt changed (or the source is
    new): its old relations are replaced, never added to. Replacing is done
    once per source because one window's relations now live on several chunks.
    """
    with get_pool().connection() as conn:
        conn.execute(
            "DELETE FROM cmap.relation WHERE chunk_id IN "
            "(SELECT id FROM cmap.chunk WHERE source_id = %s)",
            (source_id,),
        )
        conn.commit()


def _write_result(
    result: ChunkResult, prompt_hash: str, model: str, claimed: _IdentityIndex
) -> None:
    """Write one window's new mentions, relations and raw response together.

    Every relation row carries the quote's true chunk id. Identities already
    claimed (this job or a previous run) are skipped, so overlapping windows
    store one finding once.
    """
    ids = {key: item.mention_id for key, item in result.known.items()}
    by_key: dict[str, Any] = dict(result.known)
    with get_pool().connection() as conn:
        conn.execute(
            "DELETE FROM cmap.extraction WHERE chunk_id = %s AND stage = 'relations' "
            "AND prompt_hash <> %s",
            (result.chunk_id, prompt_hash),
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
                        vector_literal(mention.vector) if mention.vector is not None else None,
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
        clear_chunk_failure(conn, result.chunk_id, "relations")
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


def _record_drop_reasons(source_id: str, drops: dict[str, int], resuming: bool) -> None:
    """Store the run's drop-reason counts under ``read_notes`` (plan E1).

    A resumed run (some anchors were already done) adds to the counts already
    there; a fresh run (a new prompt hash, or a new source) replaces them.
    """
    with get_pool().connection() as conn:
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
        conn.commit()


def _process_window(
    chunk_id: str,
    window: list[WindowEntry],
    counters: _Counters,
) -> ChunkResult:
    """Ask the model for one window's relations and validate them."""
    anchor_text = window[-1][1]
    known = known_mentions(window)
    previous_context = "\n\n".join(text for _cid, text, _mentions in window[:-1])
    prompt = build_prompt(anchor_text, known, previous_context)
    payload: dict[str, Any] = {}
    for attempt in range(1, CALL_ATTEMPTS + 1):
        try:
            payload = _call_model(prompt, counters)
            break
        except FrontierCapReached:
            raise
        except (RelationsError, httpx.HTTPError) as exc:
            if attempt == CALL_ATTEMPTS:
                raise
            logger.warning("relations call failed (%s); retrying chunk %s", exc, chunk_id)
            time.sleep(read_state.BACKOFF_SECONDS * 2 ** (attempt - 1))
    by_key = {item.key: item for item in known}
    relations, new_mentions, drops = validate_response(
        [(cid, text) for cid, text, _mentions in window], by_key, payload
    )
    for reason, amount in drops.items():
        counters.drop(reason, amount)
    return ChunkResult(
        chunk_id=chunk_id,
        known=by_key,
        payload=payload,
        relations=relations,
        new_mentions=new_mentions,
    )


def handle_relations(job: dict[str, Any]) -> None:
    """Extract relations for every non-chatter chunk of one source."""
    payload = job.get("payload") or {}
    source_id = str(payload.get("source_id") or "")
    if not source_id:
        raise ValueError("relations job has no source_id")
    settings = get_settings()
    model = stage_model(settings, "relations")
    if model is None:
        raise RelationsError("BRAIN_FRONTIER_MODEL is not set")
    prompt_hash = relations_prompt_hash()
    source_kind, chunks = _load_chunks(source_id)
    mentions = _load_mentions(source_id)
    done = _load_done(source_id, prompt_hash)
    counters = _Counters(settings)

    pending: list[tuple[str, list[WindowEntry]]] = []
    for index, (chunk_id, _text, passage_kind) in enumerate(chunks):
        chunk_mentions = mentions.get(chunk_id, [])
        skip = chunk_id in done or (passage_kind == "chatter" and not chunk_mentions)
        if skip:
            continue
        window: list[WindowEntry] = []
        for at in window_indices(source_kind, index):
            other_id, other_text, _kind = chunks[at]
            window.append((other_id, other_text, mentions.get(other_id, [])))
        pending.append((chunk_id, window))
    if not done:
        # A fresh extraction (first run, or a new prompt hash): replace the
        # source's old relations rather than adding to them (repair plan A8).
        _clear_relations(source_id)
    claimed = _load_identity_index(source_id)

    cap_error: FrontierCapReached | None = None
    written = 0
    failed = 0
    relation_count = 0

    def _one(item: tuple[str, list[WindowEntry]]) -> ChunkResult:
        """Extract, embed and store one window's relations."""
        result = _process_window(item[0], item[1], counters)
        with_retries(
            lambda: _embed_new_mentions(result, counters),
            f"embedding new mentions of chunk {item[0]}",
        )
        _write_result(result, prompt_hash, model, claimed)
        return result

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = {pool.submit(_one, item): item[0] for item in pending}
        for future in as_completed(futures):
            try:
                result = future.result()
            except FrontierCapReached as exc:
                # Not the chunk's fault: the job is resumed once the cap allows.
                cap_error = exc
                continue
            except Exception as exc:
                # Keep every finished chunk; note this one and carry on, so a
                # single bad call never stops the chain (repair plan A2).
                failed += 1
                logger.warning("relations chunk %s failed for good: %s", futures[future], exc)
                record_chunk_failure(futures[future], "relations", str(exc))
                continue
            written += 1
            relation_count += len(result.relations)
    _record_usage(job.get("id"), counters.usage)
    _record_drop_reasons(source_id, counters.drops, resuming=bool(done))
    logger.info(
        "relations source=%s chunks=%d pending=%d written=%d relations=%d drops=%s usage=%s",
        source_id,
        len(chunks),
        len(pending),
        written,
        relation_count,
        counters.drops,
        counters.usage,
    )
    if cap_error is not None:
        raise cap_error
    state = finish_source(source_id)
    logger.info("relations source=%s finished as %s (failed chunks=%d)", source_id, state, failed)
    _enqueue_resolve()


def _enqueue_resolve() -> None:
    """Queue one whole-corpus ``resolve`` job (step 6), debounced (issue #415).

    A burst of sources must run resolve→project→communities once: the job is
    held until no source has finished relations for ``DEBOUNCE_SECONDS``, and
    never past ``MAX_DELAY_SECONDS`` from its first source, so the Map always
    updates within that bound.
    """
    with get_pool().connection() as conn:
        held = conn.execute(
            "UPDATE cmap.job SET run_after = LEAST("
            "now() + make_interval(secs => %s), created_at + make_interval(secs => %s)) "
            "WHERE kind = 'resolve' AND state = 'queued' AND run_after > now()",
            (DEBOUNCE_SECONDS, MAX_DELAY_SECONDS),
        ).rowcount
        if not held:
            conn.execute(
                "INSERT INTO cmap.job (kind, payload, run_after) SELECT 'resolve', '{}'::jsonb, "
                "now() + make_interval(secs => %s) "
                "WHERE NOT EXISTS (SELECT 1 FROM cmap.job WHERE kind = 'resolve' AND state = 'queued')",
                (DEBOUNCE_SECONDS,),
            )
        conn.commit()
