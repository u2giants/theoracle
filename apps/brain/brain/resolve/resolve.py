"""Entity resolution: merge the same thing named differently (plan step 6).

Job ``resolve`` runs over the whole corpus but only touches mentions with
``entity_id IS NULL``. Each mention goes through, in order:

1. the alias table ``(entity_type, normalized_name)``;
2. an exact match with an already resolved mention (adds the alias);
3. for a Person named by a single first name or initials, the one resolved
   Person whose canonical name starts with it (several → the judge);
4. the nearest entity of the same type by embedding, assigned at cosine ≥ 0.92;
5. the frontier judge (``prompts/resolve_judge.md``) for up to five candidates
   with cosine in [0.80, 0.92), assigned when it names one at confidence ≥ 0.7;
6. otherwise a new entity.

Every judge verdict lands in ``cmap.resolve_decision`` so a later pass never
asks the same (mention, candidate) pair again. After the pass every touched
entity gets fresh counts, and an entity with three or more mentions whose
description was not yet written for that count gets a frontier-written
description and canonical name (``prompts/entity_describe.md``).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import psycopg

from brain.config import Settings, get_settings
from brain.db import get_pool
from brain.embed import embed_texts, vector_literal
from brain.extract.flat import OPENROUTER_BASE_URL
from brain.extract.relations import DEFAULT_MAX_FRONTIER_CALLS, _complete_items

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
JUDGE_PROMPT_PATH = PROMPTS_DIR / "resolve_judge.md"
DESCRIBE_PROMPT_PATH = PROMPTS_DIR / "entity_describe.md"

ASSIGN_COSINE = 0.92
JUDGE_COSINE = 0.80
JUDGE_MAX_CANDIDATES = 5
JUDGE_MIN_CONFIDENCE = 0.7
EMBED_TOP_K = 5
DESCRIBE_MIN_MENTIONS = 3
DESCRIBE_MAX_QUOTES = 12
CANDIDATE_SAMPLE_QUOTES = 2
MAX_TOKENS = 4000

_INITIALS = re.compile(r"^(?:[A-Za-z]\.\s*){1,3}$|^[A-Z]{1,3}$")
_FIELD_RE = re.compile(
    r'"(canonical_name|description|same_as|reason|title|summary)"\s*:\s*"((?:[^"\\]|\\.)*)"'
    r'|"confidence"\s*:\s*(-?\d+(?:\.\d+)?)'
)


class ResolveError(RuntimeError):
    """Raised when the resolve stage cannot finish."""


class FrontierCapReached(ResolveError):
    """Raised when ``BRAIN_MAX_FRONTIER_CALLS_PER_JOB`` is used up."""


@dataclass
class Mention:
    """One unresolved mention as the resolver sees it."""

    id: str
    entity_type: str
    surface_name: str
    normalized_name: str
    description: str | None
    quote: str
    source_title: str
    has_embedding: bool


@dataclass
class Candidate:
    """One entity offered to the judge."""

    id: str
    canonical_name: str
    description: str | None
    cosine: float


def prompt_hash(path: Path) -> str:
    """Hash of one prompt file (plan §8: prompts are versioned by hash)."""
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def _post_chat(messages: list[dict[str, Any]], settings: Settings) -> dict[str, Any]:
    """POST one frontier chat-completions request in JSON mode."""
    if settings.openrouter_api_key is None:
        raise ResolveError("OPENROUTER_API_KEY is not set")
    if settings.brain_frontier_model is None:
        raise ResolveError("BRAIN_FRONTIER_MODEL is not set")
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
        raise ResolveError(
            f"frontier resolve call failed: {response.status_code} {response.text[:200]}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise ResolveError("frontier resolve response is not JSON") from exc


class _Frontier:
    """Frontier calls under the per-job cap, with usage counters."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.usage: dict[str, int] = {}

    def ask(self, prompt: str) -> dict[str, Any]:
        cap = self.settings.brain_max_frontier_calls_per_job
        if cap is None:
            cap = DEFAULT_MAX_FRONTIER_CALLS
        used = self.usage.get("frontier_calls", 0)
        if used >= cap:
            raise FrontierCapReached(
                f"BRAIN_MAX_FRONTIER_CALLS_PER_JOB cap of {cap} reached; "
                "rerun the resolve job to continue (resolved mentions are skipped)"
            )
        self.usage["frontier_calls"] = used + 1
        body = _post_chat([{"role": "user", "content": prompt}], self.settings)
        tokens = (body.get("usage") or {}).get("total_tokens")
        if isinstance(tokens, int):
            self.usage["frontier_tokens"] = (
                self.usage.get("frontier_tokens", 0) + tokens
            )
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ResolveError(
                "frontier resolve response has no message content"
            ) from exc
        start, end = content.find("{"), content.rfind("}")
        if 0 <= start < end:
            # Models sometimes answer with a trailing comma before the closing
            # brace or bracket; Python's json cannot, so drop it first.
            text = re.sub(r",(\s*[}\]])", r"\1", content[start : end + 1])
            try:
                value = json.loads(text, strict=False)
            except json.JSONDecodeError:
                value = None
            if isinstance(value, dict):
                return value
        salvaged = _salvage_fields(content)
        if salvaged:
            return salvaged
        raise ResolveError(f"resolve response is not JSON: {content[:300]!r}")


