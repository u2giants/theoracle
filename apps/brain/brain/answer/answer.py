"""Question answering over the company map: local and global modes (plan step 9).

``POST /answer`` asks one question in one of three modes:

- ``local`` — embed the question, take the nearest entities and their depth-2
  graph neighbourhood (60 nodes / 150 edges, edges ranked by weight), retrieve
  chunks by cosine from the edge sources plus the open corpus, compress the
  passages with ScaleDown ``/compress/raw/`` when they exceed the token
  threshold (the quotes list stays uncompressed for citation), and answer from
  ``prompts/answer_local.md``.
- ``global`` — map-reduce over the level-1 community reports and the company
  report (``prompts/answer_map.md`` per batch of 10 when they exceed the
  one-call budget, then ``prompts/answer_global.md``), citing finding
  source_ids resolved to titles and the chunk nearest each answer paragraph.
- ``auto`` — ScaleDown classifies the question ``specific``/``broad``; a top
  score under 0.6 runs both modes and merges.

Citations are validated: a local quote must be a substring of its chunk or the
citation is dropped, and a sentence left without any citation is marked
``(uncited)`` rather than deleted. History is the request's last turns only —
there is no server-side session store.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import psycopg

from brain.config import Settings, get_settings
from brain.db import get_pool
from brain.embed import embed_texts, vector_literal
from brain.extract import flat as flat_mod
from brain.extract.relations import DEFAULT_MAX_FRONTIER_CALLS, _complete_items
from brain.graph.communities import _tokens
from brain.graph.project import connect as connect_graph

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
LOCAL_PROMPT_PATH = PROMPTS_DIR / "answer_local.md"
GLOBAL_PROMPT_PATH = PROMPTS_DIR / "answer_global.md"
MAP_PROMPT_PATH = PROMPTS_DIR / "answer_map.md"

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

TOP_ENTITIES = 8
GRAPH_NODE_CAP = 60
GRAPH_EDGE_CAP = 150
CHUNKS_RESTRICTED = 20
CHUNKS_UNRESTRICTED = 10
COMPRESS_MIN_TOKENS = 6000
GLOBAL_ONE_SHOT_TOKENS = 60000
MAP_BATCH = 10
HISTORY_TURNS = 6
ROUTE_MIN_SCORE = 0.6
MAX_TOKENS = 4000
ASK_ATTEMPTS = 3

ROUTE_LABELS: list[dict[str, str]] = [
    {
        "name": "specific",
        "rubric": (
            "asks about a particular person, process, system, document or step"
        ),
    },
    {
        "name": "broad",
        "rubric": (
            "asks about patterns, biggest problems, overview, 'across the "
            "company', comparisons between departments"
        ),
    },
]

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_MARKER = re.compile(r"\[(\d+)\]")
_FOLDED_CHARS = re.compile(r"[^a-z0-9 ]+")


class AnswerError(RuntimeError):
    """Raised when a question cannot be answered."""


class AnswerCapReached(AnswerError):
    """Raised when ``BRAIN_MAX_FRONTIER_CALLS_PER_JOB`` is used up."""


# ------------------------------------------------------------------ model IO


def _post_chat(messages: list[dict[str, Any]], settings: Settings) -> dict[str, Any]:
    """POST one frontier chat-completions request in JSON mode."""
    if settings.openrouter_api_key is None:
        raise AnswerError("OPENROUTER_API_KEY is not set")
    if settings.brain_frontier_model is None:
        raise AnswerError("BRAIN_FRONTIER_MODEL is not set")
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
        timeout=120.0,
    )
    if response.status_code != 200:
        raise AnswerError(
            f"frontier answer call failed: {response.status_code} {response.text[:200]}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise AnswerError("frontier answer response is not JSON") from exc


def _post_scaledown(
    path: str, body: dict[str, Any], settings: Settings
) -> dict[str, Any]:
    """POST one ScaleDown call (classify or compress) and return its JSON body."""
    if settings.scaledown_api_key is None:
        raise AnswerError("SCALEDOWN_API_KEY is not set")
    try:
        response = httpx.post(
            f"{flat_mod.SCALEDOWN_BASE_URL}{path}",
            headers={"x-api-key": settings.scaledown_api_key},
            json=body,
            timeout=120.0,
        )
    except httpx.HTTPError as exc:
        raise AnswerError(f"scaledown {path} transport failed") from exc
    if response.status_code != 200:
        raise AnswerError(
            f"scaledown {path} failed: {response.status_code} {response.text[:200]}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise AnswerError(f"scaledown {path} response is not JSON") from exc
    if not isinstance(payload, dict):
        raise AnswerError(f"scaledown {path} response is not a JSON object")
    return payload


def parse_model_json(content: str, list_fields: tuple[str, ...]) -> dict[str, Any]:
    """Parse one model JSON object, salvaging fields out of cut-off output.

    Same robustness chain as steps 5-8: tolerate a code fence, trailing
    commas and content returned as text blocks; salvage the known fields when
    the closing brace never arrived.
    """
    text = content.strip()
    fenced = re.fullmatch(r"```[a-zA-Z]*\n(.*?)\n?```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        body = re.sub(r",(\s*[}\]])", r"\1", text[start : end + 1])
        try:
            value = json.loads(body, strict=False)
        except json.JSONDecodeError:
            value = None
        if isinstance(value, dict):
            return value
    salvaged: dict[str, Any] = {}
    match = re.search(r'"answer_md"\s*:\s*("(?:[^"\\]|\\.)*")', text)
    if match is not None:
        try:
            salvaged["answer_md"] = json.loads(match.group(1))
        except json.JSONDecodeError:
            salvaged["answer_md"] = match.group(1).strip('"')
    for name in list_fields:
        items = _complete_items(text, name)
        if items:
            salvaged[name] = items
    if salvaged:
        salvaged["truncated"] = True
        return salvaged
    raise AnswerError(f"answer response is not JSON: {content[:300]!r}")


def _ask(prompt: str, settings: Settings, usage: dict[str, int]) -> dict[str, Any]:
    """One JSON answer from the frontier model, retrying transient failures."""
    last_error: Exception | None = None
    for _attempt in range(ASK_ATTEMPTS):
        try:
            return _ask_once(prompt, settings, usage)
        except AnswerCapReached:
            raise
        except (AnswerError, httpx.HTTPError) as exc:
            logger.warning("answer call failed: %s", exc)
            last_error = exc
    raise AnswerError("frontier answer failed after retries") from last_error


def _ask_once(prompt: str, settings: Settings, usage: dict[str, int]) -> dict[str, Any]:
    cap = settings.brain_max_frontier_calls_per_job
    if cap is None:
        cap = DEFAULT_MAX_FRONTIER_CALLS
    used = usage.get("frontier_calls", 0)
    if used >= cap:
        raise AnswerCapReached(
            f"BRAIN_MAX_FRONTIER_CALLS_PER_JOB cap of {cap} reached while answering"
        )
    usage["frontier_calls"] = used + 1
    body = _post_chat([{"role": "user", "content": prompt}], settings)
    tokens = (body.get("usage") or {}).get("total_tokens")
    if isinstance(tokens, int):
        usage["frontier_tokens"] = usage.get("frontier_tokens", 0) + tokens
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AnswerError("frontier answer response has no message content") from exc
    if isinstance(content, list):
        content = "".join(
            str(part.get("text", "")) for part in content if isinstance(part, dict)
        )
    if content is None:
        raise AnswerError("frontier answer response has no message content")
    if not isinstance(content, str):
        raise AnswerError("frontier answer response has no message content")
    return parse_model_json(content, ("citations", "unknowns", "points"))


# ------------------------------------------------------------------- routing


def _route_mode(question: str, settings: Settings, usage: dict[str, int]) -> str:
    """ScaleDown ``specific``/``broad`` classify; low confidence runs both."""
    if not settings.brain_scaledown_enabled or settings.scaledown_api_key is None:
        return "both"
    usage["scaledown_classify_calls"] = usage.get("scaledown_classify_calls", 0) + 1
    try:
        payload = _post_scaledown(
            "/classify",
            {"text": question, "labels": ROUTE_LABELS},
            settings,
        )
    except AnswerError as exc:
        logger.warning("route classify failed (%s); running both modes", exc)
        return "both"
    top = payload.get("top_label")
    scores_raw = payload.get("scores")
    scores: dict[str, float] = {}
    if isinstance(scores_raw, dict):
        for key, value in scores_raw.items():
            try:
                scores[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
    score = scores.get(str(top), 0.0)
    if score < ROUTE_MIN_SCORE:
        return "both"
    if top == "specific":
        return "local"
    if top == "broad":
        return "global"
    return "both"


# ---------------------------------------------------------------- citations


def _sentence_slices(text: str) -> list[tuple[str, str]]:
    """Split into ``(sentence, separator)`` pairs, keeping the whitespace."""
    out: list[tuple[str, str]] = []
    position = 0
    for match in _SENTENCE_SPLIT.finditer(text):
        out.append((text[position : match.start()], match.group()))
        position = match.end()
    out.append((text[position:], ""))
    return out


def _renumber(answer_md: str, old_to_new: dict[int, int]) -> str:
    """Rewrite [n] markers to the filtered citation numbers.

    A marker whose citation was dropped disappears; a sentence left with no
    citation at all is marked ``(uncited)`` rather than deleted (plan step 9.6).
    """
    pieces: list[str] = []
    for sentence, separator in _sentence_slices(answer_md):
        found = [int(value) for value in _MARKER.findall(sentence)]
        if not found:
            pieces.append(sentence + separator)
            continue
        kept = [value for value in found if value in old_to_new]
        stripped = re.sub(r"\s*\[\d+\]", "", sentence)
        stripped = re.sub(r"\s{2,}", " ", stripped).strip()
        if kept:
            markers = "".join(f" [{old_to_new[value]}]" for value in kept)
            pieces.append(stripped + markers + separator)
        else:
            pieces.append(stripped + " (uncited)" + separator)
    return "".join(pieces)


def _finalize_local(
    answer_md: str,
    raw_citations: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Validate quotes against their chunks; drop invalid; renumber markers."""
    by_id = {chunk["id"]: chunk for chunk in chunks}
    kept: list[dict[str, Any]] = []
    old_to_new: dict[int, int] = {}
    for index, cite in enumerate(raw_citations, start=1):
        chunk_id = str(cite.get("chunk_id") or "")
        quote = str(cite.get("quote") or "")
        chunk = by_id.get(chunk_id)
        if chunk is None or not quote or quote not in chunk["text"]:
            continue
        kept.append(
            {
                "source_id": chunk["source_id"],
                "title": chunk["title"],
                "chunk_id": chunk_id,
                "quote": quote,
                "locator": chunk["locator"],
            }
        )
        old_to_new[index] = len(kept)
    return _renumber(answer_md, old_to_new), kept


