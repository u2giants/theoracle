#!/usr/bin/env python3
"""Synthetic FalkorDB workload from the S02 research gate.

Run against the isolated CI store only. Never accepts a non-loopback URL.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time
import psutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "oracle-brain"))
from falkordb import FalkorDB  # noqa: E402


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nodes", type=int, required=True)
    parser.add_argument("--relations", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (args.nodes, args.relations) not in {(10_000, 100_000), (100_000, 1_000_000)}:
        parser.error("only the planned pilot and 10x stress sizes are allowed")
    url = os.environ.get("ORACLE2_TEST_CONFIRMED_URL", "")
    parsed = urlparse(url)
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        parser.error("resource experiment requires loopback FalkorDB")
    client = FalkorDB(host=parsed.hostname, port=parsed.port or 6379,
                      password=parsed.password)
    run_id = uuid4().hex[:12]
    graphs = [client.select_graph(f"oracle2_bench_{run_id}_{index}") for index in range(3)]
    start = time.monotonic()
    errors = []
    # Three isolated access partitions and a deliberately high-degree target.
    for partition, graph in enumerate(graphs):
        graph.query("CREATE INDEX FOR (n:BenchNode) ON (n.id)")
        partition_nodes = [str(i) for i in range(partition, args.nodes, 3)]
        for offset in range(0, len(partition_nodes), 500):
            ids = partition_nodes[offset:offset + 500]
            graph.query("UNWIND $ids AS id MERGE (:BenchNode {id:id})",
                        params={"ids": ids})
    node_seconds = time.monotonic() - start
    edge_start = time.monotonic()
    for partition, graph in enumerate(graphs):
        local_count = (args.nodes + 2 - partition) // 3
        partition_relations = range(partition, args.relations, 3)
        batch = []
        for relation in partition_relations:
            local = relation // 3
            source = str(partition + 3 * (local % local_count))
            target = str(partition + 3 * ((local * 13 + 1) % local_count))
            if relation % 97 == 0:
                source = str(partition)  # high-degree node
            batch.append({"id": str(relation), "source": source, "target": target})
            if len(batch) == 500:
                graph.query(
                    """UNWIND $rows AS row
                       MATCH (a:BenchNode {id:row.source}),(b:BenchNode {id:row.target})
                       MERGE (a)-[:BenchLink {id:row.id}]->(b)""",
                    params={"rows": batch},
                )
                batch = []
        if batch:
            graph.query(
                """UNWIND $rows AS row
                   MATCH (a:BenchNode {id:row.source}),(b:BenchNode {id:row.target})
                   MERGE (a)-[:BenchLink {id:row.id}]->(b)""",
                params={"rows": batch},
            )
    edge_seconds = time.monotonic() - edge_start
    # Count records in each graph and probe bounded traversal with 20 readers.
    counts = [int(graph.query("MATCH (n:BenchNode) RETURN count(n)").result_set[0][0])
              for graph in graphs]
    relation_counts = [int(graph.query("MATCH ()-[r:BenchLink]->() RETURN count(r)").result_set[0][0])
                       for graph in graphs]

    def read(index: int) -> float:
        graph = graphs[index % 3]
        began = time.monotonic()
        rows = graph.query(
            "MATCH (a:BenchNode {id:$id})-[:BenchLink]->(b) RETURN b.id LIMIT 20",
            params={"id": str(index % 3)},
        ).result_set
        if any(str(row[0]) not in {str(n) for n in range(index % 3, args.nodes, 3)} for row in rows):
            errors.append("forbidden partition result")
        return time.monotonic() - began

    with ThreadPoolExecutor(max_workers=20) as pool:
        latencies = list(pool.map(read, range(200)))
    # Duplicate relation insert and historical correction do not increase
    # record count; source withdrawal removes only its own synthetic node.
    graph = graphs[0]
    graph.query("MERGE (a:BenchNode {id:'0'})-[r:BenchLink {id:'0'}]->(b:BenchNode {id:'3'})")
    graph.query("MATCH (n:BenchNode {id:'0'}) SET n.revision=2")
    graph.query("MATCH (n:BenchNode {id:'0'}) SET n.withdrawn=true")
    graph.query("MATCH (n:BenchNode {id:'0'}) RETURN n.revision,n.withdrawn")
    report = {
        "nodes_requested": args.nodes, "relations_requested": args.relations,
        "node_counts": counts, "relation_counts": relation_counts,
        "node_write_seconds": round(node_seconds, 3),
        "relation_write_seconds": round(edge_seconds, 3),
        "readers": 20, "reads": len(latencies),
        "read_p50_seconds": round(percentile(latencies, .5), 4),
        "read_p95_seconds": round(percentile(latencies, .95), 4),
        "errors": errors,
        "host": {"platform": platform.platform(), "cpu_count": os.cpu_count(),
                 "memory_bytes": psutil.virtual_memory().total},
        "graph_names": [graph.name for graph in graphs],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"nodes": sum(counts), "relations": sum(relation_counts),
                      "p95_seconds": report["read_p95_seconds"], "errors": errors}))
    return 0 if (sum(counts) == args.nodes and sum(relation_counts) == args.relations
                 and not errors and report["read_p95_seconds"] <= 2) else 1


if __name__ == "__main__":
    raise SystemExit(main())