def _salvage_fields(content: str) -> dict[str, Any]:
    """Pull complete known fields out of a truncated JSON answer.

    A describe answer cut off at ``max_tokens`` has no closing brace; the
    fields that did finish are still usable (same spirit as the step-5
    relations parser keeping complete items).
    """
    out: dict[str, Any] = {}
    for match in _FIELD_RE.finditer(content):
        if match.group(1) is not None:
            out[match.group(1)] = match.group(2)
        else:
            out["confidence"] = float(match.group(3))
    for name in ("findings", "open_questions"):
        items = _complete_items(content, name)
        if items:
            out[name] = items
    return out


def title_case(name: str) -> str:
    """Title Case a non-Person name without lowering acronyms (``QA``, ``PO``)."""
    words = name.strip().split()
    return " ".join(
        word if word.isupper() else word[:1].upper() + word[1:] for word in words
    )


def is_initials(surface: str) -> bool:
    """``J.``, ``J. S.``, ``JS`` are initials; ``Jo`` is a first name."""
    return bool(_INITIALS.match(surface.strip()))


def name_part_matches(surface: str, normalized: str, canonical: str) -> bool:
    """Plan step 6 rule 3: a first name or initials that start a canonical name."""
    words = canonical.casefold().replace(".", " ").split()
    if not words:
        return False
    if is_initials(surface):
        letters = [char for char in surface.casefold() if char.isalpha()]
        if len(letters) > len(words):
            return False
        return all(
            words[index].startswith(letter) for index, letter in enumerate(letters)
        )
    return words[0] == normalized


# --------------------------------------------------------------------- database


def _load_unresolved(conn: psycopg.Connection) -> list[Mention]:
    """Unresolved mentions, longest names first so full names seed entities."""
    rows = conn.execute(
        "SELECT m.id, m.entity_type, m.surface_name, m.normalized_name, m.description, "
        "m.quote, s.title, m.embedding IS NOT NULL "
        "FROM cmap.mention m JOIN cmap.chunk c ON c.id = m.chunk_id "
        "JOIN cmap.source s ON s.id = c.source_id "
        "WHERE m.entity_id IS NULL "
        "ORDER BY m.entity_type, length(m.normalized_name) DESC, s.created_at, c.ordinal, m.id"
    ).fetchall()
    return [
        Mention(
            id=str(row[0]),
            entity_type=str(row[1]),
            surface_name=str(row[2]),
            normalized_name=str(row[3]),
            description=row[4],
            quote=str(row[5]),
            source_title=str(row[6]),
            has_embedding=bool(row[7]),
        )
        for row in rows
    ]


def _assign(
    conn: psycopg.Connection, mention: Mention, entity_id: str, touched: set[str]
) -> None:
    """Point the mention at the entity and record its name as an alias."""
    conn.execute(
        "UPDATE cmap.mention SET entity_id = %s WHERE id = %s", (entity_id, mention.id)
    )
    if mention.normalized_name:
        conn.execute(
            "INSERT INTO cmap.entity_alias (entity_id, entity_type, normalized_name) "
            "VALUES (%s, %s, %s) ON CONFLICT (entity_type, normalized_name) DO NOTHING",
            (entity_id, mention.entity_type, mention.normalized_name),
        )
    touched.add(entity_id)


