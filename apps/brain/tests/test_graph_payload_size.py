"""Community graph payload cap (plan step 10 visual check).

A 2,000-node community must render without freezing the browser, so the
payload the community page receives is capped at 2,000 nodes / 5,000 edges
with a "showing top N" notice when anything was cut.
"""

from __future__ import annotations

from typing import Any

from brain.api.map import MAX_GRAPH_EDGES, MAX_GRAPH_NODES, graph_payload


def _nodes(count: int) -> list[dict[str, Any]]:
    return [
        {
            "id": f"n{index}",
            "type": "Person",
            "name": f"Node {index}",
            "mention_count": index % 7,
            "source_count": index % 5,
        }
        for index in range(count)
    ]


def _edges(count: int, node_count: int) -> list[dict[str, Any]]:
    return [
        {
            "source": f"n{index % node_count}",
            "target": f"n{(index * 7 + 1) % node_count}",
            "rel_type": "HANDS_OFF_TO",
            "weight": 1 + index % 4,
        }
        for index in range(count)
    ]


def test_payload_capped_to_2000_nodes_and_5000_edges() -> None:
    """A synthetic 3,000-node / 9,000-edge community is cut with a notice."""
    payload = graph_payload(_nodes(3000), _edges(9000, 3000))
    assert MAX_GRAPH_NODES == 2000
    assert MAX_GRAPH_EDGES == 5000
    assert len(payload["nodes"]) == 2000
    assert len(payload["edges"]) <= 5000
    assert payload["truncated"] is True
    assert payload["notice"].startswith("showing top 2000 of 3000")
    kept = {node["id"] for node in payload["nodes"]}
    assert all(edge["source"] in kept and edge["target"] in kept for edge in payload["edges"])
    kept_min = min(node["source_count"] for node in payload["nodes"])
    dropped = [node for node in _nodes(3000) if node["id"] not in kept]
    assert all(node["source_count"] <= kept_min for node in dropped)


def test_2000_node_community_renders_whole() -> None:
    """Exactly 2,000 nodes and 5,000 edges pass through untouched."""
    payload = graph_payload(_nodes(2000), _edges(5000, 2000))
    assert len(payload["nodes"]) == 2000
    assert len(payload["edges"]) == 5000
    assert payload["truncated"] is False
    assert payload["notice"] is None


def test_heaviest_edges_kept_when_edges_cut() -> None:
    """When only edges overflow, the heaviest 5,000 survive."""
    payload = graph_payload(_nodes(100), _edges(6000, 100))
    assert len(payload["edges"]) == 5000
    assert payload["truncated"] is True
    weights = [edge["weight"] for edge in payload["edges"]]
    assert sum(1 for weight in weights if weight >= 2) == 4500
    assert sum(1 for weight in weights if weight == 1) == 500