def _paragraphs(answer_md: str) -> list[str]:
    """Split the markdown answer into paragraphs on blank lines."""
    return [part.strip() for part in re.split(r"\n\s*\n", answer_md) if part.strip()]


def _finalize_global(
    answer_md: str,
    raw_citations: list[dict[str, Any]],
    settings: Settings,
    usage: dict[str, int],
) -> tuple[str, list[dict[str, Any]]]:
    """Resolve cited source_ids to titles and the chunk nearest each paragraph."""
    paragraphs = _paragraphs(answer_md)
    wanted: list[tuple[int, str, str]] = []
    for index, cite in enumerate(raw_citations, start=1):
        source_id = str(cite.get("source_id") or "")
        try:
            source_id = str(UUID(source_id))
        except ValueError:
            continue
        paragraph = answer_md
        marker = re.compile(rf"(?<!\[)\[{index}\](?!\])")
        for candidate in paragraphs:
            if marker.search(candidate):
                paragraph = candidate
                break
        wanted.append((index, source_id, paragraph))
    vectors: list[list[float]] = []
    if wanted:
        vectors = embed_texts([item[2] for item in wanted], settings, usage)
    kept: list[dict[str, Any]] = []
    old_to_new: dict[int, int] = {}
    with get_pool().connection() as conn:
        for position, (index, source_id, _paragraph) in enumerate(wanted):
            row = conn.execute(
                "SELECT title FROM cmap.source WHERE id = %s",
                (source_id,),
            ).fetchone()
            if row is None:
                continue
            chunk = _closest_chunk(conn, source_id, vectors[position])
            if chunk is None:
                continue
            kept.append(
                {
                    "source_id": source_id,
                    "title": str(row[0]),
                    "chunk_id": chunk["chunk_id"],
                    "quote": chunk["text"],
                    "locator": chunk["locator"],
                }
            )
            old_to_new[index] = len(kept)
    return _renumber(answer_md, old_to_new), kept


