"""Typed read templates over the ``company`` graph (plan step 7).

Every function below is a fixed template; no caller can pass Cypher. Name
search starts in Postgres (canonical name prefix and alias prefix) and then
fetches the matched nodes from the graph.
"""

from __future__ import annotations

from typing import Any

from brain.config import Settings, get_settings
from brain.db import get_pool
from brain.graph.project import ENTITY_TYPES, connect


def _node_props(row: list[Any]) -> dict[str, Any]:
    """Turn one ``Node`` result cell into a plain dict."""
    node = row[0]
    return {
        "id": str(node.properties.get("id")),
        "type": str(node.properties.get("type")),
        "name": str(node.properties.get("name")),
        "description": str(node.properties.get("description") or ""),
        "mention_count": int(node.properties.get("mention_count") or 0),
        "source_count": int(node.properties.get("source_count") or 0),
    }


def neighbors(
    entity_id: str,
    depth: int = 2,
    limit: int = 50,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Nodes within ``depth`` hops of ``entity_id``, most-used sources first."""
    hops = max(1, min(depth, 2))
    graph = connect(settings)
    result = graph.query(
        f"MATCH (a:Entity {{id: $id}})-[*1..{hops}]-(x:Entity) "
        "RETURN DISTINCT x "
        "ORDER BY x.source_count DESC, x.mention_count DESC LIMIT $limit",
        {"id": entity_id, "limit": limit},
    )
    return [_node_props(row) for row in result.result_set]


def path(
    a_id: str,
    b_id: str,
    max_len: int = 4,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Shortest path (up to ``max_len`` edges) between two entities.

    FalkorDB only supports directed shortestPath, so both directions are
    asked and the shorter answer is returned first.
    """
    hops = max(1, min(max_len, 4))
    graph = connect(settings)
    query = (
        "MATCH (a:Entity {id: $a}), (b:Entity {id: $b}) "
        f"WITH a, b, shortestPath((a)-[*..{hops}]->(b)) AS p "
        "WHERE p IS NOT NULL "
        "RETURN [n IN nodes(p) | n.name] AS names, "
        "[e IN relationships(p) | type(e)] AS rels"
    )
    out: list[dict[str, Any]] = []
    for forward, first, second in ((True, a_id, b_id), (False, b_id, a_id)):
        result = graph.query(query, {"a": first, "b": second})
        for names, rels in result.result_set:
            names_list = [str(name) for name in names]
            rels_list = [str(rel) for rel in rels]
            if not forward:
                names_list.reverse()
                rels_list.reverse()
            out.append({"names": names_list, "rels": rels_list})
    out.sort(key=lambda item: len(item["rels"]))
    return out


def by_type(
    entity_type: str,
    limit: int = 50,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Nodes of one entity type, most-used sources first."""
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"unknown entity type {entity_type!r}")
    graph = connect(settings)
    result = graph.query(
        f"MATCH (n:{entity_type}) "
        "RETURN n ORDER BY n.source_count DESC, n.mention_count DESC LIMIT $limit",
        {"limit": limit},
    )
    return [_node_props(row) for row in result.result_set]


def search_name(
    text: str,
    limit: int = 20,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Prefix match on canonical names and aliases, then fetch graph nodes."""
    cfg = settings if settings is not None else get_settings()
    pattern = text.strip() + "%"
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT e.id FROM cmap.entity e "
            "LEFT JOIN cmap.entity_alias a ON a.entity_id = e.id "
            "WHERE e.canonical_name ILIKE %s OR a.normalized_name LIKE %s "
            "LIMIT %s",
            (pattern, pattern.lower(), limit),
        ).fetchall()
    ids = [str(row[0]) for row in rows]
    if not ids:
        return []
    graph = connect(cfg)
    result = graph.query(
        "MATCH (n:Entity) WHERE n.id IN $ids "
        "RETURN n ORDER BY n.source_count DESC LIMIT $limit",
        {"ids": ids, "limit": limit},
    )
    return [_node_props(row) for row in result.result_set]
