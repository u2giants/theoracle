"""Recommendation endpoints (plan step 13).

``GET /recommendations`` lists the cards for every logged-in employee, sorted
by the number of distinct sources behind them; rejected cards are hidden.
``POST /recommendations/{id}/status`` (admin) records Accept / Reject /
Running / Measured.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from brain.api.deps import User, current_user, require_admin
from brain.api.map import _source_titles
from brain.db import get_pool

router = APIRouter()


class StatusBody(BaseModel):
    """New status for one recommendation."""

    status: Literal["proposed", "accepted", "rejected", "running", "measured"]


def _json(raw: Any) -> Any:
    return json.loads(raw) if isinstance(raw, str) else raw


def _cited(explanations: list[dict[str, Any]]) -> set[str]:
    return {
        str(source_id)
        for item in explanations
        for key in ("support", "against")
        for source_id in item.get(key) or []
    }


@router.get("/recommendations")
def list_recommendations(user: Annotated[User, Depends(current_user)]) -> dict[str, Any]:
    """Every non-rejected recommendation, most distinct sources first."""
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT r.id::text, r.community_id::text, c.title, r.problem, r.explanations, "
            "r.options, r.experiment, r.status, r.created_at "
            "FROM cmap.recommendation r LEFT JOIN cmap.community c ON c.id = r.community_id "
            "WHERE r.status <> 'rejected'"
        ).fetchall()
        parsed = [
            (row, _json(row[4]) or [], _json(row[5]) or [], _json(row[6]) or {})
            for row in rows
        ]
        all_ids: set[str] = set()
        for _row, explanations, _options, _experiment in parsed:
            all_ids |= _cited(explanations)
        titles = _source_titles(conn, all_ids)
    cards: list[dict[str, Any]] = []
    for row, explanations, options, experiment in parsed:
        sources = sorted(source_id for source_id in _cited(explanations) if source_id in titles)
        for item in explanations:
            for key in ("support", "against"):
                item[key] = [
                    {"id": source_id, "title": titles[source_id]}
                    for source_id in item.get(key) or []
                    if source_id in titles
                ]
        cards.append(
            {
                "id": row[0],
                "community_id": row[1],
                "community_title": row[2],
                "problem": row[3],
                "explanations": explanations,
                "options": options,
                "experiment": experiment,
                "status": row[7],
                "created_at": row[8].isoformat() if row[8] else None,
                "source_count": len(sources),
                "sources": [{"id": source_id, "title": titles[source_id]} for source_id in sources],
            }
        )
    cards.sort(key=lambda card: (-card["source_count"], card["created_at"] or ""))
    return {"recommendations": cards, "is_admin": user.is_admin}


@router.post("/recommendations/{recommendation_id}/status")
def set_status(
    recommendation_id: str,
    body: StatusBody,
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Admin: Accept / Reject / Running / Measured."""
    del user
    try:
        rec_id = str(UUID(recommendation_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid recommendation id") from exc
    with get_pool().connection() as conn:
        row = conn.execute(
            "UPDATE cmap.recommendation SET status = %s WHERE id = %s RETURNING id",
            (body.status, rec_id),
        ).fetchone()
        conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="recommendation not found")
    return {"id": rec_id, "status": body.status}
