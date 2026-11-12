"""Function assignment for sources, chunks and entities (repair plan C2).

Job ``function_assign`` (queued after ``resolve``) classifies every chunk
against the curated function list (``cmap.function``, repair C1) with a model
call on the flat seat — multi-label, 0–3 functions with weights — then rolls
the chunk rows up: a source's functions are the weighted union of its chunks'
rows, an entity's functions are the weighted union of the chunks that mention
it, so a hand-off step mentioned in two functions' passages carries both.

Two strong priors shape each chunk's assignment and must not blindly steer it:
``cmap.source.department_hint`` and the speaker's profile department
(``cmap.employee_flags.department``, matched through the C1 aliases). They
augment the model's evidence — they add their function and lift a weak weight
— but they never remove or cap a function the passage clearly belongs to
(``test_hint_is_prior_not_override``).

``origin='admin'`` rows (set on the source and entity pages) are never
overwritten: every re-run replaces only the ``origin='auto'`` rows. Chunks are
classified once per prompt (``cmap.extraction`` stage ``'function'`` marks it,
like the relations pass), so re-runs are cheap and a job retry resumes where
it stopped. Model ids never appear here; the flat seat decides.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from psycopg.types.json import Json

from brain.config import Settings, get_settings
from brain.db import get_pool
from brain.llm import message_content, post_chat_with_rescue
from brain.seats import stage_model

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "function_assign.md"
B1_SEED_PATH = Path(__file__).resolve().parents[1] / "eval" / "questions.b1.json"

# A prior (department hint, speaker's profile department) is strong enough to
# supply a function the model missed and to lift a weak weight to this floor —
# but never to remove or cap the model's own evidence.
PRIOR_WEIGHT = 0.5
MAX_MODEL_FUNCTIONS = 3
MAX_TOKENS = 2000
# A source whose chunks carry no function at all still lands in one function
# (the live gate is "every source has >= 1 function"); this is the vocabulary's
# company-wide bucket, written at a low weight and logged, never silent.
FALLBACK_FUNCTION_KEY = "executive-company-wide"
FALLBACK_WEIGHT = 0.3

PROJECTION = "id::text, key, name, description"


class FunctionAssignError(RuntimeError):
    """Raised when the assignment stage cannot finish."""


def load_functions(conn: Any) -> list[dict[str, Any]]:
    """The active function vocabulary, curated rows first."""
    rows = conn.execute(
        f"SELECT {PROJECTION} FROM cmap.function WHERE active ORDER BY sort, name"
    ).fetchall()
    return [
        {"id": row[0], "key": row[1], "name": row[2], "description": row[3]}
        for row in rows
    ]


def function_for_label(conn: Any, label: str) -> dict[str, Any] | None:
    """The function a department/title label maps to, via the C1 vocabulary.

    Case-insensitive exact match on the function's name, key or any alias
    (``cmap.function.aliases`` holds the Department names and hints the seed
    was clustered from). Returns the first curated match, else None.
    """
    cleaned = (label or "").strip()
    if not cleaned:
        return None
    row = conn.execute(
        f"SELECT {PROJECTION} FROM cmap.function WHERE active AND ("
        " lower(btrim(name)) = lower(%s) OR key = lower(%s) OR EXISTS ("
        "   SELECT 1 FROM unnest(aliases) a WHERE lower(btrim(a)) = lower(%s))) "
        "ORDER BY sort LIMIT 1",
        (cleaned, cleaned, cleaned),
    ).fetchone()
    if row is None:
        return None
    return {"id": row[0], "key": row[1], "name": row[2], "description": row[3]}


def load_function_assign_prompt() -> str:
    """Return the runtime prompt text (plan §8: prompts live in Markdown)."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def function_assign_prompt_hash() -> str:
    """Hash of the prompt file, recorded on every extraction row."""
    prompt_sha = hashlib.sha256(load_function_assign_prompt().encode("utf-8")).hexdigest()
    return hashlib.sha256(f"function_assign:{prompt_sha}".encode()).hexdigest()


