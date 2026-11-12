"""Contradictions across sources (repair plan D3).

Job ``contradictions`` (queued after ``resolve``, and immediately for an
interview answer's source) looks at pairs of quoted statements that come from
different sources and are conflict-prone — same (from, to, rel_type) pair of
kind OWNS / RESPONSIBLE_FOR / PRECEDES / APPROVES, statements about the same
Rule or Metric entity, and policy-vs-practice stance pairs — and classifies
each pair on the frontier seat (``prompts/contradiction_compare.md``, stage
``contradictions``):

* ``same`` / ``refinement`` — record-only rows in ``cmap.contradiction``
  (``status='explained'``); they are the incremental marker that stops the
  job re-classifying an unchanged pair;
* ``changed-over-time`` — the same claim at different source dates: NOT a
  conflict (``status='explained'``) and kept as the feed D2's supersession
  work can consume. When the pair is not a policy/practice stance pair and
  the two source dates differ, code classifies this without a model call
  ("dates differ -> not a conflict");
* ``policy-vs-practice gap`` / ``true contradiction`` — stored with
  ``status='open'``, shown on ``W/map/contradictions`` and both entities,
  labelled into reports and answers ("sources disagree: ..."), and each
  writes one gap-shaped ``cmap.open_question`` row for F1 addressed to
  the function's most relevant role.

A PRECEDES cycle (entity-level, current relations only) is flagged as a
``precedes_cycle`` contradiction without a model call. An interview answer
that contradicts a document runs the same classifier immediately (the
relations stage queues a scoped scan when the source is an interview answer).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from psycopg.types.json import Json

from brain.config import Settings, get_settings
from brain.db import get_pool
from brain.function_assign import function_for_label
from brain.llm import message_content, post_chat_with_rescue
from brain.seats import stage_model

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "contradiction_compare.md"

CLASS_SAME = "same"
CLASS_REFINEMENT = "refinement"
CLASS_CHANGED = "changed-over-time"
CLASS_POLICY_PRACTICE = "policy-vs-practice gap"
CLASS_TRUE = "true contradiction"
CLASSIFICATIONS = (
    CLASS_SAME,
    CLASS_REFINEMENT,
    CLASS_CHANGED,
    CLASS_POLICY_PRACTICE,
    CLASS_TRUE,
)

KIND_TRUE = "true_contradiction"
KIND_POLICY_PRACTICE = "policy_vs_practice"
KIND_CYCLE = "precedes_cycle"
KIND_CHANGED = "changed_over_time"
KIND_SAME = "same"
KIND_REFINEMENT = "refinement"

_CLASS_TO_KIND = {
    CLASS_TRUE: KIND_TRUE,
    CLASS_POLICY_PRACTICE: KIND_POLICY_PRACTICE,
    CLASS_CHANGED: KIND_CHANGED,
    CLASS_SAME: KIND_SAME,
    CLASS_REFINEMENT: KIND_REFINEMENT,
}

# Kinds stored as open conflicts: shown, labelled in answers/reports, gap for F1.
CONFLICT_KINDS = (KIND_TRUE, KIND_POLICY_PRACTICE, KIND_CYCLE)

CONFLICT_REL_TYPES = frozenset({"OWNS", "RESPONSIBLE_FOR", "PRECEDES", "APPROVES"})
STATEMENT_ENTITY_TYPES = frozenset({"Rule", "Metric"})

MAX_TOKENS = 2000
MAX_PAIRS_PER_GROUP = 12
MAX_DISAGREEMENTS = 10


class ContradictionError(RuntimeError):
    """Raised when the contradiction stage cannot finish a comparison."""


# ------------------------------------------------------------------ prompt


def load_prompt() -> str:
    """Return the runtime prompt text (plan §8: prompts live in Markdown)."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_prompt(rel_a: dict[str, Any], rel_b: dict[str, Any]) -> str:
    """Fill ``prompts/contradiction_compare.md`` for one statement pair."""
    statements = [
        {
            "rel_type": rel["rel_type"],
            "stance": rel["stance"],
            "description": rel["description"],
            "quote": rel["quote"],
            "source_title": rel["source_title"],
            "effective_date": rel["effective_date"].isoformat()
            if rel["effective_date"] is not None
            else None,
        }
        for rel in (rel_a, rel_b)
    ]
    return load_prompt().replace(
        "{{statements_json}}", json.dumps(statements, ensure_ascii=False)
    )


