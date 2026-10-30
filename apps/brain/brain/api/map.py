"""Company Map read endpoints (plan step 10).

The Next.js ``/map`` pages read everything through the proxy route; these
endpoints serve the company report, the communities, one entity, one source's
chunks and a name search. Every logged-in employee may read; only the
"Rebuild map" action needs the admin flag. Postgres is the source of truth,
so none of these reads depend on FalkorDB being up.
"""

from __future__ import annotations

import json
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from brain.api.deps import User, current_user, require_admin
from brain.db import get_pool
from brain.graph.communities import _split_report_md
from brain.graph.project import _load_edges

router = APIRouter()

MAX_GRAPH_NODES = 2000
MAX_GRAPH_EDGES = 5000
MAX_QUOTES_PER_NEIGHBOUR = 5
COMPANY_ISSUES = 10


def _uuid(value: str, label: str) -> str:
    """Reject anything that is not a UUID with a 404, never a 500."""
    try:
        return str(UUID(value))
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=404, detail=f"{label} not found") from exc


def _current_version(conn: Any) -> int | None:
    """The newest graph version that has communities, or None when empty."""
    row = conn.execute("SELECT MAX(graph_version) FROM cmap.community").fetchone()
    if row is None or row[0] is None:
        return None
    return int(row[0])


