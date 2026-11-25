"""Employee correction notes and reviewer access controls.

Designated reviewers (plus admins) submit free-text corrections describing what
is wrong on the map and what is actually true. Admins inspect submissions, apply
them as authoritative text sources ingested into the map, or dismiss them, and
toggle which employees hold submission permission.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from brain.api.deps import User, current_user, require_admin
from brain.api.sources import EASTERN, ingest_bytes
from brain.db import get_pool
from brain.read.dates import ORIGIN_ADMIN
from brain.read.detect import KIND_TEXT

router = APIRouter()

VALID_STATUSES = frozenset({"open", "applied", "dismissed"})
MAX_WHAT_WRONG_CHARS = 500
MAX_CORRECTION_CHARS = 10_000
MAX_PAGE_REF_CHARS = 300
MAX_REVIEW_NOTE_CHARS = 1_000

_NOTE_SELECT = (
    "SELECT cn.id, cn.employee_id, cn.employee_name, cn.function_id, "
    "f.name AS function_name, cn.page_ref, cn.what_is_wrong, "
    "cn.correction_text, cn.status, cn.source_id, cn.reviewed_by, "
    "cn.reviewed_at, cn.review_note, cn.created_at "
    "FROM cmap.correction_note cn "
    "LEFT JOIN cmap.function f ON f.id = cn.function_id"
)


class CreateCorrectionNoteBody(BaseModel):
    """One employee text correction submission."""

    what_is_wrong: str
    correction_text: str
    function_id: UUID | None = None
    page_ref: str | None = None


class ReviewCorrectionNoteBody(BaseModel):
    """Optional admin note when applying or dismissing a correction."""

    review_note: str | None = None


class PermissionBody(BaseModel):
    """Toggle correction-submission permission for one employee."""

    can_correct: bool


def _can_correct(conn: Any, user: User) -> bool:
    if user.is_admin:
        return True
    row = conn.execute(
        "SELECT can_correct FROM cmap.employee_flags WHERE employee_id = %s::uuid",
        (user.employee_id,),
    ).fetchone()
    return bool(row and row[0])


def _employee_display_name(conn: Any, employee_id: str) -> str:
    row = conn.execute(
        "SELECT COALESCE(NULLIF(trim(name), ''), email, '') "
        "FROM public.employees WHERE id = %s::uuid",
        (employee_id,),
    ).fetchone()
    return str(row[0]) if row and row[0] else ""


def _serialize_note(row: tuple) -> dict[str, Any]:
    (
        note_id,
        employee_id,
        employee_name,
        function_id,
        function_name,
        page_ref,
        what_is_wrong,
        correction_text,
        status,
        source_id,
        reviewed_by,
        reviewed_at,
        review_note,
        created_at,
    ) = row
    return {
        "id": str(note_id),
        "employee_id": str(employee_id),
        "employee_name": str(employee_name or ""),
        "function_id": str(function_id) if function_id else None,
        "function_name": str(function_name) if function_name else None,
        "page_ref": str(page_ref) if page_ref is not None else None,
        "what_is_wrong": str(what_is_wrong),
        "correction_text": str(correction_text),
        "status": str(status),
        "source_id": str(source_id) if source_id else None,
        "reviewed_by": str(reviewed_by) if reviewed_by else None,
        "reviewed_at": reviewed_at.isoformat() if reviewed_at else None,
        "review_note": str(review_note) if review_note is not None else None,
        "created_at": created_at.isoformat() if created_at else None,
    }


def _fetch_note(conn: Any, note_id: UUID) -> dict[str, Any]:
    row = conn.execute(
        f"{_NOTE_SELECT} WHERE cn.id = %s::uuid",
        (str(note_id),),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="correction note not found")
    return _serialize_note(row)


@router.get("/corrections/access")
def get_correction_access(
    user: Annotated[User, Depends(current_user)],
) -> dict[str, bool]:
    """Return whether the signed-in employee can submit text corrections."""
    with get_pool().connection() as conn:
        allowed = _can_correct(conn, user)
    return {"can_correct": allowed, "is_admin": user.is_admin}


@router.get("/corrections/notes")
def list_correction_notes(
    user: Annotated[User, Depends(current_user)],
    status: str | None = Query(default=None),
) -> dict[str, Any]:
    """List submitted correction notes (all for admins, own notes for reviewers)."""
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400, detail="status must be open, applied or dismissed"
        )
    with get_pool().connection() as conn:
        if not _can_correct(conn, user):
            raise HTTPException(
                status_code=403, detail="not authorized to submit corrections"
            )
        clauses: list[str] = []
        params: list[Any] = []
        if not user.is_admin:
            clauses.append("cn.employee_id = %s::uuid")
            params.append(user.employee_id)
        if status is not None:
            clauses.append("cn.status = %s")
            params.append(status)
        where = " AND ".join(clauses) if clauses else "TRUE"
        limit = 500 if user.is_admin else 200
        rows = conn.execute(
            f"{_NOTE_SELECT} WHERE {where} ORDER BY cn.created_at DESC LIMIT %s",
            (*params, limit),
        ).fetchall()
    return {
        "notes": [_serialize_note(row) for row in rows],
        "can_correct": True,
        "is_admin": user.is_admin,
    }


@router.post("/corrections/notes")
def create_correction_note(
    body: CreateCorrectionNoteBody,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, Any]:
    """Submit a free-text correction (open to admins and designated reviewers)."""
    what_is_wrong = body.what_is_wrong.strip()
    correction_text = body.correction_text.strip()
    if not what_is_wrong:
        raise HTTPException(status_code=400, detail="what_is_wrong is required")
    if len(what_is_wrong) > MAX_WHAT_WRONG_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"what_is_wrong must be at most {MAX_WHAT_WRONG_CHARS} characters",
        )
    if not correction_text:
        raise HTTPException(status_code=400, detail="correction_text is required")
    if len(correction_text) > MAX_CORRECTION_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"correction_text must be at most {MAX_CORRECTION_CHARS} characters",
        )
    page_ref = (body.page_ref or "").strip()[:MAX_PAGE_REF_CHARS] or None

    with get_pool().connection() as conn:
        if not _can_correct(conn, user):
            raise HTTPException(
                status_code=403, detail="not authorized to submit corrections"
            )
        if body.function_id is not None:
            fn_row = conn.execute(
                "SELECT id FROM cmap.function WHERE id = %s::uuid",
                (str(body.function_id),),
            ).fetchone()
            if fn_row is None:
                raise HTTPException(status_code=400, detail="unknown department/function")
        display_name = _employee_display_name(conn, user.employee_id)
        inserted = conn.execute(
            "INSERT INTO cmap.correction_note "
            "(employee_id, employee_name, function_id, page_ref, what_is_wrong, correction_text) "
            "VALUES (%s::uuid, %s, %s, %s, %s, %s) RETURNING id",
            (
                user.employee_id,
                display_name,
                str(body.function_id) if body.function_id else None,
                page_ref,
                what_is_wrong,
                correction_text,
            ),
        ).fetchone()
        note_id = UUID(str(inserted[0]))
        conn.commit()
        note = _fetch_note(conn, note_id)
    return {"note": note}


@router.post("/corrections/notes/{note_id}/apply")
def apply_correction_note(
    note_id: UUID,
    user: Annotated[User, Depends(require_admin)],
    body: Annotated[ReviewCorrectionNoteBody | None, Body()] = None,
) -> dict[str, Any]:
    """Convert one correction note into an authoritative full-map text source."""
    review_note = (
        ((body.review_note or "").strip()[:MAX_REVIEW_NOTE_CHARS] or None)
        if body is not None
        else None
    )
    with get_pool().connection() as conn:
        note = _fetch_note(conn, note_id)
    if note["status"] == "applied":
        return {"note": note, "source_id": note["source_id"]}

    dept_label = note["function_name"] or "Company-wide"
    created_date = (note["created_at"] or "")[:10] or datetime.now(EASTERN).date().isoformat()
    doc_lines = [
        "Employee Map Correction",
        f"Submitted by: {note['employee_name'] or 'Employee'}",
        f"Department: {dept_label}",
        f"Date: {created_date}",
    ]
    if note["page_ref"]:
        doc_lines.append(f"Map page reference: {note['page_ref']}")
    doc_lines.extend(
        [
            "",
            "What was wrong on the map:",
            note["what_is_wrong"],
            "",
            "Correction (how it actually works):",
            note["correction_text"],
            "",
        ]
    )
    doc_text = "\n".join(doc_lines)
    title_snippet = " ".join(note["what_is_wrong"].split())[:80]
    ingested = ingest_bytes(
        kind=KIND_TEXT,
        title=f"Correction ({dept_label}): {title_snippet}",
        original_filename=f"correction-{str(note_id)[:8]}.txt",
        data=doc_text.encode("utf-8"),
        department_hint=note["function_name"],
        effective_date=datetime.now(EASTERN).date(),
        date_origin=ORIGIN_ADMIN,
        uploaded_by=user.auth_user_id,
    )
    source_id = str(ingested["id"])

    with get_pool().connection() as conn:
        conn.execute(
            "UPDATE cmap.correction_note "
            "SET status = 'applied', source_id = %s::uuid, "
            "reviewed_by = %s::uuid, reviewed_at = now(), review_note = %s "
            "WHERE id = %s::uuid",
            (source_id, user.auth_user_id, review_note, str(note_id)),
        )
        conn.commit()
        updated = _fetch_note(conn, note_id)
    return {"note": updated, "source_id": source_id}


@router.post("/corrections/notes/{note_id}/dismiss")
def dismiss_correction_note(
    note_id: UUID,
    user: Annotated[User, Depends(require_admin)],
    body: Annotated[ReviewCorrectionNoteBody | None, Body()] = None,
) -> dict[str, Any]:
    """Dismiss one correction note without creating a map source."""
    review_note = (
        ((body.review_note or "").strip()[:MAX_REVIEW_NOTE_CHARS] or None)
        if body is not None
        else None
    )
    with get_pool().connection() as conn:
        _fetch_note(conn, note_id)
        conn.execute(
            "UPDATE cmap.correction_note "
            "SET status = 'dismissed', reviewed_by = %s::uuid, "
            "reviewed_at = now(), review_note = %s "
            "WHERE id = %s::uuid",
            (user.auth_user_id, review_note, str(note_id)),
        )
        conn.commit()
        updated = _fetch_note(conn, note_id)
    return {"note": updated}


@router.get("/corrections/permissions")
def list_correction_permissions(
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """List all active employees and their correction-submission permission."""
    del user
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT e.id::text, COALESCE(e.name, ''), COALESCE(e.email, ''), "
            "COALESCE(e.role, ''), e.is_admin, COALESCE(ef.can_correct, false) "
            "FROM public.employees e "
            "LEFT JOIN cmap.employee_flags ef ON ef.employee_id = e.id "
            "WHERE e.disabled_at IS NULL "
            "ORDER BY lower(COALESCE(NULLIF(trim(e.name), ''), e.email))"
        ).fetchall()
    return {
        "employees": [
            {
                "employee_id": str(row[0]),
                "name": str(row[1]),
                "email": str(row[2]),
                "role": str(row[3]),
                "is_admin": bool(row[4]),
                "can_correct": bool(row[5]),
            }
            for row in rows
        ]
    }


@router.put("/corrections/permissions/{employee_id}")
def set_correction_permission(
    employee_id: UUID,
    body: PermissionBody,
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Grant or revoke correction-submission permission for one employee."""
    del user
    eid = str(employee_id)
    with get_pool().connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM public.employees WHERE id = %s::uuid",
            (eid,),
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="employee not found")
        conn.execute(
            "INSERT INTO cmap.employee_flags (employee_id, can_correct) "
            "VALUES (%s::uuid, %s) "
            "ON CONFLICT (employee_id) DO UPDATE SET can_correct = EXCLUDED.can_correct",
            (eid, body.can_correct),
        )
        conn.commit()
    return {"employee_id": eid, "can_correct": body.can_correct}