def _by_alias(conn: psycopg.Connection, mention: Mention) -> str | None:
    row = conn.execute(
        "SELECT entity_id FROM cmap.entity_alias WHERE entity_type = %s AND normalized_name = %s",
        (mention.entity_type, mention.normalized_name),
    ).fetchone()
    return str(row[0]) if row else None


def _by_exact(conn: psycopg.Connection, mention: Mention) -> str | None:
    row = conn.execute(
        "SELECT entity_id FROM cmap.mention "
        "WHERE entity_type = %s AND normalized_name = %s AND entity_id IS NOT NULL LIMIT 1",
        (mention.entity_type, mention.normalized_name),
    ).fetchone()
    return str(row[0]) if row else None


def _name_part_candidates(
    conn: psycopg.Connection, mention: Mention
) -> list[str] | None:
    """Rule 3 candidates, or None when the rule does not apply to this mention."""
    if mention.entity_type != "Person":
        return None
    if len(mention.normalized_name.split()) != 1 and not is_initials(
        mention.surface_name
    ):
        return None
    rows = conn.execute(
        "SELECT id, canonical_name FROM cmap.entity WHERE entity_type = 'Person'"
    ).fetchall()
    return [
        str(entity_id)
        for entity_id, canonical in rows
        if name_part_matches(
            mention.surface_name, mention.normalized_name, str(canonical)
        )
    ]


def _nearest(
    conn: psycopg.Connection, mention: Mention, ids: list[str] | None = None
) -> list[Candidate]:
    """Top entities of the same type by cosine to the mention embedding."""
    if not mention.has_embedding:
        if ids is None:
            return []
        rows = conn.execute(
            "SELECT id, canonical_name, description, 0.0 FROM cmap.entity WHERE id = ANY(%s::uuid[])",
            (ids,),
        ).fetchall()
    else:
        where = "e.entity_type = %s AND e.embedding IS NOT NULL"
        params: list[Any] = [mention.id, mention.entity_type]
        if ids is not None:
            where = "e.id = ANY(%s::uuid[])"
            params = [mention.id, ids]
        rows = conn.execute(
            "SELECT e.id, e.canonical_name, e.description, "
            "COALESCE(1 - (e.embedding <=> m.embedding), 0.0) AS cosine "
            "FROM cmap.entity e, (SELECT embedding FROM cmap.mention WHERE id = %s) m "
            f"WHERE {where} ORDER BY cosine DESC LIMIT {EMBED_TOP_K}",
            params,
        ).fetchall()
    return [
        Candidate(
            id=str(row[0]),
            canonical_name=str(row[1]),
            description=row[2],
            cosine=float(row[3]),
        )
        for row in rows
    ]


def _past_decisions(conn: psycopg.Connection, mention: Mention) -> dict[str, bool]:
    rows = conn.execute(
        "SELECT candidate_entity_id, decided_same FROM cmap.resolve_decision WHERE mention_id = %s",
        (mention.id,),
    ).fetchall()
    return {str(row[0]): bool(row[1]) for row in rows}


def _sample_quotes(conn: psycopg.Connection, entity_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT quote FROM cmap.mention WHERE entity_id = %s ORDER BY id LIMIT %s",
        (entity_id, CANDIDATE_SAMPLE_QUOTES),
    ).fetchall()
    return [str(row[0]) for row in rows]


def _create_entity(conn: psycopg.Connection, mention: Mention) -> str:
    name = mention.surface_name.strip()
    if mention.entity_type != "Person":
        name = title_case(name)
    row = conn.execute(
        "INSERT INTO cmap.entity (entity_type, canonical_name, description, embedding) "
        "SELECT %s, %s, %s, embedding FROM cmap.mention WHERE id = %s RETURNING id",
        (mention.entity_type, name, mention.description or mention.quote, mention.id),
    ).fetchone()
    return str(row[0])


