"""Evaluation endpoints (plan step 11).

Questions are written by admins (Albert, Ilona) on the eval page; any
logged-in employee may read questions and runs. ``POST /eval/run`` (admin)
queues one ``evaluate`` job; ``GET /eval/runs`` returns runs newest first,
each with its per-question scores and the change against the run before it.
"""

from __future__ import annotations

import json
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from brain.api.deps import User, current_user, require_admin
from brain.db import get_pool

router = APIRouter()

MIN_POINTS = 3
MAX_POINTS = 6


class QuestionBody(BaseModel):
    """One eval question as typed on the eval page."""

    question: str
    expected_points: list[str]
    expected_source_titles: list[str] = []


def _clean(items: list[str]) -> list[str]:
    return [item.strip() for item in items if item and item.strip()]


@router.get("/eval/questions")
def list_questions(user: Annotated[User, Depends(current_user)]) -> dict[str, Any]:
    """Every eval question."""
    del user
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT id::text, question, expected_points, expected_source_titles, author "
            "FROM cmap.eval_question ORDER BY question"
        ).fetchall()
    return {
        "questions": [
            {
                "id": row[0],
                "question": row[1],
                "expected_points": list(row[2]),
                "expected_source_titles": list(row[3]),
                "author": row[4],
            }
            for row in rows
        ]
    }


@router.post("/eval/questions")
def add_question(
    body: QuestionBody, user: Annotated[User, Depends(require_admin)]
) -> dict[str, Any]:
    """Add one question with 3-6 expected points."""
    question = body.question.strip()
    points = _clean(body.expected_points)
    titles = _clean(body.expected_source_titles)
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    if not MIN_POINTS <= len(points) <= MAX_POINTS:
        raise HTTPException(
            status_code=400,
            detail=f"give {MIN_POINTS} to {MAX_POINTS} expected points",
        )
    with get_pool().connection() as conn:
        row = conn.execute(
            "INSERT INTO cmap.eval_question "
            "(question, expected_points, expected_source_titles, author) "
            "VALUES (%s, %s, %s, %s) RETURNING id::text",
            (question, points, titles, user.employee_id),
        ).fetchone()
        conn.commit()
    return {"id": row[0]}


@router.delete("/eval/questions/{question_id}")
def delete_question(
    question_id: str, user: Annotated[User, Depends(require_admin)]
) -> dict[str, Any]:
    """Remove one question (past runs keep their copy of it)."""
    del user
    try:
        key = str(UUID(question_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="no such question") from exc
    with get_pool().connection() as conn:
        row = conn.execute(
            "DELETE FROM cmap.eval_question WHERE id = %s RETURNING id", (key,)
        ).fetchone()
        conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="no such question")
    return {"deleted": True}


@router.post("/eval/run")
def queue_eval(user: Annotated[User, Depends(require_admin)]) -> dict[str, Any]:
    """Queue one ``evaluate`` job unless one is already queued or running."""
    del user
    with get_pool().connection() as conn:
        row = conn.execute(
            "INSERT INTO cmap.job (kind, payload) SELECT 'evaluate', '{}'::jsonb "
            "WHERE NOT EXISTS (SELECT 1 FROM cmap.job WHERE kind = 'evaluate' "
            "AND state IN ('queued','running')) RETURNING id::text"
        ).fetchone()
        conn.commit()
    if row is None:
        return {"queued": False, "detail": "an eval run is already queued or running"}
    return {"queued": True, "job_id": row[0]}


def diff_runs(
    current: list[dict[str, Any]], previous: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """Per-question score change against the previous run (matched by question text)."""
    before: dict[str, float] = {}
    for item in previous or []:
        before[str(item.get("question"))] = float(item.get("score") or 0.0)
    out: list[dict[str, Any]] = []
    for item in current:
        question = str(item.get("question"))
        score = float(item.get("score") or 0.0)
        old = before.get(question)
        out.append(
            {
                "question": question,
                "score": score,
                "previous": old,
                "delta": None if old is None else round(score - old, 4),
            }
        )
    return out


@router.get("/eval/runs")
def list_runs(
    user: Annotated[User, Depends(current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    """Runs newest first, each with results and the diff against its predecessor."""
    del user
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT id::text, created_at, graph_version, prompt_hashes, results, "
            "mean_score, models "
            "FROM cmap.eval_run ORDER BY created_at DESC, id DESC LIMIT %s",
            (limit + 1,),
        ).fetchall()
        job = conn.execute(
            "SELECT state, error, created_at FROM cmap.job WHERE kind = 'evaluate' "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    runs: list[dict[str, Any]] = []
    for position, row in enumerate(rows[:limit]):
        results = row[4] if isinstance(row[4], list) else json.loads(row[4])
        previous = None
        previous_mean = None
        if position + 1 < len(rows):
            prior = rows[position + 1]
            previous = prior[4] if isinstance(prior[4], list) else json.loads(prior[4])
            previous_mean = float(prior[5])
        mean = float(row[5])
        models = row[6]
        if isinstance(models, str):
            models = json.loads(models)
        runs.append(
            {
                "id": row[0],
                "created_at": row[1].isoformat(),
                "graph_version": row[2],
                "prompt_hashes": row[3],
                "models": models,
                "mean_score": mean,
                "previous_mean": previous_mean,
                "mean_delta": None
                if previous_mean is None
                else round(mean - previous_mean, 4),
                "results": results,
                "diff": diff_runs(results, previous),
            }
        )
    latest_job = None
    if job is not None:
        latest_job = {
            "state": job[0],
            "error": job[1],
            "created_at": job[2].isoformat(),
        }
    return {"runs": runs, "latest_job": latest_job}
