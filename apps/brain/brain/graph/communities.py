"""Community detection and hierarchical reports (plan step 8, repair C3).

Level 0: Leiden clusters inside one business function (an entity may appear
in several, one per function it is assigned to; entities with no assignment
share one logged unassigned bucket). Level 1: one report per function, whose
row id is the function's own id — stable forever. Level 2: one company report.
Each community gets one frontier-written report (``prompts/community_report.md``)
built from its own data only, stored in ``cmap.community``; the report's open
questions become ``cmap.open_question`` rows.

Stable identities (repair C3): a level-0 cluster continues the previous
build's cluster with the highest Jaccard overlap (≥ 0.5) inside the same
function, reusing that row's id and title; a report is regenerated when its
content hash (sorted entity ids + relation ids with their updated-at) changes,
not only when its entity set changes. Rows are updated in place under their
stable id, so recommendation and review-flag references survive every rebuild.
A report written while a child report failed is stored ``incomplete`` so the
next run regenerates it instead of caching it without the child. Over-budget
context is map-reduced (summarised in batches, then combined) — never
truncated silently. When the bounded reduce rounds still cannot meet the
budget, the combined summaries are hard-fitted under it at sentence
boundaries with a visible cut marker and the report is stored ``incomplete``
so the next run regenerates it — the job converges instead of failing
(#586).

Cross-boundary hand-offs (repair E4): every level-0 and level-1 report also
receives its **boundary edges** (relations to entities outside the cluster or
function) listed under "Hand-offs in / out", in its context and in its report
text; the company report receives the full function-to-function hand-off
matrix computed from relations and from E2's ``cmap.flow_step`` performer
transitions. Edge caps rank by kind weight x source count (``edge_rank``) so a
once-stated sequence or hand-off survives above repeatedly-stated generic
links. The content hash covers each report's boundary relations (and the
company's flow-step matrix inputs) so a hand-off change regenerates the
report that lists it.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import math
import re
import unicodedata
import uuid
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import igraph as ig
import leidenalg
import numpy as np
import psycopg
import tiktoken

from brain.config import Settings, get_settings
from brain.contradictions import CONFLICT_KINDS, MAX_DISAGREEMENTS, disagreement_lines
from brain.db import enqueue_job, get_pool
from brain.embed import embed_texts, vector_literal
from brain.graph.project import _load_edges, _load_entities
from brain.lang import detect_language, looks_english
from brain.resolve.resolve import FrontierCapReached, _Frontier
from brain.translate import ensure_english_question, upsert_translation

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
REPORT_PROMPT_PATH = PROMPTS_DIR / "community_report.md"
KNOWLEDGE_PROMPT_PATH = PROMPTS_DIR / "knowledge_check.md"
SUMMARISE_PROMPT_PATH = PROMPTS_DIR / "context_summary.md"
PASSAGES_PER_QUESTION = 4
PASSAGE_CHARS = 600
CHECK_BATCH = 15
MIN_IMPORTANCE = 3
MAX_QUESTIONS_PER_AREA = 3
MAX_PEOPLE_IN_CHECK = 30

RESOLUTION_L0 = 1.0
MIN_COMMUNITY = 3
MAX_MERGED_COMMUNITY = 60
MAX_COMMUNITY = 150
MAX_CONTEXT_TOKENS = 12000
MAX_SUMMARY_ROUNDS = 4
MAX_EDGES_IN_CONTEXT = 40
MAX_QUOTES_IN_CONTEXT = 25
MAX_L1_CHILDREN = 40
ROLLUP_GROUP_SIZE = 10
MAX_L2_FINDINGS_PER_FUNCTION = 3
REPORT_WORKERS = 32
L0_ASK_CHUNK = 64
# Repair C3: a level-0 cluster continues the previous build's cluster with the
# highest Jaccard overlap at or above this threshold (same function only).
CLUSTER_MATCH_MIN_JACCARD = 0.5
# Clustering edges and edge-cap ranking: MENTIONS and CONTRADICTS say nothing
# about how work moves; sequence and hand-off relations carry the flow of work
# and count double (repair E4 ranks every edge cap by this kind weight times
# the source count). A generic MENTIONS link is demoted so that, however often
# it repeats, it cannot crowd a once-stated sequence out of a capped list.
CLUSTER_EDGE_EXCLUDED = frozenset({"MENTIONS", "CONTRADICTS"})
EDGE_KIND_WEIGHTS = {"PRECEDES": 2.0, "HANDS_OFF_TO": 2.0, "MENTIONS": 0.1}

SCOPE_L0 = "one area of how a company operates"
SCOPE_L1 = "one part of the company"
SCOPE_L2 = "the whole company"
COMPANY_EXTRA = (
    "Finish with a section 'Top 10 cross-department issues' ordered by how many "
    "distinct sources mention them."
)


def _cosine(first: list[float], second: list[float]) -> float:
    """Cosine similarity of two embedding vectors."""
    dot = sum(a * b for a, b in zip(first, second, strict=True))
    norm_first = math.sqrt(sum(value * value for value in first))
    norm_second = math.sqrt(sum(value * value for value in second))
    if norm_first == 0.0 or norm_second == 0.0:
        return 0.0
    return dot / (norm_first * norm_second)


@functools.lru_cache(maxsize=1)
def _encoder() -> tiktoken.Encoding:
    """Cached cl100k_base tokenizer (get_encoding takes a lock/filesystem check otherwise)."""
    return tiktoken.get_encoding("cl100k_base")


def _tokens(text: str) -> int:
    """Approximate token count with the cl100k tokenizer."""
    return len(_encoder().encode(text, disallowed_special=()))


def _fit(lines: list[str], frontier: _Frontier, _round: int = 0) -> tuple[str, bool]:
    """Join context lines under the token budget by map-reduce, never truncation.

    An over-budget context is split into batches, each batch is summarised by
    the frontier seat (``prompts/context_summary.md``) and the summaries are
    combined; a still-over-budget combination is summarised again, up to
    ``MAX_SUMMARY_ROUNDS`` rounds. Every input line reaches a model call — the
    old behaviour silently dropped lines from the end and marked the damage
    "context truncated" (audit C2).

    Repair #586: the reduce passes are bounded and deterministic — when the
    budget still cannot be met after ``MAX_SUMMARY_ROUNDS`` rounds, the hard
    fallback ``_fit_sentences`` fits the combined summaries under the budget
    at sentence boundaries with a visible cut marker, and the caller stores
    the report ``incomplete`` so the next run regenerates it, instead of
    raising and failing the job. Returns ``(text, incomplete)``.
    """
    text = "\n".join(lines)
    if _tokens(text) <= MAX_CONTEXT_TOKENS:
        return text, False
    if _round >= MAX_SUMMARY_ROUNDS:
        fitted, cut = _fit_sentences(text, MAX_CONTEXT_TOKENS)
        logger.warning(
            "context map-reduce did not converge in %d rounds; hard-fitted "
            "the context under the token budget at a sentence boundary "
            "(cut=%s)",
            MAX_SUMMARY_ROUNDS,
            cut,
        )
        return fitted, cut
    batches = _batch_lines(lines, max(64, MAX_CONTEXT_TOKENS // 2))
    if len(batches) <= 1:
        summaries = [_ask_summary(frontier, "\n".join(batch)) for batch in batches]
    else:
        summaries = [""] * len(batches)
        with ThreadPoolExecutor(max_workers=min(REPORT_WORKERS, len(batches))) as pool:
            futures = {
                pool.submit(_ask_summary, frontier, "\n".join(batch)): index
                for index, batch in enumerate(batches)
            }
            for future in as_completed(futures):
                summaries[futures[future]] = future.result()
    combined = [
        "COMBINED SUMMARIES (the full DATA below was summarised in batches; "
        "nothing was dropped):"
    ]
    combined.extend(summaries)
    return _fit(combined, frontier, _round + 1)


# Repair #586: the marker every hard-fitted context ends with. The cut is
# visible to the model AND the stored report carries incomplete=true, so a
# sentence-boundary cut is never a silent truncation (audit C2's rule stands).
CONTEXT_CUT_MARKER = (
    "[CONTEXT INCOMPLETE: bounded map-reduce rounds could not fit every "
    "summary under the token budget; the rest was cut at a sentence boundary "
    "and this report is stored incomplete (#586).]"
)

_SENTENCE_END = re.compile(r"(?<=[.!?。！？…])\s+")


def _sentence_units(text: str) -> list[str]:
    """Content units in order: sentence ends inside each line, CJK included."""
    units: list[str] = []
    for line in text.split("\n"):
        units.extend(unit for unit in _SENTENCE_END.split(line) if unit.strip())
    return units


def _word_fit(text: str, room_tokens: int) -> str:
    """Cut ``text`` at word boundaries into ``room_tokens`` tokens.

    A single word larger than the room (a CJK run without spaces) is trimmed
    character by character — the budget is a hard guarantee.
    """
    if room_tokens <= 0:
        return ""
    piece: list[str] = []
    for word in text.split(" "):
        candidate = [*piece, word]
        if _tokens(" ".join(candidate)) > room_tokens:
            break
        piece = candidate
    if piece:
        return " ".join(piece)
    cut = max(1, int(len(text) * room_tokens / max(1, _tokens(text))))
    while cut > 1 and _tokens(text[:cut]) > room_tokens:
        cut -= 1
    return text[:cut].rstrip()


def _fit_sentences(text: str, budget_tokens: int) -> tuple[str, bool]:
    """Hard-fit ``text`` under ``budget_tokens`` at sentence boundaries (#586).

    The map-reduce fallback of last resort: whole sentences are kept in order
    while they fit; the first sentence that does not fit is cut at word
    boundaries inside itself so one pathological sentence cannot empty the
    context; the visible ``CONTEXT_CUT_MARKER`` closes the result. Returns
    the fitted text and whether anything was dropped.
    """
    units = _sentence_units(text)
    plain = "\n".join(units)
    if _tokens(plain) <= budget_tokens:
        return plain, False
    room = budget_tokens - _tokens(CONTEXT_CUT_MARKER) - 2
    kept: list[str] = []
    for unit in units:
        if _tokens("\n".join([*kept, unit])) <= room:
            kept.append(unit)
            continue
        if not kept:
            kept.append(_word_fit(unit, room))
        break
    fitted = "\n".join([*kept, "", CONTEXT_CUT_MARKER])
    # Defensive trim: the budget is a hard guarantee, not an approximation.
    while _tokens(fitted) > budget_tokens and len(kept) > 1:
        kept.pop()
        fitted = "\n".join([*kept, "", CONTEXT_CUT_MARKER])
    while _tokens(fitted) > budget_tokens and kept and len(kept[-1]) > 1:
        kept[-1] = kept[-1][:-1].rstrip()
        fitted = "\n".join([*kept, "", CONTEXT_CUT_MARKER])
    return fitted, True


def _batch_lines(lines: list[str], budget_tokens: int) -> list[list[str]]:
    """Pack whole lines into batches under the token budget.

    A single line larger than the budget (a long report body) is hard-split so
    one oversized line can never wedge the batching.
    """
    batches: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0
    for line in lines:
        line_tokens = _tokens(line)
        if line_tokens > budget_tokens:
            if current:
                batches.append(current)
                current, current_tokens = [], 0
            chunk = max(64, budget_tokens * 3)
            for start in range(0, len(line), chunk):
                batches.append([line[start : start + chunk]])
            continue
        if current and current_tokens + line_tokens > budget_tokens:
            batches.append(current)
            current, current_tokens = [], 0
        current.append(line)
        current_tokens += line_tokens
    if current:
        batches.append(current)
    return batches


def _ask_summary(frontier: _Frontier, batch_text: str) -> str:
    """One batch summary from the frontier seat; an empty answer is a failure."""
    template = SUMMARISE_PROMPT_PATH.read_text(encoding="utf-8")
    prompt = template.replace("{{context}}", batch_text)
    for _attempt in range(2):
        result = frontier.ask(prompt)
        summary = str(result.get("summary") or "").strip()
        if summary:
            return summary
        logger.warning("context summarisation returned an empty summary")
    raise RuntimeError("context summarisation returned no summary")


def _clustering_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Clustering view of the projected edges (repair C3).

    MENTIONS and CONTRADICTS never join clusters; PRECEDES and HANDS_OFF_TO
    carry the flow of work and count double.
    """
    out: list[dict[str, Any]] = []
    for edge in edges:
        rel_type = str(edge.get("rel_type") or "")
        if rel_type in CLUSTER_EDGE_EXCLUDED:
            continue
        weighted = dict(edge)
        weighted["weight"] = float(edge["weight"]) * EDGE_KIND_WEIGHTS.get(
            rel_type, 1.0
        )
        out.append(weighted)
    return out


def edge_rank(edge: dict[str, Any]) -> tuple[float, float]:
    """Edge-cap ranking key (repair E4): kind weight x authority-weighted score.

    Sequence and hand-off kinds carry the flow of work; ``score`` blends
    source authority, recency and confidence while falling back to integer
    ``weight`` when absent. Ties go to the higher kind weight.
    Used by this module's edge caps and by ``answer/answer.py``'s
    graph-neighbourhood cap.
    """
    kind_weight = EDGE_KIND_WEIGHTS.get(str(edge.get("rel_type") or ""), 1.0)
    raw = edge.get("score")
    base = float(raw) if raw is not None else float(edge.get("weight") or 0.0)
    return (kind_weight * base, kind_weight)


@dataclass(slots=True)
class _ContentHashIndex:
    """Bulk-loaded map timestamps and relations to avoid per-cluster SQL queries."""

    entity_stamp: dict[str, str]
    rels_by_entity: dict[str, list[tuple[str, str, str | None, str | None]]]
    ef_by_entity: dict[str, list[str]]


def _load_content_hash_index(conn: psycopg.Connection) -> _ContentHashIndex:
    """Load entity/relation timestamps and function links in three bulk queries."""
    entity_stamp = {
        str(eid): str(stamp)
        for eid, stamp in conn.execute(
            "SELECT e.id::text, e.updated_at::text FROM cmap.entity e"
        ).fetchall()
    }
    rels_by_entity: dict[str, list[tuple[str, str, str | None, str | None]]] = {}
    for rid, rstamp, feid, teid in conn.execute(
        "SELECT r.id::text, r.updated_at::text, fm.entity_id::text, tm.entity_id::text "
        "FROM cmap.relation r "
        "JOIN cmap.mention fm ON fm.id = r.from_mention_id "
        "JOIN cmap.mention tm ON tm.id = r.to_mention_id "
        "WHERE fm.entity_id IS NOT NULL OR tm.entity_id IS NOT NULL"
    ).fetchall():
        entry = (
            str(rid),
            str(rstamp),
            str(feid) if feid is not None else None,
            str(teid) if teid is not None else None,
        )
        if entry[2] is not None:
            rels_by_entity.setdefault(entry[2], []).append(entry)
        if entry[3] is not None and entry[3] != entry[2]:
            rels_by_entity.setdefault(entry[3], []).append(entry)
    ef_by_entity: dict[str, list[str]] = {}
    for eid, fid in conn.execute(
        "SELECT ef.entity_id::text, ef.function_id::text FROM cmap.entity_function ef"
    ).fetchall():
        key = str(eid)
        ef_by_entity.setdefault(key, []).append(f"x:{key}:{fid}:")
    return _ContentHashIndex(
        entity_stamp=entity_stamp,
        rels_by_entity=rels_by_entity,
        ef_by_entity=ef_by_entity,
    )


def _content_hash(
    conn: psycopg.Connection,
    entity_ids: list[str],
    *,
    flows: bool = False,
    index: _ContentHashIndex | None = None,
) -> str:
    """Hash of a report's inputs: sorted entity and relation ids, stamped.

    The hash changes whenever any member entity or any relation among them
    changes (their updated-at), so a report regenerates on a new relation even
    when its entity set is unchanged (audit C2). Repair E4: a report also lists
    its boundary relations under "Hand-offs in / out" with the outside ends'
    function labels, so relations crossing the member set and the entity-function
    pairs of members and their neighbours join the hash as well. ``flows`` (the
    company report only) adds the ``cmap.flow_step`` performer transitions its
    hand-off matrix is computed from — flow rows carry no updated_at, so their
    identity is hashed as content.
    """
    if not entity_ids:
        return hashlib.sha256(b"").hexdigest()
    if index is not None:
        member_set = set(entity_ids)
        parts: list[str] = []
        for eid in member_set:
            stamp = index.entity_stamp.get(eid)
            if stamp is not None:
                parts.append(f"e:{eid}:{stamp}")
        seen_rids: set[str] = set()
        neighbour_eids: set[str] = set()
        for eid in member_set:
            for rid, rstamp, feid, teid in index.rels_by_entity.get(eid, ()):
                if rid not in seen_rids:
                    seen_rids.add(rid)
                    parts.append(f"r:{rid}:{rstamp}")
                if feid is not None:
                    neighbour_eids.add(feid)
                if teid is not None:
                    neighbour_eids.add(teid)
        for eid in member_set | neighbour_eids:
            parts.extend(index.ef_by_entity.get(eid, ()))
        parts.sort()
    else:
        rows = conn.execute(
            "SELECT 'e', e.id::text, e.updated_at::text FROM cmap.entity e "
            "WHERE e.id = ANY(%s::uuid[]) "
            "UNION ALL "
            # Repair E4: the OR includes boundary relations (exactly one end in the
            # set) — their hand-off lines are part of the report's content.
            "SELECT 'r', r.id::text, r.updated_at::text FROM cmap.relation r "
            "JOIN cmap.mention fm ON fm.id = r.from_mention_id "
            "JOIN cmap.mention tm ON tm.id = r.to_mention_id "
            "WHERE fm.entity_id = ANY(%s::uuid[]) OR tm.entity_id = ANY(%s::uuid[]) "
            "UNION ALL "
            # Function labels of members and one-hop neighbours (the counterparty
            # labels in the hand-off lines).
            "SELECT 'x', ef.entity_id::text || ':' || ef.function_id::text, '' "
            "FROM cmap.entity_function ef "
            "WHERE ef.entity_id = ANY(%s::uuid[]) "
            "OR ef.entity_id IN ("
            "SELECT other_id FROM ("
            "SELECT tm.entity_id AS other_id FROM cmap.relation r "
            "JOIN cmap.mention fm ON fm.id = r.from_mention_id "
            "JOIN cmap.mention tm ON tm.id = r.to_mention_id "
            "WHERE fm.entity_id = ANY(%s::uuid[]) "
            "UNION "
            "SELECT fm.entity_id AS other_id FROM cmap.relation r "
            "JOIN cmap.mention fm ON fm.id = r.from_mention_id "
            "JOIN cmap.mention tm ON tm.id = r.to_mention_id "
            "WHERE tm.entity_id = ANY(%s::uuid[])) neighbours)",
            (entity_ids, entity_ids, entity_ids, entity_ids, entity_ids, entity_ids),
        ).fetchall()
        parts = sorted(f"{kind}:{row_id}:{stamp}" for kind, row_id, stamp in rows)
    if flows:
        for flow_id, ordinal, performer in conn.execute(
            "SELECT fs.flow_id::text, fs.ordinal, "
            "COALESCE(fs.performer_entity_id::text, '') "
            "FROM cmap.flow_step fs ORDER BY fs.flow_id, fs.ordinal"
        ).fetchall():
            parts.append(f"f:{flow_id}:{ordinal}:{performer}")
        parts.sort()
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _function_names(conn: psycopg.Connection) -> dict[str, list[str]]:
    """entity id -> names of the active functions it is assigned to."""
    out: dict[str, list[str]] = {}
    for entity_id, name in conn.execute(
        "SELECT ef.entity_id::text, f.name FROM cmap.entity_function ef "
        "JOIN cmap.function f ON f.id = ef.function_id "
        "WHERE f.active ORDER BY f.name"
    ).fetchall():
        out.setdefault(str(entity_id), []).append(str(name))
    return out


def _boundary_edges(
    edges: list[dict[str, Any]],
    member_ids: set[str],
    edges_by_entity: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Edges with exactly one endpoint in the set (repair E4).

    These are the report's boundary edges — the relations to entities outside
    the cluster or function — and the raw material of "Hand-offs in / out".
    """
    out: list[dict[str, Any]] = []
    if edges_by_entity is not None:
        seen_ids: set[int] = set()
        for member_id in member_ids:
            for edge in edges_by_entity.get(member_id, ()):
                eid_obj = id(edge)
                if eid_obj in seen_ids:
                    continue
                seen_ids.add(eid_obj)
                if (edge["from"] in member_ids) != (edge["to"] in member_ids):
                    out.append(edge)
        return out
    for edge in edges:
        from_in = edge["from"] in member_ids
        to_in = edge["to"] in member_ids
        if from_in != to_in:
            out.append(edge)
    return out


def _handoff_lines(
    edges: list[dict[str, Any]],
    member_ids: set[str],
    names: dict[str, str],
    function_names: dict[str, list[str]],
    edges_by_entity: dict[str, list[dict[str, Any]]] | None = None,
) -> list[str]:
    """ "Hand-offs in / out" lines for one level-0/level-1 report (repair E4).

    Every boundary relation crossing the cluster or function boundary is
    listed with its direction (``out`` when the edge leaves the report's own
    entities, ``in`` when it arrives), the counterparty's function labels and
    the source count, capped and ranked by ``edge_rank``.
    """
    boundary = _boundary_edges(edges, member_ids, edges_by_entity=edges_by_entity)
    boundary.sort(key=edge_rank, reverse=True)
    lines: list[str] = []
    for edge in boundary[:MAX_EDGES_IN_CONTEXT]:
        if edge["from"] in member_ids:
            direction, inner, outer = "out", edge["from"], edge["to"]
        else:
            direction, inner, outer = "in", edge["to"], edge["from"]
        target = names.get(outer, outer)
        outer_functions = function_names.get(outer)
        if outer_functions:
            target = f"{target} [{', '.join(outer_functions)}]"
        descriptions = "; ".join(edge.get("descriptions") or [])
        lines.append(
            f"- {direction}: {names.get(inner, inner)} -[{edge['rel_type']}]-> "
            f"{target} sources={edge['weight']} {descriptions}".rstrip()
        )
    return lines


def _flow_performer_pairs(conn: psycopg.Connection) -> list[tuple[str, str]]:
    """(from performer, to performer) for consecutive steps of each flow.

    E2's ``cmap.flow_step`` rows order the steps of a process by ``ordinal``;
    when consecutive steps have different performers, work moved between them
    — the flow half of the company's hand-off matrix (repair E4).
    """
    by_flow: dict[str, list[tuple[int, str]]] = {}
    for flow_id, ordinal, performer in conn.execute(
        "SELECT fs.flow_id::text, fs.ordinal, fs.performer_entity_id::text "
        "FROM cmap.flow_step fs WHERE fs.performer_entity_id IS NOT NULL "
        "ORDER BY fs.flow_id, fs.ordinal"
    ).fetchall():
        by_flow.setdefault(str(flow_id), []).append((int(ordinal), str(performer)))
    pairs: list[tuple[str, str]] = []
    for steps in by_flow.values():
        steps.sort()
        for (_ordinal_before, performer_before), (
            _ordinal_after,
            performer_after,
        ) in zip(steps, steps[1:], strict=False):
            if performer_before != performer_after:
                pairs.append((performer_before, performer_after))
    return pairs


def _handoff_matrix_lines(
    edges: list[dict[str, Any]],
    function_names: dict[str, list[str]],
    flow_pairs: list[tuple[str, str]],
) -> list[str]:
    """The function-to-function hand-off matrix for the company report (E4).

    Every ordered pair of distinct functions with any signal between them gets
    one line: projected relation edges from the first function's entities to
    the second's (broken down by kind) plus E2 flow-step performer transitions
    between them. Computed from relations and flows, uncapped — the full
    matrix. An entity assigned to several functions contributes to each pair
    its assignments form.
    """
    relations: dict[tuple[str, str], dict[str, int]] = {}
    kinds: dict[tuple[str, str], dict[str, int]] = {}
    flows: dict[tuple[str, str], int] = {}

    def _add(cell: dict[str, int], pair: tuple[str, str]) -> None:
        cell[pair] = cell.get(pair, 0) + 1

    for edge in edges:
        from_functions = function_names.get(edge["from"], [])
        to_functions = function_names.get(edge["to"], [])
        for source in from_functions:
            for target in to_functions:
                if source == target:
                    continue
                pair = (source, target)
                _add(relations, pair)
                kind_counts = kinds.setdefault(pair, {})
                kind_counts[edge["rel_type"]] = kind_counts.get(edge["rel_type"], 0) + 1
    for performer_before, performer_after in flow_pairs:
        for source in function_names.get(performer_before, []):
            for target in function_names.get(performer_after, []):
                if source != target:
                    _add(flows, (source, target))
    pairs = sorted(
        set(relations) | set(flows),
        key=lambda pair: (
            -(relations.get(pair, 0) + flows.get(pair, 0)),
            pair[0],
            pair[1],
        ),
    )
    lines: list[str] = []
    for pair in pairs:
        parts: list[str] = []
        if pair in relations:
            breakdown = ", ".join(
                f"{kind} x{count}" for kind, count in sorted(kinds[pair].items())
            )
            parts.append(f"relations x{relations[pair]} ({breakdown})")
        if pair in flows:
            parts.append(f"flow steps x{flows[pair]}")
        lines.append(f"- {pair[0]} -> {pair[1]}: " + " + ".join(parts))
    return lines


def _function_buckets(
    conn: psycopg.Connection, nodes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """One entity bucket per active function, plus the unassigned leftovers.

    An entity assigned to several functions appears in each of their buckets
    (repair C3). Entities with no active-function assignment land in one
    unassigned bucket (``function_id`` NULL) so nothing disappears from the
    map; the count is logged and reported in stats, never silent.
    """
    rows = conn.execute(
        "SELECT ef.entity_id::text, ef.function_id::text, f.name "
        "FROM cmap.entity_function ef "
        "JOIN cmap.function f ON f.id = ef.function_id "
        "WHERE f.active"
    ).fetchall()
    functions_of: dict[str, list[tuple[str, str]]] = {}
    for entity_id, function_id, name in rows:
        functions_of.setdefault(str(entity_id), []).append(
            (str(function_id), str(name))
        )
    buckets: dict[str, dict[str, Any]] = {}
    unassigned: list[dict[str, Any]] = []
    for node in nodes:
        assignments = functions_of.get(node["id"], [])
        if not assignments:
            unassigned.append(node)
        for function_id, name in dict.fromkeys(assignments):
            bucket = buckets.setdefault(
                function_id,
                {"function_id": function_id, "function_name": name, "nodes": []},
            )
            bucket["nodes"].append(node)
    out = sorted(
        buckets.values(),
        key=lambda bucket: (bucket["function_name"], bucket["function_id"]),
    )
    if unassigned:
        out.append({"function_id": None, "function_name": None, "nodes": unassigned})
    return out


def _match_previous(
    clusters: list[dict[str, Any]], previous_rows: list[dict[str, Any]]
) -> dict[int, dict[str, Any]]:
    """Greedy one-to-one Jaccard match of new clusters to the previous build.

    Each new cluster takes the previous cluster with the highest overlap at or
    above ``CLUSTER_MATCH_MIN_JACCARD``; a claimed previous row serves only one
    new cluster (a split keeps the id on the larger half, deterministically
    ordered by score then position).
    """
    pairs: list[tuple[float, int, int]] = []
    for position, cluster in enumerate(clusters):
        members = set(cluster["member_ids"])
        for previous_index, row in enumerate(previous_rows):
            other = row["entity_ids"]
            union = members | other
            if not union:
                continue
            score = len(members & other) / len(union)
            if score >= CLUSTER_MATCH_MIN_JACCARD:
                pairs.append((score, position, previous_index))
    pairs.sort(key=lambda item: (-item[0], item[1], item[2]))
    used_clusters: set[int] = set()
    used_rows: set[int] = set()
    out: dict[int, dict[str, Any]] = {}
    for _score, position, previous_index in pairs:
        if position in used_clusters or previous_index in used_rows:
            continue
        used_clusters.add(position)
        used_rows.add(previous_index)
        out[position] = previous_rows[previous_index]
    return out


def _level0_membership(
    edges: list[dict[str, Any]],
    entity_ids: list[str],
    entity_sources: dict[str, set[str]] | None = None,
    entity_vectors: dict[str, list[float]] | None = None,
) -> dict[str, int]:
    """Leiden level 0, then fold communities smaller than MIN_COMMUNITY.

    A small community merges into its highest-weight edge neighbour; one with
    no edge to any other community merges into the community sharing the most
    sources (``entity_sources``: entity id -> source ids). ``_fold_leftovers``
    then folds whatever neither signal can reach — entities whose mentions were
    deleted carry no source at all (#437) — into the most similar community
    (``entity_vectors``: entity id -> embedding), and keeps every community
    within [MIN_COMMUNITY, MAX_COMMUNITY] entities.
    """
    index_of = {entity_id: position for position, entity_id in enumerate(entity_ids)}
    pairs: list[tuple[int, int]] = []
    weights: list[float] = []
    adjacency: dict[tuple[int, int], float] = {}
    for edge in edges:
        first = index_of.get(edge["from"])
        second = index_of.get(edge["to"])
        if first is None or second is None or first == second:
            continue
        key = (min(first, second), max(first, second))
        adjacency[key] = adjacency.get(key, 0.0) + float(edge["weight"])
        pairs.append(key)
        weights.append(float(edge["weight"]))
    graph = ig.Graph(n=len(entity_ids), edges=pairs, directed=False)
    if pairs:
        graph.es["weight"] = weights
    partition = leidenalg.find_partition(
        graph,
        leidenalg.RBConfigurationVertexPartition,
        weights="weight" if pairs else None,
        resolution_parameter=RESOLUTION_L0,
        seed=0,
    )
    membership = list(partition.membership)
    neighbours: list[list[tuple[int, float]]] = [[] for _ in range(len(entity_ids))]
    for (first, second), weight in adjacency.items():
        neighbours[first].append((second, weight))
        neighbours[second].append((first, weight))
    src_vertices: dict[str, list[int]] = {}
    if entity_sources:
        for vertex, entity_id in enumerate(entity_ids):
            for source_id in entity_sources.get(entity_id, ()):
                src_vertices.setdefault(source_id, []).append(vertex)

    groups: dict[int, list[int]] = {}
    for vertex, community in enumerate(membership):
        groups.setdefault(community, []).append(vertex)
    small_comms: set[int] = {
        community
        for community, members in groups.items()
        if len(members) < MIN_COMMUNITY
    }
    unmergeable: set[int] = set()
    while True:
        candidates = sorted(small_comms - unmergeable)
        if not candidates:
            break
        merged = False
        for community in candidates:
            members = groups[community]
            neighbour_weights: dict[int, float] = {}
            for vertex in members:
                for other, weight in neighbours[vertex]:
                    other_comm = membership[other]
                    if other_comm != community:
                        neighbour_weights[other_comm] = (
                            neighbour_weights.get(other_comm, 0.0) + weight
                        )
            if not neighbour_weights and src_vertices:
                # No edge to another community (an isolated entity or a
                # disconnected pair, most of a real graph: #410). Fall back to
                # the community sharing the most sources with it.
                own_sources: set[str] = set()
                for vertex in members:
                    own_sources |= entity_sources.get(entity_ids[vertex], set())
                size_self = len(members)
                for source_id in own_sources:
                    for other_vertex in src_vertices[source_id]:
                        other_comm = membership[other_vertex]
                        if other_comm == community:
                            continue
                        if len(groups[other_comm]) + size_self <= MAX_MERGED_COMMUNITY:
                            neighbour_weights[other_comm] = (
                                neighbour_weights.get(other_comm, 0.0) + 1.0
                            )
            if not neighbour_weights:
                unmergeable.add(community)
                continue
            target = max(
                neighbour_weights, key=lambda key: (neighbour_weights[key], -key)
            )
            for vertex in members:
                membership[vertex] = target
            groups[target].extend(members)
            del groups[community]
            small_comms.discard(community)
            if len(groups[target]) >= MIN_COMMUNITY:
                small_comms.discard(target)
            merged = True
            break
        if not merged:
            break
    sources = [(entity_sources or {}).get(entity_id, set()) for entity_id in entity_ids]
    vectors = [(entity_vectors or {}).get(entity_id) for entity_id in entity_ids]
    _fold_leftovers(membership, adjacency, sources, vectors)
    return {
        entity_id: membership[position] for position, entity_id in enumerate(entity_ids)
    }


def _fold_leftovers(
    membership: list[int],
    adjacency: dict[tuple[int, int], float],
    entity_sources: list[set[str]],
    entity_vectors: list[list[float] | None],
) -> None:
    """Fold communities under MIN_COMMUNITY and split those over MAX_COMMUNITY.

    The merge loop only reaches a neighbour through an edge or a shared source.
    Entities with neither — their mentions were deleted upstream, so nothing
    links them any more (#437) — had no candidate and stayed singletons. This
    pass folds whatever is left into the most similar community (edge weight,
    shared sources, then embedding similarity, preferring targets that stay
    under MAX_MERGED_COMMUNITY) and peels any community over MAX_COMMUNITY into
    bounded pieces, so every community holds [MIN_COMMUNITY, MAX_COMMUNITY]
    entities whenever the corpus holds at least MIN_COMMUNITY.
    """
    total = len(membership)
    neighbours: list[list[tuple[int, float]]] = [[] for _ in range(total)]
    for (first, second), weight in adjacency.items():
        neighbours[first].append((second, weight))
        neighbours[second].append((first, weight))
    src_vertices: dict[str, list[int]] = {}
    for vertex, srcs in enumerate(entity_sources):
        for source_id in srcs:
            src_vertices.setdefault(source_id, []).append(vertex)
    has_sources = bool(src_vertices)
    vec_dim = next((len(v) for v in entity_vectors if v is not None), 0)
    has_vectors = vec_dim > 0
    vec_arrays = (
        [
            np.asarray(v, dtype=np.float64) if v is not None else None
            for v in entity_vectors
        ]
        if has_vectors
        else []
    )

    groups: dict[int, set[int]] = {}
    sums: dict[int, np.ndarray] = {}
    counts: dict[int, int] = {}
    for vertex, community in enumerate(membership):
        groups.setdefault(community, set()).add(vertex)
        counts[community] = counts.get(community, 0) + 1
        if has_vectors:
            vector = vec_arrays[vertex]
            if vector is not None:
                if community in sums:
                    sums[community] += vector
                else:
                    sums[community] = vector.copy()

    small_comms: set[int] = {
        c for c, members in groups.items() if len(members) < MIN_COMMUNITY
    }
    oversized_comms: set[int] = {
        c for c, members in groups.items() if len(members) > MAX_COMMUNITY
    }

    vec_comm_at: list[int] = []
    vec_slot_of: dict[int, int] = {}
    unit_matrix = np.zeros((max(len(groups), 16), max(vec_dim, 1)), dtype=np.float64)

    def _sync_unit(community: int) -> None:
        nonlocal unit_matrix
        if not has_vectors:
            return
        bucket = sums.get(community)
        if bucket is None or counts.get(community, 0) == 0:
            slot = vec_slot_of.pop(community, None)
            if slot is not None:
                last_comm = vec_comm_at.pop()
                if slot < len(vec_comm_at):
                    vec_comm_at[slot] = last_comm
                    vec_slot_of[last_comm] = slot
                    unit_matrix[slot] = unit_matrix[len(vec_comm_at)]
            return
        norm = float(np.linalg.norm(bucket))
        unit = bucket / norm if norm > 0.0 else bucket
        slot = vec_slot_of.get(community)
        if slot is None:
            slot = len(vec_comm_at)
            if slot >= unit_matrix.shape[0]:
                extra = np.zeros_like(unit_matrix)
                unit_matrix = np.vstack([unit_matrix, extra])
            vec_comm_at.append(community)
            vec_slot_of[community] = slot
        unit_matrix[slot] = unit

    if has_vectors:
        for community in list(sums):
            _sync_unit(community)

    next_comm_id = (max(groups) + 1) if groups else 0

    def _centroid(community: int) -> list[float] | None:
        bucket = sums.get(community)
        if bucket is None:
            return None
        count = counts[community]
        return (bucket / count).tolist()

    def _move(vertex: int, target: int, *, sync_vecs: bool = True) -> None:
        source = membership[vertex]
        membership[vertex] = target
        groups[source].remove(vertex)
        target_group = groups.setdefault(target, set())
        target_group.add(vertex)
        counts[source] -= 1
        counts[target] = counts.get(target, 0) + 1
        if has_vectors:
            vector = vec_arrays[vertex]
            if vector is not None:
                if target in sums:
                    sums[target] += vector
                else:
                    sums[target] = vector.copy()
                if source in sums:
                    sums[source] -= vector
        if counts[source] == 0:
            counts.pop(source, None)
            sums.pop(source, None)
            groups.pop(source, None)
            small_comms.discard(source)
            oversized_comms.discard(source)
        else:
            if len(groups[source]) < MIN_COMMUNITY:
                small_comms.add(source)
            else:
                small_comms.discard(source)
            if len(groups[source]) > MAX_COMMUNITY:
                oversized_comms.add(source)
            else:
                oversized_comms.discard(source)
        if len(target_group) < MIN_COMMUNITY:
            small_comms.add(target)
        else:
            small_comms.discard(target)
        if len(target_group) > MAX_COMMUNITY:
            oversized_comms.add(target)
        else:
            oversized_comms.discard(target)
        if sync_vecs:
            _sync_unit(source)
            _sync_unit(target)

    def _split(community: int) -> None:
        nonlocal next_comm_id
        members = list(groups[community])
        centre = _centroid(community) if has_vectors else None

        def _central(vertex: int) -> float:
            if centre is None or entity_vectors[vertex] is None:
                return 0.0
            return _cosine(entity_vectors[vertex], centre)

        ordered = sorted(members, key=lambda vertex: (-_central(vertex), vertex))
        size = len(ordered)
        chunks: list[list[int]] = []
        position = 0
        while size - position > MAX_COMMUNITY:
            rest = size - position
            take = (
                MAX_COMMUNITY
                if rest - MAX_COMMUNITY >= MIN_COMMUNITY
                else rest - MIN_COMMUNITY
            )
            chunks.append(ordered[position : position + take])
            position += take
        chunks.append(ordered[position:])
        touched: set[int] = {community}
        for chunk in chunks[1:]:
            new_id = next_comm_id
            next_comm_id += 1
            touched.add(new_id)
            for vertex in chunk:
                _move(vertex, new_id, sync_vecs=False)
        for cid in touched:
            _sync_unit(cid)

    while True:
        if oversized_comms:
            oversized_id = min(oversized_comms)
            _split(oversized_id)
            continue
        if not small_comms:
            return
        community = min(small_comms, key=lambda c: (len(groups[c]), c))
        members = list(groups[community])
        edge_by: dict[int, float] = {}
        for vertex in members:
            for other, weight in neighbours[vertex]:
                other_community = membership[other]
                if other_community != community:
                    edge_by[other_community] = (
                        edge_by.get(other_community, 0.0) + weight
                    )
        source_by: dict[int, int] = {}
        if has_sources:
            own: set[str] = set()
            for vertex in members:
                own |= entity_sources[vertex]
            for source_id in own:
                for other_vertex in src_vertices[source_id]:
                    other_community = membership[other_vertex]
                    if other_community != community:
                        source_by[other_community] = (
                            source_by.get(other_community, 0) + 1
                        )
        cos_by: dict[int, float] = {}
        if has_vectors and community in vec_slot_of:
            q = unit_matrix[vec_slot_of[community]]
            if np.any(q):
                dots = unit_matrix[: len(vec_comm_at)] @ q
                for idx, dot_val in enumerate(dots.tolist()):
                    cos_by[vec_comm_at[idx]] = dot_val

        best: int | None = None
        best_key: tuple[float, float, float, int, int] | None = None
        size_self = len(members)
        for other_community, other_members in groups.items():
            if other_community == community:
                continue
            other_len = len(other_members)
            if other_len + size_self > MAX_COMMUNITY:
                continue
            score = (
                3.0 * edge_by.get(other_community, 0.0)
                + 2.0 * source_by.get(other_community, 0)
                + cos_by.get(other_community, 0.0)
            )
            tier = 0.0 if other_len + size_self <= MAX_MERGED_COMMUNITY else 1.0
            key = (
                1.0 if other_len < MIN_COMMUNITY else 0.0,
                tier,
                -score,
                other_len,
                other_community,
            )
            if best_key is None or key < best_key:
                best_key, best = key, other_community
        if best is None:
            # Everything else sits at the hard cap: take the smallest anyway
            # and let _split bring it back under MAX_COMMUNITY.
            candidates = [c for c in groups if c != community]
            if not candidates:
                return
            best = min(candidates, key=lambda c: (counts.get(c, 0), c))
        for vertex in members:
            _move(vertex, best, sync_vecs=False)
        _sync_unit(community)
        _sync_unit(best)


def _entity_sources(conn: psycopg.Connection) -> dict[str, set[str]]:
    """Entity id -> ids of map-eligible sources that mention it."""
    out: dict[str, set[str]] = {}
    for entity_id, source_id in conn.execute(
        "SELECT DISTINCT m.entity_id, ch.source_id FROM cmap.mention m "
        "JOIN cmap.chunk ch ON ch.id = m.chunk_id "
        "JOIN cmap.source s ON s.id = ch.source_id "
        "WHERE m.entity_id IS NOT NULL AND s.map_eligible = true"
    ).fetchall():
        out.setdefault(str(entity_id), set()).add(str(source_id))
    return out


def _entity_vectors(conn: psycopg.Connection) -> dict[str, list[float]]:
    """Entity id -> embedding, for folding entities no edge or source can reach."""
    out: dict[str, list[float]] = {}
    for entity_id, raw in conn.execute(
        "SELECT id, embedding::text FROM cmap.entity WHERE embedding IS NOT NULL"
    ).fetchall():
        out[str(entity_id)] = [float(value) for value in json.loads(str(raw))]
    return out


def _pick_quotes_from_rows(
    rows: Sequence[tuple[Any, ...]],
) -> list[dict[str, Any]]:
    """Up to MAX_QUOTES_IN_CONTEXT quotes, prioritizing authoritative + recent sources."""
    deduped: dict[str, tuple[str, str, str, str, str, Any]] = {}
    for row in rows:
        quote = str(row[0])
        title = str(row[1])
        source_id = str(row[2])
        source_role = str(row[3]) if len(row) > 3 and row[3] else "observed_practice"
        authority_tier = str(row[4]) if len(row) > 4 and row[4] else "standard"
        eff_date = row[5] if len(row) > 5 else None
        is_auth = 1 if authority_tier == "authoritative" else 0
        date_str = eff_date.isoformat() if hasattr(eff_date, "isoformat") else str(eff_date or "")
        existing = deduped.get(quote)
        if existing is None:
            deduped[quote] = (quote, title, source_id, source_role, authority_tier, eff_date)
        else:
            prev_auth = 1 if existing[4] == "authoritative" else 0
            prev_date = (
                existing[5].isoformat()
                if hasattr(existing[5], "isoformat")
                else str(existing[5] or "")
            )
            if (is_auth, date_str) > (prev_auth, prev_date) or (
                (is_auth, date_str) == (prev_auth, prev_date) and title < existing[1]
            ):
                deduped[quote] = (quote, title, source_id, source_role, authority_tier, eff_date)

    def _sort_key(item: tuple[str, str, str, str, str, Any]) -> tuple[int, str, str, str]:
        _q, t, _s, _role, tier, eff = item
        is_auth = 1 if tier == "authoritative" else 0
        date_str = eff.isoformat() if hasattr(eff, "isoformat") else str(eff or "")
        return (
            -is_auth,
            "\xff" * 16
            if not date_str
            else "".join(chr(255 - ord(c)) for c in date_str),
            _q,
            t,
        )

    ordered = sorted(deduped.values(), key=_sort_key)
    picked: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for quote, title, source_id, source_role, authority_tier, eff_date in ordered:
        if source_id not in seen_sources and len(picked) < MAX_QUOTES_IN_CONTEXT:
            seen_sources.add(source_id)
            picked.append(
                {
                    "quote": quote,
                    "title": title,
                    "source_id": source_id,
                    "source_role": source_role,
                    "authority_tier": authority_tier,
                    "effective_date": eff_date,
                }
            )
    for quote, title, source_id, source_role, authority_tier, eff_date in ordered:
        if len(picked) >= MAX_QUOTES_IN_CONTEXT:
            break
        item = {
            "quote": quote,
            "title": title,
            "source_id": source_id,
            "source_role": source_role,
            "authority_tier": authority_tier,
            "effective_date": eff_date,
        }
        if item not in picked:
            picked.append(item)
    return picked


def _quote_rows_bulk(
    conn: psycopg.Connection, entity_ids: list[str]
) -> dict[str, list[tuple[str, str, str, str, str, Any]]]:
    """Load quote rows for a batch of entity ids in one SQL query."""
    out: dict[str, list[tuple[str, str, str, str, str, Any]]] = {}
    if not entity_ids:
        return out
    rows = conn.execute(
        "SELECT DISTINCT ON (m.entity_id, m.quote) "
        "m.entity_id::text, m.quote, s.title, ch.source_id::text, "
        "s.source_role, s.authority_tier, s.effective_date "
        "FROM cmap.mention m "
        "JOIN cmap.chunk ch ON ch.id = m.chunk_id "
        "JOIN cmap.source s ON s.id = ch.source_id "
        "WHERE m.entity_id = ANY(%s::uuid[]) AND s.map_eligible = true "
        "ORDER BY m.entity_id, m.quote, "
        "(s.authority_tier = 'authoritative') DESC, s.effective_date DESC NULLS LAST, s.title",
        (entity_ids,),
    ).fetchall()
    for eid, quote, title, source_id, source_role, authority_tier, eff_date in rows:
        out.setdefault(str(eid), []).append(
            (str(quote), str(title), str(source_id), str(source_role), str(authority_tier), eff_date)
        )
    return out


def _quote_rows(
    conn: psycopg.Connection, entity_ids: list[str]
) -> list[dict[str, Any]]:
    """Up to MAX_QUOTES_IN_CONTEXT quotes, preferring authoritative and distinct sources."""
    rows = conn.execute(
        "SELECT DISTINCT ON (m.quote) m.quote, s.title, ch.source_id, "
        "s.source_role, s.authority_tier, s.effective_date "
        "FROM cmap.mention m "
        "JOIN cmap.chunk ch ON ch.id = m.chunk_id "
        "JOIN cmap.source s ON s.id = ch.source_id "
        "WHERE m.entity_id = ANY(%s::uuid[]) AND s.map_eligible = true "
        "ORDER BY m.quote, "
        "(s.authority_tier = 'authoritative') DESC, s.effective_date DESC NULLS LAST, s.title",
        (entity_ids,),
    ).fetchall()
    return _pick_quotes_from_rows(
        [
            (str(quote), str(title), str(source_id), str(role), str(tier), eff_date)
            for quote, title, source_id, role, tier, eff_date in rows
        ]
    )


def _load_disagreements_by_entity(conn: psycopg.Connection) -> dict[str, list[str]]:
    """Map entity id -> formatted open disagreement lines in canonical order."""
    rows = conn.execute(
        "SELECT DISTINCT ct.id::text, ct.kind, ct.summary, sa.title, sb.title, m.entity_id::text "
        "FROM cmap.contradiction ct "
        "JOIN cmap.relation ra ON ra.id = ct.relation_a "
        "JOIN cmap.relation rb ON rb.id = ct.relation_b "
        "JOIN cmap.chunk ca ON ca.id = ra.chunk_id "
        "JOIN cmap.chunk cb ON cb.id = rb.chunk_id "
        "JOIN cmap.source sa ON sa.id = ca.source_id "
        "JOIN cmap.source sb ON sb.id = cb.source_id "
        "JOIN cmap.relation r ON r.id IN (ct.relation_a, ct.relation_b) "
        "JOIN cmap.mention m ON m.id IN (r.from_mention_id, r.to_mention_id) "
        "WHERE ct.status = 'open' AND ct.kind = ANY(%s) AND m.entity_id IS NOT NULL "
        "ORDER BY ct.kind, sa.title, ct.id::text",
        (list(CONFLICT_KINDS),),
    ).fetchall()
    out: dict[str, list[str]] = {}
    seen_per_entity: dict[str, set[str]] = {}
    for _cid, _kind, summary, title_a, title_b, eid in rows:
        key = str(eid)
        line = f"sources disagree: {summary} ({title_a} vs {title_b})"
        seen = seen_per_entity.setdefault(key, set())
        if line not in seen:
            seen.add(line)
            out.setdefault(key, []).append(line)
    return out


def _context_l0_lines(
    conn: psycopg.Connection,
    members: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    function_name: str | None = None,
    handoffs: list[str] | None = None,
    edges_by_entity: dict[str, list[dict[str, Any]]] | None = None,
    disagreements_by_entity: dict[str, list[str]] | None = None,
    quotes_by_entity: dict[str, list[tuple[Any, ...]]] | None = None,
) -> list[str]:
    """Build raw L0 context lines before token fitting."""
    member_ids = {member["id"] for member in members}
    names = {member["id"]: member["name"] for member in members}
    lines = []
    if function_name:
        lines.append(f"FUNCTION: {function_name}")
    lines.append("ENTITIES:")
    for member in members:
        lines.append(
            f"- [{member['type']}] {member['name']}: "
            f"{member['description'] or '(no description)'}"
        )
    if edges_by_entity is not None:
        seen_edge_ids: set[int] = set()
        scoped = []
        for member_id in member_ids:
            for edge in edges_by_entity.get(member_id, ()):
                eid_obj = id(edge)
                if (
                    eid_obj not in seen_edge_ids
                    and edge["from"] in member_ids
                    and edge["to"] in member_ids
                ):
                    seen_edge_ids.add(eid_obj)
                    scoped.append(edge)
    else:
        scoped = [
            edge
            for edge in edges
            if edge["from"] in member_ids and edge["to"] in member_ids
        ]
    scoped.sort(key=edge_rank, reverse=True)
    lines.append("EDGES:")
    for edge in scoped[:MAX_EDGES_IN_CONTEXT]:
        descriptions = "; ".join(edge.get("descriptions") or [])
        auth_tag = " [AUTHORITATIVE]" if edge.get("authority_sources") else ""
        score_val = edge.get("score")
        score_part = f" score={score_val}" if score_val is not None else ""
        lines.append(
            f"- {names.get(edge['from'], edge['from'])} -[{edge['rel_type']}]-> "
            f"{names.get(edge['to'], edge['to'])} weight={edge['weight']}{score_part} "
            f"stances={edge.get('stances') or '{}'}{auth_tag} {descriptions}"
        )
    if handoffs:
        lines.append(
            "Hand-offs in / out (relations to entities outside this area; "
            "out leaves the area, in arrives):"
        )
        lines.extend(handoffs)
    if quotes_by_entity is not None:
        raw_quotes: list[tuple[Any, ...]] = []
        for member in members:
            raw_quotes.extend(quotes_by_entity.get(member["id"], ()))
        quotes = _pick_quotes_from_rows(raw_quotes)
    else:
        quotes = _quote_rows(conn, [member["id"] for member in members])
    from brain.scoring import format_source_tag

    lines.append("SOURCES (findings must cite these ids):")
    seen: dict[str, str] = {}
    for item in quotes:
        tag = format_source_tag(
            item.get("source_role"),
            item.get("authority_tier"),
            item.get("effective_date"),
        )
        seen[item["source_id"]] = f"{tag} {item['title']}"
    for source_id, title in seen.items():
        lines.append(f"- {source_id}: {title}")
    lines.append("QUOTES:")
    for item in quotes:
        lines.append(f'- [{item["source_id"]}] "{item["quote"]}"')
    if disagreements_by_entity is not None:
        seen_disagreements: set[str] = set()
        disagreements: list[str] = []
        for member in members:
            for line in disagreements_by_entity.get(member["id"], ()):
                if line not in seen_disagreements:
                    seen_disagreements.add(line)
                    disagreements.append(line)
                    if len(disagreements) >= MAX_DISAGREEMENTS:
                        break
            if len(disagreements) >= MAX_DISAGREEMENTS:
                break
    else:
        disagreements = disagreement_lines(conn, [member["id"] for member in members])
    if disagreements:
        lines.append(
            "SOURCES DISAGREE (state these as contradictions or gaps in findings):"
        )
        for line in disagreements:
            lines.append(f"- {line}")
    return lines


def _context_l0(
    conn: psycopg.Connection,
    members: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    frontier: _Frontier,
    function_name: str | None = None,
    handoffs: list[str] | None = None,
    edges_by_entity: dict[str, list[dict[str, Any]]] | None = None,
    disagreements_by_entity: dict[str, list[str]] | None = None,
) -> tuple[str, bool]:
    """Entity list, top edges, boundary hand-offs and quotes for one community.

    Returns the context and whether the token-budget hard fallback cut it
    (#586) — the report is then stored ``incomplete``.
    """
    lines = _context_l0_lines(
        conn,
        members,
        edges,
        function_name=function_name,
        handoffs=handoffs,
        edges_by_entity=edges_by_entity,
        disagreements_by_entity=disagreements_by_entity,
    )
    return _fit(lines, frontier)


def _build_source_aliases(
    source_ids: Iterable[str],
) -> tuple[dict[str, str], dict[str, str]]:
    """Map full source UUIDs to deterministic collision-free short aliases ``s<hex8+>``."""
    unique_ids = sorted({str(sid).strip() for sid in source_ids if str(sid).strip()})
    if not unique_ids:
        return {}, {}
    length = 8
    max_len = max(len(sid.replace("-", "")) for sid in unique_ids)
    while length < max_len:
        prefixes = ["s" + sid.replace("-", "")[:length] for sid in unique_ids]
        if len(set(prefixes)) == len(unique_ids):
            break
        length += 1
    uuid_to_alias: dict[str, str] = {}
    alias_to_uuid: dict[str, str] = {}
    for sid in unique_ids:
        compact = sid.replace("-", "")
        alias = "s" + compact[:length]
        if alias in alias_to_uuid:
            alias = "s" + compact
        uuid_to_alias[sid] = alias
        alias_to_uuid[alias] = sid
    return uuid_to_alias, alias_to_uuid


def _resolve_source_aliases(
    report: dict[str, Any], alias_to_uuid: dict[str, str]
) -> None:
    """Translate compact source aliases in ``report['findings']`` back to full UUIDs."""
    if not alias_to_uuid:
        return
    for finding in report.get("findings") or []:
        if not isinstance(finding, dict):
            continue
        resolved: list[str] = []
        seen: set[str] = set()
        for raw_id in finding.get("source_ids") or []:
            sid = str(raw_id).strip()
            canonical = alias_to_uuid.get(sid, sid)
            if canonical and canonical not in seen:
                seen.add(canonical)
                resolved.append(canonical)
        finding["source_ids"] = resolved


def _select_findings(
    findings: Sequence[dict[str, Any]] | list[dict[str, Any]],
    max_findings: int | None,
) -> list[dict[str, Any]]:
    items = [f for f in findings if isinstance(f, dict)]
    if max_findings is None or len(items) <= max_findings:
        return items
    ranked = sorted(
        enumerate(items),
        key=lambda pair: (-(len(pair[1].get("source_ids") or [])), pair[0]),
    )
    return [item for _idx, item in ranked[:max_findings]]


def _render_report_block(
    rows: list[dict[str, Any]],
    uuid_to_alias: dict[str, str],
    *,
    max_findings_per_row: int | None = None,
) -> list[str]:
    lines: list[str] = []
    for row in rows:
        lines.append(f"## {row['title']}")
        lines.append(str(row.get("summary") or ""))
        deduped: dict[tuple[str, str], list[str]] = {}
        repeat_counts: dict[tuple[str, str], int] = {}
        for finding in _select_findings(row.get("findings") or [], max_findings_per_row):
            kind = str(finding.get("kind") or "")
            text = " ".join(str(finding.get("text") or "").split())
            key = (kind, text.lower())
            repeat_counts[key] = repeat_counts.get(key, 0) + 1
            aliases = deduped.setdefault(key, [])
            for raw_id in finding.get("source_ids") or []:
                alias = uuid_to_alias.get(str(raw_id), str(raw_id))
                if alias and alias not in aliases:
                    aliases.append(alias)
        seen_display: set[tuple[str, str]] = set()
        for finding in _select_findings(row.get("findings") or [], max_findings_per_row):
            kind = str(finding.get("kind") or "")
            raw_text = " ".join(str(finding.get("text") or "").split())
            key = (kind, raw_text.lower())
            if key in seen_display:
                continue
            seen_display.add(key)
            extra = repeat_counts[key] - 1
            suffix = f" (+{extra} similar)" if extra > 0 else ""
            lines.append(f"- [{kind}] {raw_text}{suffix}")
        aliases = sorted(
            {
                uuid_to_alias.get(str(sid), str(sid))
                for sid in (row.get("source_ids") or [])
                if str(sid).strip()
            }
        )
        lines.append(f"sources: {', '.join(aliases)}")
    return lines


def _context_reports(
    rows: list[dict[str, Any]],
    frontier: _Frontier,
    header: str | None = None,
    handoffs: list[str] | None = None,
    *,
    max_findings_per_row: int | None = None,
    alias_map: dict[str, str] | None = None,
) -> tuple[str, bool]:
    """Level-1/2 context: child reports with compact aliases and K=40 tree rollup.

    Uses collision-free ``s<uuid8>`` aliases so citation validation survives
    without burning 36-char UUID tokens. When ``len(rows) > MAX_L1_CHILDREN``,
    partitions deterministically into groups of ``ROLLUP_GROUP_SIZE`` and
    summarizes each group once before ``_fit``, eliminating context overflow at
    6x+ scale (#607 phase 1).
    """
    all_source_ids = [
        str(sid)
        for row in rows
        for sid in (row.get("source_ids") or [])
        if str(sid).strip()
    ]
    all_source_ids.extend(
        str(sid)
        for row in rows
        for finding in (row.get("findings") or [])
        if isinstance(finding, dict)
        for sid in (finding.get("source_ids") or [])
        if str(sid).strip()
    )
    unique_sources = sorted(set(all_source_ids))
    compact_aliases = (
        len(rows) > MAX_L1_CHILDREN or len(unique_sources) > MAX_L1_CHILDREN
    )
    if compact_aliases:
        uuid_to_alias, alias_to_uuid = _build_source_aliases(unique_sources)
        if alias_map is not None:
            alias_map.update(alias_to_uuid)
        reports_heading = "REPORTS (cite source aliases such as s1234abcd in source_ids):"
    else:
        uuid_to_alias = {sid: sid for sid in unique_sources}
        reports_heading = "REPORTS:"

    lines: list[str] = []
    if header:
        lines.append(header)
    if handoffs:
        lines.append("Hand-offs in / out:")
        lines.extend(handoffs)
    lines.append(reports_heading)

    if len(rows) > MAX_L1_CHILDREN:
        ordered = sorted(
            rows,
            key=lambda r: (str(r.get("title") or ""), str(r.get("summary") or "")[:80]),
        )
        groups = [
            ordered[group_idx : group_idx + ROLLUP_GROUP_SIZE]
            for group_idx in range(0, len(ordered), ROLLUP_GROUP_SIZE)
        ]
        group_texts = [
            "\n".join(
                _render_report_block(
                    group, uuid_to_alias, max_findings_per_row=max_findings_per_row
                )
            )
            for group in groups
        ]
        summaries = [""] * len(groups)
        with ThreadPoolExecutor(max_workers=min(REPORT_WORKERS, len(groups))) as pool:
            futures = {
                pool.submit(_ask_summary, frontier, text): idx
                for idx, text in enumerate(group_texts)
            }
            for future in as_completed(futures):
                summaries[futures[future]] = future.result()
        for idx, (group, summary) in enumerate(zip(groups, summaries, strict=True)):
            group_aliases = sorted(
                {
                    uuid_to_alias.get(str(sid), str(sid))
                    for r in group
                    for sid in (r.get("source_ids") or [])
                    if str(sid).strip()
                }
            )
            titles = "; ".join(str(r.get("title") or "Area") for r in group[:4])
            if len(group) > 4:
                titles += f" (+{len(group) - 4} more)"
            lines.append(f"## Group {idx + 1}: {titles}")
            lines.append(summary)
            lines.append(f"sources: {', '.join(group_aliases)}")
    else:
        lines.extend(
            _render_report_block(
                rows, uuid_to_alias, max_findings_per_row=max_findings_per_row
            )
        )
    return _fit(lines, frontier)


def _ask_report(
    frontier: _Frontier, scope: str, extra_instructions: str, context: str
) -> dict[str, Any]:
    """One community report from the frontier model."""
    template = REPORT_PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        template.replace("{{scope}}", scope)
        .replace("{{extra_instructions}}", extra_instructions)
        .replace("{{context}}", context)
    )
    result = frontier.ask(prompt)
    findings = result.get("findings")
    if not isinstance(findings, list):
        findings = []
    open_questions = result.get("open_questions")
    if not isinstance(open_questions, list):
        open_questions = []
    return {
        "title": str(result.get("title") or "").strip() or "Untitled area",
        "title_en": str(result.get("title_en") or "").strip(),
        "summary": str(result.get("summary") or "").strip(),
        "summary_en": str(result.get("summary_en") or "").strip(),
        "findings": [item for item in findings if isinstance(item, dict)],
        "open_questions": [str(item) for item in open_questions if str(item).strip()],
    }


def _report_md(report: dict[str, Any]) -> str:
    """Render one stored report as Markdown."""
    lines = [f"# {report['title']}", "", report["summary"], "", "## Findings"]
    for finding in report["findings"]:
        lines.append(
            f"- **[{finding.get('kind', '')}]** {finding.get('text', '')} "
            f"_({finding.get('stance', '')})_"
        )
    if report["open_questions"]:
        lines.append("")
        lines.append("## Open questions")
        for question in report["open_questions"]:
            lines.append(f"- {question}")
    handoffs = report.get("handoffs") or []
    if handoffs:
        lines.append("")
        lines.append("## Hand-offs in / out")
        lines.extend(handoffs)
    return "\n".join(lines)


def _filter_findings(
    report: dict[str, Any], valid_sources: set[str]
) -> tuple[list[dict[str, Any]], int]:
    """Keep only findings citing at least one real source; count the rest."""
    kept: list[dict[str, Any]] = []
    dropped = 0
    for finding in report["findings"]:
        source_ids = [
            str(source_id)
            for source_id in (finding.get("source_ids") or [])
            if str(source_id) in valid_sources
        ]
        if not source_ids:
            dropped += 1
            continue
        finding["source_ids"] = source_ids
        kept.append(finding)
    return kept, dropped


def _store(
    conn: psycopg.Connection,
    level: int,
    parent_id: str | None,
    report: dict[str, Any],
    entity_ids: list[str],
    graph_version: int,
    valid_sources: set[str],
    *,
    row_id: str | None = None,
    function_id: str | None = None,
    content_hash: str = "",
    incomplete: bool = False,
    title_override: str | None = None,
) -> tuple[str, int]:
    """Write one report, updating its stable row in place when there is one.

    ``row_id`` is the report's stable identity (the function's id at level 1,
    the Jaccard-matched cluster id at level 0, the company row at level 2);
    updating that row keeps every ``cmap.recommendation`` / ``cmap.review_flag``
    reference valid across rebuilds. ``title_override`` keeps a matched
    cluster's title (and sets the function name at level 1).
    """
    findings, dropped = _filter_findings(report, valid_sources)
    report["findings"] = findings
    if title_override is not None:
        report["title"] = title_override
        report["title_en"] = ""
    title_en = str(report.get("title_en") or "").strip()
    summary_en = str(report.get("summary_en") or "").strip()
    canonical = {
        "title": title_en or report["title"],
        "summary": summary_en or report["summary"],
        "findings": findings,
        "open_questions": report["open_questions"],
        "handoffs": report.get("handoffs") or [],
    }
    community_id = row_id or str(uuid.uuid4())
    row = conn.execute(
        "INSERT INTO cmap.community (id, level, parent_id, title, report_md, "
        "findings, entity_ids, graph_version, content_hash, incomplete, function_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (id) DO UPDATE SET parent_id = EXCLUDED.parent_id, "
        "title = EXCLUDED.title, report_md = EXCLUDED.report_md, "
        "findings = EXCLUDED.findings, entity_ids = EXCLUDED.entity_ids, "
        "graph_version = EXCLUDED.graph_version, "
        "content_hash = EXCLUDED.content_hash, incomplete = EXCLUDED.incomplete, "
        "function_id = EXCLUDED.function_id "
        "RETURNING id",
        (
            community_id,
            level,
            parent_id,
            canonical["title"],
            _report_md(canonical),
            json.dumps(findings, ensure_ascii=False),
            entity_ids,
            graph_version,
            content_hash,
            incomplete,
            function_id,
        ),
    ).fetchone()
    community_id = str(row[0])
    upsert_translation("community", community_id, "title", "en", canonical["title"])
    upsert_translation("community", community_id, "summary", "en", canonical["summary"])
    if (
        canonical["title"] != report["title"]
        or detect_language(str(report["title"])) == "zh"
    ):
        upsert_translation("community", community_id, "title", "zh-CN", report["title"])
        upsert_translation(
            "community", community_id, "summary", "zh-CN", report["summary"]
        )
    return community_id, dropped


def _closest_passages(conn: psycopg.Connection, vector: list[float]) -> list[str]:
    """The passages in the whole brain nearest one question."""
    rows = conn.execute(
        "SELECT text FROM cmap.chunk WHERE embedding IS NOT NULL "
        "ORDER BY embedding <=> %s::vector LIMIT %s",
        (vector_literal(vector), PASSAGES_PER_QUESTION),
    ).fetchall()
    return [" ".join(str(row[0]).split())[:PASSAGE_CHARS] for row in rows]


def _departments(conn: psycopg.Connection) -> list[str]:
    """The departments active employees say they work in (their own wording)."""
    rows = conn.execute(
        # to_jsonb: the directory's own department column is optional.
        "SELECT DISTINCT trim(COALESCE(NULLIF(trim(f.department), ''), NULLIF(trim(to_jsonb(e)->>'department'), ''))) "
        "FROM public.employees e LEFT JOIN cmap.employee_flags f ON f.employee_id = e.id "
        "WHERE e.disabled_at IS NULL AND COALESCE(NULLIF(trim(f.department), ''), NULLIF(trim(to_jsonb(e)->>'department'), '')) IS NOT NULL "
        "ORDER BY 1"
    ).fetchall()
    return [str(row[0]) for row in rows]


_TRAILING_PARENS = re.compile(r"\s*[（(][^()（）]*[)）]\s*$")
_POLLUTED_SEPARATORS = re.compile(r"[/|\\;:→=•·&+,@0-9]|->")
_CONJUNCTION_RE = re.compile(
    r"\b(?:and|or|for|with|from|to|via|by|as)\b", re.IGNORECASE
)
_NON_PERSON_WORDS = frozenset(
    {
        "designer",
        "designers",
        "manager",
        "director",
        "coordinator",
        "lead",
        "assistant",
        "buyer",
        "buyers",
        "team",
        "dept",
        "department",
        "division",
        "licensor",
        "vendor",
        "factory",
        "supplier",
        "client",
        "customer",
        "staff",
        "intern",
        "analyst",
        "specialist",
        "engineer",
        "representative",
        "contact",
        "owner",
        "proxy",
        "shared",
        "recipient",
        "person",
        "employee",
        "unknown",
        "tbd",
        "sales",
        "salesman",
        "salesperson",
        "licensing",
        "production",
        "operations",
        "admin",
        "shipping",
        "logistics",
        "warehouse",
        "accounting",
        "finance",
        "legal",
        "tech",
        "technical",
        "creative",
        "senior",
        "junior",
        "head",
        "vp",
        "ceo",
        "coo",
        "cfo",
        "pm",
        "qc",
        "qa",
        "pd",
        "new",
        "other",
        "all",
        "everyone",
        "anybody",
        "someone",
        "nobody",
        "him",
        "her",
        "them",
        "oracle",
    }
)


def _fold_person_key(name: str) -> str:
    """Normalised accent-free key with trailing parentheticals stripped."""
    text = " ".join(str(name or "").split())
    while True:
        stripped = _TRAILING_PARENS.sub("", text).strip()
        if stripped == text:
            break
        text = stripped
    folded = "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )
    return " ".join(folded.split()).casefold()


def _clean_area_person(raw: str) -> str | None:
    """Return a clean person name or None for lane headers, roles, and junk."""
    text = " ".join(str(raw or "").split())
    while True:
        stripped = _TRAILING_PARENS.sub("", text).strip()
        if stripped == text:
            break
        text = stripped
    if not text or text.casefold() == "the oracle":
        return None
    if _POLLUTED_SEPARATORS.search(text) or _CONJUNCTION_RE.search(text):
        return None
    tokens = text.split()
    if len(tokens) == 1 and text.isascii() and text.islower():
        return None
    lower_tokens = [tok.strip(".,!?'\"()[]{}").casefold() for tok in tokens]
    if any(tok in _NON_PERSON_WORDS for tok in lower_tokens if tok):
        return None
    if len(lower_tokens) != len(set(lower_tokens)):
        return None
    if text.isascii() and len(tokens) > 3:
        return None
    return text


def _active_employee_maps(
    conn: psycopg.Connection,
) -> tuple[dict[str, str], dict[str, str]]:
    """Return ``(by_email, by_folded_name)`` for active company employees."""
    rows = conn.execute(
        "SELECT name, email FROM public.employees "
        "WHERE disabled_at IS NULL AND name IS NOT NULL ORDER BY name, id"
    ).fetchall()
    by_email: dict[str, str] = {}
    by_folded_name: dict[str, str] = {}
    for name_val, email_val in rows:
        name = " ".join(str(name_val).split())
        if not name or name.casefold() == "the oracle":
            continue
        if _POLLUTED_SEPARATORS.search(name) or "ai test" in name.casefold():
            continue
        if email_val:
            by_email.setdefault(str(email_val).strip().casefold(), name)
        key = _fold_person_key(name)
        if key:
            by_folded_name.setdefault(key, name)
    return by_email, by_folded_name


def _area_people(conn: psycopg.Connection, entity_ids: list[str]) -> list[str]:
    """Canonical employee names who belong to one area (filtered, #589)."""
    if not entity_ids:
        return []
    mapping = _area_people_bulk(conn, entity_ids)
    return sorted(set(mapping.values()))[:MAX_PEOPLE_IN_CHECK]


def _area_people_bulk(conn: psycopg.Connection, entity_ids: list[str]) -> dict[str, str]:
    """Map Person entity id -> canonical employee name for a batch (#589)."""
    if not entity_ids:
        return {}
    rows = conn.execute(
        "SELECT id::text, canonical_name FROM cmap.entity WHERE entity_type = 'Person' "
        "AND id = ANY(%s::uuid[])",
        (entity_ids,),
    ).fetchall()
    by_email, by_folded_name = _active_employee_maps(conn)
    out: dict[str, str] = {}
    for eid, raw in rows:
        raw_str = str(raw or "").strip()
        if not raw_str:
            continue
        email_hit = by_email.get(raw_str.casefold())
        if email_hit:
            out[str(eid)] = email_hit
            continue
        if _clean_area_person(raw_str) is None:
            continue
        emp_hit = by_folded_name.get(_fold_person_key(raw_str))
        if emp_hit:
            out[str(eid)] = emp_hit
    return out


def _vet_question_groups(
    conn: psycopg.Connection,
    groups: list[tuple[list[str], list[str]]],
    frontier: _Frontier,
    settings: Settings,
    *,
    departments: list[str] | None = None,
) -> list[dict[str, dict[str, Any]]]:
    """Vet candidate questions across multiple areas with bulk embeddings and parallel batches."""
    out: list[dict[str, dict[str, Any]]] = [{} for _ in groups]
    unique_questions: list[str] = []
    seen_q: set[str] = set()
    for questions, _people in groups:
        for question in questions:
            if question not in seen_q:
                seen_q.add(question)
                unique_questions.append(question)
    if not unique_questions:
        return out
    try:
        vectors = embed_texts(unique_questions, settings)
    except Exception:  # noqa: BLE001 - never fail the run
        logger.warning(
            "question vetting could not embed %d questions", len(unique_questions)
        )
        return out

    passages_by_q: dict[str, str] = {}
    for question, vector in zip(unique_questions, vectors, strict=True):
        passages = "\n".join(
            f"  - {text}" for text in _closest_passages(conn, vector)
        )
        passages_by_q[question] = passages or "  (no passages)"

    dept_list = _departments(conn) if departments is None else departments
    by_lower = {dep.lower(): dep for dep in dept_list}
    raw_template = KNOWLEDGE_PROMPT_PATH.read_text(encoding="utf-8").replace(
        "{{departments}}", "\n".join(dept_list) or "(none)"
    )

    by_people: dict[tuple[str, ...], list[tuple[int, str]]] = {}
    for group_idx, (questions, people) in enumerate(groups):
        if not questions:
            continue
        people_key = tuple(people)
        bucket = by_people.setdefault(people_key, [])
        for question in questions:
            bucket.append((group_idx, question))

    tasks: list[tuple[tuple[str, ...], list[tuple[int, str]], str]] = []
    for people_key, items in by_people.items():
        template = raw_template.replace(
            "{{people}}", "\n".join(people_key) or "(none)"
        )
        for start in range(0, len(items), CHECK_BATCH):
            batch_items = items[start : start + CHECK_BATCH]
            blocks = [
                f"{number}. {question}\n{passages_by_q[question]}"
                for number, (_gidx, question) in enumerate(batch_items, start=1)
            ]
            tasks.append(
                (
                    people_key,
                    batch_items,
                    template.replace("{{candidates}}", "\n\n".join(blocks)),
                )
            )

    if not tasks:
        return out

    responses: list[dict[str, Any] | None] = [None] * len(tasks)
    if len(tasks) == 1:
        try:
            responses[0] = frontier.ask(tasks[0][2])
        except FrontierCapReached:
            raise
        except Exception:  # noqa: BLE001 - never fail the run
            logger.warning("question vetting failed for %d questions", len(tasks[0][1]))
    else:
        with ThreadPoolExecutor(max_workers=min(REPORT_WORKERS, len(tasks))) as pool:
            futures = {
                pool.submit(frontier.ask, prompt): idx
                for idx, (_pk, _items, prompt) in enumerate(tasks)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    responses[idx] = future.result()
                except FrontierCapReached:
                    raise
                except Exception:  # noqa: BLE001 - never fail the run
                    logger.warning(
                        "question vetting failed for %d questions",
                        len(tasks[idx][1]),
                    )

    for (people_key, batch_items, _prompt), result in zip(
        tasks, responses, strict=True
    ):
        if not isinstance(result, dict):
            continue
        results = result.get("results")
        if not isinstance(results, list):
            continue
        people_lower = {name.lower(): name for name in people_key}
        for item in results:
            if not isinstance(item, dict):
                continue
            try:
                number = int(item.get("n"))
                importance = int(item.get("importance"))
            except (TypeError, ValueError):
                continue
            if not 1 <= number <= len(batch_items):
                continue
            group_idx, question = batch_items[number - 1]
            out[group_idx][question] = {
                "answered": bool(item.get("answered")),
                "importance": max(1, min(5, importance)),
                "person": people_lower.get(
                    str(item.get("person") or "").strip().lower(), ""
                ),
                "department": by_lower.get(
                    str(item.get("department") or "").strip().lower(), ""
                ),
            }
    return out


def vet_questions(
    conn: psycopg.Connection,
    questions: list[str],
    people: list[str],
    frontier: _Frontier,
    settings: Settings,
    *,
    departments: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Vet candidate questions against everything the brain knows.

    Returns ``{question: {answered, importance, person, department}}`` for the
    questions the check actually judged. A question missing from the result
    was not checked (model or embedding failure) and must not be stored.
    """
    if not questions:
        return {}
    return _vet_question_groups(
        conn,
        [(questions, people)],
        frontier,
        settings,
        departments=departments,
    )[0]


def _worth_asking(verdicts: dict[str, dict[str, Any]], limit: int) -> list[str]:
    """Unanswered, important questions — the most important ``limit`` of them."""
    good = [
        question
        for question, verdict in verdicts.items()
        if not verdict["answered"] and verdict["importance"] >= MIN_IMPORTANCE
    ]
    good.sort(key=lambda question: -verdicts[question]["importance"])
    return good[: max(0, limit)]


def _store_open_questions(
    conn: psycopg.Connection,
    report: dict[str, Any],
    entity_ids: list[str],
    frontier: _Frontier,
    settings: Settings,
    seen: set[str],
    *,
    departments: list[str] | None = None,
) -> int:
    """Store the report's few questions that matter and the brain cannot answer.

    ``seen`` holds this run's questions only, so one gap raised by several
    reports in the same run is stored once.
    """
    return _store_open_questions_chunk(
        conn,
        [(report, entity_ids)],
        frontier,
        settings,
        seen,
        departments=departments,
    )


def _store_open_questions_chunk(
    conn: psycopg.Connection,
    entries: list[tuple[dict[str, Any], list[str]]],
    frontier: _Frontier,
    settings: Settings,
    seen: set[str],
    *,
    departments: list[str] | None = None,
) -> int:
    """Store vetted open questions for a chunk of reports in batched bulk calls."""
    if not entries:
        return 0
    fresh_per_entry: list[list[str]] = []
    to_translate: list[tuple[int, int, str]] = []
    for entry_idx, (report, _entity_ids) in enumerate(entries):
        fresh: list[str] = []
        for question in report["open_questions"]:
            key = " ".join(question.lower().split())
            if key and key not in seen:
                seen.add(key)
                q_text = str(question or "").strip()
                if q_text:
                    fresh.append(q_text)
                    if looks_english(q_text) is not True:
                        to_translate.append((entry_idx, len(fresh) - 1, q_text))
        fresh_per_entry.append(fresh)

    if to_translate:
        if len(to_translate) == 1:
            e_idx, q_idx, q_text = to_translate[0]
            fresh_per_entry[e_idx][q_idx] = (
                ensure_english_question(q_text, frontier.ask) or ""
            )
        else:
            with ThreadPoolExecutor(
                max_workers=min(REPORT_WORKERS, len(to_translate))
            ) as pool:
                futures = {
                    pool.submit(ensure_english_question, q_text, frontier.ask): (
                        e_idx,
                        q_idx,
                    )
                    for e_idx, q_idx, q_text in to_translate
                }
                for future in as_completed(futures):
                    e_idx, q_idx = futures[future]
                    try:
                        fresh_per_entry[e_idx][q_idx] = future.result() or ""
                    except FrontierCapReached:
                        raise

    english_per_entry: list[list[str]] = [
        [q for q in qs if q] for qs in fresh_per_entry
    ]
    all_eids = sorted(
        {
            str(eid)
            for idx, (_rep, eids) in enumerate(entries)
            if english_per_entry[idx]
            for eid in eids
        }
    )
    people_by_id = _area_people_bulk(conn, all_eids)
    groups: list[tuple[list[str], list[str]]] = []
    for idx, (_report, entity_ids) in enumerate(entries):
        people = sorted(
            {people_by_id[str(eid)] for eid in entity_ids if str(eid) in people_by_id}
        )[:MAX_PEOPLE_IN_CHECK]
        groups.append((english_per_entry[idx], people))

    verdicts_per_entry = _vet_question_groups(
        conn, groups, frontier, settings, departments=departments
    )
    written = 0
    for (report, entity_ids), verdicts in zip(entries, verdicts_per_entry, strict=True):
        for question in _worth_asking(verdicts, MAX_QUESTIONS_PER_AREA):
            verdict = verdicts[question]
            conn.execute(
                "INSERT INTO cmap.open_question "
                "(question, why, entity_ids, state, priority, suggested_person, department) "
                "VALUES (%s, %s, %s, 'open', %s, %s, %s)",
                (
                    question,
                    report["title"],
                    entity_ids,
                    verdict["importance"],
                    verdict["person"] or None,
                    verdict["department"],
                ),
            )
            written += 1
    return written


def _refresh_open_questions(
    conn: psycopg.Connection,
    run_started: Any,
    kept_sets: set[frozenset[str]],
    frontier: _Frontier,
    settings: Settings,
    *,
    departments: list[str] | None = None,
) -> int:
    """Retire waiting questions that no longer deserve to be asked.

    A rebuilt area's questions were regenerated from current knowledge, so its
    old unasked ones go. Unasked questions of areas kept as they were are
    vetted again: answered or unimportant ones go, and each area keeps at most
    ``MAX_QUESTIONS_PER_AREA``. A question the check could not judge stays as
    it is.
    """
    rows = conn.execute(
        "SELECT id::text, question, entity_ids FROM cmap.open_question "
        "WHERE state = 'open' AND target_employee_id IS NULL AND created_at < %s "
        "ORDER BY created_at, id",
        (run_started,),
    ).fetchall()
    retire: list[str] = []
    areas: dict[frozenset[str], list[tuple[str, str, list[str]]]] = {}
    for qid, question, ids in rows:
        key = frozenset(str(item) for item in (ids or []))
        if key not in kept_sets:
            retire.append(str(qid))
        else:
            areas.setdefault(key, []).append((str(qid), str(question), list(ids or [])))
    dept_list = _departments(conn) if departments is None else departments
    area_values = list(areas.values())
    for start in range(0, len(area_values), 64):
        area_chunk = area_values[start : start + 64]
        chunk_eids = sorted(
            {str(eid) for members in area_chunk for eid in members[0][2]}
        )
        people_by_id = _area_people_bulk(conn, chunk_eids)
        groups: list[tuple[list[str], list[str]]] = []
        chunk_maps: list[dict[str, str]] = []
        for members in area_chunk:
            ids_by_question: dict[str, str] = {}
            for qid, question, _ids in members:
                if question in ids_by_question:
                    retire.append(qid)
                else:
                    ids_by_question[question] = qid
            people = sorted(
                {
                    people_by_id[str(eid)]
                    for eid in members[0][2]
                    if str(eid) in people_by_id
                }
            )[:MAX_PEOPLE_IN_CHECK]
            groups.append((list(ids_by_question), people))
            chunk_maps.append(ids_by_question)
        verdicts_chunk = _vet_question_groups(
            conn, groups, frontier, settings, departments=dept_list
        )
        for ids_by_question, verdicts in zip(chunk_maps, verdicts_chunk, strict=True):
            keep = set(_worth_asking(verdicts, MAX_QUESTIONS_PER_AREA))
            for question, verdict in verdicts.items():
                qid = ids_by_question[question]
                if question not in keep:
                    retire.append(qid)
                    continue
                conn.execute(
                    "UPDATE cmap.open_question SET priority = %s, suggested_person = %s, "
                    "department = %s WHERE id = %s",
                    (
                        verdict["importance"],
                        verdict["person"] or None,
                        verdict["department"],
                        qid,
                    ),
                )
        conn.commit()
    if retire:
        conn.execute(
            "UPDATE cmap.open_question SET state = 'dismissed' WHERE id = ANY(%s::uuid[])",
            (retire,),
        )
    conn.commit()
    return len(retire)


def _split_report_md(report_md: str) -> tuple[str, str]:
    """Recover ``(title, summary)`` from the Markdown ``_report_md`` renders."""
    head = str(report_md).split("\n## Findings", 1)[0]
    title, _, summary = head.partition("\n\n")
    if title.startswith("# "):
        title = title[2:]
    return title.strip(), summary.strip()


def _parse_row(row: Any) -> dict[str, Any]:
    """One community row as reuse metadata (title/summary split from report_md)."""
    title, summary = _split_report_md(row[2])
    findings = row[3] if isinstance(row[3], list) else json.loads(row[3] or "[]")
    return {
        "row_id": str(row[0]),
        "title": title or str(row[1] or ""),
        "summary": summary,
        "findings": findings,
        "entity_ids": frozenset(str(item) for item in (row[4] or [])),
        "content_hash": row[5],
        "incomplete": bool(row[6]),
    }


_ROW_COLUMNS = (
    "id::text, title, report_md, findings, entity_ids, content_hash, incomplete"
)


def _previous_l0_rows(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Level-0 rows as stored, for Jaccard identity matching and reuse.

    A rerun over the same graph matches each new cluster to these rows,
    reusing the matched row's id and title (and its whole report when the
    content hash is unchanged), so a pass stopped partway continues where it
    died.
    """
    rows = conn.execute(
        f"SELECT {_ROW_COLUMNS}, function_id::text FROM cmap.community WHERE level = 0"
    ).fetchall()
    out = []
    for row in rows:
        parsed = _parse_row(row)
        parsed["function_id"] = str(row[7]) if row[7] is not None else None
        out.append(parsed)
    return out


def _stored_row(conn: psycopg.Connection, row_id: str) -> dict[str, Any] | None:
    """One community row by id, or None."""
    row = conn.execute(
        f"SELECT {_ROW_COLUMNS} FROM cmap.community WHERE id = %s", (row_id,)
    ).fetchone()
    return None if row is None else _parse_row(row)


def _company_row(conn: psycopg.Connection) -> dict[str, Any] | None:
    """The newest level-2 row (the company report's stable identity)."""
    row = conn.execute(
        f"SELECT {_ROW_COLUMNS} FROM cmap.community WHERE level = 2 "
        "ORDER BY graph_version DESC, created_at DESC LIMIT 1"
    ).fetchone()
    return None if row is None else _parse_row(row)


def _summary_of(stored: dict[str, Any]) -> dict[str, Any]:
    """The parent-facing summary block of one report."""
    return {
        "title": stored["title"],
        "summary": stored["summary"],
        "findings": stored["findings"],
        "source_ids": sorted(
            {
                source_id
                for finding in stored["findings"]
                for source_id in finding.get("source_ids", [])
            }
        ),
    }


def _ask_with_retry(
    frontier: _Frontier, scope: str, extra_instructions: str, context: str
) -> dict[str, Any] | None:
    """One community report; a flaky answer never kills the pass.

    ``frontier.ask`` already retries transient failures; one more full ask
    follows before the community is skipped and counted.
    """
    try:
        return _ask_report(frontier, scope, extra_instructions, context)
    except FrontierCapReached:
        raise
    except Exception as exc:
        logger.warning("community report failed: %s", exc)
    try:
        return _ask_report(frontier, scope, extra_instructions, context)
    except FrontierCapReached:
        raise
    except Exception as exc:
        logger.warning("community report failed on retry: %s", exc)
        return None


def _ask_many(
    frontier: _Frontier,
    tasks: list[tuple[str, str, str]],
    workers: int = REPORT_WORKERS,
) -> list[dict[str, Any] | None]:
    """Run report asks on a bounded pool, preserving input order in results.

    Only the frontier calls are parallel; contexts are built before and every
    store runs after, so the written rows are identical to a serial pass.
    """
    if not tasks:
        return []
    results: list[dict[str, Any] | None] = [None] * len(tasks)
    with ThreadPoolExecutor(max_workers=min(workers, len(tasks))) as pool:
        futures = {
            pool.submit(_ask_with_retry, frontier, scope, extra, context): index
            for index, (scope, extra, context) in enumerate(tasks)
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return results


def run_communities(settings: Settings | None = None) -> dict[str, Any]:
    """Detect communities and write their reports at levels 0, 1 and 2.

    Level 0 is Leiden per function bucket, level 1 is one report per function
    (row id = the function's id), level 2 is the company report. A report is
    reused only while its content hash is unchanged and every child report is
    present; otherwise it is regenerated in place under its stable id.
    """
    cfg = settings if settings is not None else get_settings()
    frontier = _Frontier(cfg, "reports")
    stats: dict[str, Any] = {
        "communities_l0": 0,
        "communities_l1": 0,
        "reports": 0,
        "reports_reused": 0,
        "reports_failed": 0,
        "findings_dropped": 0,
        "open_questions": 0,
        "open_questions_retired": 0,
        "cluster_ids_reused": 0,
        "unassigned_entities": 0,
    }
    seen_questions: set[str] = set()
    kept_sets: set[frozenset[str]] = set()
    with get_pool().connection() as conn:
        run_started = conn.execute("SELECT now()").fetchone()[0]
        nodes = _load_entities(conn)
        if not nodes:
            stats.update(frontier.usage)
            return stats
        edges = _load_edges(conn)
        valid_sources = {
            str(row[0]) for row in conn.execute("SELECT id FROM cmap.source").fetchall()
        }
        graph_version = int(
            conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM cmap.graph_version"
            ).fetchone()[0]
        )
        entity_ids = [node["id"] for node in nodes]
        cluster_edges = _clustering_edges(edges)
        entity_sources = _entity_sources(conn)
        entity_vectors = _entity_vectors(conn)
        names = {node["id"]: node["name"] for node in nodes}
        function_names = _function_names(conn)
        hash_index = _load_content_hash_index(conn)
        edges_by_entity: dict[str, list[dict[str, Any]]] = {}
        for edge in edges:
            edges_by_entity.setdefault(edge["from"], []).append(edge)
            if edge["to"] != edge["from"]:
                edges_by_entity.setdefault(edge["to"], []).append(edge)

        buckets = _function_buckets(conn, nodes)
        stats["unassigned_entities"] = sum(
            len(bucket["nodes"]) for bucket in buckets if bucket["function_id"] is None
        )
        if stats["unassigned_entities"]:
            logger.warning(
                "%d entities carry no active function assignment and are "
                "clustered in the unassigned bucket",
                stats["unassigned_entities"],
            )

        # Level 0: one Leiden pass per function bucket — an entity assigned to
        # several functions appears in one cluster per function.
        clusters: list[dict[str, Any]] = []
        for bucket in buckets:
            bucket_ids = [member["id"] for member in bucket["nodes"]]
            membership = _level0_membership(
                cluster_edges, bucket_ids, entity_sources, entity_vectors
            )
            grouped: dict[int, list[str]] = {}
            for entity_id, community in membership.items():
                grouped.setdefault(community, []).append(entity_id)
            node_by_id = {member["id"]: member for member in bucket["nodes"]}
            for community in sorted(grouped):
                member_ids = sorted(grouped[community])
                clusters.append(
                    {
                        "function_id": bucket["function_id"],
                        "function_name": bucket["function_name"],
                        "member_ids": member_ids,
                        "members": [node_by_id[entity_id] for entity_id in member_ids],
                    }
                )
        clusters.sort(
            key=lambda cluster: (
                cluster["function_id"] or "",
                tuple(cluster["member_ids"]),
            )
        )
        stats["communities_l0"] = len(clusters)
        del entity_vectors, entity_sources, cluster_edges, buckets

        # Stable identities: each cluster continues the previous build's
        # cluster with the highest Jaccard overlap in the same function,
        # reusing that row's id and title (repair C3).
        previous_by_function: dict[str | None, list[dict[str, Any]]] = {}
        for row in _previous_l0_rows(conn):
            previous_by_function.setdefault(row["function_id"], []).append(row)
        by_function: dict[str | None, list[dict[str, Any]]] = {}
        for cluster in clusters:
            cluster["content_hash"] = _content_hash(
                conn, cluster["member_ids"], index=hash_index
            )
            cluster["handoffs"] = _handoff_lines(
                edges,
                set(cluster["member_ids"]),
                names,
                function_names,
                edges_by_entity=edges_by_entity,
            )
            cluster["failed"] = False
            cluster["kept"] = False
            cluster["summary"] = None
            cluster["previous"] = None
            by_function.setdefault(cluster["function_id"], []).append(cluster)
        for function_id, group in by_function.items():
            matched = _match_previous(group, previous_by_function.get(function_id, []))
            for position, cluster in enumerate(group):
                previous = matched.get(position)
                if previous is None:
                    cluster["row_id"] = None
                    cluster["title_override"] = None
                    cluster["reuse"] = False
                    continue
                cluster["previous"] = previous
                cluster["row_id"] = previous["row_id"]
                cluster["title_override"] = previous["title"]
                cluster["reuse"] = (
                    not previous["incomplete"]
                    and previous["content_hash"] == cluster["content_hash"]
                )
                stats["cluster_ids_reused"] += 1

        # Ask level 0 only where the content hash changed or the row is new,
        # committing chunk by chunk so progress survives restarts and memory
        # stays bounded.
        disagreements_by_entity = _load_disagreements_by_entity(conn)
        departments = _departments(conn)
        for cluster in clusters:
            if not cluster["reuse"]:
                continue
            cluster["summary"] = _summary_of(cluster["previous"])
            cluster["kept"] = True
            conn.execute(
                "UPDATE cmap.community SET graph_version = %s, "
                "function_id = %s WHERE id = %s",
                (graph_version, cluster["function_id"], cluster["row_id"]),
            )
            kept_sets.add(frozenset(cluster["member_ids"]))
            stats["reports_reused"] += 1
            stats["reports"] += 1
        conn.commit()

        ask_items = [cluster for cluster in clusters if not cluster["reuse"]]
        total_ask = len(ask_items)
        for start in range(0, total_ask, L0_ASK_CHUNK):
            chunk = ask_items[start : start + L0_ASK_CHUNK]
            chunk_eids = sorted(
                {eid for cluster in chunk for eid in cluster["member_ids"]}
            )
            quotes_by_entity = _quote_rows_bulk(conn, chunk_eids)
            raw_lines_list = [
                _context_l0_lines(
                    conn,
                    cluster["members"],
                    edges,
                    function_name=cluster["function_name"],
                    handoffs=cluster["handoffs"],
                    edges_by_entity=edges_by_entity,
                    disagreements_by_entity=disagreements_by_entity,
                    quotes_by_entity=quotes_by_entity,
                )
                for cluster in chunk
            ]
            fit_results: list[tuple[str, bool]] = [("", False)] * len(chunk)
            if len(chunk) == 1:
                fit_results[0] = _fit(raw_lines_list[0], frontier)
            else:
                with ThreadPoolExecutor(
                    max_workers=min(REPORT_WORKERS, len(chunk))
                ) as pool:
                    futures = {
                        pool.submit(_fit, lines, frontier): idx
                        for idx, lines in enumerate(raw_lines_list)
                    }
                    for future in as_completed(futures):
                        fit_results[futures[future]] = future.result()
            chunk_contexts: list[str] = []
            for cluster, (context, incomplete) in zip(chunk, fit_results, strict=True):
                chunk_contexts.append(context)
                cluster["context_incomplete"] = incomplete
            asked = _ask_many(
                frontier,
                [(SCOPE_L0, "", context) for context in chunk_contexts],
            )
            question_entries: list[tuple[dict[str, Any], list[str]]] = []
            for cluster, report in zip(chunk, asked, strict=True):
                if report is None:
                    # A failed child leaves no row; its parents are regenerated
                    # (never reused) and marked incomplete below.
                    stats["reports_failed"] += 1
                    cluster["failed"] = True
                    continue
                report["handoffs"] = cluster["handoffs"]
                row_id, dropped = _store(
                    conn,
                    0,
                    None,
                    report,
                    cluster["member_ids"],
                    graph_version,
                    valid_sources,
                    row_id=cluster["row_id"],
                    function_id=cluster["function_id"],
                    content_hash=cluster["content_hash"],
                    incomplete=cluster["context_incomplete"],
                    title_override=cluster["title_override"],
                )
                stats["findings_dropped"] += dropped
                question_entries.append((report, cluster["member_ids"]))
                cluster["row_id"] = row_id
                cluster["summary"] = _summary_of(report)
                cluster["kept"] = True
                stats["reports"] += 1
            stats["open_questions"] += _store_open_questions_chunk(
                conn,
                question_entries,
                frontier,
                cfg,
                seen_questions,
                departments=departments,
            )
            conn.commit()
            logger.info(
                "communities l0 progress: %d/%d",
                min(start + len(chunk), total_ask),
                total_ask,
            )

        # Level 1: one report per function; the row id IS the function's id,
        # so it is stable for ever and references survive regeneration.
        function_groups: dict[str, list[dict[str, Any]]] = {}
        for cluster in clusters:
            if cluster["function_id"] is not None:
                function_groups.setdefault(cluster["function_id"], []).append(cluster)
        level1_rows: dict[str, str] = {}
        level1_summaries: list[tuple[int, dict[str, Any]]] = []
        for function_id in sorted(
            function_groups,
            key=lambda key: (function_groups[key][0]["function_name"], key),
        ):
            group = function_groups[function_id]
            function_name = group[0]["function_name"]
            member_ids = sorted(
                {member for cluster in group for member in cluster["member_ids"]}
            )
            content_hash = _content_hash(conn, member_ids, index=hash_index)
            function_handoffs = _handoff_lines(
                edges,
                set(member_ids),
                names,
                function_names,
                edges_by_entity=edges_by_entity,
            )
            available = [
                cluster["summary"]
                for cluster in group
                if cluster["summary"] is not None
            ]
            complete = len(available) == len(group)
            existing = _stored_row(conn, function_id)
            stats["communities_l1"] += 1
            if (
                existing
                and not existing["incomplete"]
                and existing["content_hash"] == content_hash
                and complete
            ):
                kept_sets.add(frozenset(member_ids))
                conn.execute(
                    "UPDATE cmap.community SET graph_version = %s WHERE id = %s",
                    (graph_version, function_id),
                )
                conn.commit()
                level1_rows[function_id] = function_id
                reused_summary = _summary_of(existing)
                reused_summary["title"] = function_name
                level1_summaries.append((len(member_ids), reused_summary))
                stats["reports_reused"] += 1
                stats["reports"] += 1
                continue
            if not available:
                # Every child failed: a report built from nothing is worse
                # than the old one flagged incomplete for the next run.
                if existing:
                    conn.execute(
                        "UPDATE cmap.community SET incomplete = true WHERE id = %s",
                        (function_id,),
                    )
                    conn.commit()
                continue
            l1_aliases: dict[str, str] = {}
            context, context_incomplete = _context_reports(
                available,
                frontier,
                header=f"FUNCTION: {function_name}",
                handoffs=function_handoffs,
                alias_map=l1_aliases,
            )
            report = _ask_with_retry(frontier, SCOPE_L1, "", context)
            if report is None:
                stats["reports_failed"] += 1
                if existing:
                    conn.execute(
                        "UPDATE cmap.community SET incomplete = true WHERE id = %s",
                        (function_id,),
                    )
                    conn.commit()
                continue
            _resolve_source_aliases(report, l1_aliases)
            report["handoffs"] = function_handoffs
            row_id, dropped = _store(
                conn,
                1,
                None,
                report,
                member_ids,
                graph_version,
                valid_sources,
                row_id=function_id,
                function_id=function_id,
                content_hash=content_hash,
                incomplete=not complete or context_incomplete,
                title_override=function_name,
            )
            stats["findings_dropped"] += dropped
            stats["open_questions"] += _store_open_questions(
                conn,
                report,
                member_ids,
                frontier,
                cfg,
                seen_questions,
                departments=departments,
            )
            conn.commit()
            level1_rows[function_id] = row_id
            l1_summary = _summary_of(report)
            l1_summary["title"] = function_name
            level1_summaries.append((len(member_ids), l1_summary))
            stats["reports"] += 1

        # Level 2: the company report. When business functions exist, build from
        # the Level-1 function reports (ordered largest-first) rather than
        # thousands of raw Level-0 clusters so the company summary never
        # truncates or lets an unassigned/fringe cluster dominate the company
        # view. Fall back to Level-0 summaries only when no functions exist.
        any_failed = stats["reports_failed"] > 0
        if level1_summaries:
            company_inputs = [
                summary
                for _count, summary in sorted(
                    level1_summaries,
                    key=lambda item: (-item[0], str(item[1].get("title") or "")),
                )
            ]
        else:
            company_inputs = [
                cluster["summary"]
                for cluster in clusters
                if cluster["summary"] is not None
            ]
        matrix_lines = _handoff_matrix_lines(
            edges, function_names, _flow_performer_pairs(conn)
        )
        # The matrix is computed from relations and flows (E4): the hash covers
        # the flow-step hand-offs too, so a flow change regenerates it.
        company_hash = _content_hash(conn, entity_ids, flows=True, index=hash_index)
        existing_company = _company_row(conn)
        if (
            existing_company
            and not existing_company["incomplete"]
            and existing_company["content_hash"] == company_hash
            and not any_failed
        ):
            company_row = existing_company["row_id"]
            kept_sets.add(frozenset(entity_ids))
            conn.execute(
                "UPDATE cmap.community SET graph_version = %s WHERE id = %s",
                (graph_version, company_row),
            )
            conn.commit()
            stats["reports_reused"] += 1
        else:
            l2_aliases: dict[str, str] = {}
            company_context, context_incomplete = _context_reports(
                company_inputs,
                frontier,
                handoffs=matrix_lines,
                max_findings_per_row=MAX_L2_FINDINGS_PER_FUNCTION,
                alias_map=l2_aliases,
            )
            company = _ask_with_retry(
                frontier, SCOPE_L2, COMPANY_EXTRA, company_context
            )
            if company is None:
                raise RuntimeError("company community report failed after retries")
            _resolve_source_aliases(company, l2_aliases)
            company["handoffs"] = matrix_lines
            company_row, dropped = _store(
                conn,
                2,
                None,
                company,
                entity_ids,
                graph_version,
                valid_sources,
                row_id=existing_company["row_id"] if existing_company else None,
                content_hash=company_hash,
                incomplete=any_failed or context_incomplete,
            )
            stats["findings_dropped"] += dropped
            stats["open_questions"] += _store_open_questions(
                conn,
                company,
                entity_ids,
                frontier,
                cfg,
                seen_questions,
                departments=departments,
            )
            conn.commit()
        stats["reports"] += 1

        # Wire the tree: level 0 under its function report (unassigned
        # clusters straight under the company), functions under the company.
        for function_id, parent_row in level1_rows.items():
            children = [
                cluster["row_id"]
                for cluster in function_groups[function_id]
                if cluster["kept"] and cluster["row_id"]
            ]
            if children:
                conn.execute(
                    "UPDATE cmap.community SET parent_id = %s WHERE id = ANY(%s::uuid[])",
                    (parent_row, children),
                )
        unassigned_children = [
            cluster["row_id"]
            for cluster in clusters
            if cluster["function_id"] is None and cluster["kept"] and cluster["row_id"]
        ]
        if unassigned_children:
            conn.execute(
                "UPDATE cmap.community SET parent_id = %s WHERE id = ANY(%s::uuid[])",
                (company_row, unassigned_children),
            )
        if level1_rows:
            conn.execute(
                "UPDATE cmap.community SET parent_id = %s WHERE id = ANY(%s::uuid[])",
                (company_row, list(level1_rows.values())),
            )
        conn.commit()
        stats["open_questions_retired"] = _refresh_open_questions(
            conn, run_started, kept_sets, frontier, cfg, departments=departments
        )
        if cfg.brain_community_prune_enabled:
            selected = [
                cluster["row_id"]
                for cluster in clusters
                if cluster["kept"] and cluster["row_id"]
            ]
            selected += [*level1_rows.values(), company_row]
            stats["communities_pruned"] = prune_old_versions(
                conn, graph_version, selected
            )
            conn.commit()
    single_source = sum(1 for n in nodes if int(n.get("source_count") or 0) <= 1)
    stats["source_count_1_entities"] = single_source
    stats["source_count_1_share"] = round(single_source / len(nodes), 4)
    stats.update(frontier.usage)
    return stats


KEEP_VERSIONS = 2


def prune_old_versions(
    conn: psycopg.Connection, graph_version: int, selected: list[str]
) -> int:
    """Delete reports superseded more than one build ago; return the count.

    Runs only after a successful build. ``selected`` is every report this
    build chose (new or reused). A report left at the current version number
    that this build did not choose (two builds of one projection) is first
    moved back one version, so "current" stays exactly this build's choice.
    Reports older than the newest ``KEEP_VERSIONS`` versions are deleted
    unless a recommendation or a review flag still points at them.
    """
    conn.execute(
        "UPDATE cmap.community SET graph_version = %s "
        "WHERE graph_version >= %s AND NOT (id = ANY(%s::uuid[]))",
        (graph_version - 1, graph_version, selected),
    )
    doomed = [
        str(row[0])
        for row in conn.execute(
            "SELECT c.id FROM cmap.community c WHERE c.graph_version <= %s "
            "AND NOT EXISTS (SELECT 1 FROM cmap.recommendation r "
            "                WHERE r.community_id = c.id) "
            "AND NOT EXISTS (SELECT 1 FROM cmap.review_flag f "
            "                WHERE f.item_type = 'community' AND f.item_id = c.id::text)",
            (graph_version - KEEP_VERSIONS,),
        ).fetchall()
    ]
    if not doomed:
        return 0
    conn.execute(
        "UPDATE cmap.community SET parent_id = NULL "
        "WHERE parent_id = ANY(%s::uuid[]) AND NOT (id = ANY(%s::uuid[]))",
        (doomed, doomed),
    )
    conn.execute(
        "DELETE FROM cmap.translation WHERE kind = 'community' AND ref_id = ANY(%s)",
        (doomed,),
    )
    conn.execute("DELETE FROM cmap.community WHERE id = ANY(%s::uuid[])", (doomed,))
    return len(doomed)


def handle_communities(job: dict[str, Any]) -> None:
    """Job ``communities``: Leiden levels 0-2 and one report per community."""
    stats = run_communities()
    job_id = job.get("id")
    if job_id is not None:
        with get_pool().connection() as conn:
            conn.execute(
                "UPDATE cmap.job SET payload = jsonb_set(payload, '{usage}', %s::jsonb) WHERE id = %s",
                (json.dumps(stats), job_id),
            )
            conn.commit()
    logger.info("communities stats=%s", stats)
    # Step 13: recommendations run after every communities pass.
    enqueue_job("recommend", {})
