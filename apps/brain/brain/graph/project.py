"""Project the Postgres map into FalkorDB (plan step 7).

Full rebuild of the single graph named ``company`` on every run: Postgres is
the durable store and the graph is rebuildable from it at any time (plan §8).
Edge labels are relation types and node secondary labels are entity types;
both come from the locked ontologies and are validated before they are
interpolated into Cypher.
"""

from __future__ import annotations

import functools
import json
import logging
from typing import Any

import psycopg
from falkordb import FalkorDB
from falkordb.graph import Graph

from brain.config import Settings, get_settings
from brain.db import get_pool

logger = logging.getLogger(__name__)

GRAPH_NAME = "company"
BATCH = 500
MAX_DESCRIPTIONS = 5
MAX_SOURCE_REFS = 20

ENTITY_TYPES = frozenset(
    {
        "Person",
        "Role",
        "Department",
        "Process",
        "Step",
        "System",
        "Artifact",
        "Rule",
        "Exception",
        "Issue",
        "Decision",
        "Metric",
        "Customer",
        "Vendor",
        "Licensor",
        "Product",
    }
)

EDGE_TYPES = frozenset(
    {
        "PERFORMS",
        "OWNS",
        "PART_OF",
        "PRECEDES",
        "HANDS_OFF_TO",
        "DEPENDS_ON",
        "USES",
        "PRODUCES",
        "APPLIES_TO",
        "EXCEPT_WHEN",
        "CAUSES",
        "BLOCKED_BY",
        "CONTRADICTS",
        "MENTIONS",
    }
)


class ProjectionError(RuntimeError):
    """Raised when the projection cannot complete."""


def connect(settings: Settings | None = None) -> Graph:
    """Return the ``company`` graph handle from ``FALKORDB_URL``."""
    return _client(settings).select_graph(GRAPH_NAME)


def _client(settings: Settings | None = None) -> FalkorDB:
    """Return the shared FalkorDB client for ``FALKORDB_URL``.

    One client per URL for the process: a client built per call can be
    garbage-collected while its graph handle still needs the connection
    (the label/property-key refresh during result parsing), which closes the
    connection mid-query.
    """
    cfg = settings if settings is not None else get_settings()
    return _client_for(cfg.falkordb_url)


@functools.lru_cache(maxsize=4)
def _client_for(url: str) -> FalkorDB:
    return FalkorDB.from_url(url)


def _drop(graph_client: FalkorDB) -> Graph:
    """Delete the ``company`` graph if it exists and return its handle."""
    if GRAPH_NAME in graph_client.list_graphs():
        graph_client.select_graph(GRAPH_NAME).delete()
    return graph_client.select_graph(GRAPH_NAME)


