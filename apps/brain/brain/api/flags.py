"""Admin review flags for the Map review gate (issue #255).

An admin marks an entity, a projected relation edge or a community as wrong
with an optional note; the flags are listed and resolved on the review page.
Behind the plan §8 admin flag, like upload, delete and run.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from brain.api.deps import User, require_admin
from brain.db import get_pool

router = APIRouter()

ITEM_TYPES = frozenset({"entity", "relation", "community"})

_FLAG_COLUMNS = (
    "id, item_type, item_id, note, created_by, created_at, resolved_at, resolved_by"
)


class FlagBody(BaseModel):
    """One mark-as-wrong on a map surface."""

    item_type: str
    item_id: str
    note: str | None = None


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
    entity_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Open flags by default (newest first); ``include_resolved`` adds the rest.

    ``item_type``/``item_id`` narrow the list to one flagged map item.
    ``entity_id`` returns all relation flags touching that entity in one batch.
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
        if item_type is None:
            raise HTTPException(status_code=400, detail="item_type is required with item_id")
        params.append(_norm_item(item_type, item_id))
    if entity_id is not None:
        entity_id = _norm_uuid(entity_id, "entity_id")
        where += (
            " AND item_type = 'relation'"
            " AND (split_part(item_id, ':', 1) = %s"
            " OR split_part(item_id, ':', 2) = %s)"
        )
        params.extend([entity_id, entity_id])
    if not include_resolved:
        where += " AND resolved_at IS NULL"
    limit = "" if entity_id is not None else " LIMIT 500"
    with get_pool().connection() as conn:
        rows = conn.execute(
            f"SELECT {_FLAG_COLUMNS} FROM cmap.review_flag WHERE {where} "
            f"ORDER BY created_at DESC{limit}",
            params,
        ).fetchall()
        flags = [_row_to_dict(row) for row in rows]
        _labels(conn, flags)
    return {"flags": flags}


@router.post("/flags/{flag_id}/resolve")
def resolve_flag(
    flag_id: UUID,
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Resolve one flag; resolving twice keeps the first resolution."""
    key = str(flag_id)
    with get_pool().connection() as conn:
        row = conn.execute(
            "UPDATE cmap.review_flag SET resolved_at = now(), resolved_by = %s "
            f"WHERE id = %s AND resolved_at IS NULL RETURNING {_FLAG_COLUMNS}",
            (user.auth_user_id, key),
        ).fetchone()
        if row is None:
            row = conn.execute(
                f"SELECT {_FLAG_COLUMNS} FROM cmap.review_flag WHERE id = %s",
                (key,),
            ).fetchone()
        if row is not None:
            flag = _row_to_dict(row)
            _labels(conn, [flag])
        conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="flag not found")
    return {"flag": flag}
