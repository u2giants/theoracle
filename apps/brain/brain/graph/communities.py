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
truncated silently.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import igraph as ig
import leidenalg
import psycopg
import tiktoken

from brain.config import Settings, get_settings
from brain.contradictions import disagreement_lines
from brain.db import enqueue_job, get_pool
from brain.embed import embed_texts, vector_literal
from brain.graph.project import _load_edges, _load_entities
from brain.lang import detect_language
from brain.resolve.resolve import FrontierCapReached, _Frontier
from brain.translate import upsert_translation

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
REPORT_WORKERS = 6
# Repair C3: a level-0 cluster continues the previous build's cluster with the
# highest Jaccard overlap at or above this threshold (same function only).
CLUSTER_MATCH_MIN_JACCARD = 0.5
# Clustering edges: MENTIONS and CONTRADICTS say nothing about how work moves;
# sequence and hand-off relations carry the flow of work and count double.
CLUSTER_EDGE_EXCLUDED = frozenset({"MENTIONS", "CONTRADICTS"})
CLUSTER_EDGE_KIND_WEIGHTS = {"PRECEDES": 2.0, "HANDS_OFF_TO": 2.0}

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


def _tokens(text: str) -> int:
    """Approximate token count with the cl100k tokenizer."""
    encoder = tiktoken.get_encoding("cl100k_base")
    return len(encoder.encode(text, disallowed_special=()))