def _closest_chunk(
    conn: psycopg.Connection, source_id: str, vector: list[float]
) -> dict[str, Any] | None:
    """The chunk of ``source_id`` whose embedding is nearest ``vector``."""
    try:
        source_id = str(UUID(source_id))
    except ValueError:
        return None
    row = conn.execute(
        "SELECT id::text, text, locator FROM cmap.chunk "
        "WHERE source_id = %s AND embedding IS NOT NULL "
        "ORDER BY embedding <=> %s::vector LIMIT 1",
        (source_id, vector_literal(vector)),
    ).fetchone()
    if row is not None:
        return {"chunk_id": row[0], "text": row[1], "locator": row[2]}
    row = conn.execute(
        "SELECT id::text, text, locator FROM cmap.chunk "
        "WHERE source_id = %s ORDER BY ordinal LIMIT 1",
        (source_id,),
    ).fetchone()
    if row is None:
        return None
    return {"chunk_id": row[0], "text": row[1], "locator": row[2]}


# -------------------------------------------------------------------- local


def _fold_question(question: str) -> str:
    """Casefold and strip punctuation so alias names can appear-match."""
    text = question.casefold().replace("'", "")
    return _FOLDED_CHARS.sub(" ", text)


def _select_entities(question: str, vector: list[float]) -> list[dict[str, Any]]:
    """Top-8 entities by embedding cosine, plus any entity whose alias appears."""
    folded = _fold_question(question)
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT id::text, entity_type, canonical_name, description, "
            "mention_count, source_count "
            "FROM cmap.entity WHERE embedding IS NOT NULL "
            "ORDER BY embedding <=> %s::vector LIMIT %s",
            (vector_literal(vector), TOP_ENTITIES),
        ).fetchall()
        alias_rows = conn.execute(
            "SELECT DISTINCT e.id::text, e.entity_type, e.canonical_name, "
            "e.description, e.mention_count, e.source_count "
            "FROM cmap.entity e "
            "JOIN cmap.entity_alias a ON a.entity_id = e.id "
            "WHERE a.normalized_name <> '' AND position(a.normalized_name IN %s) > 0",
            (folded,),
        ).fetchall()
    seen: dict[str, dict[str, Any]] = {}
    for row in list(rows) + list(alias_rows):
        entity_id = str(row[0])
        if entity_id in seen:
            continue
        seen[entity_id] = {
            "id": entity_id,
            "type": str(row[1]),
            "name": str(row[2]),
            "description": str(row[3] or ""),
            "mention_count": int(row[4]),
            "source_count": int(row[5]),
        }
    return list(seen.values())


