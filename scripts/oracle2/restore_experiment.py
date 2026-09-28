#!/usr/bin/env python3
"""Compare exact graph counts after loading a snapshot in a new instance."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "oracle-brain"))
from falkordb import FalkorDB  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--stress", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--kind", choices=["restart", "new-instance"], required=True)
    parser.add_argument("--started-epoch", type=float, required=True)
    args = parser.parse_args()
    url = os.environ.get("ORACLE2_TEST_RESTORED_URL", "")
    parsed = urlparse(url)
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        parser.error("restore check requires a new loopback instance")
    client = FalkorDB(host=parsed.hostname, port=parsed.port or 6379,
                      password=parsed.password)
    results = []
    for report_path in (args.pilot, args.stress):
        expected = json.loads(report_path.read_text())
        actual_nodes, actual_relations = [], []
        for name in expected["graph_names"]:
            graph = client.select_graph(name)
            actual_nodes.append(int(graph.query("MATCH (n:BenchNode) RETURN count(n)").result_set[0][0]))
            actual_relations.append(int(graph.query("MATCH ()-[r:BenchLink]->() RETURN count(r)").result_set[0][0]))
        results.append({"scale": expected["nodes_requested"],
                        "node_counts_match": actual_nodes == expected["node_counts"],
                        "relation_counts_match": actual_relations == expected["relation_counts"],
                        "node_counts": actual_nodes,
                        "relation_counts": actual_relations})
    result = {"kind": args.kind, "restore_seconds": round(time.time() - args.started_epoch, 3),
              "scales": results, "passed": all(r["node_counts_match"] and r["relation_counts_match"]
                                              for r in results)}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": result["passed"], "restore_seconds": result["restore_seconds"]}))
    return 0 if result["passed"] and result["restore_seconds"] < 3600 else 1


if __name__ == "__main__":
    raise SystemExit(main())
