"""Admin review flags for the Map review gate (issue #255) and their G1
resolution into corrections.

An admin marks an entity, a projected relation edge or a community as wrong
with an optional note; the flags are listed and resolved on the review page.
Resolving (G1) REQUIRES choosing an action — reject, edit, confirm, merge,
split, rename or reassign — and each write creates a ``cmap.correction`` row
keyed by content (brain/corrections.py), so the verdict survives rebuilds.
Community flags have no correction target kind and resolve without one.
Behind the plan §8 admin flag, like upload, delete and run.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from brain.api.deps import User, require_admin
from brain.corrections import CORRECTION_ACTIONS, flag_target, record_correction
from brain.db import get_pool

router = APIRouter()

ITEM_TYPES = frozenset({"entity", "relation", "community"})

_FLAG_COLUMNS = (
    "id, item_type, item_id, note, created_by, created_at, resolved_at, resolved_by, action"
)


class FlagBody(BaseModel):
    """One mark-as-wrong on a map surface."""

    item_type: str
    item_id: str
    note: str | None = None


class ResolveBody(BaseModel):
    """The verdict chosen when resolving a flag (G1: an action is required)."""

    action: str
    reason: str | None = None
    payload: dict[str, Any] | None = None


def _norm_uuid(value: str, label: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=400, detail=f"{label} must be a uuid") from exc


def _norm_item(item_type: str, item_id: str) -> str:
    """Validate and normalise the flag target; raise 400 on anything else."""
    if item_type not in ITEM_TYPES:
        raise HTTPException(
            status_code=400,
            detail="item_type must be entity, relation or community",
        )
    if item_type == "relation":
        parts = item_id.split(":")
        if len(parts) != 3 or not parts[2].strip():
            raise HTTPException(
                status_code=400,
                detail="relation item_id must be 'from_uuid:to_uuid:rel_type'",
            )
        return (
            f"{_norm_uuid(parts[0], 'relation from')}:"
            f"{_norm_uuid(parts[1], 'relation to')}:{parts[2].strip()}"
        )
    return _norm_uuid(item_id, item_type)


def _row_to_dict(row: tuple) -> dict[str, Any]:
    (
        flag_id,
        item_type,
        item_id,
        note,
        created_by,
        created_at,
        resolved_at,
        resolved_by,
        action,
    ) = row
    return {
        "id": str(flag_id),
        "item_type": str(item_type),
        "item_id": str(item_id),
        "note": str(note) if note is not None else None,
        "created_by": str(created_by) if created_by else None,
        "created_at": created_at.isoformat() if created_at else None,
        "resolved_at": resolved_at.isoformat() if resolved_at else None,
        "resolved_by": str(resolved_by) if resolved_by else None,
        "action": str(action) if action is not None else None,
    }


def _labels(conn: Any, rows: list[dict[str, Any]]) -> None:
    """Attach a readable ``label`` to every flag row (names when they survive)."""
    entity_ids: set[str] = set()
    community_ids: set[str] = set()
    for row in rows:
        if row["item_type"] == "entity":
            entity_ids.add(row["item_id"])
        elif row["item_type"] == "community":
            community_ids.add(row["item_id"])
        else:
            from_id, to_id, _rel_type = row["item_id"].split(":", 2)
            entity_ids.add(from_id)
            entity_ids.add(to_id)
    names: dict[str, str] = {}
    if entity_ids:
        for item in conn.execute(
            "SELECT id::text, canonical_name FROM cmap.entity WHERE id = ANY(%s::uuid[])",
            (sorted(entity_ids),),
        ).fetchall():
            names[str(item[0])] = str(item[1])
    if community_ids:
        for item in conn.execute(
            "SELECT id::text, title FROM cmap.community WHERE id = ANY(%s::uuid[])",
            (sorted(community_ids),),
        ).fetchall():
            names[str(item[0])] = str(item[1] or "")
    for row in rows:
        if row["item_type"] == "entity":
            row["label"] = names.get(row["item_id"], row["item_id"])
        elif row["item_type"] == "community":
            row["label"] = names.get(row["item_id"]) or row["item_id"]
        else:
            from_id, to_id, rel_type = row["item_id"].split(":", 2)
            row["label"] = (
                f"{names.get(from_id, from_id)} —{rel_type}→ {names.get(to_id, to_id)}"
            )


@router.post("/flags")
def create_flag(
    body: FlagBody,
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Flag one entity, relation or community as wrong.

    A second open flag on the same item just refreshes the note.
    """
    item_id = _norm_item(body.item_type, body.item_id)
    note = (body.note or "").strip() or None
    with get_pool().connection() as conn:
        row = conn.execute(
            "INSERT INTO cmap.review_flag (item_type, item_id, note, created_by) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (item_type, item_id) WHERE resolved_at IS NULL "
            "DO UPDATE SET note = COALESCE(EXCLUDED.note, cmap.review_flag.note) "
            f"RETURNING {_FLAG_COLUMNS}",
            (body.item_type, item_id, note, user.auth_user_id),
        ).fetchone()
        flag = _row_to_dict(row)
        _labels(conn, [flag])
        conn.commit()
    return {"flag": flag}