def _findings(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _source_titles(conn: Any, source_ids: set[str]) -> dict[str, str]:
    if not source_ids:
        return {}
    rows = conn.execute(
        "SELECT id, title FROM cmap.source WHERE id = ANY(%s::uuid[])",
        (sorted(source_ids),),
    ).fetchall()
    return {str(row[0]): str(row[1]) for row in rows}


def _with_sources(conn: Any, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach ``sources: [{id, title}]`` to every finding for the chips."""
    wanted: set[str] = set()
    for finding in findings:
        for source_id in finding.get("source_ids") or []:
            wanted.add(str(source_id))
    titles = _source_titles(conn, wanted)
    out: list[dict[str, Any]] = []
    for finding in findings:
        sources = [
            {"id": str(source_id), "title": titles[str(source_id)]}
            for source_id in finding.get("source_ids") or []
            if str(source_id) in titles
        ]
        out.append(
            {
                "text": str(finding.get("text") or ""),
                "kind": str(finding.get("kind") or ""),
                "stance": str(finding.get("stance") or "inference"),
                "source_ids": [item["id"] for item in sources],
                "sources": sources,
            }
        )
    return out


def graph_payload(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    max_nodes: int = MAX_GRAPH_NODES,
    max_edges: int = MAX_GRAPH_EDGES,
) -> dict[str, Any]:
    """Cap a community graph for the browser canvas.

    Keeps the ``max_nodes`` most-attested nodes (source count, then mention
    count) and the ``max_edges`` heaviest edges between kept nodes, and says
    so in ``notice`` when anything was cut.
    """
    ranked = sorted(
        nodes,
        key=lambda node: (node["source_count"], node["mention_count"], node["name"]),
        reverse=True,
    )
    kept_nodes = ranked[:max_nodes]
    kept_ids = {node["id"] for node in kept_nodes}
    inside = [
        edge for edge in edges if edge["source"] in kept_ids and edge["target"] in kept_ids
    ]
    inside.sort(key=lambda edge: edge["weight"], reverse=True)
    kept_edges = inside[:max_edges]
    truncated = len(kept_nodes) < len(nodes) or len(kept_edges) < len(edges)
    notice = None
    if truncated:
        notice = (
            f"showing top {len(kept_nodes)} of {len(nodes)} entities and "
            f"{len(kept_edges)} of {len(edges)} links"
        )
    return {
        "nodes": kept_nodes,
        "edges": kept_edges,
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "truncated": truncated,
        "notice": notice,
    }


def _community_graph(conn: Any, entity_ids: list[str]) -> dict[str, Any]:
    """Nodes and aggregated edges for one community's entities."""
    rows = conn.execute(
        "SELECT id, entity_type, canonical_name, mention_count, source_count "
        "FROM cmap.entity WHERE id = ANY(%s::uuid[])",
        (entity_ids,),
    ).fetchall()
    nodes = [
        {
            "id": str(row[0]),
            "type": str(row[1]),
            "name": str(row[2]),
            "mention_count": int(row[3]),
            "source_count": int(row[4]),
        }
        for row in rows
    ]
    edges = [
        {
            "source": edge["from"],
            "target": edge["to"],
            "rel_type": edge["rel_type"],
            "weight": edge["weight"],
        }
        for edge in _load_edges(conn, entity_ids)
    ]
    return graph_payload(nodes, edges)


@router.get("/map/company")
def get_company(user: Annotated[User, Depends(current_user)]) -> dict[str, Any]:
    """The level-2 company report with its top-10 issues list."""
    del user
    with get_pool().connection() as conn:
        version = _current_version(conn)
        if version is None:
            return {"company": None, "graph_version": None}
        row = conn.execute(
            "SELECT id, title, report_md, findings FROM cmap.community "
            "WHERE level = 2 AND graph_version = %s ORDER BY created_at DESC LIMIT 1",
            (version,),
        ).fetchone()
        if row is None:
            return {"company": None, "graph_version": version}
        title, summary = _split_report_md(str(row[2] or ""))
        issues = _with_sources(conn, _findings(row[3]))[:COMPANY_ISSUES]
    return {
        "company": {
            "id": str(row[0]),
            "title": str(row[1] or title),
            "summary": summary,
            "report_md": str(row[2] or ""),
            "issues": issues,
        },
        "graph_version": version,
    }


@router.get("/communities")
def list_communities(
    user: Annotated[User, Depends(current_user)],
    level: int = Query(default=1, ge=0, le=2),
) -> dict[str, Any]:
    """Cards for one level of the current map: title, summary, finding count."""
    del user
    with get_pool().connection() as conn:
        version = _current_version(conn)
        if version is None:
            return {"communities": [], "graph_version": None}
        rows = conn.execute(
            "SELECT id, level, parent_id, title, report_md, findings, "
            "cardinality(entity_ids) FROM cmap.community "
            "WHERE level = %s AND graph_version = %s",
            (level, version),
        ).fetchall()
    cards: list[dict[str, Any]] = []
    for row in rows:
        _, summary = _split_report_md(str(row[4] or ""))
        cards.append(
            {
                "id": str(row[0]),
                "level": int(row[1]),
                "parent_id": str(row[2]) if row[2] else None,
                "title": str(row[3] or "Untitled area"),
                "summary": summary,
                "finding_count": len(_findings(row[5])),
                "entity_count": int(row[6] or 0),
            }
        )
    cards.sort(key=lambda card: (-card["finding_count"], -card["entity_count"], card["title"]))
    return {"communities": cards, "graph_version": version}


@router.get("/communities/{community_id}")
def get_community(
    community_id: str,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, Any]:
    """One community: report, findings with source chips, and its graph."""
    del user
    key = _uuid(community_id, "community")
    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT id, level, parent_id, title, report_md, findings, entity_ids, "
            "graph_version FROM cmap.community WHERE id = %s",
            (key,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="community not found")
        _, summary = _split_report_md(str(row[4] or ""))
        findings = _with_sources(conn, _findings(row[5]))
        entity_ids = [str(item) for item in (row[6] or [])]
        graph = _community_graph(conn, entity_ids)
        children = conn.execute(
            "SELECT id, title FROM cmap.community WHERE parent_id = %s ORDER BY title",
            (key,),
        ).fetchall()
    return {
        "id": str(row[0]),
        "level": int(row[1]),
        "parent_id": str(row[2]) if row[2] else None,
        "title": str(row[3] or "Untitled area"),
        "summary": summary,
        "report_md": str(row[4] or ""),
        "findings": findings,
        "graph": graph,
        "graph_version": int(row[7]),
        "children": [{"id": str(item[0]), "title": str(item[1] or "")} for item in children],
    }


@router.get("/entities/{entity_id}")
def get_entity(
    entity_id: str,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, Any]:
    """One entity: name, type, aliases, sources and quoted neighbours."""
    del user
    key = _uuid(entity_id, "entity")
    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT id, entity_type, canonical_name, description, mention_count, "
            "source_count FROM cmap.entity WHERE id = %s",
            (key,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="entity not found")
        aliases = [
            str(item[0])
            for item in conn.execute(
                "SELECT DISTINCT normalized_name FROM cmap.entity_alias "
                "WHERE entity_id = %s ORDER BY normalized_name",
                (key,),
            ).fetchall()
        ]
        sources = conn.execute(
            "SELECT s.id, s.title, s.kind, count(*) FROM cmap.mention m "
            "JOIN cmap.chunk ch ON ch.id = m.chunk_id "
            "JOIN cmap.source s ON s.id = ch.source_id "
            "WHERE m.entity_id = %s GROUP BY s.id, s.title, s.kind "
            "ORDER BY count(*) DESC, s.title",
            (key,),
        ).fetchall()
        mentions = conn.execute(
            "SELECT m.quote, m.chunk_id, ch.source_id, s.title FROM cmap.mention m "
            "JOIN cmap.chunk ch ON ch.id = m.chunk_id "
            "JOIN cmap.source s ON s.id = ch.source_id "
            "WHERE m.entity_id = %s ORDER BY s.title, ch.ordinal LIMIT 20",
            (key,),
        ).fetchall()
        relations = conn.execute(
            "SELECT r.rel_type, fm.entity_id, tm.entity_id, r.quote, r.chunk_id, "
            "ch.source_id, s.title, r.stance, r.description "
            "FROM cmap.relation r "
            "JOIN cmap.mention fm ON fm.id = r.from_mention_id "
            "JOIN cmap.mention tm ON tm.id = r.to_mention_id "
            "JOIN cmap.chunk ch ON ch.id = r.chunk_id "
            "JOIN cmap.source s ON s.id = ch.source_id "
            "WHERE (fm.entity_id = %s OR tm.entity_id = %s) "
            "AND fm.entity_id IS NOT NULL AND tm.entity_id IS NOT NULL "
            "ORDER BY r.rel_type, s.title",
            (key, key),
        ).fetchall()
        other_ids = {
            str(rel[2]) if str(rel[1]) == key else str(rel[1]) for rel in relations
        }
        others = {
            str(item[0]): {"name": str(item[1]), "type": str(item[2])}
            for item in conn.execute(
                "SELECT id, canonical_name, entity_type FROM cmap.entity "
                "WHERE id = ANY(%s::uuid[])",
                (sorted(other_ids),),
            ).fetchall()
        }
    grouped: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    for rel_type, from_id, to_id, quote, chunk_id, source_id, title, stance, desc in relations:
        outgoing = str(from_id) == key
        other = str(to_id) if outgoing else str(from_id)
        info = others.get(other, {"name": other, "type": ""})
        direction = "out" if outgoing else "in"
        bucket = grouped.setdefault(str(rel_type), {})
        neighbour = bucket.setdefault(
            (other, direction),
            {
                "entity_id": other,
                "name": info["name"],
                "type": info["type"],
                "direction": direction,
                "quotes": [],
            },
        )
        if len(neighbour["quotes"]) < MAX_QUOTES_PER_NEIGHBOUR:
            neighbour["quotes"].append(
                {
                    "quote": str(quote),
                    "chunk_id": str(chunk_id),
                    "source_id": str(source_id),
                    "source_title": str(title),
                    "stance": str(stance),
                    "description": str(desc),
                }
            )
    neighbours = {
        rel_type: list(bucket.values()) for rel_type, bucket in sorted(grouped.items())
    }
    return {
        "id": str(row[0]),
        "type": str(row[1]),
        "canonical_name": str(row[2]),
        "description": str(row[3] or ""),
        "mention_count": int(row[4]),
        "source_count": int(row[5]),
        "aliases": aliases,
        "sources": [
            {
                "id": str(item[0]),
                "title": str(item[1]),
                "kind": str(item[2]),
                "mentions": int(item[3]),
            }
            for item in sources
        ],
        "mentions": [
            {
                "quote": str(item[0]),
                "chunk_id": str(item[1]),
                "source_id": str(item[2]),
                "source_title": str(item[3]),
            }
            for item in mentions
        ],
        "neighbours": neighbours,
    }


@router.get("/sources/{source_id}/chunks")
def get_source_chunks(
    source_id: str,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, Any]:
    """One source's metadata and its chunk text in reading order."""
    del user
    key = _uuid(source_id, "source")
    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT id, kind, title, original_filename, bytes, department_hint, "
            "effective_date, created_at, read_state FROM cmap.source WHERE id = %s",
            (key,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="source not found")
        chunks = conn.execute(
            "SELECT id, ordinal, locator, text, passage_kind FROM cmap.chunk "
            "WHERE source_id = %s ORDER BY ordinal",
            (key,),
        ).fetchall()
    return {
        "source": {
            "id": str(row[0]),
            "kind": str(row[1]),
            "title": str(row[2]),
            "original_filename": row[3],
            "bytes": int(row[4]),
            "department_hint": row[5],
            "effective_date": row[6].isoformat() if row[6] else None,
            "created_at": row[7].isoformat() if row[7] else None,
            "read_state": str(row[8]),
        },
        "chunks": [
            {
                "id": str(item[0]),
                "ordinal": int(item[1]),
                "locator": item[2],
                "text": str(item[3]),
                "passage_kind": item[4],
            }
            for item in chunks
        ],
    }


@router.get("/search")
def search(
    user: Annotated[User, Depends(current_user)],
    q: str = Query(default="", max_length=200),
) -> dict[str, Any]:
    """Entities (name or alias), sources (title) and communities (title)."""
    del user
    text = q.strip()
    if not text:
        return {"entities": [], "sources": [], "communities": []}
    contains = f"%{text}%"
    with get_pool().connection() as conn:
        entities = conn.execute(
            "SELECT e.id, e.entity_type, e.canonical_name, e.source_count "
            "FROM cmap.entity e WHERE e.canonical_name ILIKE %s OR EXISTS ("
            "SELECT 1 FROM cmap.entity_alias a WHERE a.entity_id = e.id "
            "AND a.normalized_name ILIKE %s) "
            "ORDER BY e.source_count DESC, e.canonical_name LIMIT 20",
            (contains, contains),
        ).fetchall()
        sources = conn.execute(
            "SELECT id, kind, title FROM cmap.source WHERE title ILIKE %s "
            "ORDER BY title LIMIT 20",
            (contains,),
        ).fetchall()
        version = _current_version(conn)
        communities = conn.execute(
            "SELECT id, level, title FROM cmap.community "
            "WHERE title ILIKE %s AND graph_version = %s ORDER BY level DESC, title LIMIT 20",
            (contains, version if version is not None else -1),
        ).fetchall()
    return {
        "entities": [
            {"id": str(r[0]), "type": str(r[1]), "name": str(r[2]), "source_count": int(r[3])}
            for r in entities
        ],
        "sources": [{"id": str(r[0]), "kind": str(r[1]), "title": str(r[2])} for r in sources],
        "communities": [
            {"id": str(r[0]), "level": int(r[1]), "title": str(r[2] or "")} for r in communities
        ],
    }


@router.post("/map/rebuild")
def rebuild_map(user: Annotated[User, Depends(require_admin)]) -> dict[str, Any]:
    """Queue ``resolve``; the worker chains ``project`` then ``communities``."""
    del user
    with get_pool().connection() as conn:
        row = conn.execute(
            "INSERT INTO cmap.job (kind, payload) SELECT 'resolve', '{}'::jsonb "
            "WHERE NOT EXISTS (SELECT 1 FROM cmap.job WHERE kind = 'resolve' "
            "AND state IN ('queued','running')) RETURNING id"
        ).fetchone()
        conn.commit()
    if row is None:
        return {"queued": False, "detail": "a rebuild is already queued or running"}
    return {"queued": True, "job_id": str(row[0])}