def _graph_context(
    entities: list[dict[str, Any]], settings: Settings
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Depth-2 neighbourhood of the seeds: capped nodes and weight-ranked edges."""
    ids = [entity["id"] for entity in entities]
    graph = connect_graph(settings)
    result = graph.query(
        "MATCH (a:Entity)-[*1..2]-(x:Entity) WHERE a.id IN $ids "
        "RETURN DISTINCT x "
        "ORDER BY x.source_count DESC, x.mention_count DESC LIMIT $limit",
        {"ids": ids, "limit": GRAPH_NODE_CAP},
    )
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entity in entities:
        seen.add(entity["id"])
        nodes.append(
            {
                "id": entity["id"],
                "type": entity["type"],
                "name": entity["name"],
                "description": entity["description"],
            }
        )
    for row in result.result_set:
        node = row[0]
        node_id = str(node.properties.get("id"))
        if node_id in seen:
            continue
        seen.add(node_id)
        nodes.append(
            {
                "id": node_id,
                "type": str(node.properties.get("type")),
                "name": str(node.properties.get("name")),
                "description": str(node.properties.get("description") or ""),
            }
        )
    nodes = nodes[:GRAPH_NODE_CAP]
    node_ids = [node["id"] for node in nodes]
    edge_rows = graph.query(
        "MATCH (a:Entity)-[r]->(b:Entity) "
        "WHERE a.id IN $ids AND b.id IN $ids "
        "RETURN a.id, b.id, type(r), r.weight, r.descriptions, r.stances, r.source_refs",
        {"ids": node_ids},
    ).result_set
    edges: list[dict[str, Any]] = []
    for from_id, to_id, rel_type, weight, descriptions, stances, source_refs in edge_rows:
        refs = source_refs
        if isinstance(refs, str):
            try:
                refs = json.loads(refs)
            except json.JSONDecodeError:
                refs = []
        if not isinstance(refs, list):
            refs = []
        edges.append(
            {
                "from": str(from_id),
                "to": str(to_id),
                "rel_type": str(rel_type),
                "weight": int(weight or 0),
                "descriptions": [str(item) for item in (descriptions or [])],
                "stances": str(stances or "{}"),
                "source_refs": [
                    {
                        "source_id": str(ref.get("source_id") or ""),
                        "chunk_id": str(ref.get("chunk_id") or ""),
                        "quote": str(ref.get("quote") or ""),
                    }
                    for ref in refs
                    if isinstance(ref, dict)
                ],
            }
        )
    edges.sort(key=lambda edge: edge["weight"], reverse=True)
    edges = edges[:GRAPH_EDGE_CAP]
    return nodes[:GRAPH_NODE_CAP], edges


def _select_chunks(vector: list[float], source_ids: list[str]) -> list[dict[str, Any]]:
    """Top chunks from the edge sources, plus the open-corpus top."""
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    with get_pool().connection() as conn:
        queries: list[tuple[str, list[Any]]] = []
        if source_ids:
            queries.append(
                (
                    "SELECT c.id::text, c.source_id::text, s.title, c.locator, c.text "
                    "FROM cmap.chunk c JOIN cmap.source s ON s.id = c.source_id "
                    "WHERE c.embedding IS NOT NULL AND c.source_id = ANY(%s::uuid[]) "
                    "ORDER BY c.embedding <=> %s::vector LIMIT %s",
                    [source_ids, vector_literal(vector), CHUNKS_RESTRICTED],
                )
            )
        queries.append(
            (
                "SELECT c.id::text, c.source_id::text, s.title, c.locator, c.text "
                "FROM cmap.chunk c JOIN cmap.source s ON s.id = c.source_id "
                "WHERE c.embedding IS NOT NULL "
                "ORDER BY c.embedding <=> %s::vector LIMIT %s",
                [vector_literal(vector), CHUNKS_UNRESTRICTED],
            )
        )
        for sql, params in queries:
            for row in conn.execute(sql, params).fetchall():
                chunk_id = str(row[0])
                if chunk_id in seen:
                    continue
                seen.add(chunk_id)
                selected.append(
                    {
                        "id": chunk_id,
                        "source_id": str(row[1]),
                        "title": str(row[2]),
                        "locator": row[3],
                        "text": str(row[4]),
                    }
                )
    return selected


def _quotes_for(chunks: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Sentence-level quotes of the selected chunks, one entry per quote."""
    chunk_ids = [chunk["id"] for chunk in chunks]
    if not chunk_ids:
        return []
    by_chunk = {chunk["id"]: chunk for chunk in chunks}
    quotes: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    with get_pool().connection() as conn:
        mention_rows = conn.execute(
            "SELECT chunk_id::text, quote FROM cmap.mention "
            "WHERE chunk_id = ANY(%s::uuid[]) ORDER BY quote, id",
            (chunk_ids,),
        ).fetchall()
        relation_rows = conn.execute(
            "SELECT chunk_id::text, quote FROM cmap.relation "
            "WHERE chunk_id = ANY(%s::uuid[]) ORDER BY quote, id",
            (chunk_ids,),
        ).fetchall()
    per_chunk: dict[str, list[str]] = {}
    for chunk_id, quote in list(mention_rows) + list(relation_rows):
        key = (str(chunk_id), str(quote))
        if key in seen:
            continue
        if str(chunk_id) not in by_chunk:
            continue
        seen.add(key)
        per_chunk.setdefault(str(chunk_id), []).append(str(quote))
    for chunk in chunks:
        for quote in per_chunk.get(chunk["id"], []):
            quotes.append(
                {
                    "chunk_id": chunk["id"],
                    "quote": quote,
                    "source_id": chunk["source_id"],
                    "title": chunk["title"],
                }
            )
    return quotes


def _compress_passages(
    texts: list[str], question: str, settings: Settings, usage: dict[str, int]
) -> str:
    """Join the chunk texts, compressing through ScaleDown past the threshold."""
    raw = "\n\n".join(texts)
    if _tokens(raw) <= COMPRESS_MIN_TOKENS:
        return raw
    if not settings.brain_scaledown_enabled or settings.scaledown_api_key is None:
        return raw
    usage["scaledown_compress_calls"] = usage.get("scaledown_compress_calls", 0) + 1
    try:
        payload = _post_scaledown(
            "/compress/raw/",
            {"context": raw, "prompt": question, "rate": "auto"},
            settings,
        )
    except AnswerError as exc:
        logger.warning("compress failed (%s); sending uncompressed passages", exc)
        return raw
    inner = payload.get("results")
    if not isinstance(inner, dict):
        inner = payload
    compressed = inner.get("compressed_prompt")
    if not isinstance(compressed, str) or not compressed.strip():
        return raw
    return compressed


def _render_history(history: list[dict[str, str]]) -> str:
    """Render the conversation turns kept for this request."""
    turns = history[-HISTORY_TURNS:] if history else []
    if not turns:
        return "CONVERSATION SO FAR: (none)"
    lines = ["CONVERSATION SO FAR:"]
    for turn in turns:
        lines.append(f"{str(turn.get('role') or 'user')}: {str(turn.get('content') or '')}")
    return "\n".join(lines)


def _render_graph(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> str:
    """Render the entity/edge list with stances for the prompt."""
    names = {node["id"]: node["name"] for node in nodes}
    lines = ["ENTITIES:"]
    for node in nodes:
        lines.append(
            f"- [{node['type']}] {node['name']}: "
            f"{node['description'] or '(no description)'}"
        )
    lines.append("EDGES:")
    for edge in edges:
        descriptions = "; ".join(edge["descriptions"])
        lines.append(
            f"- {names.get(edge['from'], edge['from'])} -[{edge['rel_type']}]-> "
            f"{names.get(edge['to'], edge['to'])} weight={edge['weight']} "
            f"stances={edge['stances']} {descriptions}"
        )
    return "\n".join(lines)


def _local_answer(
    question: str,
    history: list[dict[str, str]],
    settings: Settings,
    usage: dict[str, int],
) -> dict[str, Any]:
    """Local mode: graph neighbourhood + chunk retrieval + quote citations."""
    vector = embed_texts([question], settings, usage)[0]
    entities = _select_entities(question, vector)
    nodes, edges = _graph_context(entities, settings)
    edge_sources = sorted(
        {
            ref["source_id"]
            for edge in edges
            for ref in edge["source_refs"]
            if ref["source_id"]
        }
    )
    chunks = _select_chunks(vector, edge_sources)
    quotes = _quotes_for(chunks)
    passages = _compress_passages(
        [chunk["text"] for chunk in chunks], question, settings, usage
    )
    template = LOCAL_PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        template.replace("{{history}}", _render_history(history))
        .replace("{{question}}", question)
        .replace("{{graph}}", _render_graph(nodes, edges))
        .replace("{{passages}}", passages)
        .replace("{{quotes}}", json.dumps(quotes, ensure_ascii=False))
    )
    raw = _ask(prompt, settings, usage)
    answer_md = str(raw.get("answer_md") or "")
    raw_citations = [
        item for item in (raw.get("citations") or []) if isinstance(item, dict)
    ]
    unknowns = [
        str(item) for item in (raw.get("unknowns") or []) if str(item).strip()
    ]
    final_md, citations = _finalize_local(answer_md, raw_citations, chunks)
    return {
        "answer_md": final_md,
        "citations": citations,
        "mode_used": "local",
        "entities": entities,
        "communities": [],
        "unknowns": unknowns,
    }


# -------------------------------------------------------------------- global


def _report_summary(report_md: str) -> str:
    """The prose under the report title, before its Findings section."""
    text = (report_md or "").strip()
    if text.startswith("# "):
        text = text.split("\n", 1)[1] if "\n" in text else ""
    return text.split("\n## Findings", 1)[0].strip()


def _load_reports() -> list[dict[str, Any]]:
    """The level-1 community reports plus the company report."""
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT id::text, level, title, report_md, findings "
            "FROM cmap.community WHERE level IN (1, 2) "
            "AND graph_version = (SELECT COALESCE(MAX(version), 0) FROM cmap.graph_version) "
            "ORDER BY level, title"
        ).fetchall()
    reports: list[dict[str, Any]] = []
    for report_id, level, title, report_md, findings in rows:
        if not isinstance(findings, list):
            findings = []
        reports.append(
            {
                "id": report_id,
                "level": int(level),
                "title": str(title or ""),
                "summary": _report_summary(str(report_md or "")),
                "findings": [item for item in findings if isinstance(item, dict)],
            }
        )
    return reports