@router.get("/flags")
def list_flags(
    user: Annotated[User, Depends(require_admin)],
    item_type: str | None = Query(default=None),
    item_id: str | None = Query(default=None),
    include_resolved: bool = Query(default=False),
) -> dict[str, Any]:
    """Open flags by default (newest first); ``include_resolved`` adds the rest.

    ``item_type``/``item_id`` narrow the list to one flagged map item.
    """
    del user
    where = "TRUE"
    params: list[Any] = []
    if item_type is not None:
        if item_type not in ITEM_TYPES:
            raise HTTPException(
                status_code=400,
                detail="item_type must be entity, relation or community",
            )
        where += " AND item_type = %s"
        params.append(item_type)
    if item_id is not None:
        where += " AND item_id = %s"
        params.append(item_id)
    if not include_resolved:
        where += " AND resolved_at IS NULL"
    with get_pool().connection() as conn:
        rows = conn.execute(
            f"SELECT {_FLAG_COLUMNS} FROM cmap.review_flag WHERE {where} "
            "ORDER BY created_at DESC LIMIT 500",
            params,
        ).fetchall()
        flags = [_row_to_dict(row) for row in rows]
        _labels(conn, flags)
    return {"flags": flags}


@router.post("/flags/{flag_id}/resolve")
def resolve_flag(
    flag_id: UUID,
    body: ResolveBody,
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Resolve one flag with the chosen action; the write creates a correction.

    An action is required (G1). The correction's target is the flag's content
    key, so the verdict survives rebuilds. A community flag (no correction
    target kind) or a flag whose entity rows are gone resolves without one.
    Resolving twice keeps the first resolution and writes nothing new.
    """
    if body.action not in CORRECTION_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail="action must be reject, edit, confirm, merge, split, rename or reassign",
        )
    key = str(flag_id)
    with get_pool().connection() as conn:
        row = conn.execute(
            f"SELECT {_FLAG_COLUMNS} FROM cmap.review_flag WHERE id = %s",
            (key,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="flag not found")
        flag = _row_to_dict(row)
        correction = None
        if flag["resolved_at"] is None:
            target = flag_target(conn, flag["item_type"], flag["item_id"])
            if target is not None:
                try:
                    correction = record_correction(
                        conn,
                        target_kind=target[0],
                        target_key=target[1],
                        action=body.action,
                        payload=body.payload,
                        reason=(body.reason or "").strip() or flag["note"],
                        by=str(user.auth_user_id),
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
            row = conn.execute(
                "UPDATE cmap.review_flag SET resolved_at = now(), resolved_by = %s, "
                f"action = %s WHERE id = %s AND resolved_at IS NULL "
                f"RETURNING {_FLAG_COLUMNS}",
                (user.auth_user_id, body.action, key),
            ).fetchone()
            if row is not None:
                flag = _row_to_dict(row)
        _labels(conn, [flag])
        conn.commit()
    return {"flag": flag, "correction": correction}
