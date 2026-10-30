"""Community detection and hierarchical reports (plan step 8).

Level 0: Leiden over the projected edge weights (weight = distinct sources).
Level 1: Leiden over the level-0 communities. Level 2: one company report.
Each community gets one frontier-written report (``prompts/community_report.md``)
built from its own data only, stored in ``cmap.community``; the report's open
questions become ``cmap.open_question`` rows.
"""

from __future__ import annotations

import json
import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import igraph as ig
import leidenalg
import psycopg
import tiktoken

from brain.config import Settings, get_settings
from brain.db import get_pool
from brain.embed import embed_texts
from brain.graph.project import _load_edges, _load_entities
from brain.resolve.resolve import FrontierCapReached, _Frontier

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
REPORT_PROMPT_PATH = PROMPTS_DIR / "community_report.md"

RESOLUTION_L0 = 1.0
RESOLUTION_L1 = 0.5
MIN_COMMUNITY = 3
MAX_CONTEXT_TOKENS = 12000
MAX_EDGES_IN_CONTEXT = 40
MAX_QUOTES_IN_CONTEXT = 25
DEDUPE_COSINE = 0.9
REPORT_WORKERS = 6

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


def _fit(lines: list[str]) -> str:
    """Join context lines under the token budget, dropping from the end."""
    kept = list(lines)
    text = "\n".join(kept)
    while _tokens(text) > MAX_CONTEXT_TOKENS and len(kept) > 3:
        kept.pop()
        text = "\n".join(kept) + "\ncontext truncated"
    return text


def _level0_membership(
    edges: list[dict[str, Any]], entity_ids: list[str]
) -> dict[str, int]:
    """Leiden level 0, then fold communities smaller than MIN_COMMUNITY."""
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
            if not neighbour_weights:
                # No edge to any other community; the plan only defines the
                # merge into the highest-weight neighbour, so it stays.
                continue
            target = max(neighbour_weights, key=lambda key: neighbour_weights[key])
            for vertex in members:
                membership[vertex] = target
            changed = True
            break
    return {
        entity_id: membership[position] for position, entity_id in enumerate(entity_ids)
    }


def _level1_membership(
    edges: list[dict[str, Any]], level0: dict[str, int]
) -> dict[int, int]:
    """Leiden over the level-0 communities (resolution 0.5)."""
    communities = sorted(set(level0.values()))
    index_of = {community: position for position, community in enumerate(communities)}
    cross: dict[tuple[int, int], float] = {}
    for edge in edges:
        first = level0.get(edge["from"])
        second = level0.get(edge["to"])
        if first is None or second is None or first == second:
            continue
        key = (
            min(index_of[first], index_of[second]),
            max(index_of[first], index_of[second]),
        )
        cross[key] = cross.get(key, 0.0) + float(edge["weight"])
    pairs = list(cross.keys())
    graph = ig.Graph(n=len(communities), edges=pairs, directed=False)
    if pairs:
        graph.es["weight"] = [cross[key] for key in pairs]
    partition = leidenalg.find_partition(
        graph,
        leidenalg.RBConfigurationVertexPartition,
        weights="weight" if pairs else None,
        resolution_parameter=RESOLUTION_L1,
        seed=0,
    )
    membership = list(partition.membership)
    return {community: membership[index_of[community]] for community in communities}


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
) -> str:
    """Entity list, top edges and quotes for one level-0 community."""
    member_ids = {member["id"] for member in members}
    names = {member["id"]: member["name"] for member in members}
    lines = ["ENTITIES:"]
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
    return _fit(lines)


def _context_reports(rows: list[dict[str, Any]]) -> str:
    """Level-1/2 context: the reports beneath, with findings."""
    lines = ["REPORTS:"]
    for row in rows:
        lines.append(f"## {row['title']}")
        lines.append(str(row["summary"]))
        for finding in row["findings"]:
            lines.append(f"- [{finding.get('kind')}] {finding.get('text')}")
        source_ids = row.get("source_ids") or sorted({
            source_id
            for finding in row["findings"]
            for source_id in finding.get("source_ids", [])
        })
        lines.append(f"sources: {', '.join(source_ids)}")
    return _fit(lines)


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
        "summary": str(result.get("summary") or "").strip(),
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
) -> tuple[str, int]:
    findings, dropped = _filter_findings(report, valid_sources)
    report["findings"] = findings
    row = conn.execute(
        "INSERT INTO cmap.community (level, parent_id, title, report_md, "
        "findings, entity_ids, graph_version) VALUES (%s, %s, %s, %s, %s, %s, %s) "
        "RETURNING id",
        (
            level,
            parent_id,
            report["title"],
            _report_md(report),
            json.dumps(findings, ensure_ascii=False),
            entity_ids,
            graph_version,
        ),
    ).fetchone()
    return str(row[0]), dropped