def _fit(lines: list[str], frontier: _Frontier, _round: int = 0) -> str:
    """Join context lines under the token budget by map-reduce, never truncation.

    An over-budget context is split into batches, each batch is summarised by
    the frontier seat (``prompts/context_summary.md``) and the summaries are
    combined; a still-over-budget combination is summarised again, up to
    ``MAX_SUMMARY_ROUNDS`` rounds. Every input line reaches a model call — the
    old behaviour silently dropped lines from the end and marked the damage
    "context truncated" (audit C2).
    """
    text = "\n".join(lines)
    if _tokens(text) <= MAX_CONTEXT_TOKENS:
        return text
    if _round >= MAX_SUMMARY_ROUNDS:
        raise RuntimeError("context map-reduce did not converge under the token budget")
    summaries = [
        _ask_summary(frontier, "\n".join(batch))
        for batch in _batch_lines(lines, max(64, MAX_CONTEXT_TOKENS // 2))
    ]
    combined = [
        "COMBINED SUMMARIES (the full DATA below was summarised in batches; "
        "nothing was dropped):"
    ]
    combined.extend(summaries)
    return _fit(combined, frontier, _round + 1)


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
        weighted["weight"] = float(edge["weight"]) * CLUSTER_EDGE_KIND_WEIGHTS.get(
            rel_type, 1.0
        )
        out.append(weighted)
    return out


def _content_hash(conn: psycopg.Connection, entity_ids: list[str]) -> str:
    """Hash of a report's inputs: sorted entity and relation ids, stamped.

    The hash changes whenever any member entity or any relation among them
    changes (their updated-at), so a report regenerates on a new relation even
    when its entity set is unchanged (audit C2).
    """
    if not entity_ids:
        return hashlib.sha256(b"").hexdigest()
    rows = conn.execute(
        "SELECT 'e', e.id::text, e.updated_at FROM cmap.entity e "
        "WHERE e.id = ANY(%s::uuid[]) "
        "UNION ALL "
        "SELECT 'r', r.id::text, r.updated_at FROM cmap.relation r "
        "JOIN cmap.mention fm ON fm.id = r.from_mention_id "
        "JOIN cmap.mention tm ON tm.id = r.to_mention_id "
        "WHERE fm.entity_id = ANY(%s::uuid[]) AND tm.entity_id = ANY(%s::uuid[])",
        (entity_ids, entity_ids, entity_ids),
    ).fetchall()
    parts = sorted(f"{kind}:{row_id}:{stamp.isoformat()}" for kind, row_id, stamp in rows)
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


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
        out.append(
            {"function_id": None, "function_name": None, "nodes": unassigned}
        )
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
    changed = True
    while changed:
        changed = False
        groups: dict[int, list[int]] = {}
        for vertex, community in enumerate(membership):
            groups.setdefault(community, []).append(vertex)
        sizes = {community: len(members) for community, members in groups.items()}
        for community, members in sorted(groups.items()):
            if len(members) >= MIN_COMMUNITY:
                continue
            neighbour_weights: dict[int, float] = {}
            for (first, second), weight in adjacency.items():
                first_comm = membership[first]
                second_comm = membership[second]
                if first_comm == second_comm:
                    continue
                if first_comm == community:
                    neighbour_weights[second_comm] = (
                        neighbour_weights.get(second_comm, 0.0) + weight
                    )
                elif second_comm == community:
                    neighbour_weights[first_comm] = (
                        neighbour_weights.get(first_comm, 0.0) + weight
                    )
            if not neighbour_weights and entity_sources:
                # No edge to another community (an isolated entity or a
                # disconnected pair, most of a real graph: #410). Fall back to
                # the community sharing the most sources with it.
                own_sources: set[str] = set()
                for vertex in members:
                    own_sources |= entity_sources.get(entity_ids[vertex], set())
                for vertex, other in enumerate(membership):
                    if other == community:
                        continue
                    shared = own_sources & entity_sources.get(entity_ids[vertex], set())
                    if shared and sizes[other] + len(members) <= MAX_MERGED_COMMUNITY:
                        neighbour_weights[other] = neighbour_weights.get(
                            other, 0.0
                        ) + len(shared)
            if not neighbour_weights:
                continue
            target = max(
                neighbour_weights, key=lambda key: (neighbour_weights[key], -key)
            )
            for vertex in members:
                membership[vertex] = target
            changed = True
            break
    sources = [
        (entity_sources or {}).get(entity_id, set()) for entity_id in entity_ids
    ]
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
    has_sources = any(entity_sources)
    has_vectors = any(vector is not None for vector in entity_vectors)

    sums: dict[int, list[float]] = {}
    counts: dict[int, int] = {}
    for vertex, community in enumerate(membership):
        counts[community] = counts.get(community, 0) + 1
        vector = entity_vectors[vertex]
        if vector is not None:
            if community in sums:
                bucket = sums[community]
                for index, value in enumerate(vector):
                    bucket[index] += value
            else:
                sums[community] = list(vector)

    def _centroid(community: int) -> list[float] | None:
        bucket = sums.get(community)
        if bucket is None:
            return None
        count = counts[community]
        return [value / count for value in bucket]

    def _move(vertex: int, target: int) -> None:
        source = membership[vertex]
        membership[vertex] = target
        counts[source] -= 1
        counts[target] = counts.get(target, 0) + 1
        vector = entity_vectors[vertex]
        if vector is not None:
            bucket = sums.setdefault(target, [0.0] * len(vector))
            for index, value in enumerate(vector):
                bucket[index] += value
            if source in sums:
                old = sums[source]
                for index, value in enumerate(vector):
                    old[index] -= value
        if counts[source] == 0:
            counts.pop(source, None)
            sums.pop(source, None)

    def _split(members: list[int]) -> None:
        community = membership[members[0]]
        centre = _centroid(community)

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
        next_id = max(membership) + 1
        for chunk in chunks[1:]:
            for vertex in chunk:
                _move(vertex, next_id)
            next_id += 1

    while True:
        groups: dict[int, list[int]] = {}
        for vertex, community in enumerate(membership):
            groups.setdefault(community, []).append(vertex)
        oversized = [m for m in groups.values() if len(m) > MAX_COMMUNITY]
        if oversized:
            _split(oversized[0])
            continue
        smalls = [m for m in groups.values() if len(m) < MIN_COMMUNITY]
        if not smalls:
            return
        members = min(smalls, key=lambda m: (len(m), membership[m[0]]))
        community = membership[members[0]]
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
            if own:
                for vertex, other_community in enumerate(membership):
                    if other_community == community:
                        continue
                    shared = own & entity_sources[vertex]
                    if shared:
                        source_by[other_community] = (
                            source_by.get(other_community, 0) + len(shared)
                        )
        centre = _centroid(community) if has_vectors else None
        best: int | None = None
        best_key: tuple[float, float, int, int] | None = None
        for other_community, other_members in groups.items():
            if other_community == community:
                continue
            if len(other_members) + len(members) > MAX_COMMUNITY:
                continue
            score = 3.0 * edge_by.get(other_community, 0.0) + 2.0 * source_by.get(
                other_community, 0
            )
            if centre is not None:
                other_centre = _centroid(other_community)
                if other_centre is not None:
                    score += _cosine(centre, other_centre)
            tier = (
                0.0
                if len(other_members) + len(members) <= MAX_MERGED_COMMUNITY
                else 1.0
            )
            key = (
                1.0 if len(other_members) < MIN_COMMUNITY else 0.0,
                tier,
                -score,
                len(other_members),
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
            _move(vertex, best)


def _entity_sources(conn: psycopg.Connection) -> dict[str, set[str]]:
    """Entity id -> ids of the sources that mention it."""
    out: dict[str, set[str]] = {}
    for entity_id, source_id in conn.execute(
        "SELECT DISTINCT m.entity_id, ch.source_id FROM cmap.mention m "
        "JOIN cmap.chunk ch ON ch.id = m.chunk_id WHERE m.entity_id IS NOT NULL"
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


def _quote_rows(
    conn: psycopg.Connection, entity_ids: list[str]
) -> list[dict[str, Any]]:
    """Up to MAX_QUOTES_IN_CONTEXT quotes, preferring different sources."""
    rows = conn.execute(
        "SELECT DISTINCT ON (m.quote) m.quote, s.title, ch.source_id "
        "FROM cmap.mention m "
        "JOIN cmap.chunk ch ON ch.id = m.chunk_id "
        "JOIN cmap.source s ON s.id = ch.source_id "
        "WHERE m.entity_id = ANY(%s::uuid[]) "
        "ORDER BY m.quote, s.title",
        (entity_ids,),
    ).fetchall()
    picked: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for quote, title, source_id in rows:
        key = str(source_id)
        if key not in seen_sources and len(picked) < MAX_QUOTES_IN_CONTEXT:
            seen_sources.add(key)
            picked.append({"quote": str(quote), "title": str(title), "source_id": key})
    for quote, title, source_id in rows:
        if len(picked) >= MAX_QUOTES_IN_CONTEXT:
            break
        item = {"quote": str(quote), "title": str(title), "source_id": str(source_id)}
        if item not in picked:
            picked.append(item)
    return picked


def _context_l0(
    conn: psycopg.Connection,
    members: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    frontier: _Frontier,
    function_name: str | None = None,
) -> str:
    """Entity list, top edges and quotes for one level-0 community."""
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
    scoped = [
        edge for edge in edges if edge["from"] in member_ids and edge["to"] in member_ids
    ]
    scoped.sort(key=lambda edge: edge["weight"], reverse=True)
    lines.append("EDGES:")
    for edge in scoped[:MAX_EDGES_IN_CONTEXT]:
        descriptions = "; ".join(edge.get("descriptions") or [])
        lines.append(
            f"- {names.get(edge['from'], edge['from'])} -[{edge['rel_type']}]-> "
            f"{names.get(edge['to'], edge['to'])} weight={edge['weight']} "
            f"stances={edge.get('stances') or '{}'} {descriptions}"
        )
    quotes = _quote_rows(conn, [member["id"] for member in members])
    lines.append("SOURCES (findings must cite these ids):")
    seen: dict[str, str] = {}
    for item in quotes:
        seen[item["source_id"]] = item["title"]
    for source_id, title in seen.items():
        lines.append(f"- {source_id}: {title}")
    lines.append("QUOTES:")
    for item in quotes:
        lines.append(f'- [{item["source_id"]}] "{item["quote"]}"')
    disagreements = disagreement_lines(conn, [member["id"] for member in members])
    if disagreements:
        lines.append("SOURCES DISAGREE (state these as contradictions or gaps in findings):")
        for line in disagreements:
            lines.append(f"- {line}")
    return _fit(lines, frontier)


def _context_reports(
    rows: list[dict[str, Any]], frontier: _Frontier, header: str | None = None
) -> str:
    """Level-1/2 context: the reports beneath, with findings."""
    lines = []
    if header:
        lines.append(header)
    lines.append("REPORTS:")
    for row in rows:
        lines.append(f"## {row['title']}")
        lines.append(str(row["summary"]))
        for finding in row["findings"]:
            lines.append(f"- [{finding.get('kind')}] {finding.get('text')}")
        lines.append(f"sources: {', '.join(row.get('source_ids') or [])}")
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
    if canonical["title"] != report["title"] or detect_language(str(report["title"])) == "zh":
        upsert_translation("community", community_id, "title", "zh-CN", report["title"])
        upsert_translation("community", community_id, "summary", "zh-CN", report["summary"])
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


def _area_people(conn: psycopg.Connection, entity_ids: list[str]) -> list[str]:
    """Names of the people who belong to one area."""
    if not entity_ids:
        return []
    rows = conn.execute(
        "SELECT canonical_name FROM cmap.entity WHERE entity_type = 'Person' "
        "AND id = ANY(%s::uuid[]) ORDER BY canonical_name LIMIT %s",
        (entity_ids, MAX_PEOPLE_IN_CHECK),
    ).fetchall()
    return [str(row[0]) for row in rows]


def vet_questions(
    conn: psycopg.Connection,
    questions: list[str],
    people: list[str],
    frontier: _Frontier,
    settings: Settings,
) -> dict[str, dict[str, Any]]:
    """Vet candidate questions against everything the brain knows.

    Returns ``{question: {answered, importance, person, department}}`` for the
    questions the check actually judged. A question missing from the result
    was not checked (model or embedding failure) and must not be stored.
    """
    if not questions:
        return {}
    try:
        vectors = embed_texts(questions, settings)
    except Exception:  # noqa: BLE001 - never fail the run
        logger.warning("question vetting could not embed %d questions", len(questions))
        return {}
    departments = _departments(conn)
    template = (
        KNOWLEDGE_PROMPT_PATH.read_text(encoding="utf-8")
        .replace("{{people}}", "\n".join(people) or "(none)")
        .replace("{{departments}}", "\n".join(departments) or "(none)")
    )
    by_lower = {dep.lower(): dep for dep in departments}
    people_lower = {name.lower(): name for name in people}
    out: dict[str, dict[str, Any]] = {}
    for start in range(0, len(questions), CHECK_BATCH):
        batch = questions[start : start + CHECK_BATCH]
        blocks = []
        for number, (question, vector) in enumerate(
            zip(batch, vectors[start : start + CHECK_BATCH], strict=True), start=1
        ):
            passages = "\n".join(f"  - {text}" for text in _closest_passages(conn, vector))
            blocks.append(f"{number}. {question}\n{passages or '  (no passages)'}")
        try:
            result = frontier.ask(template.replace("{{candidates}}", "\n\n".join(blocks)))
        except Exception:  # noqa: BLE001 - never fail the run
            logger.warning("question vetting failed for %d questions", len(batch))
            continue
        results = result.get("results")
        if not isinstance(results, list):
            continue
        for item in results:
            if not isinstance(item, dict):
                continue
            try:
                number = int(item.get("n"))
                importance = int(item.get("importance"))
            except (TypeError, ValueError):
                continue
            if not 1 <= number <= len(batch):
                continue
            out[batch[number - 1]] = {
                "answered": bool(item.get("answered")),
                "importance": max(1, min(5, importance)),
                "person": people_lower.get(str(item.get("person") or "").strip().lower(), ""),
                "department": by_lower.get(
                    str(item.get("department") or "").strip().lower(), ""
                ),
            }
    return out


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
) -> int:
    """Store the report's few questions that matter and the brain cannot answer.

    ``seen`` holds this run's questions only, so one gap raised by several
    reports in the same run is stored once.
    """
    fresh = []
    for question in report["open_questions"]:
        key = " ".join(question.lower().split())
        if key and key not in seen:
            seen.add(key)
            fresh.append(question)
    verdicts = vet_questions(conn, fresh, _area_people(conn, entity_ids), frontier, settings)
    written = 0
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
    for members in areas.values():
        ids_by_question: dict[str, str] = {}
        for qid, question, _ids in members:
            if question in ids_by_question:
                retire.append(qid)
            else:
                ids_by_question[question] = qid
        verdicts = vet_questions(
            conn,
            list(ids_by_question),
            _area_people(conn, [str(item) for item in members[0][2]]),
            frontier,
            settings,
        )
        keep = set(_worth_asking(verdicts, MAX_QUESTIONS_PER_AREA))
        for question, verdict in verdicts.items():
            qid = ids_by_question[question]
            if question not in keep:
                retire.append(qid)
                continue
            conn.execute(
                "UPDATE cmap.open_question SET priority = %s, suggested_person = %s, "
                "department = %s WHERE id = %s",
                (verdict["importance"], verdict["person"] or None, verdict["department"], qid),
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
        f"SELECT {_ROW_COLUMNS}, function_id::text FROM cmap.community "
        "WHERE level = 0"
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
            conn.execute("SELECT COALESCE(MAX(version), 0) FROM cmap.graph_version")
            .fetchone()[0]
        )
        entity_ids = [node["id"] for node in nodes]
        cluster_edges = _clustering_edges(edges)
        entity_sources = _entity_sources(conn)
        entity_vectors = _entity_vectors(conn)

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

        # Stable identities: each cluster continues the previous build's
        # cluster with the highest Jaccard overlap in the same function,
        # reusing that row's id and title (repair C3).
        previous_by_function: dict[str | None, list[dict[str, Any]]] = {}
        for row in _previous_l0_rows(conn):
            previous_by_function.setdefault(row["function_id"], []).append(row)
        by_function: dict[str | None, list[dict[str, Any]]] = {}
        for cluster in clusters:
            cluster["content_hash"] = _content_hash(conn, cluster["member_ids"])
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

        # Ask level 0 only where the content hash changed or the row is new.
        # Contexts (and their map-reduce summaries) build serially first, so
        # the written rows match a serial pass exactly.
        ask_items = [cluster for cluster in clusters if not cluster["reuse"]]
        for position, cluster in enumerate(ask_items):
            cluster["ask_index"] = position
        asked = _ask_many(
            frontier,
            [
                (
                    SCOPE_L0,
                    "",
                    _context_l0(
                        conn,
                        cluster["members"],
                        edges,
                        frontier,
                        function_name=cluster["function_name"],
                    ),
                )
                for cluster in ask_items
            ],
        )
        for cluster in clusters:
            if cluster["reuse"]:
                cluster["summary"] = _summary_of(cluster["previous"])
                cluster["kept"] = True
                conn.execute(
                    "UPDATE cmap.community SET graph_version = %s, "
                    "function_id = %s WHERE id = %s",
                    (graph_version, cluster["function_id"], cluster["row_id"]),
                )
                conn.commit()
                kept_sets.add(frozenset(cluster["member_ids"]))
                stats["reports_reused"] += 1
                stats["reports"] += 1
                continue
            report = asked[cluster["ask_index"]]
            if report is None:
                # A failed child leaves no row; its parents are regenerated
                # (never reused) and marked incomplete below.
                stats["reports_failed"] += 1
                cluster["failed"] = True
                continue
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
                title_override=cluster["title_override"],
            )
            stats["findings_dropped"] += dropped
            stats["open_questions"] += _store_open_questions(
                conn, report, cluster["member_ids"], frontier, cfg, seen_questions
            )
            conn.commit()
            cluster["row_id"] = row_id
            cluster["summary"] = _summary_of(report)
            cluster["kept"] = True
            stats["reports"] += 1

        # Level 1: one report per function; the row id IS the function's id,
        # so it is stable for ever and references survive regeneration.
        function_groups: dict[str, list[dict[str, Any]]] = {}
        for cluster in clusters:
            if cluster["function_id"] is not None:
                function_groups.setdefault(cluster["function_id"], []).append(cluster)
        level1_rows: dict[str, str] = {}
        for function_id in sorted(
            function_groups,
            key=lambda key: (function_groups[key][0]["function_name"], key),
        ):
            group = function_groups[function_id]
            function_name = group[0]["function_name"]
            member_ids = sorted(
                {member for cluster in group for member in cluster["member_ids"]}
            )
            content_hash = _content_hash(conn, member_ids)
            available = [
                cluster["summary"] for cluster in group if cluster["summary"] is not None
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
            report = _ask_with_retry(
                frontier,
                SCOPE_L1,
                "",
                _context_reports(
                    available, frontier, header=f"FUNCTION: {function_name}"
                ),
            )
            if report is None:
                stats["reports_failed"] += 1
                if existing:
                    conn.execute(
                        "UPDATE cmap.community SET incomplete = true WHERE id = %s",
                        (function_id,),
                    )
                    conn.commit()
                continue
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
                incomplete=not complete,
                title_override=function_name,
            )
            stats["findings_dropped"] += dropped
            stats["open_questions"] += _store_open_questions(
                conn, report, member_ids, frontier, cfg, seen_questions
            )
            conn.commit()
            level1_rows[function_id] = row_id
            stats["reports"] += 1

        # Level 2: the company report over every level-0 summary. Any failed
        # child marks it incomplete so the next run regenerates it.
        any_failed = stats["reports_failed"] > 0
        l0_summaries = [
            cluster["summary"] for cluster in clusters if cluster["summary"] is not None
        ]
        company_hash = _content_hash(conn, entity_ids)
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
            company = _ask_with_retry(
                frontier,
                SCOPE_L2,
                COMPANY_EXTRA,
                _context_reports(l0_summaries, frontier),
            )
            if company is None:
                raise RuntimeError("company community report failed after retries")
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
                incomplete=any_failed,
            )
            stats["findings_dropped"] += dropped
            stats["open_questions"] += _store_open_questions(
                conn, company, entity_ids, frontier, cfg, seen_questions
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
            conn, run_started, kept_sets, frontier, cfg
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