# ------------------------------------------------------------------------ judge


def build_judge_prompt(
    conn: psycopg.Connection, mention: Mention, candidates: list[Candidate]
) -> str:
    mention_json = json.dumps(
        {
            "name": mention.surface_name,
            "type": mention.entity_type,
            "quote": mention.quote,
            "source_title": mention.source_title,
        },
        ensure_ascii=False,
    )
    candidates_json = json.dumps(
        [
            {
                "id": item.id,
                "canonical_name": item.canonical_name,
                "description": item.description or "",
                "sample_quotes": _sample_quotes(conn, item.id),
            }
            for item in candidates
        ],
        ensure_ascii=False,
    )
    return (
        JUDGE_PROMPT_PATH.read_text(encoding="utf-8")
        .replace("{{mention_json}}", mention_json)
        .replace("{{candidates_json}}", candidates_json)
    )


def _judge(
    conn: psycopg.Connection,
    mention: Mention,
    candidates: list[Candidate],
    frontier: _Frontier,
) -> str | None:
    """Ask the judge once about the not-yet-asked candidates; record every verdict."""
    past = _past_decisions(conn, mention)
    for candidate in candidates:
        if past.get(candidate.id):
            return candidate.id
    fresh = [item for item in candidates if item.id not in past][:JUDGE_MAX_CANDIDATES]
    if not fresh:
        return None
    verdict = frontier.ask(build_judge_prompt(conn, mention, fresh))
    same_as = verdict.get("same_as")
    reason = str(verdict.get("reason") or "")
    try:
        confidence = float(verdict.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    chosen: str | None = None
    for candidate in fresh:
        same = candidate.id == same_as and confidence >= JUDGE_MIN_CONFIDENCE
        if same:
            chosen = candidate.id
        conn.execute(
            "INSERT INTO cmap.resolve_decision (mention_id, candidate_entity_id, decided_same, reason) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (mention_id, candidate_entity_id) DO NOTHING",
            (mention.id, candidate.id, same, reason),
        )
    frontier.usage["judge_calls"] = frontier.usage.get("judge_calls", 0) + 1
    return chosen


# --------------------------------------------------------------------- the pass


def resolve_mention(
    conn: psycopg.Connection,
    mention: Mention,
    frontier: _Frontier,
) -> tuple[str, str]:
    """Run rules 1–6 for one mention; return ``(rule, entity_id)``."""
    entity_id = _by_alias(conn, mention)
    if entity_id is not None:
        return "alias", entity_id
    entity_id = _by_exact(conn, mention)
    if entity_id is not None:
        return "exact", entity_id
    name_part = _name_part_candidates(conn, mention)
    if name_part is not None and len(name_part) == 1:
        return "name_part", name_part[0]
    if name_part is not None and len(name_part) > 1:
        chosen = _judge(conn, mention, _nearest(conn, mention, name_part), frontier)
        if chosen is not None:
            return "judge", chosen
        return "new", _create_entity(conn, mention)
    nearest = _nearest(conn, mention)
    if nearest and nearest[0].cosine >= ASSIGN_COSINE:
        return "embedding", nearest[0].id
    band = [item for item in nearest if JUDGE_COSINE <= item.cosine < ASSIGN_COSINE]
    if band:
        chosen = _judge(conn, mention, band, frontier)
        if chosen is not None:
            return "judge", chosen
    return "new", _create_entity(conn, mention)


def _refresh_counts(conn: psycopg.Connection, entity_ids: set[str]) -> None:
    conn.execute(
        "UPDATE cmap.entity e SET mention_count = c.mentions, source_count = c.sources, "
        "updated_at = now() FROM ("
        "  SELECT m.entity_id, count(*) AS mentions, count(DISTINCT ch.source_id) AS sources "
        "  FROM cmap.mention m JOIN cmap.chunk ch ON ch.id = m.chunk_id "
        "  WHERE m.entity_id = ANY(%s::uuid[]) GROUP BY m.entity_id"
        ") c WHERE e.id = c.entity_id",
        (list(entity_ids),),
    )


def _describe(conn: psycopg.Connection, frontier: _Frontier) -> int:
    """Rewrite description and canonical name for entities with ≥3 new-count mentions.

    Candidates are selected corpus-wide, not from this run's touched entities,
    so a run interrupted by the frontier cap finishes describing on the next run.
    """
    rows = conn.execute(
        "SELECT id, entity_type, mention_count FROM cmap.entity "
        "WHERE mention_count >= %s "
        "AND described_at_count IS DISTINCT FROM mention_count",
        (DESCRIBE_MIN_MENTIONS,),
    ).fetchall()
    template = DESCRIBE_PROMPT_PATH.read_text(encoding="utf-8")
    written = 0
    for entity_id, entity_type, mention_count in rows:
        mentions = conn.execute(
            "SELECT DISTINCT ON (quote) surface_name, quote FROM cmap.mention "
            "WHERE entity_id = %s ORDER BY quote, id",
            (entity_id,),
        ).fetchall()
        names = sorted({str(row[0]) for row in mentions})
        quotes = "\n".join(f"- {row[1]}" for row in mentions[:DESCRIBE_MAX_QUOTES])
        prompt = (
            template.replace("{{entity_type}}", str(entity_type))
            .replace("{{names_json}}", json.dumps(names, ensure_ascii=False))
            .replace("{{quotes}}", quotes)
        )
        result = frontier.ask(prompt)
        name = str(result.get("canonical_name") or "").strip()
        description = str(result.get("description") or "").strip()
        row = conn.execute(
            "UPDATE cmap.entity SET canonical_name = COALESCE(NULLIF(%s, ''), canonical_name), "
            "description = COALESCE(NULLIF(%s, ''), description), described_at_count = %s "
            "WHERE id = %s RETURNING canonical_name, description",
            (name, description, mention_count, entity_id),
        ).fetchone()
        # The embedding follows the rewritten text, one entity per call so a
        # cap-hit interruption cannot leave a described entity stale (step-6
        # drift note on #240).
        vector = embed_texts(
            [f"{str(row[0])} — {str(row[1] or '')}"],
            frontier.settings,
            frontier.usage,
        )[0]
        conn.execute(
            "UPDATE cmap.entity SET embedding = %s::vector WHERE id = %s",
            (vector_literal(vector), entity_id),
        )
        conn.commit()
        written += 1
    return written


def run_resolve(settings: Settings | None = None) -> dict[str, int]:
    """Resolve every unresolved mention; return counts per rule plus usage."""
    cfg = settings if settings is not None else get_settings()
    frontier = _Frontier(cfg)
    stats: dict[str, int] = {}
    touched: set[str] = set()
    with get_pool().connection() as conn:
        try:
            for mention in _load_unresolved(conn):
                rule, entity_id = resolve_mention(conn, mention, frontier)
                _assign(conn, mention, entity_id, touched)
                conn.commit()
                stats[rule] = stats.get(rule, 0) + 1
        finally:
            # Counts stay right for whatever was assigned, even if the cap hit.
            conn.rollback()
            if touched:
                _refresh_counts(conn, touched)
                conn.commit()
        stats["described"] = _describe(conn, frontier)
    stats.update(frontier.usage)
    return stats


def handle_resolve(job: dict[str, Any]) -> None:
    """Job ``resolve``: incremental whole-corpus entity resolution."""
    stats = run_resolve()
    job_id = job.get("id")
    if job_id is not None:
        with get_pool().connection() as conn:
            conn.execute(
                "UPDATE cmap.job SET payload = jsonb_set(payload, '{usage}', %s::jsonb) WHERE id = %s",
                (json.dumps(stats), job_id),
            )
            conn.commit()
    logger.info("resolve stats=%s", stats)
    _enqueue_project()


def _enqueue_project() -> None:
    """Queue one whole-corpus ``project`` job (step 7) unless one is waiting."""
    with get_pool().connection() as conn:
        conn.execute(
            "INSERT INTO cmap.job (kind, payload) SELECT 'project', '{}'::jsonb "
            "WHERE NOT EXISTS (SELECT 1 FROM cmap.job WHERE kind = 'project' AND state = 'queued')"
        )
        conn.commit()