def _reports_context(reports: list[dict[str, Any]]) -> str:
    """Render the reports with their findings' source ids for citing."""
    lines = ["REPORTS:"]
    for report in reports:
        lines.append(f"## {report['title']}")
        lines.append(report["summary"])
        for finding in report["findings"]:
            source_ids = [
                str(source_id) for source_id in (finding.get("source_ids") or [])
            ]
            lines.append(
                f"- [{finding.get('kind', '')}] {finding.get('text', '')} "
                f"(sources: {', '.join(source_ids)})"
            )
    return "\n".join(lines)


def _points_context(points: list[dict[str, Any]]) -> str:
    """Render mapped points (the map-reduce middle step) as the report context."""
    lines = ["MAPPED POINTS:"]
    for point in points:
        source_ids = [str(source_id) for source_id in (point.get("source_ids") or [])]
        lines.append(
            f"- [{point.get('relevance', '')}] {point.get('text', '')} "
            f"(sources: {', '.join(source_ids)})"
        )
    return "\n".join(lines)


def _map_points(
    question: str,
    reports: list[dict[str, Any]],
    settings: Settings,
    usage: dict[str, int],
) -> list[dict[str, Any]]:
    """Map step: one frontier call per 10 reports, keeping relevant points."""
    template = MAP_PROMPT_PATH.read_text(encoding="utf-8")
    points: list[dict[str, Any]] = []
    for start in range(0, len(reports), MAP_BATCH):
        batch = reports[start : start + MAP_BATCH]
        prompt = (
            template.replace("{{question}}", question)
            .replace("{{reports}}", _reports_context(batch))
        )
        raw = _ask(prompt, settings, usage)
        for item in raw.get("points") or []:
            if not isinstance(item, dict):
                continue
            try:
                relevance = float(item.get("relevance") or 0)
            except (TypeError, ValueError):
                relevance = 0.0
            points.append(
                {
                    "text": str(item.get("text") or ""),
                    "source_ids": [
                        str(source_id)
                        for source_id in (item.get("source_ids") or [])
                        if str(source_id).strip()
                    ],
                    "relevance": relevance,
                }
            )
    points.sort(key=lambda point: point["relevance"], reverse=True)
    return points


