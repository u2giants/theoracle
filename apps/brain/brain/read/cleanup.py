"""Remove knowledge left behind when a source's passages go away (repair A7).

Deleting or re-reading a source deletes its chunks, and with them its
mentions and relations. The things those mentions named would otherwise
linger: entities with no mention left, and aliases only that source ever
used. Both are removed here, scoped to the entities the source touched.
"""

from __future__ import annotations

from typing import Any

from brain.extract.normalize import normalize_name


def touched_entities(conn: Any, source_id: str) -> set[str]:
    """Entities named by this source's mentions (call before deleting chunks)."""
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT DISTINCT m.entity_id FROM cmap.mention m "
            "JOIN cmap.chunk ch ON ch.id = m.chunk_id "
            "WHERE ch.source_id = %s AND m.entity_id IS NOT NULL",
            (source_id,),
        ).fetchall()
    }


def drop_orphaned(conn: Any, touched: set[str]) -> dict[str, int]:
    """Delete touched entities with no mention left and aliases nothing supports.

    Only aliases the resolver recorded are considered (never a translated or
    imported one). An alias is kept when a remaining mention of the entity still uses that
    name, or when it is the entity's own canonical name. Counts on the
    surviving entities are refreshed. Call after the chunks are deleted, in
    the same transaction.
    """
    if not touched:
        return {"entities": 0, "aliases": 0}
    ids = sorted(touched)
    removed = conn.execute(
        "DELETE FROM cmap.entity e WHERE e.id = ANY(%s::uuid[]) "
        "AND NOT EXISTS (SELECT 1 FROM cmap.mention m WHERE m.entity_id = e.id)",
        (ids,),
    ).rowcount
    unsupported = conn.execute(
        "SELECT a.entity_id::text, a.entity_type, a.normalized_name, e.canonical_name "
        "FROM cmap.entity_alias a JOIN cmap.entity e ON e.id = a.entity_id "
        "WHERE a.entity_id = ANY(%s::uuid[]) AND a.source = 'resolve' AND NOT EXISTS ("
        "  SELECT 1 FROM cmap.mention m WHERE m.entity_id = a.entity_id "
        "  AND m.normalized_name = a.normalized_name)",
        (ids,),
    ).fetchall()
    aliases = 0
    for _entity_id, entity_type, name, canonical in unsupported:
        if normalize_name(str(canonical or ""), str(entity_type)) == name:
            continue
        aliases += conn.execute(
            "DELETE FROM cmap.entity_alias WHERE entity_type = %s AND normalized_name = %s",
            (entity_type, name),
        ).rowcount
    # Local import: resolve imports the extraction modules at load time.
    from brain.resolve.resolve import _refresh_counts

    _refresh_counts(conn, touched)
    return {"entities": int(removed), "aliases": aliases}
