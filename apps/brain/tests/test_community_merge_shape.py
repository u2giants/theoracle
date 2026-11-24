"""#410/#437: isolated entities and disconnected pairs must still be merged.

Shape mirrors the real corpus (cmap_bake_5: 969 entities, 335 with no edge,
41 disconnected pairs): a few dense clusters, many orphans and stray pairs
whose only link to a cluster is a shared source. #437 added the entities with
no link at all (mentions deleted upstream leave no source and no edge): they
must still land in a real community, and every community must stay within
[MIN_COMMUNITY, MAX_COMMUNITY] entities.
"""

from __future__ import annotations

import time
from collections import Counter

from brain.graph.communities import (
    MAX_COMMUNITY,
    MIN_COMMUNITY,
    _level0_membership,
)


def _shape() -> tuple[list[dict], list[str], dict[str, set[str]]]:
    edges: list[dict] = []
    ids: list[str] = []
    sources: dict[str, set[str]] = {}
    for cluster in range(4):
        members = [f"c{cluster}_{i}" for i in range(12)]
        ids += members
        for position, first in enumerate(members):
            sources[first] = {f"s{cluster}"}
            for second in members[position + 1 : position + 4]:
                edges.append({"from": first, "to": second, "weight": 1})
    for orphan in range(40):
        name = f"orphan{orphan}"
        ids.append(name)
        sources[name] = {f"s{orphan % 4}"}
    for pair in range(10):
        first, second = f"pa{pair}", f"pb{pair}"
        ids += [first, second]
        edges.append({"from": first, "to": second, "weight": 2})
        sources[first] = sources[second] = {f"s{pair % 4}"}
    ids.append("nosource")
    return edges, ids, sources


def test_orphans_and_pairs_merge_by_shared_source() -> None:
    edges, ids, sources = _shape()
    membership = _level0_membership(edges, ids, sources)
    sizes = Counter(membership.values())
    assert [size for size in sizes.values() if size < MIN_COMMUNITY] == []
    for orphan in range(40):
        assert membership[f"orphan{orphan}"] == membership[f"c{orphan % 4}_0"]
    for pair in range(10):
        assert membership[f"pa{pair}"] == membership[f"c{pair % 4}_0"]
    # The entity with no edge and no source still joins a real community.
    assert sizes[membership["nosource"]] >= MIN_COMMUNITY


def test_without_sources_leftovers_still_meet_the_bounds() -> None:
    """No sources and no vectors: the fold still packs everyone to >= 3."""
    edges, ids, _ = _shape()
    membership = _level0_membership(edges, ids)
    sizes = Counter(membership.values())
    assert [size for size in sizes.values() if size < MIN_COMMUNITY] == []
    assert max(sizes.values()) <= MAX_COMMUNITY
    assert len(sizes) == 4  # the four clusters absorb every orphan


def test_linkless_entity_folds_into_similar_community() -> None:
    """#437: an entity with no edge and no source merges by embedding."""
    edges = [
        {"from": "a0", "to": "a1", "weight": 1},
        {"from": "a1", "to": "a2", "weight": 1},
        {"from": "b0", "to": "b1", "weight": 1},
        {"from": "b1", "to": "b2", "weight": 1},
    ]
    ids = ["a0", "a1", "a2", "b0", "b1", "b2", "ghost"]
    sources = {
        "a0": {"sa"},
        "a1": {"sa"},
        "a2": {"sa"},
        "b0": {"sb"},
        "b1": {"sb"},
        "b2": {"sb"},
    }
    vectors = {
        "a0": [1.0, 0.0],
        "a1": [1.0, 0.0],
        "a2": [1.0, 0.0],
        "b0": [0.0, 1.0],
        "b1": [0.0, 1.0],
        "b2": [0.0, 1.0],
        "ghost": [0.0, 1.0],
    }
    membership = _level0_membership(edges, ids, sources, vectors)
    assert membership["ghost"] == membership["b0"]
    assert membership["ghost"] != membership["a0"]
    sizes = Counter(membership.values())
    assert [size for size in sizes.values() if size < MIN_COMMUNITY] == []


def test_disconnected_pile_meets_the_bounds() -> None:
    """N entities with no link at all: groups stay within [3, MAX_COMMUNITY]."""
    ids = [f"e{index}" for index in range(37)]
    membership = _level0_membership([], ids)
    sizes = Counter(membership.values())
    assert sum(sizes.values()) == 37
    assert [size for size in sizes.values() if size < MIN_COMMUNITY] == []
    assert max(sizes.values()) <= MAX_COMMUNITY


def test_oversized_community_is_split() -> None:
    from brain.graph.communities import _fold_leftovers

    membership = [0] * 200
    _fold_leftovers(membership, {}, [set()] * 200, [None] * 200)
    sizes = Counter(membership)
    assert sum(sizes.values()) == 200
    assert [size for size in sizes.values() if size < MIN_COMMUNITY] == []
    assert max(sizes.values()) <= MAX_COMMUNITY


