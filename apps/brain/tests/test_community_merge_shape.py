"""#410: isolated entities and disconnected pairs must still be merged.

Shape mirrors the real corpus (cmap_bake_5: 969 entities, 335 with no edge,
41 disconnected pairs): a few dense clusters, many orphans and stray pairs
whose only link to a cluster is a shared source.
"""

from __future__ import annotations

from collections import Counter

from brain.graph.communities import MIN_COMMUNITY, _level0_membership


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
    small = [size for size in sizes.values() if size < MIN_COMMUNITY]
    assert small == [1]  # only the entity with no edge and no source stays
    for orphan in range(40):
        assert membership[f"orphan{orphan}"] == membership[f"c{orphan % 4}_0"]
    for pair in range(10):
        assert membership[f"pa{pair}"] == membership[f"c{pair % 4}_0"]


def test_without_sources_old_behaviour_leaves_orphans() -> None:
    edges, ids, _ = _shape()
    sizes = Counter(_level0_membership(edges, ids).values())
    assert sum(1 for size in sizes.values() if size < MIN_COMMUNITY) == 51