def _post_chat(
    messages: list[dict[str, Any]], settings: Settings
) -> dict[str, Any]:
    """POST one contradiction-classifier chat request on the frontier seat."""
    model = stage_model(settings, "contradictions")
    if model is None:
        raise ContradictionError(
            "no model on the contradictions seat (BRAIN_FRONTIER_MODEL)"
        )
    return post_chat_with_rescue(
        {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": MAX_TOKENS,
            "response_format": {"type": "json_object"},
        },
        settings=settings,
        timeout=180.0,
        error_cls=ContradictionError,
        label="contradiction compare",
    )


def _parse_response(body: dict[str, Any]) -> dict[str, Any]:
    raw = message_content(body)
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise ContradictionError("contradiction response is not JSON") from exc
    if not isinstance(payload, dict):
        raise ContradictionError("contradiction response is not a JSON object")
    return payload


# ------------------------------------------------------------- classification


def _stance_pair(rel_a: dict[str, Any], rel_b: dict[str, Any]) -> bool:
    return {rel_a["stance"], rel_b["stance"]} == {"policy", "practice"}


def _dates_differ(rel_a: dict[str, Any], rel_b: dict[str, Any]) -> bool:
    a = rel_a.get("effective_date")
    b = rel_b.get("effective_date")
    return a is not None and b is not None and a != b


def classify_pair(
    rel_a: dict[str, Any], rel_b: dict[str, Any], settings: Settings
) -> tuple[str, str]:
    """Classify one pair; return ``(classification, summary)``.

    The date rule wins without a model call: outside policy/practice stance
    pairs, differing source dates mean the claim changed over time ("dates
    differ -> not a conflict, feed D2").
    """
    if not _stance_pair(rel_a, rel_b) and _dates_differ(rel_a, rel_b):
        summary = (
            f"Timeline change: “{rel_a['description']}” "
            f"({rel_a['source_title']}, {rel_a['effective_date']}) then "
            f"“{rel_b['description']}” ({rel_b['source_title']}, "
            f"{rel_b['effective_date']}) — the claim changed over time, "
            f"not a contradiction."
        )
        return CLASS_CHANGED, summary
    body = _post_chat(
        [{"role": "user", "content": build_prompt(rel_a, rel_b)}], settings
    )
    payload = _parse_response(body)
    classification = str(payload.get("classification") or "").strip()
    summary = str(payload.get("summary") or "").strip()
    if classification not in CLASSIFICATIONS:
        raise ContradictionError(
            f"contradiction classification {classification!r} is not one of {CLASSIFICATIONS}"
        )
    if not summary:
        raise ContradictionError("contradiction response has no summary")
    return classification, summary


# ---------------------------------------------------------------- candidates


def _load_relations(conn: Any) -> list[dict[str, Any]]:
    """Current, entity-resolved relations with their sources' dates."""
    rows = conn.execute(
        "SELECT r.id::text, r.rel_type, r.stance, r.description, r.quote, "
        "r.chunk_id::text, fm.entity_id::text, tm.entity_id::text, "
        "fm.entity_type, tm.entity_type, "
        "c.source_id::text, s.title, s.effective_date "
        "FROM cmap.relation r "
        "JOIN cmap.mention fm ON fm.id = r.from_mention_id "
        "JOIN cmap.mention tm ON tm.id = r.to_mention_id "
        "JOIN cmap.chunk c ON c.id = r.chunk_id "
        "JOIN cmap.source s ON s.id = c.source_id "
        "WHERE r.status = 'current' "
        "AND fm.entity_id IS NOT NULL AND tm.entity_id IS NOT NULL "
        "ORDER BY s.created_at, r.id"
    ).fetchall()
    return [
        {
            "id": row[0],
            "rel_type": str(row[1]),
            "stance": str(row[2]),
            "description": str(row[3]),
            "quote": str(row[4]),
            "chunk_id": row[5],
            "from_entity": row[6],
            "to_entity": row[7],
            "from_type": str(row[8]),
            "to_type": str(row[9]),
            "source_id": row[10],
            "source_title": str(row[11]),
            "effective_date": row[12],
        }
        for row in rows
    ]