def _global_answer(
    question: str,
    history: list[dict[str, str]],
    settings: Settings,
    usage: dict[str, int],
) -> dict[str, Any]:
    """Global mode: synthesise the community reports, citing finding sources."""
    reports = _load_reports()
    context = _reports_context(reports)
    if _tokens(context) > GLOBAL_ONE_SHOT_TOKENS:
        context = _points_context(
            _map_points(question, reports, settings, usage)
        )
    template = GLOBAL_PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        template.replace("{{history}}", _render_history(history))
        .replace("{{question}}", question)
        .replace("{{reports}}", context)
    )
    raw = _ask(prompt, settings, usage)
    answer_md = str(raw.get("answer_md") or "")
    raw_citations = [
        item for item in (raw.get("citations") or []) if isinstance(item, dict)
    ]
    unknowns = [
        str(item) for item in (raw.get("unknowns") or []) if str(item).strip()
    ]
    final_md, citations = _finalize_global(answer_md, raw_citations, settings, usage)
    return {
        "answer_md": final_md,
        "citations": citations,
        "mode_used": "global",
        "entities": [],
        "communities": [
            {"id": report["id"], "level": report["level"], "title": report["title"]}
            for report in reports
        ],
        "unknowns": unknowns,
    }


def _shift_markers(answer_md: str, offset: int) -> str:
    """Renumber [n] markers by ``offset`` for a merged answer."""
    return _MARKER.sub(lambda match: f"[{int(match.group(1)) + offset}]", answer_md)


