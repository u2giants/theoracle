"""Entity admin actions (repair plan G2, issue #520).

Merge, split, rename, change type, add/remove alias and "these two are never
the same", from the entity page (``W/map/entity/[id]``), behind the plan §8
admin flag like upload, delete and run. Every action writes its human verdict
through ``brain/corrections.py`` — never a side channel — so the verdict is
content-keyed and survives a full re-read (Phase A drift note), then applies
its immediate effect to the rows and triggers a targeted re-projection (the
``project`` job; projection consumes corrections, see ``brain/graph/project``).

Action contracts:

* merge — ``merge`` pair correction(s): the source entity's canonical key and
  each of its alias keys pair with the destination's key, so every name of the
  source steers to the destination on every resolution re-run. Immediately the
  mentions move to the destination, the alias rows follow and the source row
  goes away.
* split — chosen mentions move to the destination (existing entity or a new
  one), and a ``split`` pair correction separates the two sides' names so
  resolution never rejoins them. Names only the moved mentions used follow the
  moved side.
* rename — a ``rename`` correction (``payload["name"]`` wins) applied at once;
  the old key is kept as an alias.
* change type — an ``edit`` correction (``payload["entity_type"]``) applied at
  once; the pre-change key is kept as an alias so the correction keeps
  matching after extraction re-creates the entity under the old type.
* alias add/remove — an ``edit`` correction (``alias_add`` / ``alias_remove``,
  normalised names) applied at once; successive edits merge into one payload
  (newest edit wins at load).
* never-merge — a ``reject`` pair correction: resolution never joins the two
  entities' names again (``Corrections.blocks_join``).
"""

from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from brain.api.deps import User, require_admin
from brain.corrections import (
    apply_entity_edits,
    apply_renames,
    entity_key,
    entity_key_sets,
    load_corrections,
    mention_key,
    record_correction,
)
from brain.db import get_pool
from brain.extract.flat import ENTITY_TYPES
from brain.extract.normalize import normalize_name
from brain.resolve.resolve import _refresh_counts

logger = logging.getLogger(__name__)

router = APIRouter()

_RENAME_ALIAS_SOURCE = "correction"


class MergeBody(BaseModel):
    """Fold this entity into another one."""

    into: str
    reason: str | None = None


class SplitInto(BaseModel):
    """Where the chosen mentions go: an existing entity, or a new one."""

    entity_id: str | None = None
    new_name: str | None = None
    new_type: str | None = None


class SplitBody(BaseModel):
    """Move chosen mentions of this entity to one destination."""

    mention_ids: list[str]
    into: SplitInto
    reason: str | None = None


class RenameBody(BaseModel):
    """Give the entity a new canonical name."""

    name: str
    reason: str | None = None


class TypeBody(BaseModel):
    """Change the entity's type."""

    entity_type: str
    reason: str | None = None


class AliasBody(BaseModel):
    """Add or remove one alias name."""

    alias: str
    mode: str
    reason: str | None = None


class NeverMergeBody(BaseModel):
    """These two entities are never the same."""

    other: str
    reason: str | None = None


# ------------------------------------------------------------------ helpers


def _uuid(value: str, label: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=404, detail=f"{label} not found") from exc


