"""#410/#437: isolated entities and disconnected pairs must still be merged.

Shape mirrors the real corpus (cmap_bake_5: 969 entities, 335 with no edge,
41 disconnected pairs): a few dense clusters, many orphans and stray pairs
whose only link to a cluster is a shared source. #437 added the entities with
no link at all (mentions deleted upstream leave no source and no edge): they
must still land in a real community, and every community must stay within
[MIN_COMMUNITY, MAX_COMMUNITY] entities.
"""

from __future__ import annotations

from collections import Counter

from brain.graph.communities import (
    MAX_COMMUNITY,
    MIN_COMMUNITY,
    _level0_membership,
    _level1_membership,
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


def test_level1_groups_stay_under_entity_cap() -> None:
    # 30 level-0 communities of 40 entities, chained densely: Leiden alone
    # would lump them into a few giant level-1 groups.
    level0 = {f"e{c}_{i}": c for c in range(30) for i in range(40)}
    edges = [
        {"from": f"e{c}_0", "to": f"e{d}_0", "weight": 5}
        for c in range(30)
        for d in range(c + 1, min(c + 6, 30))
    ]
    level1 = _level1_membership(edges, level0)
    totals = Counter(level1[community] for community in level0.values())
    assert max(totals.values()) <= MAX_COMMUNITY
    assert len(totals) < 30  # still a real middle level, not one per child