def build_prompt(chunk_text: str, functions: list[dict[str, Any]]) -> str:
    """Fill ``prompts/function_assign.md`` for one chunk."""
    functions_json = json.dumps(
        [
            {
                "key": item["key"],
                "name": item["name"],
                "description": item["description"],
            }
            for item in functions
        ],
        ensure_ascii=False,
    )
    return (
        load_function_assign_prompt()
        .replace("{{functions_json}}", functions_json)
        .replace("{{chunk_text}}", chunk_text)
    )


def _post_chat(
    messages: list[dict[str, Any]], settings: Settings, max_tokens: int = MAX_TOKENS
) -> dict[str, Any]:
    """POST one flat-seat chat-completions request in JSON mode."""
    model = stage_model(settings, "flat")
    if model is None:
        raise FunctionAssignError("no model on the flat seat (BRAIN_FLAT_MODEL / BRAIN_FRONTIER_MODEL)")
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
        error_cls=FunctionAssignError,
        label="flat function assign",
    )


def _weight(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return min(1.0, max(0.0, number))


def validate_response(
    payload: dict[str, Any], known: dict[str, str]
) -> dict[str, float]:
    """Keep the model's 0–3 known function keys with clamped weights.

    ``known`` maps function key -> function id. Unknown keys and malformed
    weights are dropped; more than three picks keep the three strongest.
    """
    picked: dict[str, float] = {}
    for item in payload.get("functions") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        weight = _weight(item.get("weight"))
        if key not in known or weight is None or key in picked:
            continue
        picked[key] = weight
    if len(picked) > MAX_MODEL_FUNCTIONS:
        strongest = sorted(picked, key=picked.get, reverse=True)[:MAX_MODEL_FUNCTIONS]
        picked = {key: picked[key] for key in strongest}
    return picked


def merge_priors(
    evidence: dict[str, float], priors: dict[str, float]
) -> dict[str, float]:
    """Fold the strong priors into the model's evidence.

    The prior is a prior, not an override: it adds its function when the model
    found none of it and lifts a weaker weight up to its own, but it never
    removes or caps a function the passage's evidence supports.
    """
    merged = dict(evidence)
    for key, prior in priors.items():
        merged[key] = max(merged.get(key, 0.0), prior)
    return merged


def _parse_response(body: dict[str, Any]) -> dict[str, Any]:
    raw = message_content(body)
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise FunctionAssignError("function assign response is not JSON") from exc
    if not isinstance(payload, dict):
        raise FunctionAssignError("function assign response is not a JSON object")
    return payload


def classify_chunk(
    chunk_text: str,
    functions: list[dict[str, Any]],
    priors: dict[str, float],
    settings: Settings,
) -> dict[str, float]:
    """One chunk's function weights: model evidence merged with the priors."""
    known = {item["key"]: item["id"] for item in functions}
    if not known:
        raise FunctionAssignError("no active functions to classify against")
    body = _post_chat(
        [{"role": "user", "content": build_prompt(chunk_text, functions)}],
        settings,
    )
    evidence = validate_response(_parse_response(body), known)
    return merge_priors(evidence, priors)


def _speaker_priors(conn: Any, speaker: str | None) -> dict[str, float]:
    """The speaker's profile department as a prior (transcript chunks)."""
    if not speaker or not speaker.strip():
        return {}
    priors: dict[str, float] = {}
    rows = conn.execute(
        "SELECT DISTINCT f.department FROM public.employees e "
        "JOIN cmap.employee_flags f ON f.employee_id = e.id "
        "WHERE lower(btrim(e.name)) = lower(btrim(%s))",
        (speaker,),
    ).fetchall()
    for (department,) in rows:
        function = function_for_label(conn, str(department or ""))
        if function is not None:
            priors[function["key"]] = PRIOR_WEIGHT
    return priors


def _hint_prior(conn: Any, department_hint: str | None) -> dict[str, float]:
    """The source's ``department_hint`` as a prior."""
    function = function_for_label(conn, department_hint or "")
    return {function["key"]: PRIOR_WEIGHT} if function else {}


def _pending_chunks(conn: Any, prompt_hash: str) -> list[dict[str, Any]]:
    """Chunks with no classifier run for this prompt, with their prior inputs."""
    rows = conn.execute(
        "SELECT c.id::text, c.text, c.locator, s.department_hint "
        "FROM cmap.chunk c JOIN cmap.source s ON s.id = c.source_id "
        "WHERE NOT EXISTS (SELECT 1 FROM cmap.extraction e "
        "  WHERE e.chunk_id = c.id AND e.stage = 'function' AND e.prompt_hash = %s) "
        "ORDER BY s.created_at, c.ordinal",
        (prompt_hash,),
    ).fetchall()
    return [
        {
            "chunk_id": row[0],
            "text": row[1],
            "speaker": (row[2] or {}).get("speaker"),
            "department_hint": row[3],
        }
        for row in rows
    ]


def _write_chunk_functions(
    conn: Any,
    chunk_id: str,
    weights: dict[str, float],
    known: dict[str, str],
    prompt_hash: str,
    model: str,
    payload: dict[str, Any],
) -> None:
    """Store one chunk's auto rows and its classifier marker.

    Only ``origin='auto'`` rows are replaced; a pair the admin has set keeps
    its admin row untouched (``test_admin_assignment_survives_rerun``).
    """
    conn.execute(
        "DELETE FROM cmap.chunk_function WHERE chunk_id = %s AND origin = 'auto'",
        (chunk_id,),
    )
    for key, weight in weights.items():
        conn.execute(
            "INSERT INTO cmap.chunk_function (chunk_id, function_id, weight, origin) "
            "VALUES (%s, %s, %s, 'auto') "
            "ON CONFLICT (chunk_id, function_id) DO NOTHING",
            (chunk_id, known[key], weight),
        )
    conn.execute(
        "DELETE FROM cmap.extraction WHERE chunk_id = %s AND stage = 'function' "
        "AND prompt_hash <> %s",
        (chunk_id, prompt_hash),
    )
    conn.execute(
        "INSERT INTO cmap.extraction (chunk_id, stage, prompt_hash, model, payload) "
        "VALUES (%s, 'function', %s, %s, %s) "
        "ON CONFLICT (chunk_id, stage, prompt_hash) DO NOTHING",
        (chunk_id, prompt_hash, model, Json(payload)),
    )


def _aggregate_sources(conn: Any, known: dict[str, str]) -> int:
    """Recompute every source's auto rows as the weighted union of its chunks.

    Admin rows survive (``ON CONFLICT DO NOTHING``); a source left with no
    function at all falls back to the company-wide function, logged, so the
    live "every source has >= 1 function" gate holds.
    """
    conn.execute("DELETE FROM cmap.source_function WHERE origin = 'auto'")
    conn.execute(
        "INSERT INTO cmap.source_function (source_id, function_id, weight, origin) "
        "SELECT ch.source_id, cf.function_id, max(cf.weight), 'auto' "
        "FROM cmap.chunk_function cf JOIN cmap.chunk ch ON ch.id = cf.chunk_id "
        "GROUP BY ch.source_id, cf.function_id "
        "ON CONFLICT (source_id, function_id) DO NOTHING"
    )
    # A source with no row at all — no chunk function and no admin row — falls
    # back to the company-wide function so every source keeps >= 1 function.
    empty = conn.execute(
        "SELECT s.id::text FROM cmap.source s WHERE NOT EXISTS "
        "(SELECT 1 FROM cmap.source_function sf WHERE sf.source_id = s.id)"
    ).fetchall()
    fallback_id = known.get(FALLBACK_FUNCTION_KEY)
    for (source_id,) in empty:
        if fallback_id is None:
            logger.warning(
                "source %s carried no function and %s is not in the vocabulary",
                source_id,
                FALLBACK_FUNCTION_KEY,
            )
            continue
        conn.execute(
            "INSERT INTO cmap.source_function (source_id, function_id, weight, origin) "
            "VALUES (%s, %s, %s, 'auto') "
            "ON CONFLICT (source_id, function_id) DO NOTHING",
            (source_id, fallback_id, FALLBACK_WEIGHT),
        )
        logger.warning(
            "source %s carried no function; assigned %s at weight %.2f",
            source_id,
            FALLBACK_FUNCTION_KEY,
            FALLBACK_WEIGHT,
        )
    covered = conn.execute(
        "SELECT count(DISTINCT source_id) FROM cmap.source_function"
    ).fetchone()[0]
    return int(covered)


def _aggregate_entities(conn: Any) -> int:
    """Recompute every entity's auto rows from the chunks that mention it.

    An entity mentioned in chunks of two functions carries both — the
    hand-off case (``test_handoff_entity_in_two_functions``). Admin rows
    survive; entities with no matching chunks simply keep none.
    """
    conn.execute("DELETE FROM cmap.entity_function WHERE origin = 'auto'")
    conn.execute(
        "INSERT INTO cmap.entity_function (entity_id, function_id, weight, origin) "
        "SELECT m.entity_id, cf.function_id, max(cf.weight), 'auto' "
        "FROM cmap.mention m JOIN cmap.chunk_function cf ON cf.chunk_id = m.chunk_id "
        "WHERE m.entity_id IS NOT NULL "
        "GROUP BY m.entity_id, cf.function_id "
        "ON CONFLICT (entity_id, function_id) DO NOTHING"
    )
    return int(
        conn.execute(
            "SELECT count(DISTINCT entity_id) FROM cmap.entity_function"
        ).fetchone()[0]
    )


def backfill_eval_functions(conn: Any) -> int:
    """Pre-fill ``cmap.eval_question.function`` from the B1 question metadata.

    Idempotent: only rows whose ``function`` is still NULL are filled, so an
    admin's later edit on the eval page is never clobbered.
    """
    if not B1_SEED_PATH.exists():
        return 0
    data = json.loads(B1_SEED_PATH.read_text(encoding="utf-8"))
    filled = 0
    for item in data.get("questions") or []:
        names = [
            str(name).strip()
            for name in item.get("functions") or []
            if str(name).strip()
        ]
        question = str(item.get("question") or "")
        if not names or not question:
            continue
        row = conn.execute(
            "UPDATE cmap.eval_question SET function = %s "
            "WHERE question = %s AND function IS NULL RETURNING id",
            (names, question),
        ).fetchone()
        if row is not None:
            filled += 1
    return filled


def run_function_assign(settings: Settings | None = None) -> dict[str, int]:
    """Classify pending chunks, roll up source/entity rows, backfill eval."""
    cfg = settings if settings is not None else get_settings()
    with get_pool().connection() as conn:
        functions = load_functions(conn)
        if not functions:
            raise FunctionAssignError(
                "no active functions in cmap.function; load the C1 vocabulary first"
            )
        known = {item["key"]: item["id"] for item in functions}
        prompt_hash = function_assign_prompt_hash()
        pending = _pending_chunks(conn, prompt_hash)
        conn.commit()

    model = stage_model(cfg, "flat")
    if model is None:
        raise FunctionAssignError("no model on the flat seat (BRAIN_FLAT_MODEL / BRAIN_FRONTIER_MODEL)")
    classified = 0
    with get_pool().connection() as conn:
        for item in pending:
            priors = _hint_prior(conn, item["department_hint"])
            priors.update(_speaker_priors(conn, item["speaker"]))
            weights = classify_chunk(item["text"], functions, priors, cfg)
            payload = {"functions": [{"key": key, "weight": w} for key, w in weights.items()]}
            _write_chunk_functions(
                conn, item["chunk_id"], weights, known, prompt_hash, model, payload
            )
            conn.commit()
            classified += 1

    with get_pool().connection() as conn:
        sources = _aggregate_sources(conn, known)
        entities = _aggregate_entities(conn)
        eval_filled = backfill_eval_functions(conn)
        conn.commit()
    stats = {
        "classified": classified,
        "sources": sources,
        "entities": entities,
        "eval_filled": eval_filled,
    }
    logger.info("function_assign %s", stats)
    return stats


def handle_function_assign(job: dict[str, Any]) -> None:
    """Job ``function_assign``: classify chunks and roll up the assignments."""
    stats = run_function_assign()
    job_id = job.get("id")
    if job_id is not None:
        with get_pool().connection() as conn:
            conn.execute(
                "UPDATE cmap.job SET payload = jsonb_set(payload, '{stats}', %s::jsonb) WHERE id = %s",
                (Json(stats), job_id),
            )
            conn.commit()
    logger.info("function_assign job=%s stats=%s", job_id, stats)
