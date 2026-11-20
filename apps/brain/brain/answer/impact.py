"""Source-backed impact tracing for named people, systems, vendors and steps."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any
from uuid import UUID

from brain.config import Settings
from brain.db import get_pool
from brain.graph.query import impact_edges
from brain.text_util import fold_key

# Match a hypothetical consequence question or an explicit disruption.
SCENARIO = re.compile(
    r"\b(?:(?:what (?:breaks|stops|would break|would stop|"
    r"(?:is|would be) (?:affected|blocked))|"
    r"who (?:is affected|waits|would be affected|would wait)) if)\s+(?P<explicit>.+)"
    r"|\b(?:what (?:happens if|would happen if|if)|suppose)\s+(?P<generic>.+)",
    re.I,
)
DISRUPTION = re.compile(
    r"\b(?:out|absent|unavailable|sick|offline|down|fails?|late|delayed|"
    r"remove|skip|without|on (?:leave|vacation)|stops? working)\b",
    re.I,
)
TYPES = ("Person", "Role", "System", "Vendor", "Step", "Decision")
MAX_HOPS = 4
MAX_LINES = 24

IMPACT_LABELS = {
    "PRECEDES": "then",
    "HANDS_OFF_TO": "hands off to",
    "PERFORMS": "performs",
    "OWNS": "owns",
    "DEPENDS_ON": "is needed by",
    "USES": "is used by",
    "BLOCKED_BY": "can block",
}


def scenario_subject(question: str) -> str | None:
    match = SCENARIO.search(question)
    if match is None:
        return None
    subject = match.group("explicit") or match.group("generic")
    return subject if DISRUPTION.search(subject) else None


def _named_subject(
    conn: Any, subject: str, universe_ids: list[str] | None = None
) -> tuple[str, str] | None:
    folded = fold_key(subject)
    rows = conn.execute(
        "SELECT e.id::text, e.canonical_name, a.normalized_name "
        "FROM cmap.entity e LEFT JOIN cmap.entity_alias a ON a.entity_id = e.id "
        "WHERE e.entity_type = ANY(%s) "
        "AND (%s OR e.id = ANY(%s::uuid[])) AND EXISTS ("
        "SELECT 1 FROM cmap.mention m JOIN cmap.chunk c ON c.id = m.chunk_id "
        "WHERE m.entity_id = e.id AND NOT EXISTS (SELECT 1 FROM cmap.source_version sv "
        "WHERE sv.supersedes_source_id = c.source_id AND sv.decided_at IS NOT NULL))",
        (list(TYPES), universe_ids is None, universe_ids or []),
    ).fetchall()
    candidates: dict[str, tuple[str, int]] = {}
    for entity_id, name, alias in rows:
        for term in {fold_key(name), fold_key(alias or "")}:
            if len(term) < 3 or not re.search(
                r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", folded
            ):
                continue
            candidates[entity_id] = (
                name,
                max(len(term), candidates.get(entity_id, ("", 0))[1]),
            )
    ranked = sorted(candidates.items(), key=lambda pair: -pair[1][1])
    if not ranked or (len(ranked) > 1 and ranked[0][1][1] == ranked[1][1][1]):
        return None
    return ranked[0][0], ranked[0][1][0]


def _uuid_text(value: Any) -> str | None:
    if isinstance(value, str):
        try:
            return str(UUID(value))
        except ValueError:
            pass
    return None


def _edge_refs(raw_refs: Any) -> list[tuple[str, str]]:
    if isinstance(raw_refs, str):
        try:
            raw_refs = json.loads(raw_refs)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw_refs, list):
        return []
    refs = []
    for ref in raw_refs:
        if not isinstance(ref, dict):
            continue
        chunk_id = _uuid_text(ref.get("chunk_id"))
        quote = ref.get("quote")
        if chunk_id and isinstance(quote, str) and quote:
            refs.append((chunk_id, quote))
    return refs


def _live_quotes(conn: Any, refs: list[tuple[str, str]]) -> list[dict[str, Any]]:
    if not refs:
        return []
    rows = conn.execute(
        "SELECT c.id::text, c.source_id::text, s.title, c.locator, c.text "
        "FROM cmap.chunk c JOIN cmap.source s ON s.id = c.source_id "
        "WHERE c.id = ANY(%s::uuid[]) AND NOT EXISTS (SELECT 1 FROM cmap.source_version sv "
        "WHERE sv.supersedes_source_id = c.source_id AND sv.decided_at IS NOT NULL)",
        (list({chunk_id for chunk_id, _ in refs}),),
    ).fetchall()
    by_id = {row[0]: row for row in rows}
    citations = []
    for chunk_id, quote in dict.fromkeys(refs):
        row = by_id.get(chunk_id)
        if row and quote and quote in row[4]:
            citations.append(
                dict(
                    chunk_id=chunk_id,
                    source_id=row[1],
                    title=row[2],
                    locator=row[3],
                    quote=quote,
                )
            )
    return citations


def _flow_rows(
    conn: Any, ids: list[str], function_ids: list[str] | None
) -> list[tuple[Any, ...]]:
    return conn.execute(
        """
        SELECT f.title, s.ordinal, names.canonical_name, s.input, s.output,
               s.branch_of, s.evidence_relation_ids, performer.canonical_name,
               s.step_entity_id::text,
               s.step_entity_id = ANY(%(ids)s::uuid[])
                 OR s.performer_entity_id = ANY(%(ids)s::uuid[])
                 OR s.system_entity_id = ANY(%(ids)s::uuid[]) AS direct,
               f.id
        FROM cmap.process_flow f JOIN cmap.flow_step s ON s.flow_id = f.id
        LEFT JOIN cmap.entity names ON names.id = s.step_entity_id
        LEFT JOIN cmap.entity performer ON performer.id = s.performer_entity_id
        WHERE (%(unscoped)s OR f.function_id = ANY(%(functions)s::uuid[])) AND EXISTS (
            SELECT 1 FROM cmap.flow_step seed WHERE seed.flow_id = f.id
            AND (seed.step_entity_id = ANY(%(ids)s::uuid[])
              OR seed.performer_entity_id = ANY(%(ids)s::uuid[])
              OR seed.system_entity_id = ANY(%(ids)s::uuid[]))
        )
        ORDER BY direct DESC NULLS LAST, f.title, f.id, s.ordinal
        LIMIT 250
        """,
        {"ids": ids, "unscoped": function_ids is None, "functions": function_ids or []},
    ).fetchall()


def _flow_evidence(conn: Any, ids: list[Any]) -> list[tuple[str, str]]:
    return conn.execute(
        "SELECT chunk_id::text, quote FROM cmap.relation "
        "WHERE id = ANY(%s::uuid[]) AND status <> 'superseded' "
        "UNION SELECT chunk_id::text, quote FROM cmap.mention WHERE id = ANY(%s::uuid[]) "
        "ORDER BY 1, 2",
        (ids, ids),
    ).fetchall()


def trace_impact(
    subject: str,
    settings: Settings,
    *,
    function_ids: list[str] | None = None,
    universe_ids: list[str] | None = None,
    graph_scope: set[str] | None = None,
) -> tuple[str, list[dict[str, Any]]] | None:
    citations: list[dict[str, Any]] = []
    lines: list[str] = []

    def add(line: str, evidence: list[dict[str, Any]]) -> None:
        markers = []
        for citation in evidence:
            if citation not in citations:
                citations.append(citation)
            markers.append(f"[{citations.index(citation) + 1}]")
        # Source-derived names must not introduce answer citation markers.
        line = " ".join(line.split()).replace("[", "［").replace("]", "］")
        lines.append(f"- {line} " + " ".join(dict.fromkeys(markers)))

    with get_pool().connection() as conn:
        matched = _named_subject(conn, subject, universe_ids)
        if matched is None:
            return None
        seed_id, name = matched
        names = {seed_id: name}
        frontier = [seed_id]
        seen_edges = set()
        for _ in range(MAX_HOPS):
            next_frontier = []
            # E2 can know a performer or system even where extraction did not
            # project a PERFORMS/USES edge. Its grounded step can seed a handoff.
            for row in _flow_rows(conn, frontier, function_ids):
                _, _, step, _, _, _, evidence_ids, _, step_id, direct, _ = row
                if (
                    direct
                    and step_id
                    and step_id not in names
                    and (graph_scope is None or step_id in graph_scope)
                    and _live_quotes(conn, _flow_evidence(conn, evidence_ids))
                ):
                    names[step_id] = step
                    frontier.append(step_id)
            for source, target, target_name, kind, raw_refs in impact_edges(
                frontier, settings
            ):
                target = _uuid_text(target)
                if target is None or (
                    graph_scope is not None and target not in graph_scope
                ):
                    continue
                key = (source, target, kind)
                if key in seen_edges or len(lines) >= MAX_LINES // 2:
                    continue
                evidence = _live_quotes(conn, _edge_refs(raw_refs))
                if not evidence:
                    continue
                seen_edges.add(key)
                if kind == "EXCEPT_WHEN":
                    add(
                        f"Documented exception or possible workaround for {names[source]}: {target_name}",
                        evidence[:1],
                    )
                    continue
                add(
                    f"{names[source]} {IMPACT_LABELS[kind]} {target_name}", evidence[:1]
                )
                if target not in names:
                    names[target] = target_name
                    next_frontier.append(target)
            frontier = next_frontier
            if not frontier:
                break

        flow_rows = _flow_rows(conn, list(names), function_ids)
        affected_steps: dict[Any, dict[int, dict[str, Any]]] = defaultdict(dict)
        # Direct hits need current evidence even when flow order is available.
        for (
            title,
            ordinal,
            step,
            input_,
            output,
            _branch,
            ids,
            performer,
            _step_id,
            direct,
            flow_id,
        ) in flow_rows:
            if not direct or len(lines) >= MAX_LINES * 3 // 4:
                continue
            evidence = _live_quotes(conn, _flow_evidence(conn, ids))
            if evidence:
                affected_steps[flow_id][ordinal] = evidence[0]
                label = step or output or input_ or f"step {ordinal}"
                owner = f", handled by {performer}" if performer else ""
                add(f"{title}: {label}{owner} (linked step to check)", evidence[:1])

        for (
            title,
            ordinal,
            step,
            input_,
            output,
            branch,
            ids,
            performer,
            _step_id,
            direct,
            flow_id,
        ) in flow_rows:
            earlier = affected_steps.get(flow_id)
            if direct or not earlier or len(lines) >= MAX_LINES:
                continue
            if (branch is not None and branch not in earlier) or ordinal <= min(
                earlier
            ):
                continue
            evidence = _live_quotes(conn, _flow_evidence(conn, ids))
            if evidence:
                label = step or output or input_ or f"step {ordinal}"
                owner = f", handled by {performer}" if performer else ""
                predecessor = branch if branch is not None else min(earlier)
                add(
                    f"{title}: {label}{owner} (later step to check)",
                    [earlier[predecessor], evidence[0]],
                )

    if not lines:
        return None
    header = (
        f"Potential impact if **{name.replace('[', '［').replace(']', '］')}** is disrupted. "
        "Later steps may still proceed through another route."
    )
    return header + "\n\n" + "\n".join(lines), citations