def _merge_answers(local: dict[str, Any], global_: dict[str, Any]) -> dict[str, Any]:
    """Merge both modes: local prose first, then the company-wide view."""
    offset = len(local["citations"])
    return {
        "answer_md": local["answer_md"] + "\n\n" + _shift_markers(global_["answer_md"], offset),
        "citations": list(local["citations"]) + list(global_["citations"]),
        "mode_used": "both",
        "entities": local["entities"],
        "communities": global_["communities"],
        "unknowns": list(local["unknowns"]) + list(global_["unknowns"]),
    }


def answer_question(
    question: str,
    mode: str = "auto",
    history: list[dict[str, str]] | None = None,
    settings: Settings | None = None,
    usage: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Answer one question; return the step-9 response shape.

    ``mode`` is ``auto``, ``local`` or ``global``. The caller owns any
    session state: only ``history``'s last turns are used, never stored.
    """
    cfg = settings if settings is not None else get_settings()
    counters = usage if usage is not None else {}
    turns = list(history or [])
    text = question.strip()
    if not text:
        raise AnswerError("question is required")
    if mode not in {"auto", "local", "global"}:
        raise AnswerError("mode must be auto, local or global")
    if mode == "auto":
        mode = _route_mode(text, cfg, counters)
    if mode == "local":
        return _local_answer(text, turns, cfg, counters)
    if mode == "global":
        return _global_answer(text, turns, cfg, counters)
    return _merge_answers(
        _local_answer(text, turns, cfg, counters),
        _global_answer(text, turns, cfg, counters),
    )