def _pair_key(rel_a: dict[str, Any], rel_b: dict[str, Any]) -> tuple[str, str]:
    return tuple(sorted((rel_a["id"], rel_b["id"])))  # type: ignore[return-value]


def candidate_pairs(
    relations: list[dict[str, Any]], source_id: str | None = None
) -> list[tuple[dict[str, Any], dict[str, Any], str]]:
    """Cross-source conflict-prone pairs, deduped, with the group that found them.

    Groups: same (from, to, rel_type) of kind OWNS/RESPONSIBLE_FOR/PRECEDES/
    APPROVES; statements about the same Rule/Metric entity; policy-vs-practice
    stance pairs on the same (from, to). A scoped run keeps only pairs that
    touch ``source_id``.
    """
    groups: list[tuple[str, list[dict[str, Any]]]] = []
    by_triple: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    by_entity: dict[str, list[dict[str, Any]]] = {}
    by_pair: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = {}
    for rel in relations:
        if rel["rel_type"] in CONFLICT_REL_TYPES:
            key = (rel["from_entity"], rel["to_entity"], rel["rel_type"])
            by_triple.setdefault(key, []).append(rel)
        for entity_id, entity_type in (
            (rel["from_entity"], rel["from_type"]),
            (rel["to_entity"], rel["to_type"]),
        ):
            if entity_type in STATEMENT_ENTITY_TYPES:
                by_entity.setdefault(entity_id, []).append(rel)
        pair = (rel["from_entity"], rel["to_entity"])
        stances = by_pair.setdefault(pair, {"policy": [], "practice": []})
        if rel["stance"] in stances:
            stances[rel["stance"]].append(rel)
    for members in by_triple.values():
        groups.append(("pair", members))
    for members in by_entity.values():
        groups.append(("statement", members))
    for stances in by_pair.values():
        if stances["policy"] and stances["practice"]:
            groups.append(("stance", stances["policy"] + stances["practice"]))

    pairs: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any], str]] = {}
    for group_kind, members in groups:
        picked = 0
        for index, rel_a in enumerate(members):
            for rel_b in members[index + 1 :]:
                if rel_a["source_id"] == rel_b["source_id"]:
                    continue
                if source_id is not None and source_id not in (
                    rel_a["source_id"],
                    rel_b["source_id"],
                ):
                    continue
                key = _pair_key(rel_a, rel_b)
                if key in pairs:
                    continue
                pairs[key] = (rel_a, rel_b, group_kind)
                picked += 1
                if picked >= MAX_PAIRS_PER_GROUP:
                    break
            if picked >= MAX_PAIRS_PER_GROUP:
                break
    return sorted(pairs.values(), key=lambda item: _pair_key(item[0], item[1]))


def _already_seen(conn: Any, rel_a_id: str, rel_b_id: str) -> bool:
    """Whether this pair already has a verdict row (the incremental marker)."""
    row = conn.execute(
        "SELECT 1 FROM cmap.contradiction WHERE "
        "(relation_a = %s::uuid AND relation_b = %s::uuid) "
        "OR (relation_a = %s::uuid AND relation_b = %s::uuid) LIMIT 1",
        (rel_a_id, rel_b_id, rel_b_id, rel_a_id),
    ).fetchone()
    return row is not None


# ------------------------------------------------------------- PRECEDES cycle