def _entity_row(conn: Any, entity_id: str) -> tuple[str, str]:
    """``(canonical_name, entity_type)`` of one entity, or 404."""
    row = conn.execute(
        "SELECT canonical_name, entity_type FROM cmap.entity WHERE id = %s",
        (entity_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="entity not found")
    return str(row[0]), str(row[1])


def _entity_brief(conn: Any, entity_id: str) -> dict[str, str]:
    name, etype = _entity_row(conn, entity_id)
    return {"id": entity_id, "name": name, "type": etype}


def _enqueue_project() -> None:
    """Queue one ``project`` job unless one is already waiting.

    The targeted re-projection of an admin action: projection is a full
    rebuild from Postgres (the durable store) and consumes the corrections,
    so the queued rebuild is what refreshes the affected graph state.
    """
    with get_pool().connection() as conn:
        conn.execute(
            "INSERT INTO cmap.job (kind, payload) SELECT 'project', '{}'::jsonb "
            "WHERE NOT EXISTS (SELECT 1 FROM cmap.job WHERE kind = 'project' "
            "AND state IN ('queued', 'running'))"
        )
        conn.commit()


def _alias_keys(conn: Any, entity_id: str) -> set[str]:
    keys: set[str] = set()
    for norm, etype in conn.execute(
        "SELECT normalized_name, entity_type FROM cmap.entity_alias WHERE entity_id = %s",
        (entity_id,),
    ).fetchall():
        keys.add(mention_key(str(norm), str(etype)))
    return keys


def _write_pairs(
    conn: Any,
    *,
    action: str,
    keys_a: set[str],
    key_a: str,
    keys_b: set[str],
    key_b: str,
    reason: str | None,
    by: str,
) -> list[dict[str, Any]]:
    """Separation verdicts covering every name crossing between two sides.

    One pair correction per name of A against B's canonical key and per name
    of B against A's canonical key — the covering set ``blocks_join`` needs so
    no name of either side ever joins the other side again. Degenerate pairs
    (both keys equal, possible when two entities share a name) are skipped:
    the content-key scheme cannot tell same-named entities apart.
    """
    written: list[dict[str, Any]] = []
    for left, right in {(name, key_b) for name in keys_a} | {
        (key_a, name) for name in keys_b
    }:
        if left == right:
            continue
        written.append(
            record_correction(
                conn,
                target_kind="entity",
                target_key=left,
                action=action,
                payload={"pair": right},
                reason=reason,
                by=by,
            )
        )
    return written


def _merged_edit_payload(
    conn: Any, entity_id: str, target_key: str, updates: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Fold one entity edit into the in-force edit payload for this entity.

    Newest edit wins at load (``load_corrections``), so a type change must not
    drop an earlier alias instruction and vice versa: the fields are merged
    here and the alias lists stay disjoint (an add undoes a remove of the
    same name and the other way round). The correction keeps the in-force
    edit's target key, so every edit of one entity accumulates on the key
    that first carried one — the key a rebuild's re-created entity still
    matches.
    """
    keys = set(entity_key_sets(conn, [entity_id]).get(entity_id, set()))
    keys.add(target_key)
    current = load_corrections(conn).edit_for(keys)
    payload: dict[str, Any] = dict(current.payload) if current is not None else {}
    stable = current.target_key if current is not None else target_key
    if "entity_type" in updates:
        payload["entity_type"] = updates["entity_type"]
    for field, other in (("alias_add", "alias_remove"), ("alias_remove", "alias_add")):
        if field not in updates:
            continue
        name = str(updates[field])
        kept = [item for item in _str_list(payload.get(other)) if item != name]
        if kept:
            payload[other] = kept
        else:
            payload.pop(other, None)
        merged = _str_list(payload.get(field))
        if name not in merged:
            merged.append(name)
        payload[field] = sorted(merged)
    return stable, payload


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


# ------------------------------------------------------------------ actions


@router.post("/entities/{entity_id}/merge")
def merge_entity(
    entity_id: str,
    body: MergeBody,
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Merge this entity into another: one thing under the other's name.

    Writes a ``merge`` pair per name of this entity, moves its mentions and
    aliases to the destination, drops the empty row and re-projects. The
    merge survives a resolution re-run: a new mention of any merged name is
    forced onto the destination entity by the pair correction.
    """
    key = _uuid(entity_id, "entity")
    into = _uuid(body.into, "merge target")
    if key == into:
        raise HTTPException(status_code=400, detail="cannot merge an entity into itself")
    reason = (body.reason or "").strip() or None
    with get_pool().connection() as conn:
        src_name, src_type = _entity_row(conn, key)
        dest_name, dest_type = _entity_row(conn, into)
        src_key = entity_key(src_name, src_type)
        dest_key = entity_key(dest_name, dest_type)
        names = {src_key} | _alias_keys(conn, key)
        corrections = []
        for name_key in sorted(names):
            if name_key == dest_key:
                continue
            corrections.append(
                record_correction(
                    conn,
                    target_kind="entity",
                    target_key=name_key,
                    action="merge",
                    payload={"pair": dest_key},
                    reason=reason,
                    by=str(user.auth_user_id),
                )
            )
        conn.execute(
            "UPDATE cmap.mention SET entity_id = %s WHERE entity_id = %s", (into, key)
        )
        # Alias names are globally unique per type; keep the destination's own
        # row where both sides carried the same name.
        conn.execute(
            "DELETE FROM cmap.entity_alias a WHERE a.entity_id = %s AND EXISTS ("
            "  SELECT 1 FROM cmap.entity_alias b WHERE b.entity_type = a.entity_type "
            "  AND b.normalized_name = a.normalized_name AND b.entity_id <> a.entity_id)",
            (key,),
        )
        conn.execute(
            "UPDATE cmap.entity_alias SET entity_id = %s WHERE entity_id = %s",
            (into, key),
        )
        conn.execute(
            "DELETE FROM cmap.translation WHERE kind = 'entity' AND ref_id = %s", (key,)
        )
        conn.execute("DELETE FROM cmap.entity WHERE id = %s", (key,))
        _refresh_counts(conn, {into})
        conn.commit()
    _enqueue_project()
    return {
        "corrections": corrections,
        "merged_into": {"id": into, "name": dest_name, "type": dest_type},
    }


@router.post("/entities/{entity_id}/split")
def split_entity(
    entity_id: str,
    body: SplitBody,
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Move the chosen mentions of this entity to one destination.

    The destination is an existing entity or a new one (``new_name`` +
    ``new_type``). The chosen mentions are reassigned at once; a ``split``
    pair separates the two sides' names so resolution never rejoins them, and
    names only the moved mentions used follow the moved side.
    """
    key = _uuid(entity_id, "entity")
    if not body.mention_ids:
        raise HTTPException(status_code=400, detail="mention_ids must not be empty")
    existing_dest = (body.into.entity_id or "").strip()
    new_name = (body.into.new_name or "").strip()
    new_type = (body.into.new_type or "").strip()
    if bool(existing_dest) == bool(new_name or new_type):
        raise HTTPException(
            status_code=400,
            detail="into must name exactly one of entity_id or new_name+new_type",
        )
    reason = (body.reason or "").strip() or None
    wanted = [str(item) for item in body.mention_ids]
    if len(set(wanted)) != len(wanted):
        raise HTTPException(status_code=400, detail="mention_ids must be unique")
    with get_pool().connection() as conn:
        src_name, src_type = _entity_row(conn, key)
        src_key = entity_key(src_name, src_type)
        rows = conn.execute(
            "SELECT id::text, normalized_name, entity_type, embedding::text "
            "FROM cmap.mention WHERE id = ANY(%s::uuid[])",
            (wanted,),
        ).fetchall()
        found = {str(row[0]) for row in rows}
        owned = {
            str(row[0])
            for row in conn.execute(
                "SELECT id::text FROM cmap.mention WHERE id = ANY(%s::uuid[]) "
                "AND entity_id = %s",
                (wanted, key),
            ).fetchall()
        }
        missing = [item for item in wanted if item not in found]
        foreign = [item for item in wanted if item in found and item not in owned]
        if missing or foreign:
            raise HTTPException(
                status_code=400,
                detail="every mention must belong to this entity",
            )
        warning: str | None = None
        if existing_dest:
            dest = _uuid(existing_dest, "split target")
            if dest == key:
                raise HTTPException(
                    status_code=400, detail="cannot split an entity into itself"
                )
            dest_name, dest_type = _entity_row(conn, dest)
            created = False
        else:
            if not new_type:
                raise HTTPException(
                    status_code=400, detail="into.new_type is required with new_name"
                )
            if new_type not in ENTITY_TYPES:
                raise HTTPException(
                    status_code=400,
                    detail="into.new_type must be one of the entity types",
                )
            first_embedding = next(
                (str(row[3]) for row in rows if row[3] is not None), None
            )
            row = conn.execute(
                "INSERT INTO cmap.entity (entity_type, canonical_name, embedding) "
                "VALUES (%s, %s, %s::vector) RETURNING id, canonical_name, entity_type",
                (new_type, new_name, first_embedding),
            ).fetchone()
            dest, dest_name, dest_type = str(row[0]), str(row[1]), str(row[2])
            created = True
        dest_key = entity_key(dest_name, dest_type)
        if dest_key == src_key:
            warning = (
                "both sides share one content key: the reassignment stands, "
                "but a full rebuild cannot keep same-named entities apart"
            )
        conn.execute(
            "UPDATE cmap.mention SET entity_id = %s WHERE id = ANY(%s::uuid[])",
            (dest, wanted),
        )
        # A name only the moved mentions used belongs to the moved side now.
        for norm in {str(row[1]) for row in rows}:
            left = conn.execute(
                "SELECT 1 FROM cmap.mention WHERE entity_id = %s "
                "AND normalized_name = %s LIMIT 1",
                (key, norm),
            ).fetchone()
            if left is None:
                conn.execute(
                    "UPDATE cmap.entity_alias SET entity_id = %s "
                    "WHERE entity_id = %s AND normalized_name = %s",
                    (dest, key, norm),
                )
        keys_a = {src_key} | _alias_keys(conn, key)
        keys_b = {dest_key} | _alias_keys(conn, dest)
        corrections = _write_pairs(
            conn,
            action="split",
            keys_a=keys_a,
            key_a=src_key,
            keys_b=keys_b,
            key_b=dest_key,
            reason=reason,
            by=str(user.auth_user_id),
        )
        _refresh_counts(conn, {key, dest})
        conn.commit()
    _enqueue_project()
    return {
        "corrections": corrections,
        "destination": {"id": dest, "name": dest_name, "type": dest_type},
        "created": created,
        "moved": len(wanted),
        "warning": warning,
    }


@router.post("/entities/{entity_id}/rename")
def rename_entity(
    entity_id: str,
    body: RenameBody,
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Rename the entity; the old key stays as an alias so corrections match.

    The ``rename`` correction wins over the describer and over every
    re-extraction; it is applied to the rows at once.
    """
    key = _uuid(entity_id, "entity")
    reason = (body.reason or "").strip() or None
    new_name = (body.name or "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="name must not be empty")
    with get_pool().connection() as conn:
        old_name, etype = _entity_row(conn, key)
        correction = record_correction(
            conn,
            target_kind="entity",
            target_key=entity_key(old_name, etype),
            action="rename",
            payload={"name": new_name},
            reason=reason,
            by=str(user.auth_user_id),
        )
        apply_renames(conn, load_corrections(conn))
        conn.commit()
    _enqueue_project()
    return {"correction": correction, "entity": {"id": key, "name": new_name, "type": etype}}


@router.post("/entities/{entity_id}/type")
def change_entity_type(
    entity_id: str,
    body: TypeBody,
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Change the entity's type; the pre-change key stays as an alias.

    The ``edit`` correction keeps winning after a re-extraction re-creates the
    entity under the old type (the correction keys on that pre-change key).
    """
    key = _uuid(entity_id, "entity")
    reason = (body.reason or "").strip() or None
    new_type = (body.entity_type or "").strip()
    if new_type not in ENTITY_TYPES:
        raise HTTPException(
            status_code=400, detail="entity_type must be one of the entity types"
        )
    with get_pool().connection() as conn:
        name, etype = _entity_row(conn, key)
        edit_target, payload = _merged_edit_payload(
            conn, key, entity_key(name, etype), {"entity_type": new_type}
        )
        correction = record_correction(
            conn,
            target_kind="entity",
            target_key=edit_target,
            action="edit",
            payload=payload,
            reason=reason,
            by=str(user.auth_user_id),
        )
        apply_entity_edits(conn, load_corrections(conn))
        conn.commit()
    _enqueue_project()
    return {
        "correction": correction,
        "entity": {"id": key, "name": name, "type": new_type},
    }


@router.post("/entities/{entity_id}/alias")
def edit_entity_alias(
    entity_id: str,
    body: AliasBody,
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Add or remove one alias name (``mode`` is ``add`` or ``remove``).

    The ``edit`` correction re-applies the alias verdict after every rebuild;
    the alias row follows at once.
    """
    key = _uuid(entity_id, "entity")
    if body.mode not in {"add", "remove"}:
        raise HTTPException(status_code=400, detail="mode must be add or remove")
    raw = (body.alias or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="alias must not be empty")
    reason = (body.reason or "").strip() or None
    with get_pool().connection() as conn:
        name, etype = _entity_row(conn, key)
        norm = normalize_name(raw, etype)
        if not norm:
            raise HTTPException(status_code=400, detail="alias normalises to nothing")
        edit_target, payload = _merged_edit_payload(
            conn, key, entity_key(name, etype), {f"alias_{body.mode}": norm}
        )
        correction = record_correction(
            conn,
            target_kind="entity",
            target_key=edit_target,
            action="edit",
            payload=payload,
            reason=reason,
            by=str(user.auth_user_id),
        )
        apply_entity_edits(conn, load_corrections(conn))
        aliases = [
            str(item[0])
            for item in conn.execute(
                "SELECT DISTINCT normalized_name FROM cmap.entity_alias "
                "WHERE entity_id = %s ORDER BY normalized_name",
                (key,),
            ).fetchall()
        ]
        conn.commit()
    _enqueue_project()
    return {"correction": correction, "aliases": aliases}


@router.post("/entities/{entity_id}/never-merge")
def never_merge(
    entity_id: str,
    body: NeverMergeBody,
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """These two entities are never the same.

    A ``reject`` pair per name crossing: resolution keeps the two sides apart
    on every re-run (``Corrections.blocks_join``), even when the names look
    alike and the embeddings agree.
    """
    key = _uuid(entity_id, "entity")
    other = _uuid(body.other, "other entity")
    if key == other:
        raise HTTPException(status_code=400, detail="an entity is always itself")
    reason = (body.reason or "").strip() or None
    with get_pool().connection() as conn:
        name, etype = _entity_row(conn, key)
        other_name, other_type = _entity_row(conn, other)
        key_a = entity_key(name, etype)
        key_b = entity_key(other_name, other_type)
        corrections = _write_pairs(
            conn,
            action="reject",
            keys_a={key_a} | _alias_keys(conn, key),
            key_a=key_a,
            keys_b={key_b} | _alias_keys(conn, other),
            key_b=key_b,
            reason=reason,
            by=str(user.auth_user_id),
        )
        conn.commit()
    _enqueue_project()
    return {
        "corrections": corrections,
        "other": {"id": other, "name": other_name, "type": other_type},
    }
