"""Admin list of Teams meeting transcripts with their one-paragraph summaries."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from brain.api.deps import User, require_admin
from brain.db import get_pool

router = APIRouter()

KEYS = (
    "id",
    "title",
    "call_kind",
    "meeting_at",
    "ended_at",
    "organizer_name",
    "participants",
    "summary",
    "summary_error",
    "state",
    "error",
)


@router.get("/meetings")
def list_meetings(
    user: Annotated[User, Depends(require_admin)],
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> list[dict[str, Any]]:
    """Newest first. Never returns transcript text."""
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT id::text, title, call_kind, meeting_at, ended_at, organizer_name, "
            "participants, summary, summary_error, state, error "
            "FROM cmap.transcript_candidate ORDER BY meeting_at DESC NULLS LAST LIMIT %s",
            (limit,),
        ).fetchall()
    return [dict(zip(KEYS, r, strict=True)) for r in rows]
