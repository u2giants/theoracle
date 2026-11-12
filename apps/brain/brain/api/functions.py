"""Curated business functions (repair plan C1).

The vocabulary the owner curates on ``/map/functions``: any logged-in
employee may read it; admins add, rename, merge and retire. Merging moves
children and aliases onto the target, points the merged row's ``parent_id``
at the target and deactivates it — the row stays as the record C2's
assignment tables re-point through later. No approval queues; login + admin
is the only permission model (locked owner rules).
"""

from __future__ import annotations

import re
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from brain.api.deps import User, current_user, require_admin
from brain.db import get_pool

router = APIRouter()

_FUNCTION_COLUMNS = (
    "id::text, key, name, description, aliases, parent_id::text, sort, active"
)

_KEY_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class FunctionBody(BaseModel):
    """One function as typed on the functions page (add)."""

    key: str
    name: str
    description: str = ""
    aliases: list[str] = []
    parent_id: str | None = None
    sort: int | None = None


class EditBody(BaseModel):
    """Rename/edit one function (plan C1: rename is the core action)."""

    name: str
    description: str | None = None
    aliases: list[str] | None = None
    sort: int | None = None


class MergeBody(BaseModel):
    """Merge one function into another (by id or key)."""

    into: str


def _clean(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in items if item and item.strip()))


def _function_dict(row: tuple) -> dict[str, Any]:
    return {
        "id": row[0],
        "key": row[1],
        "name": row[2],
        "description": row[3],
        "aliases": list(row[4]),
        "parent_id": row[5],
        "sort": row[6],
        "active": bool(row[7]),
    }


def _function_key(function_id: str) -> str:
    try:
        return str(UUID(function_id))
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=404, detail="no such function") from exc


def _fetch(conn: Any, key: str) -> dict[str, Any] | None:
    row = conn.execute(
        f"SELECT {_FUNCTION_COLUMNS} FROM cmap.function WHERE id = %s", (key,)
    ).fetchone()
    return _function_dict(row) if row else None


def _resolve(conn: Any, ref: str) -> dict[str, Any]:
    """One function by id or by key."""
    ref = ref.strip()
    try:
        row = conn.execute(
            f"SELECT {_FUNCTION_COLUMNS} FROM cmap.function WHERE id = %s OR key = %s",
            (str(UUID(ref)), ref),
        ).fetchone()
    except ValueError:
        row = conn.execute(
            f"SELECT {_FUNCTION_COLUMNS} FROM cmap.function WHERE key = %s", (ref,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no such function")
    return _function_dict(row)


@router.get("/functions")
def list_functions(user: Annotated[User, Depends(current_user)]) -> dict[str, Any]:
    """Every function, curated rows first, then retired ones."""
    del user
    with get_pool().connection() as conn:
        rows = conn.execute(
            f"SELECT {_FUNCTION_COLUMNS} FROM cmap.function "
            "ORDER BY active DESC, sort, name"
        ).fetchall()
    return {"functions": [_function_dict(row) for row in rows]}


@router.post("/functions")
def add_function(
    body: FunctionBody, user: Annotated[User, Depends(require_admin)]
) -> dict[str, Any]:
    """Add one function with a stable slug key."""
    del user
    key = body.key.strip().lower()
    name = body.name.strip()
    if not _KEY_RE.match(key):
        raise HTTPException(
            status_code=400, detail="key must be a lowercase slug like 'sampling'"
        )
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    aliases = _clean(body.aliases)
    with get_pool().connection() as conn:
        if conn.execute(
            "SELECT 1 FROM cmap.function WHERE key = %s", (key,)
        ).fetchone():
            raise HTTPException(status_code=409, detail="key already exists")
        if body.parent_id is not None:
            _resolve(conn, body.parent_id)
        sort = body.sort
        if sort is None:
            row = conn.execute(
                "SELECT COALESCE(MAX(sort), 0) + 10 FROM cmap.function"
            ).fetchone()
            sort = int(row[0])
        row = conn.execute(
            "INSERT INTO cmap.function (key, name, description, aliases, "
            "parent_id, sort) VALUES (%s, %s, %s, %s, %s, %s) "
            f"RETURNING {_FUNCTION_COLUMNS}",
            (key, name, body.description.strip(), aliases, body.parent_id, sort),
        ).fetchone()
        conn.commit()
    return _function_dict(row)


@router.put("/functions/{function_id}")
def edit_function(
    function_id: str,
    body: EditBody,
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Rename one function and edit its description, aliases and sort."""
    del user
    key = _function_key(function_id)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    with get_pool().connection() as conn:
        current = _fetch(conn, key)
        if current is None:
            raise HTTPException(status_code=404, detail="no such function")
        description = (
            current["description"]
            if body.description is None
            else body.description.strip()
        )
        aliases = current["aliases"] if body.aliases is None else _clean(body.aliases)
        sort = current["sort"] if body.sort is None else body.sort
        row = conn.execute(
            "UPDATE cmap.function SET name = %s, description = %s, aliases = %s, "
            f"sort = %s WHERE id = %s RETURNING {_FUNCTION_COLUMNS}",
            (name, description, aliases, sort, key),
        ).fetchone()
        conn.commit()
    return _function_dict(row)


@router.post("/functions/{function_id}/merge")
def merge_function(
    function_id: str,
    body: MergeBody,
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Merge one function into another.

    Moves children and aliases onto the target (the merged name is kept as an
    alias), points the merged row's ``parent_id`` at the target and deactivates
    it. The row stays so C2's assignment tables can re-point through it later.
    """
    del user
    key = _function_key(function_id)
    with get_pool().connection() as conn:
        source = _fetch(conn, key)
        if source is None:
            raise HTTPException(status_code=404, detail="no such function")
        target = _resolve(conn, body.into.strip())
        if target["id"] == source["id"]:
            raise HTTPException(status_code=400, detail="cannot merge a function into itself")
        if not target["active"]:
            raise HTTPException(status_code=400, detail="target function is retired")
        conn.execute(
            "UPDATE cmap.function SET parent_id = %s WHERE parent_id = %s",
            (target["id"], source["id"]),
        )
        aliases = _clean([*target["aliases"], *source["aliases"], source["name"]])
        row = conn.execute(
            "UPDATE cmap.function SET aliases = %s WHERE id = %s "
            f"RETURNING {_FUNCTION_COLUMNS}",
            (aliases, target["id"]),
        ).fetchone()
        merged = conn.execute(
            "UPDATE cmap.function SET active = false, parent_id = %s WHERE id = %s "
            f"RETURNING {_FUNCTION_COLUMNS}",
            (target["id"], source["id"]),
        ).fetchone()
        conn.commit()
    return {
        "merged": _function_dict(merged),
        "into": _function_dict(row),
        "detail": (
            "children and aliases moved onto the target; the merged row is kept "
            "inactive with parent_id pointing at the target for C2 re-pointing"
        ),
    }


@router.post("/functions/{function_id}/retire")
def retire_function(
    function_id: str, user: Annotated[User, Depends(require_admin)]
) -> dict[str, Any]:
    """Retire one function (``active = false``); the row stays."""
    del user
    key = _function_key(function_id)
    with get_pool().connection() as conn:
        row = conn.execute(
            "UPDATE cmap.function SET active = false WHERE id = %s "
            f"RETURNING {_FUNCTION_COLUMNS}",
            (key,),
        ).fetchone()
        conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="no such function")
    return _function_dict(row)