def precedes_cycles(relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Entity-level cycles among current PRECEDES relations (self-loops count).

    Each cycle is returned once, rotated to start at its lowest entity id:
    ``{'entities': [entity ids in walk order], 'edges': [relation ids]}`` where
    ``edges[i]`` connects ``entities[i]`` to ``entities[(i + 1) % n]``.
    """
    edges: dict[str, list[tuple[str, str]]] = {}
    for rel in relations:
        if rel["rel_type"] != "PRECEDES":
            continue
        edges.setdefault(rel["from_entity"], []).append((rel["to_entity"], rel["id"]))
    for members in edges.values():
        members.sort(key=lambda item: item[1])
    cycles: dict[tuple[str, ...], dict[str, Any]] = {}
    for start in sorted(edges):
        stack: list[tuple[str, list[str], list[str]]] = [(start, [start], [])]
        while stack:
            node, path, edge_ids = stack.pop()
            for nxt, rel_id in edges.get(node, []):
                walk_edges = edge_ids + [rel_id]
                if nxt == start:
                    key = tuple(sorted(walk_edges))
                    if key in cycles:
                        continue
                    offset = path.index(min(path))
                    cycles[key] = {
                        "entities": path[offset:] + path[:offset],
                        "edges": walk_edges[offset:] + walk_edges[:offset],
                    }
                    continue
                if nxt in path:
                    continue
                stack.append((nxt, path + [nxt], walk_edges))
    return list(cycles.values())


def _cycle_record(
    cycle: dict[str, Any], names: dict[str, str]
) -> tuple[str, str, str, str]:
    """(relation_a, relation_b, summary, question names) for one cycle."""
    edge_ids = cycle["edges"]
    rel_a, rel_b = edge_ids[0], edge_ids[-1]
    entities = cycle["entities"]
    label = " -> ".join(
        names.get(entity_id, entity_id[:8]) for entity_id in entities + [entities[0]]
    )
    summary = f"PRECEDES cycle: {label} (relation ids: {', '.join(sorted(edge_ids))})"
    names_label = " -> ".join(names.get(entity_id, entity_id[:8]) for entity_id in entities)
    return rel_a, rel_b, summary, names_label


# ------------------------------------------------------------------- storing


def _entity_ids_for(rel_a: dict[str, Any], rel_b: dict[str, Any]) -> list[str]:
    seen: list[str] = []
    for rel in (rel_a, rel_b):
        for key in ("from_entity", "to_entity"):
            if rel[key] and rel[key] not in seen:
                seen.append(rel[key])
    return seen


def gap_target(
    conn: Any, entity_ids: list[str], source_ids: list[str]
) -> tuple[str | None, str | None, str | None]:
    """The function's most relevant role for one conflict.

    Returns ``(department, suggested_person, target_employee_id)``: the
    highest-weight function over the entities is the department; the role is
    the ``job_title`` of that function's employee with the most mentions in the
    involved sources (matched through the C1 aliases via ``employee_flags.department``).
    """
    if not entity_ids:
        return None, None, None
    row = conn.execute(
        "SELECT f.key, f.name, sum(ef.weight) AS w FROM cmap.entity_function ef "
        "JOIN cmap.function f ON f.id = ef.function_id "
        "WHERE ef.entity_id = ANY(%s::uuid[]) AND f.active "
        "GROUP BY f.key, f.name ORDER BY w DESC, f.name LIMIT 1",
        (entity_ids,),
    ).fetchone()
    if row is None:
        return None, None, None
    function_key, function_name = str(row[0]), str(row[1])
    employees = conn.execute(
        "SELECT e.id::text, e.name, f.department, f.job_title "
        "FROM public.employees e "
        "JOIN cmap.employee_flags f ON f.employee_id = e.id "
        "WHERE e.disabled_at IS NULL"
    ).fetchall()
    best: tuple[str | None, str | None] | None = None
    best_hits = -1
    for emp_id, name, department, job_title in employees:
        function = function_for_label(conn, str(department or ""))
        if function is None or function["key"] != function_key:
            continue
        hits = int(
            conn.execute(
                "SELECT count(*) FROM cmap.mention m "
                "JOIN cmap.chunk c ON c.id = m.chunk_id "
                "WHERE c.source_id = ANY(%s::uuid[]) "
                "AND lower(btrim(m.surface_name)) = lower(btrim(%s))",
                (source_ids, name),
            ).fetchone()[0]
        )
        if hits > best_hits:
            best = (emp_id, str(job_title or name))
            best_hits = hits
    if best is None:
        return function_name, function_name, None
    return function_name, best[1], best[0]


def _write_gap(
    conn: Any,
    question: str,
    summary: str,
    entity_ids: list[str],
    source_ids: list[str],
) -> None:
    """One gap-shaped ``cmap.open_question`` row for F1 (the gap finder).

    Shape written (F1 owns the full gap machinery later): question, why
    ("Sources disagree: ..."), entity_ids, state='open', priority NULL (not
    vetted — F1 vets), department = the function name, suggested_person =
    the function's most relevant role (job_title), target_employee_id = that
    role's employee when one is known.
    """
    department, suggested_person, target_employee_id = gap_target(
        conn, entity_ids, source_ids
    )
    conn.execute(
        "INSERT INTO cmap.open_question "
        "(question, why, entity_ids, state, department, suggested_person, target_employee_id) "
        "VALUES (%s, %s, %s, 'open', %s, %s, %s::uuid)",
        (
            question,
            f"Sources disagree: {summary}",
            entity_ids,
            department,
            suggested_person,
            target_employee_id,
        ),
    )


def _gap_question(kind: str, rel_a: dict[str, Any], rel_b: dict[str, Any]) -> str:
    if kind == KIND_POLICY_PRACTICE:
        return (
            f"Why does practice differ from the written policy here: "
            f"“{rel_a['description']}” vs “{rel_b['description']}”?"
        )
    return (
        f"Which statement is correct: “{rel_a['description']}” "
        f"or “{rel_b['description']}”?"
    )


def _store_conflict(
    conn: Any,
    rel_a: dict[str, Any],
    rel_b: dict[str, Any],
    kind: str,
    summary: str,
) -> None:
    conn.execute(
        "INSERT INTO cmap.contradiction "
        "(relation_a, relation_b, kind, summary, status) "
        "VALUES (%s::uuid, %s::uuid, %s, %s, 'open')",
        (rel_a["id"], rel_b["id"], kind, summary),
    )
    _write_gap(
        conn,
        _gap_question(kind, rel_a, rel_b),
        summary,
        _entity_ids_for(rel_a, rel_b),
        [rel_a["source_id"], rel_b["source_id"]],
    )


def _store_changed(
    conn: Any, rel_a: dict[str, Any], rel_b: dict[str, Any], summary: str
) -> None:
    """Record a timeline change for D2 — not a conflict, never a gap."""
    conn.execute(
        "INSERT INTO cmap.contradiction "
        "(relation_a, relation_b, kind, summary, status, resolution) "
        "VALUES (%s::uuid, %s::uuid, %s, %s, 'explained', %s)",
        (
            rel_a["id"],
            rel_b["id"],
            KIND_CHANGED,
            summary,
            "dates differ — timeline change, not a conflict; "
            "supersedes-over-time signal for D2",
        ),
    )


def _store_record(
    conn: Any, rel_a: dict[str, Any], rel_b: dict[str, Any], kind: str, summary: str
) -> None:
    """Record a same/refinement verdict — the pair's incremental marker."""
    conn.execute(
        "INSERT INTO cmap.contradiction "
        "(relation_a, relation_b, kind, summary, status, resolution) "
        "VALUES (%s::uuid, %s::uuid, %s, %s, 'explained', %s)",
        (
            rel_a["id"],
            rel_b["id"],
            kind,
            summary,
            "record only — not a conflict",
        ),
    )


# --------------------------------------------------------------------- job


def run_contradictions(
    settings: Settings | None = None, source_id: str | None = None
) -> dict[str, int]:
    """Classify pending pairs, flag PRECEDES cycles, write gaps."""
    cfg = settings if settings is not None else get_settings()
    with get_pool().connection() as conn:
        if source_id is not None:
            unresolved = conn.execute(
                "SELECT 1 FROM cmap.mention m JOIN cmap.chunk c ON c.id = m.chunk_id "
                "WHERE m.entity_id IS NULL AND c.source_id = %s::uuid LIMIT 1",
                (source_id,),
            ).fetchone()
        else:
            unresolved = conn.execute(
                "SELECT 1 FROM cmap.mention WHERE entity_id IS NULL LIMIT 1"
            ).fetchone()
    if unresolved:
        # The immediate interview path must not wait for the debounced resolve.
        from brain.resolve.resolve import run_resolve

        run_resolve(cfg)
    with get_pool().connection() as conn:
        relations = _load_relations(conn)
        pairs = candidate_pairs(relations, source_id=source_id)
        pending: list[tuple[dict[str, Any], dict[str, Any], str]] = []
        for rel_a, rel_b, group_kind in pairs:
            first, second = sorted((rel_a, rel_b), key=lambda rel: rel["id"])
            if _already_seen(conn, first["id"], second["id"]):
                continue
            pending.append((rel_a, rel_b, group_kind))
        conn.commit()

    stats = {
        "pairs_seen": len(pairs),
        "compared": 0,
        "conflicts": 0,
        "changed_over_time": 0,
        "same_or_refinement": 0,
        "cycles": 0,
        "gaps": 0,
    }
    for rel_a, rel_b, group_kind in pending:
        classification, summary = classify_pair(rel_a, rel_b, cfg)
        kind = _CLASS_TO_KIND[classification]
        with get_pool().connection() as conn:
            if kind in (KIND_TRUE, KIND_POLICY_PRACTICE):
                _store_conflict(conn, rel_a, rel_b, kind, summary)
                stats["conflicts"] += 1
                stats["gaps"] += 1
            elif kind == KIND_CHANGED:
                _store_changed(conn, rel_a, rel_b, summary)
                stats["changed_over_time"] += 1
            else:
                _store_record(conn, rel_a, rel_b, kind, summary)
                stats["same_or_refinement"] += 1
            conn.commit()
        stats["compared"] += 1
        logger.info(
            "contradiction pair %s/%s (%s): %s",
            rel_a["id"],
            rel_b["id"],
            group_kind,
            classification,
        )

    with get_pool().connection() as conn:
        names = {
            str(row[0]): str(row[1])
            for row in conn.execute(
                "SELECT id::text, canonical_name FROM cmap.entity "
                "WHERE id = ANY(%s::uuid[])",
                (
                    sorted(
                        {
                            entity_id
                            for rel in relations
                            for entity_id in (rel["from_entity"], rel["to_entity"])
                        }
                    ),
                ),
            ).fetchall()
        }
        for cycle in precedes_cycles(relations):
            rel_a_id, rel_b_id, summary, names_label = _cycle_record(cycle, names)
            exists = conn.execute(
                "SELECT 1 FROM cmap.contradiction WHERE kind = %s AND summary = %s LIMIT 1",
                (KIND_CYCLE, summary),
            ).fetchone()
            if exists is not None:
                continue
            rel_by_id = {rel["id"]: rel for rel in relations}
            if rel_a_id not in rel_by_id or rel_b_id not in rel_by_id:
                continue
            conn.execute(
                "INSERT INTO cmap.contradiction "
                "(relation_a, relation_b, kind, summary, status) "
                "VALUES (%s::uuid, %s::uuid, %s, %s, 'open')",
                (rel_a_id, rel_b_id, KIND_CYCLE, summary),
            )
            entity_ids: list[str] = []
            for entity_id in cycle["entities"]:
                if entity_id not in entity_ids:
                    entity_ids.append(entity_id)
            source_ids = sorted(
                {rel_by_id[edge]["source_id"] for edge in cycle["edges"] if edge in rel_by_id}
            )
            _write_gap(
                conn,
                f"In what order do these steps actually happen: {names_label}?",
                summary,
                entity_ids,
                source_ids,
            )
            conn.commit()
            stats["cycles"] += 1
            stats["gaps"] += 1
    logger.info("contradictions %s", stats)
    return stats


def handle_contradictions(job: dict[str, Any]) -> None:
    """Job ``contradictions``: classify pairs and flag cycles."""
    payload = job.get("payload") or {}
    source_id = payload.get("source_id")
    stats = run_contradictions(source_id=str(source_id) if source_id else None)
    job_id = job.get("id")
    if job_id is not None:
        with get_pool().connection() as conn:
            conn.execute(
                "UPDATE cmap.job SET payload = jsonb_set(payload, '{stats}', %s::jsonb) WHERE id = %s",
                (Json(stats), job_id),
            )
            conn.commit()
    logger.info("contradictions job=%s stats=%s", job_id, stats)


def queue_interview_scan(source_id: str) -> bool:
    """Queue an immediate scoped scan when this source is an interview answer.

    Interview answers enter the pipeline as speaker-attributed transcripts;
    when their relations are extracted this queues the same classifier right
    away (no debounce, no chain wait) so a contradiction with a document is
    caught immediately.
    """
    with get_pool().connection() as conn:
        row = conn.execute(
            "INSERT INTO cmap.job (kind, payload) "
            "SELECT 'contradictions', jsonb_build_object('source_id', %s::text) "
            "WHERE (EXISTS (SELECT 1 FROM cmap.open_question "
            "        WHERE answer_source_id = %s::uuid) "
            "    OR EXISTS (SELECT 1 FROM cmap.teams_intake "
            "        WHERE source_id = %s::uuid)) "
            "AND NOT EXISTS (SELECT 1 FROM cmap.job WHERE kind = 'contradictions' "
            "  AND payload->>'source_id' = %s::text AND state IN ('queued', 'running')) "
            "RETURNING id",
            (source_id, source_id, source_id, source_id),
        ).fetchone()
        conn.commit()
    return row is not None


def after_source_relations(source_id: str) -> None:
    """Relations hook: an interview answer triggers the same path immediately."""
    try:
        queued = queue_interview_scan(source_id)
    except Exception as exc:  # noqa: BLE001 - never break the relations stage
        logger.warning("interview contradiction scan not queued for %s: %s", source_id, exc)
        return
    if queued:
        logger.info("queued immediate contradiction scan for interview source %s", source_id)


# ------------------------------------------------------------------ surfacing


def _disagreement_rows(conn: Any, entity_ids: Any | None = None) -> list[dict[str, Any]]:
    """Open conflict rows with both quoted statements and their source titles."""
    rows = conn.execute(
        "SELECT ct.id::text, ct.kind, ct.summary, "
        "ra.quote, ra.description, ra.rel_type, ra.stance, sa.title, sa.effective_date, "
        "rb.quote, rb.description, rb.rel_type, rb.stance, sb.title, sb.effective_date "
        "FROM cmap.contradiction ct "
        "JOIN cmap.relation ra ON ra.id = ct.relation_a "
        "JOIN cmap.relation rb ON rb.id = ct.relation_b "
        "JOIN cmap.chunk ca ON ca.id = ra.chunk_id "
        "JOIN cmap.chunk cb ON cb.id = rb.chunk_id "
        "JOIN cmap.source sa ON sa.id = ca.source_id "
        "JOIN cmap.source sb ON sb.id = cb.source_id "
        "WHERE ct.status = 'open' AND ct.kind = ANY(%s) "
        "AND (%s::uuid[] IS NULL OR EXISTS ("
        "  SELECT 1 FROM cmap.relation r "
        "  JOIN cmap.mention m ON m.id IN (r.from_mention_id, r.to_mention_id) "
        "  WHERE r.id IN (ct.relation_a, ct.relation_b) "
        "  AND m.entity_id = ANY(%s::uuid[]))) "
        "ORDER BY ct.kind, sa.title",
        (list(CONFLICT_KINDS), entity_ids, entity_ids),
    ).fetchall()
    return [
        {
            "id": row[0],
            "kind": str(row[1]),
            "summary": str(row[2]),
            "relation_a": {
                "quote": str(row[3]),
                "description": str(row[4]),
                "rel_type": str(row[5]),
                "stance": str(row[6]),
                "source_title": str(row[7]),
                "effective_date": row[8].isoformat() if row[8] is not None else None,
            },
            "relation_b": {
                "quote": str(row[9]),
                "description": str(row[10]),
                "rel_type": str(row[11]),
                "stance": str(row[12]),
                "source_title": str(row[13]),
                "effective_date": row[14].isoformat() if row[14] is not None else None,
            },
        }
        for row in rows
    ]


def disagreement_lines(conn: Any, entity_ids: Any | None = None) -> list[str]:
    """``sources disagree: ...`` lines for the open conflicts in scope."""
    return [
        f"sources disagree: {item['summary']} "
        f"({item['relation_a']['source_title']} vs {item['relation_b']['source_title']})"
        for item in _disagreement_rows(conn, entity_ids)[:MAX_DISAGREEMENTS]
    ]


def list_rows(conn: Any) -> list[dict[str, Any]]:
    """Every contradiction row with both quoted statements, for the map page."""
    rows = conn.execute(
        "SELECT ct.id::text, ct.kind, ct.status, ct.summary, ct.resolution, "
        "ct.resolved_by::text, "
        "ra.id::text, ra.quote, ra.description, ra.rel_type, ra.stance, "
        "sa.id::text, sa.title, sa.effective_date, "
        "rb.id::text, rb.quote, rb.description, rb.rel_type, rb.stance, "
        "sb.id::text, sb.title, sb.effective_date "
        "FROM cmap.contradiction ct "
        "JOIN cmap.relation ra ON ra.id = ct.relation_a "
        "JOIN cmap.relation rb ON rb.id = ct.relation_b "
        "JOIN cmap.chunk ca ON ca.id = ra.chunk_id "
        "JOIN cmap.chunk cb ON cb.id = rb.chunk_id "
        "JOIN cmap.source sa ON sa.id = ca.source_id "
        "JOIN cmap.source sb ON sb.id = cb.source_id "
        "WHERE ct.kind NOT IN ('same', 'refinement') "
        "ORDER BY ct.status, ct.kind, sa.title"
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        entities: list[dict[str, str]] = []
        seen_entities: set[str] = set()
        for rel_id in (row[6], row[14]):
            members = conn.execute(
                "SELECT DISTINCT m.entity_id::text, e.canonical_name, e.entity_type "
                "FROM cmap.relation r "
                "JOIN cmap.mention m ON m.id IN (r.from_mention_id, r.to_mention_id) "
                "JOIN cmap.entity e ON e.id = m.entity_id "
                "WHERE r.id = %s::uuid",
                (rel_id,),
            ).fetchall()
            for member in members:
                if str(member[0]) in seen_entities:
                    continue
                seen_entities.add(str(member[0]))
                entities.append(
                    {"id": str(member[0]), "name": str(member[1]), "type": str(member[2])}
                )
        items.append(
            {
                "id": row[0],
                "kind": str(row[1]),
                "status": str(row[2]),
                "summary": str(row[3]),
                "resolution": str(row[4]) if row[4] is not None else None,
                "resolved_by": row[5],
                "relation_a": {
                    "id": row[6],
                    "quote": str(row[7]),
                    "description": str(row[8]),
                    "rel_type": str(row[9]),
                    "stance": str(row[10]),
                    "source_id": row[11],
                    "source_title": str(row[12]),
                    "effective_date": row[13].isoformat() if row[13] is not None else None,
                },
                "relation_b": {
                    "id": row[14],
                    "quote": str(row[15]),
                    "description": str(row[16]),
                    "rel_type": str(row[17]),
                    "stance": str(row[18]),
                    "source_id": row[19],
                    "source_title": str(row[20]),
                    "effective_date": row[21].isoformat() if row[21] is not None else None,
                },
                "entity_ids": [entity["id"] for entity in entities],
                "entities": entities,
            }
        )
    return items


def entity_contradictions(conn: Any, entity_id: str) -> list[dict[str, Any]]:
    """Contradiction rows touching one entity, for its page section."""
    rows = conn.execute(
        "SELECT DISTINCT ct.id::text, ct.kind, ct.status, ct.summary, ct.resolution, "
        "sa.title, sb.title "
        "FROM cmap.contradiction ct "
        "JOIN cmap.relation ra ON ra.id = ct.relation_a "
        "JOIN cmap.relation rb ON rb.id = ct.relation_b "
        "JOIN cmap.chunk ca ON ca.id = ra.chunk_id "
        "JOIN cmap.chunk cb ON cb.id = rb.chunk_id "
        "JOIN cmap.source sa ON sa.id = ca.source_id "
        "JOIN cmap.source sb ON sb.id = cb.source_id "
        "WHERE ct.status <> 'resolved' "
        "AND ct.kind NOT IN ('same', 'refinement') "
        "AND EXISTS ("
        "  SELECT 1 FROM cmap.relation r "
        "  JOIN cmap.mention m ON m.id IN (r.from_mention_id, r.to_mention_id) "
        "  WHERE r.id IN (ct.relation_a, ct.relation_b) "
        "  AND m.entity_id = %s::uuid) "
        "ORDER BY ct.kind, sa.title",
        (entity_id,),
    ).fetchall()
    return [
        {
            "id": row[0],
            "kind": str(row[1]),
            "status": str(row[2]),
            "summary": str(row[3]),
            "resolution": str(row[4]) if row[4] is not None else None,
            "source_a_title": str(row[5]),
            "source_b_title": str(row[6]),
        }
        for row in rows
    ]