def test_level0_membership_large_sparse_graph_is_fast() -> None:
    """2,500 sparse entities with 64-dim vectors fold well under 3s."""
    n = 2500
    ids = [f"e{i}" for i in range(n)]
    edges = [
        {"from": f"e{i}", "to": f"e{i + 1}", "weight": 1.0}
        for i in range(0, 1200, 3)
    ]
    sources = {f"e{i}": {f"src{i % 25}"} for i in range(0, n, 2)}
    vectors = {
        f"e{i}": [1.0 if j == (i % 64) else 0.0 for j in range(64)]
        for i in range(n)
    }
    started = time.perf_counter()
    membership = _level0_membership(edges, ids, sources, vectors)
    elapsed = time.perf_counter() - started
    sizes = Counter(membership.values())
    assert elapsed < 3.0, f"folding took too long: {elapsed:.2f}s"
    assert sum(sizes.values()) == n
    assert [size for size in sizes.values() if size < MIN_COMMUNITY] == []
    assert max(sizes.values()) <= MAX_COMMUNITY


def test_content_hash_index_matches_sql_parts() -> None:
    import hashlib

    from brain.graph.communities import _content_hash, _ContentHashIndex

    rel_internal = ("r1", "t1", "e1", "e2")
    rel_boundary = ("r2", "t2", "e2", "e3")
    index = _ContentHashIndex(
        entity_stamp={"e1": "ts1", "e2": "ts2", "e3": "ts3"},
        rels_by_entity={
            "e1": [rel_internal],
            "e2": [rel_internal, rel_boundary],
            "e3": [rel_boundary],
        },
        ef_by_entity={
            "e1": ["x:e1:f1:"],
            "e3": ["x:e3:f2:"],
        },
    )
    digest = _content_hash(None, ["e1", "e2", "e1"], index=index)  # type: ignore[arg-type]
    expected_parts = sorted(
        [
            "e:e1:ts1",
            "e:e2:ts2",
            "r:r1:t1",
            "r:r2:t2",
            "x:e1:f1:",
            "x:e3:f2:",
        ]
    )
    assert digest == hashlib.sha256("\n".join(expected_parts).encode("utf-8")).hexdigest()


def test_boundary_edges_indexed_matches_flat() -> None:
    from brain.graph.communities import _boundary_edges

    e1 = {"from": "a", "to": "b", "rel_type": "USES", "weight": 1}
    e2 = {"from": "b", "to": "c", "rel_type": "OWNS", "weight": 2}
    e3 = {"from": "d", "to": "a", "rel_type": "PRECEDES", "weight": 3}
    e4 = {"from": "c", "to": "d", "rel_type": "USES", "weight": 4}
    edges = [e1, e2, e3, e4]
    by_ent: dict[str, list[dict]] = {}
    for edge in edges:
        by_ent.setdefault(edge["from"], []).append(edge)
        if edge["to"] != edge["from"]:
            by_ent.setdefault(edge["to"], []).append(edge)
    members = {"a", "b"}
    flat_res = _boundary_edges(edges, members)
    idx_res = _boundary_edges(edges, members, edges_by_entity=by_ent)
    assert sorted(repr(x) for x in idx_res) == sorted(repr(x) for x in flat_res)
    assert len(idx_res) == 2


def test_context_l0_uses_preloaded_disagreements_with_dedup_and_cap(
    monkeypatch,
) -> None:
    from unittest.mock import MagicMock

    from brain.config import Settings
    from brain.contradictions import MAX_DISAGREEMENTS
    from brain.graph import communities as comm

    monkeypatch.setattr(comm, "_quote_rows", lambda conn, entity_ids: [])
    monkeypatch.setattr(
        comm,
        "disagreement_lines",
        lambda conn, entity_ids: (_ for _ in ()).throw(
            AssertionError("should not query disagreement_lines when preloaded")
        ),
    )

    extra = [f"sources disagree: item {i} (A vs B)" for i in range(MAX_DISAGREEMENTS + 4)]
    disagreements_by_entity = {
        "m1": ["sources disagree: shared (A vs B)", extra[0], extra[1]],
        "m2": ["sources disagree: shared (A vs B)", *extra],
    }
    members = [
        {"id": "m1", "type": "Process", "name": "P1", "description": "d1"},
        {"id": "m2", "type": "Process", "name": "P2", "description": "d2"},
    ]
    ctx, incomplete = comm._context_l0(
        MagicMock(),
        members,
        [],
        comm._Frontier(Settings(database_url="postgresql://u:p@localhost/db"), stage="reports"),
        disagreements_by_entity=disagreements_by_entity,
    )
    assert incomplete is False
    lines = [ln for ln in ctx.splitlines() if ln.startswith("- sources disagree:")]
    assert len(lines) == MAX_DISAGREEMENTS
    assert len(set(lines)) == MAX_DISAGREEMENTS