def _store_open_questions(
    conn: psycopg.Connection,
    report: dict[str, Any],
    entity_ids: list[str],
    settings: Settings,
) -> int:
    """Insert deduped open questions (cosine >= 0.9 counts as the same)."""
    written = 0
    for question in report["open_questions"]:
        existing = [
            str(row[0])
            for row in conn.execute(
                "SELECT question FROM cmap.open_question WHERE state = 'open'"
            ).fetchall()
        ]
        vectors = embed_texts(existing + [question], settings)
        new_vector = vectors[-1]
        duplicate = any(
            _cosine(new_vector, other) >= DEDUPE_COSINE for other in vectors[:-1]
        )
        if duplicate:
            continue
        conn.execute(
            "INSERT INTO cmap.open_question (question, why, entity_ids, state) "
            "VALUES (%s, %s, %s, 'open')",
            (question, report["title"], entity_ids),
        )
        written += 1
    return written


def _split_report_md(report_md: str) -> tuple[str, str]:
    """Recover ``(title, summary)`` from the Markdown ``_report_md`` renders."""
    head = str(report_md).split("\n## Findings", 1)[0]
    title, _, summary = head.partition("\n\n")
    if title.startswith("# "):
        title = title[2:]
    return title.strip(), summary.strip()


def _existing_reports(
    conn: psycopg.Connection,
    graph_version: int,
) -> dict[tuple[int, frozenset[str]], dict[str, Any]]:
    """Community rows already stored, keyed by (level, entity set).

    A rerun over the same graph reuses them instead of asking the frontier
    again (per-report upsert semantics), so a pass stopped partway continues
    where it died.
    """
    rows = conn.execute(
        "SELECT id, level, title, report_md, findings, entity_ids FROM cmap.community "
        "WHERE graph_version = %s",
        (graph_version,),
    ).fetchall()
    out: dict[tuple[int, frozenset[str]], dict[str, Any]] = {}
    for row in rows:
        title, summary = _split_report_md(row[3])
        findings = row[4] if isinstance(row[4], list) else json.loads(row[4] or "[]")
        key = (int(row[1]), frozenset(str(item) for item in (row[5] or [])))
        out[key] = {
            "row_id": str(row[0]),
            "title": title or str(row[2]),
            "summary": summary,
            "findings": findings,
        }
    return out


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
    """Detect communities and write their reports at levels 0, 1 and 2."""
    cfg = settings if settings is not None else get_settings()
    frontier = _Frontier(cfg)
    stats: dict[str, Any] = {
        "communities_l0": 0,
        "communities_l1": 0,
        "reports": 0,
        "reports_reused": 0,
        "reports_failed": 0,
        "findings_dropped": 0,
        "open_questions": 0,
    }
    with get_pool().connection() as conn:
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
        level0 = _level0_membership(edges, entity_ids)
        level1 = _level1_membership(edges, level0)
        by_community: dict[int, list[dict[str, Any]]] = {}
        for node in nodes:
            by_community.setdefault(level0[node["id"]], []).append(node)
        stats["communities_l0"] = len(by_community)
        stats["communities_l1"] = len(set(level1.values()))
        existing = _existing_reports(conn, graph_version)

        # Contexts first, serially: identical input order to a serial pass.
        l0_items: list[tuple[int, list[str], tuple[int, frozenset[str]], str]] = []
        for community, members in sorted(by_community.items()):
            member_ids = [member["id"] for member in members]
            key = (0, frozenset(str(item) for item in member_ids))
            l0_items.append((community, member_ids, key, _context_l0(conn, members, edges)))

        def _finish_l0(
            community: int,
            member_ids: list[str],
            key: tuple[int, frozenset[str]],
            report: dict[str, Any] | None,
        ) -> tuple[dict[str, Any], str]:
            if key in existing:
                stored = existing[key]
                row_id = stored["row_id"]
                conn.execute(
                    "UPDATE cmap.community SET graph_version = %s WHERE id = %s",
                    (graph_version, row_id),
                )
                conn.commit()
                stats["reports_reused"] += 1
            elif report is not None:
                stored = report
                row_id, dropped = _store(
                    conn, 0, None, stored, member_ids, graph_version, valid_sources
                )
                stats["findings_dropped"] += dropped
                stats["open_questions"] += _store_open_questions(
                    conn, stored, member_ids, cfg
                )
                conn.commit()
            else:
                stats["reports_failed"] += 1
                raise KeyError(community)
            stats["reports"] += 1
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
            }, row_id

        asked = _ask_many(
            frontier,
            [
                (SCOPE_L0, "", context)
                for community, member_ids, key, context in l0_items
                if key not in existing
            ],
        )
        summaries: dict[int, dict[str, Any]] = {}
        row_ids: dict[int, str] = {}
        ask_index = 0
        for community, member_ids, key, _context in l0_items:
            report = None
            if key not in existing:
                report = asked[ask_index]
                ask_index += 1
                if report is None:
                    stats["reports_failed"] += 1
                    continue
            summary, row_id = _finish_l0(community, member_ids, key, report)
            summaries[community] = summary
            row_ids[community] = row_id

        level1_groups = _group_summaries(level1, summaries)
        level1_rows: dict[int, str] = {}
        level1_reports: list[dict[str, Any]] = []
        level1_items: list[tuple[int, list[dict[str, Any]], list[str], tuple[int, frozenset[str]], str]] = []
        for level1_id, report_rows in level1_groups.items():
            member_ids = _member_ids(level1, level0, level1_id)
            key = (1, frozenset(str(item) for item in member_ids))
            level1_items.append(
                (level1_id, report_rows, member_ids, key, _context_reports(report_rows))
            )
        asked_l1 = _ask_many(
            frontier,
            [
                (SCOPE_L1, "", context)
                for level1_id, report_rows, member_ids, key, context in level1_items
                if key not in existing
            ],
        )
        ask_index = 0
        for level1_id, _report_rows, member_ids, key, _context in level1_items:
            if key in existing:
                row_id = existing[key]["row_id"]
                conn.execute(
                    "UPDATE cmap.community SET graph_version = %s WHERE id = %s",
                    (graph_version, row_id),
                )
                conn.commit()
                stats["reports_reused"] += 1
                stats["reports"] += 1
                level1_rows[level1_id] = row_id
                level1_reports.append(existing[key])
                continue
            report = asked_l1[ask_index]
            ask_index += 1
            if report is None:
                stats["reports_failed"] += 1
                continue
            row_id, dropped = _store(
                conn, 1, None, report, member_ids, graph_version, valid_sources
            )
            level1_rows[level1_id] = row_id
            level1_reports.append(report)
            stats["findings_dropped"] += dropped
            stats["reports"] += 1
            stats["open_questions"] += _store_open_questions(
                conn, report, member_ids, cfg
            )
            conn.commit()

        for level1_id, parent_row in level1_rows.items():
            children = _child_rows(row_ids, level1, level1_id)
            if children:
                conn.execute(
                    "UPDATE cmap.community SET parent_id = %s WHERE id = ANY(%s::uuid[])",
                    (parent_row, children),
                )
                conn.commit()

        company_key = (2, frozenset(str(item) for item in entity_ids))
        if company_key in existing:
            company_row = existing[company_key]["row_id"]
            conn.execute(
                "UPDATE cmap.community SET graph_version = %s WHERE id = %s",
                (graph_version, company_row),
            )
            stats["reports_reused"] += 1
        else:
            company = _ask_with_retry(
                frontier,
                SCOPE_L2,
                COMPANY_EXTRA,
                _context_reports(level1_reports),
            )
            if company is None:
                raise RuntimeError("company community report failed after retries")
            company_row, dropped = _store(
                conn, 2, None, company, entity_ids, graph_version, valid_sources
            )
            stats["findings_dropped"] += dropped
            stats["open_questions"] += _store_open_questions(conn, company, entity_ids, cfg)
        stats["reports"] += 1
        conn.execute(
            "UPDATE cmap.community SET parent_id = %s WHERE level = 1",
            (company_row,),
        )
        conn.commit()
    stats.update(frontier.usage)
    return stats


def _group_summaries(
    level1: dict[int, int], summaries: dict[int, dict[str, Any]]
) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = {}
    for community, summary in summaries.items():
        out.setdefault(level1[community], []).append(summary)
    return out


def _member_ids(
    level1: dict[int, int], level0: dict[str, int], level1_id: int
) -> list[str]:
    return [
        entity_id
        for entity_id, community in level0.items()
        if level1[community] == level1_id
    ]


def _child_rows(
    row_ids: dict[int, str], level1: dict[int, int], level1_id: int
) -> list[str]:
    return [
        row_id
        for community, row_id in row_ids.items()
        if level1[community] == level1_id
    ]


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
