"""Admin listing of staged message-intake threads (plan_pm_message_intake.md 1.5).

Returns title, dates, counts, verdict, gate scores and summary only. Never
message text.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from brain.api.deps import User, require_admin
from brain.db import get_pool

router = APIRouter()

VERDICTS = frozenset({"pending", "kept", "dropped"})


@router.get("/intake/threads")
def list_threads(
    user: Annotated[User, Depends(require_admin)],
    verdict: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[dict[str, Any]]:
    if verdict is not None and verdict not in VERDICTS:
        raise HTTPException(
            status_code=422, detail="verdict must be pending, kept or dropped"
        )
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT origin, title, started_at, ended_at, item_count, token_count, "
            "verdict, gate_scores, summary FROM cmap.intake_thread "
            "WHERE %(v)s::text IS NULL OR verdict = %(v)s "
            "ORDER BY ended_at DESC NULLS LAST LIMIT %(n)s",
            {"v": verdict, "n": limit},
        ).fetchall()
    keys = (
        "origin",
        "title",
        "started_at",
        "ended_at",
        "item_count",
        "token_count",
        "verdict",
        "gate_scores",
        "summary",
    )
    return [dict(zip(keys, r, strict=True)) for r in rows]
