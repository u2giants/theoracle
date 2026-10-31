"""Passage classification and flat extraction (plan step 4).

Every chunk of a source is classified with ScaleDown ``/classify`` and its flat
mentions are extracted with ScaleDown ``/extract``, 8 chunks at a time. When
``BRAIN_SCALEDOWN_ENABLED=false`` or a ScaleDown call returns non-200 three
times, the frontier model answers ``prompts/flat_extract.md`` instead, in the
same result shape, so the pipeline completes either way (plan §8, §11). Model
ids come from the environment only and never from this code.

Each raw response is recorded in ``cmap.extraction(stage='flat')``; mentions
with confidence >= 0.5 become ``cmap.mention`` rows whose quote is the sentence
that contains the extracted span. Chunks labelled ``chatter`` with score
>= 0.8 are not extracted at all.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from psycopg.types.json import Json

from brain.config import Settings, get_settings
from brain.db import enqueue_job, get_pool
from brain.embed import embed_texts, vector_literal
from brain.extract.normalize import normalize_name
from brain.llm import post_chat_with_rescue

logger = logging.getLogger(__name__)

SCALEDOWN_BASE_URL = "https://api.scaledown.xyz"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "flat_extract.md"

SCALE_DOWN_ATTEMPTS = 3
CONCURRENCY = 8
CHATTER_SKIP_SCORE = 0.8
MIN_MENTION_CONFIDENCE = 0.5

CLASSIFY_LABELS: list[dict[str, str]] = [
    {
        "name": "process",
        "rubric": "Describes ordered work steps, approvals, hand-offs or transitions.",
    },
    {
        "name": "responsibility",
        "rubric": "States who owns, performs or approves something.",
    },
    {
        "name": "rule",
        "rubric": "States a requirement, condition, prohibition, threshold or exception.",
    },
    {
        "name": "reference",
        "rubric": "Lists entities, codes, definitions, or lookup data without a flow.",
    },
    {
        "name": "problem",
        "rubric": "Describes something going wrong, a delay, workaround, complaint or pain point.",
    },
    {
        "name": "decision",
        "rubric": "Records a decision made, or a disagreement about what to do.",
    },
    {
        "name": "chatter",
        "rubric": "Greetings, scheduling, jokes, or content with no business information.",
    },
]

ENTITY_TYPES: dict[str, str] = {
    "Person": "A named individual employee or contact (first name, full name or initials).",
    "Role": "A job title or role, e.g. Licensing Manager, buyer, QA.",
    "Department": "An internal team or department.",
    "Process": "A named business process or workflow, e.g. licensing approval, sample room review.",
    "Step": "A single action or stage inside a process.",
    "System": "Software, tool, spreadsheet, email box or portal used to do work.",
    "Artifact": "A document, form, report, file or record that is produced or needed.",
    "Rule": "A requirement, threshold, deadline or condition.",
    "Exception": "A case where the normal process does not apply.",
    "Issue": "A problem, delay, bottleneck, complaint or workaround.",
    "Decision": "A choice made or pending.",
    "Metric": "A number, KPI, quantity, time or cost.",
    "Customer": "A customer or retailer account.",
    "Vendor": "A supplier or factory.",
    "Licensor": "A brand or IP licensor.",
    "Product": "A product, SKU family or product class.",
}

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


class FlatError(RuntimeError):
    """Raised when the flat stage cannot classify or extract a chunk."""


@dataclass
class ModelRecord:
    """One raw model response destined for ``cmap.extraction(stage='flat')``."""

    model: str
    prompt_hash: str
    payload: dict[str, Any]


@dataclass
class Mention:
    """One ``cmap.mention`` row to insert."""

    entity_type: str
    surface_name: str
    normalized_name: str
    quote: str
    embed_text: str
    vector: list[float] | None = None


@dataclass
class ChunkOutcome:
    """What one chunk contributed to the flat stage."""

    chunk_id: str
    passage_kind: str | None = None
    mentions: list[Mention] = field(default_factory=list)
    records: list[ModelRecord] = field(default_factory=list)
    skipped_chatter: bool = False
    extract_done: bool = False


def load_flat_prompt() -> str:
    """Return the runtime prompt text for the frontier fallback."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def _spec_hash(prefix: str, spec: Any) -> str:
    """Return a stable hash of one call specification (plan §8 prompt hashing)."""
    canonical = json.dumps(spec, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256((prefix + canonical).encode("utf-8")).hexdigest()


def classify_prompt_hash() -> str:
    """Prompt hash of the ScaleDown classify call (shared by every path)."""
    return _spec_hash("flat-classify:", {"labels": CLASSIFY_LABELS})


def extract_prompt_hash() -> str:
    """Prompt hash of the ScaleDown extract call."""
    return _spec_hash("flat-extract:", {"entities": ENTITY_TYPES})


def frontier_prompt_hash() -> str:
    """Prompt hash of the frontier fallback call (prompt file participates)."""
    prompt_sha = hashlib.sha256(load_flat_prompt().encode("utf-8")).hexdigest()
    return _spec_hash(
        "flat-frontier:",
        {"labels": CLASSIFY_LABELS, "entities": ENTITY_TYPES, "prompt_sha256": prompt_sha},
    )


def classify_body(text: str) -> dict[str, Any]:
    """Return the ``/classify`` request body for one chunk."""
    return {"text": text, "labels": CLASSIFY_LABELS}


def extract_body(text: str) -> dict[str, Any]:
    """Return the ``/extract`` request body for one chunk."""
    return {"text": text, "entities": ENTITY_TYPES}


def _post_scaledown(path: str, body: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """POST one ScaleDown call and return its JSON body."""
    if settings.scaledown_api_key is None:
        raise FlatError("SCALEDOWN_API_KEY is not set")
    response = httpx.post(
        f"{SCALEDOWN_BASE_URL}{path}",
        headers={"x-api-key": settings.scaledown_api_key},
        json=body,
        timeout=120.0,
    )
    if response.status_code != 200:
        raise FlatError(
            f"scaledown {path} failed: {response.status_code} {response.text[:200]}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise FlatError(f"scaledown {path} response is not JSON") from exc
    if not isinstance(payload, dict):
        raise FlatError(f"scaledown {path} response is not a JSON object")
    return payload


def _post_chat(messages: list[dict[str, Any]], settings: Settings) -> dict[str, Any]:
    """POST one frontier chat-completions request and return the response body."""
    if settings.openrouter_api_key is None:
        raise FlatError("OPENROUTER_API_KEY is not set")
    if settings.brain_frontier_model is None:
        raise FlatError("BRAIN_FRONTIER_MODEL is not set")
    return post_chat_with_rescue(
        {
            "model": settings.brain_frontier_model,
            "messages": messages,
            "temperature": 0,
        },
        api_key=settings.openrouter_api_key,
        timeout=120.0,
        error_cls=FlatError,
        label="frontier flat",
    )


def parse_model_json(content: str) -> dict[str, Any]:
    """Parse a model's JSON object, tolerating a surrounding code fence."""
    text = content.strip()
    fenced = re.fullmatch(r"```[a-zA-Z]*\n(.*?)\n?```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FlatError("model response is not valid JSON") from exc
    if not isinstance(value, dict):
        raise FlatError("model response is not a JSON object")
    return value


def sentence_containing(text: str, start: int, end: int) -> str | None:
    """Return the sentence of ``text`` that contains ``[start, end)``."""
    if start < 0 or end > len(text) or start >= end:
        return None
    bounds = [0]
    for match in _SENTENCE_END.finditer(text):
        bounds.append(match.start())
    bounds.append(len(text))
    pairs = [(bounds[index], bounds[index + 1]) for index in range(len(bounds) - 1)]
    for left, right in pairs:
        if left <= start and end <= right:
            sentence = text[left:right].strip()
            if sentence:
                return sentence
    for left, right in pairs:
        if left <= start < right:
            sentence = text[left:right].strip()
            if sentence:
                return sentence
    return None


def _locate_span(chunk_text: str, item: dict[str, Any]) -> tuple[int, int] | None:
    """Return ``[start, end)`` of one entity in the chunk, repairing bad spans."""
    surface = str(item.get("text") or "")
    if not surface:
        return None
    start = item.get("start")
    end = item.get("end")
    if isinstance(start, int) and isinstance(end, int):
        if 0 <= start < end <= len(chunk_text) and chunk_text[start:end] == surface:
            return start, end
    at = chunk_text.find(surface)
    if at >= 0:
        return at, at + len(surface)
    folded = chunk_text.casefold().find(surface.casefold())
    if folded >= 0:
        return folded, folded + len(surface)
    return None


def mentions_from_entities(
    chunk_text: str,
    entities: Sequence[dict[str, Any]],
) -> list[Mention]:
    """Turn validated ``entities[]`` items into mention rows (plan step 4, 2)."""
    mentions: list[Mention] = []
    for item in entities:
        if not isinstance(item, dict):
            continue
        entity_type = str(item.get("type") or "")
        if entity_type not in ENTITY_TYPES:
            continue
        try:
            confidence = float(item.get("confidence"))
        except (TypeError, ValueError):
            continue
        if confidence < MIN_MENTION_CONFIDENCE:
            continue
        span = _locate_span(chunk_text, item)
        if span is None:
            continue
        start, end = span
        quote = sentence_containing(chunk_text, start, end)
        if quote is None:
            continue
        surface = str(item.get("text") or "")
        mentions.append(
            Mention(
                entity_type=entity_type,
                surface_name=surface,
                normalized_name=normalize_name(surface, entity_type),
                quote=quote,
                embed_text=f"{surface} — {quote}",
            )
        )
    return mentions


def _classify_half(payload: dict[str, Any]) -> tuple[str | None, dict[str, float]]:
    """Return ``(top_label, scores)`` from a classify-shaped payload."""
    top_label = payload.get("top_label")
    scores_raw = payload.get("scores")
    scores: dict[str, float] = {}
    if isinstance(scores_raw, dict):
        for key, value in scores_raw.items():
            try:
                scores[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
    if isinstance(top_label, str):
        return top_label, scores
    return None, scores


def _extract_half(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the ``entities[]`` list from an extract-shaped payload."""
    entities = payload.get("entities")
    if isinstance(entities, list):
        return [item for item in entities if isinstance(item, dict)]
    return []


def is_chatter(top_label: str | None, scores: dict[str, float]) -> bool:
    """True when the chunk is chatter with score >= 0.8 (plan step 4, 1)."""
    if top_label != "chatter":
        return False
    return scores.get("chatter", 0.0) >= CHATTER_SKIP_SCORE


class _CallCounters:
    """Thread-safe call counters shared by the chunk workers."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.lock = threading.Lock()
        self.usage: dict[str, int] = {}

    def bump(self, key: str, amount: int = 1) -> None:
        with self.lock:
            self.usage[key] = self.usage.get(key, 0) + amount

    def frontier_allowed(self) -> None:
        """Raise once the per-job frontier cap is reached (plan §11)."""
        cap = self.settings.brain_max_frontier_calls_per_job
        if cap is None:
            return
        with self.lock:
            used = self.usage.get("frontier_calls", 0)
            if used >= cap:
                raise FlatError(
                    f"BRAIN_MAX_FRONTIER_CALLS_PER_JOB cap of {cap} reached; "
                    "the job can be resumed once the cap is raised"
                )
            self.usage["frontier_calls"] = used + 1


def _scaledown_available(settings: Settings) -> bool:
    """ScaleDown is used only when it is enabled and keyed (plan §8 fallback)."""
    if not settings.brain_scaledown_enabled:
        return False
    return settings.scaledown_api_key is not None


def _call_scaledown(
    path: str,
    body: dict[str, Any],
    counters: _CallCounters,
    usage_key: str,
) -> dict[str, Any] | None:
    """Try one ScaleDown endpoint three times; return None to fall back."""
    if not _scaledown_available(counters.settings):
        return None
    for _ in range(SCALE_DOWN_ATTEMPTS):
        counters.bump(usage_key)
        try:
            return _post_scaledown(path, body, counters.settings)
        except FlatError as exc:
            logger.warning("scaledown %s failed (%s); falling back after retries", path, exc)
    return None


def _frontier_flat(text: str, counters: _CallCounters) -> dict[str, Any]:
    """Run the frontier fallback prompt over one chunk."""
    counters.frontier_allowed()
    prompt = load_flat_prompt().replace("{{chunk_text}}", text)
    messages = [{"role": "user", "content": prompt}]
    body = _post_chat(messages, counters.settings)
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise FlatError("frontier flat response has no message content") from exc
    if not isinstance(content, str):
        raise FlatError("frontier flat message content is not text")
    reported = body.get("usage") or {}
    tokens = reported.get("total_tokens")
    if isinstance(tokens, int):
        counters.bump("frontier_tokens", tokens)
    return parse_model_json(content)


def _process_chunk(
    chunk_id: str,
    text: str,
    counters: _CallCounters,
    classify_done: dict[str, Any] | None,
) -> ChunkOutcome:
    """Classify and extract one chunk, with the frontier fallback per call."""
    outcome = ChunkOutcome(chunk_id=chunk_id)
    frontier_cache: dict[str, Any] | None = None

    def frontier() -> dict[str, Any]:
        nonlocal frontier_cache
        if frontier_cache is None:
            frontier_cache = _frontier_flat(text, counters)
        return frontier_cache

    if classify_done is not None:
        top_label, scores = _classify_half(classify_done)
    else:
        top_label, scores = None, {}
        response = _call_scaledown(
            "/classify", classify_body(text), counters, "scaledown_classify_calls"
        )
        if response is not None:
            top_label, scores = _classify_half(response)
            outcome.records.append(
                ModelRecord(
                    model="scaledown/classify",
                    prompt_hash=classify_prompt_hash(),
                    payload=response,
                )
            )
        else:
            fallback = frontier()
            top_label, scores = _classify_half(fallback)
            outcome.records.append(
                ModelRecord(
                    model=counters.settings.brain_frontier_model or "frontier",
                    prompt_hash=frontier_prompt_hash(),
                    payload=fallback,
                )
            )
    outcome.passage_kind = top_label

    if is_chatter(top_label, scores):
        outcome.skipped_chatter = True
        return outcome

    response = _call_scaledown(
        "/extract", extract_body(text), counters, "scaledown_extract_calls"
    )
    if response is not None:
        outcome.records.append(
            ModelRecord(
                model="scaledown/extract",
                prompt_hash=extract_prompt_hash(),
                payload=response,
            )
        )
        entities = _extract_half(response)
    else:
        fallback = frontier()
        if not any(record.prompt_hash == frontier_prompt_hash() for record in outcome.records):
            outcome.records.append(
                ModelRecord(
                    model=counters.settings.brain_frontier_model or "frontier",
                    prompt_hash=frontier_prompt_hash(),
                    payload=fallback,
                )
            )
        entities = _extract_half(fallback)
    outcome.mentions = mentions_from_entities(text, entities)
    outcome.extract_done = True
    return outcome


def _load_chunks(source_id: str) -> list[tuple[str, str]]:
    """Return ``(chunk_id, text)`` for one source in ordinal order."""
    pool = get_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT id, text FROM cmap.chunk WHERE source_id = %s ORDER BY ordinal",
            (source_id,),
        ).fetchall()
    return [(str(row[0]), str(row[1])) for row in rows]


def _load_done_state(
    source_id: str,
) -> tuple[set[str], dict[str, dict[str, Any]]]:
    """Return chunks already extracted and the classify payloads already stored."""
    classify_hash = classify_prompt_hash()
    frontier_hash = frontier_prompt_hash()
    extract_hash = extract_prompt_hash()
    pool = get_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT e.chunk_id, e.prompt_hash, e.payload FROM cmap.extraction e "
            "JOIN cmap.chunk c ON c.id = e.chunk_id "
            "WHERE c.source_id = %s AND e.stage = 'flat'",
            (source_id,),
        ).fetchall()
    done: set[str] = set()
    classify_payloads: dict[str, dict[str, Any]] = {}
    for chunk_id, prompt_hash, payload in rows:
        chunk_id = str(chunk_id)
        if prompt_hash in (extract_hash, frontier_hash):
            done.add(chunk_id)
        elif prompt_hash == classify_hash and isinstance(payload, dict):
            classify_payloads[chunk_id] = payload
    return done, classify_payloads


def _write_outcome(outcome: ChunkOutcome) -> None:
    """Write one chunk's records and mentions in a single transaction."""
    pool = get_pool()
    with pool.connection() as conn:
        if outcome.passage_kind is not None:
            conn.execute(
                "UPDATE cmap.chunk SET passage_kind = %s WHERE id = %s",
                (outcome.passage_kind, outcome.chunk_id),
            )
        for record in outcome.records:
            conn.execute(
                "INSERT INTO cmap.extraction "
                "(chunk_id, stage, prompt_hash, model, payload) "
                "VALUES (%s, 'flat', %s, %s, %s) "
                "ON CONFLICT (chunk_id, stage, prompt_hash) DO NOTHING",
                (
                    outcome.chunk_id,
                    record.prompt_hash,
                    record.model,
                    Json(record.payload),
                ),
            )
        for mention in outcome.mentions:
            conn.execute(
                "INSERT INTO cmap.mention "
                "(chunk_id, entity_type, surface_name, normalized_name, quote, embedding) "
                "VALUES (%s, %s, %s, %s, %s, %s::vector)",
                (
                    outcome.chunk_id,
                    mention.entity_type,
                    mention.surface_name,
                    mention.normalized_name,
                    mention.quote,
                    vector_literal(mention.vector) if mention.vector is not None else None,
                ),
            )
        conn.commit()


def _record_usage(job_id: Any, usage: dict[str, int]) -> None:
    """Log the job's model usage into ``cmap.job.payload.usage`` (plan §11)."""
    if not usage:
        return
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(
            "UPDATE cmap.job SET payload = jsonb_set(payload, '{usage}', %s::jsonb) "
            "WHERE id = %s",
            (Json(usage), job_id),
        )
        conn.commit()


def handle_classify_extract(job: dict[str, Any]) -> None:
    """Classify every chunk of one source and extract its flat mentions."""
    payload = job.get("payload") or {}
    source_id = str(payload.get("source_id") or "")
    if not source_id:
        raise ValueError("classify_extract job has no source_id")
    settings = get_settings()
    chunks = _load_chunks(source_id)
    done_ids, classify_payloads = _load_done_state(source_id)
    counters = _CallCounters(settings)

    pending: list[tuple[str, str, dict[str, Any] | None]] = []
    for chunk_id, text in chunks:
        if chunk_id in done_ids:
            continue
        classify_done = classify_payloads.get(chunk_id)
        if classify_done is not None:
            top_label, scores = _classify_half(classify_done)
            if is_chatter(top_label, scores):
                continue
        pending.append((chunk_id, text, classify_done))

    outcomes: list[ChunkOutcome] = []
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = [
            pool.submit(_process_chunk, chunk_id, text, counters, classify_done)
            for chunk_id, text, classify_done in pending
        ]
        for future in futures:
            outcomes.append(future.result())

    _embed_outcomes(outcomes, counters)
    for outcome in outcomes:
        _write_outcome(outcome)
    _record_usage(job.get("id"), counters.usage)
    if job.get("id") is not None:
        enqueue_job("relations", {"source_id": source_id})
    logger.info(
        "classify_extract source=%s chunks=%d mentions=%d usage=%s",
        source_id,
        len(chunks),
        sum(len(outcome.mentions) for outcome in outcomes),
        counters.usage,
    )


def _embed_outcomes(outcomes: list[ChunkOutcome], counters: _CallCounters) -> None:
    """Embed every mention text and attach the vectors to the mentions."""
    texts: list[str] = []
    for outcome in outcomes:
        for mention in outcome.mentions:
            texts.append(mention.embed_text)
    if not texts:
        return
    vectors = embed_texts(texts, counters.settings, counters.usage)
    cursor = 0
    for outcome in outcomes:
        for mention in outcome.mentions:
            mention.vector = vectors[cursor]
            cursor += 1