def _load_entities(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Every entity as one node row."""
    rows = conn.execute(
        "SELECT id, entity_type, canonical_name, description, "
        "mention_count, source_count FROM cmap.entity"
    ).fetchall()
    nodes: list[dict[str, Any]] = []
    for entity_id, entity_type, name, description, mentions, sources in rows:
        if entity_type not in ENTITY_TYPES:
            raise ProjectionError(f"unknown entity type {entity_type!r}")
        nodes.append(
            {
                "id": str(entity_id),
                "type": entity_type,
                "name": str(name),
                "description": str(description) if description is not None else "",
                "mention_count": int(mentions),
                "source_count": int(sources),
            }
        )
    return nodes


def _load_edges(
    conn: psycopg.Connection, entity_ids: list[str] | None = None
) -> list[dict[str, Any]]:
    """Group source-level relations into one projected edge per triple.

    With ``entity_ids`` only edges whose both ends are in that set are read
    (the step-10 community graph); without it the whole corpus is read.
    """
    scope = ""
    params: tuple[Any, ...] = ()
    if entity_ids is not None:
        scope = (
            " AND fm.entity_id = ANY(%s::uuid[]) AND tm.entity_id = ANY(%s::uuid[])"
        )
        params = (entity_ids, entity_ids)
    rows = conn.execute(
        "SELECT fm.entity_id AS from_id, tm.entity_id AS to_id, r.rel_type, "
        "ch.source_id, r.description, r.stance, r.confidence, r.quote, r.chunk_id "
        "FROM cmap.relation r "
        "JOIN cmap.mention fm ON fm.id = r.from_mention_id "
        "JOIN cmap.mention tm ON tm.id = r.to_mention_id "
        "JOIN cmap.chunk ch ON ch.id = r.chunk_id "
        "WHERE fm.entity_id IS NOT NULL AND tm.entity_id IS NOT NULL" + scope,
        params,
    ).fetchall()
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for from_id, to_id, rel_type, source_id, description, stance, confidence, quote, chunk_id in rows:
        if rel_type not in EDGE_TYPES:
            raise ProjectionError(f"unknown relation type {rel_type!r}")
        key = (str(from_id), str(to_id), str(rel_type))
        group = groups.setdefault(
            key,
            {
                "sources": set(),
                "descriptions": [],
                "seen_descriptions": set(),
                "stances": {},
                "confidence_max": 0.0,
                "source_refs": [],
                "seen_refs": set(),
            },
        )
        group["sources"].add(str(source_id))
        text = str(description) if description is not None else ""
        if text and text not in group["seen_descriptions"]:
            group["seen_descriptions"].add(text)
            if len(group["descriptions"]) < MAX_DESCRIPTIONS:
                group["descriptions"].append(text)
        group["stances"][str(stance)] = group["stances"].get(str(stance), 0) + 1
        group["confidence_max"] = max(group["confidence_max"], float(confidence))
        ref = (str(source_id), str(chunk_id), str(quote))
        if ref not in group["seen_refs"] and len(group["source_refs"]) < MAX_SOURCE_REFS:
            group["seen_refs"].add(ref)
            group["source_refs"].append(
                {"source_id": ref[0], "chunk_id": ref[1], "quote": ref[2]}
            )
    edges: list[dict[str, Any]] = []
    for (from_id, to_id, rel_type), group in groups.items():
        edges.append(
            {
                "from": from_id,
                "to": to_id,
                "rel_type": rel_type,
                "weight": len(group["sources"]),
                "descriptions": group["descriptions"],
                "stances": json.dumps(group["stances"], sort_keys=True),
                "confidence_max": group["confidence_max"],
                "source_refs": json.dumps(group["source_refs"], ensure_ascii=False),
            }
        )
    return edges


def _create_nodes(graph: Graph, nodes: list[dict[str, Any]]) -> None:
    """MERGE every node on ``id``, then add the per-type secondary label."""
    query = (
        "UNWIND $rows AS row "
        "MERGE (n:Entity {id: row.id}) "
        "SET n.type = row.type, n.name = row.name, "
        "n.description = row.description, "
        "n.mention_count = row.mention_count, n.source_count = row.source_count"
    )
    for start in range(0, len(nodes), BATCH):
        graph.query(query, {"rows": nodes[start : start + BATCH]})
    by_type: dict[str, list[str]] = {}
    for node in nodes:
        by_type.setdefault(node["type"], []).append(node["id"])
    for entity_type, ids in by_type.items():
        label = entity_type
        if label not in ENTITY_TYPES:
            raise ProjectionError(f"unknown entity type {label!r}")
        for start in range(0, len(ids), BATCH):
            graph.query(
                f"UNWIND $ids AS id MATCH (n:Entity {{id: id}}) SET n:{label}",
                {"ids": ids[start : start + BATCH]},
            )


def _create_edges(graph: Graph, edges: list[dict[str, Any]]) -> None:
    """CREATE one edge per projected triple; the rel_type is the edge label."""
    by_type: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        rows = by_type.setdefault(edge["rel_type"], [])
        rows.append(edge)
    for rel_type, rows in by_type.items():
        if rel_type not in EDGE_TYPES:
            raise ProjectionError(f"unknown relation type {rel_type!r}")
        query = (
            "UNWIND $rows AS row "
            "MATCH (a:Entity {id: row.from}), (b:Entity {id: row.to}) "
            f"CREATE (a)-[r:{rel_type}]->(b) "
            "SET r.weight = row.weight, r.descriptions = row.descriptions, "
            "r.stances = row.stances, r.confidence_max = row.confidence_max, "
            "r.source_refs = row.source_refs"
        )
        for start in range(0, len(rows), BATCH):
            graph.query(query, {"rows": rows[start : start + BATCH]})


def _create_indexes(graph: Graph) -> None:
    """Range indexes on the ``Entity`` label (plan step 7)."""
    for prop in ("id", "name", "type"):
        graph.query(f"CREATE INDEX FOR (n:Entity) ON (n.{prop})")


def _record_version(conn: psycopg.Connection, nodes: int, edges: int) -> int:
    """Insert the next ``cmap.graph_version`` row and return its version."""
    row = conn.execute(
        "INSERT INTO cmap.graph_version (version, node_count, edge_count, note) "
        "VALUES ((SELECT COALESCE(MAX(version), 0) + 1 FROM cmap.graph_version), "
        "%s, %s, %s) RETURNING version",
        (nodes, edges, "full rebuild"),
    ).fetchone()
    conn.commit()
    return int(row[0])


def run_project(settings: Settings | None = None) -> dict[str, int]:
    """Rebuild the ``company`` graph from Postgres; return node/edge counts."""
    cfg = settings if settings is not None else get_settings()
    with get_pool().connection() as conn:
        nodes = _load_entities(conn)
        edges = _load_edges(conn)
    graph = _drop(_client(cfg))
    _create_nodes(graph, nodes)
    _create_edges(graph, edges)
    _create_indexes(graph)
    with get_pool().connection() as conn:
        version = _record_version(conn, len(nodes), len(edges))
    return {"nodes": len(nodes), "edges": len(edges), "version": version}


def handle_project(job: dict[str, Any]) -> None:
    """Job ``project``: full graph rebuild, then queue ``communities``."""
    stats = run_project()
    job_id = job.get("id")
    if job_id is not None:
        with get_pool().connection() as conn:
            conn.execute(
                "UPDATE cmap.job SET payload = jsonb_set(payload, '{usage}', %s::jsonb) WHERE id = %s",
                (json.dumps(stats), job_id),
            )
            conn.commit()
    logger.info("project stats=%s", stats)
    _enqueue_communities()


def _enqueue_communities() -> None:
    """Queue one ``communities`` job (step 8) unless one is waiting."""
    with get_pool().connection() as conn:
        conn.execute(
            "INSERT INTO cmap.job (kind, payload) SELECT 'communities', '{}'::jsonb "
            "WHERE NOT EXISTS (SELECT 1 FROM cmap.job WHERE kind = 'communities' AND state = 'queued')"
        )
        conn.commit()
