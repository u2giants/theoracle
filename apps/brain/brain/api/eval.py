"""Evaluation endpoints (plan step 11, repair step B1).

Questions are written by admins (Albert, Ilona) on the eval page; any
logged-in employee may read questions and runs. Admin actions per question
(B1): approve (sets ``approved_at``; only approved questions count toward the
eval bar), edit and retire (sets ``retired_at``). ``POST /eval/run`` (admin or
service) queues one ``evaluate`` job; ``GET /eval/runs`` returns runs newest
first, each with its per-question scores, the change against the run before
it and the quality gate's ``accepted`` mark (B3). The service (shared token
only) may queue and read runs, and ``POST /eval/runs/{id}/accept`` marks the
gate's baseline run, so ``brain-quality.yml`` can gate live quality.
"""

from __future__ import annotations

import json
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from brain.api.deps import (
    User,
    admin_or_service,
    current_user,
    employee_or_service,
    require_admin,
)
from brain.db import get_pool

router = APIRouter()

MIN_POINTS = 3
MAX_POINTS = 6

_QUESTION_COLUMNS = (
    "id::text, question, expected_points, expected_source_titles, author, "
    "approved_at, retired_at, abstention, recommendation, function"
)


class QuestionBody(BaseModel):
    """One eval question as typed on the eval page."""

    question: str
    expected_points: list[str]
    expected_source_titles: list[str] = []
    abstention: bool = False
    recommendation: str | None = None
    function: list[str] | None = None


def _clean(items: list[str]) -> list[str]:
    return [item.strip() for item in items if item and item.strip()]


def _question_dict(row: tuple) -> dict[str, Any]:
    return {
        "id": row[0],
        "question": row[1],
        "expected_points": list(row[2]),
        "expected_source_titles": list(row[3]),
        "author": row[4],
        "approved_at": row[5].isoformat() if row[5] else None,
        "retired_at": row[6].isoformat() if row[6] else None,
        "abstention": bool(row[7]),
        "recommendation": row[8],
        "function": list(row[9]) if row[9] else [],
    }


def _question_key(question_id: str) -> str:
    try:
        return str(UUID(question_id))
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=404, detail="no such question") from exc


def _validate_body(body: QuestionBody) -> tuple[str, list[str], list[str]]:
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
    return question, points, titles


@router.get("/eval/questions")
def list_questions(user: Annotated[User, Depends(current_user)]) -> dict[str, Any]:
    """Every eval question."""
    del user
    with get_pool().connection() as conn:
        rows = conn.execute(
            f"SELECT {_QUESTION_COLUMNS} FROM cmap.eval_question ORDER BY question"
        ).fetchall()
    return {"questions": [_question_dict(row) for row in rows]}


@router.post("/eval/questions")
def add_question(
    body: QuestionBody, user: Annotated[User, Depends(require_admin)]
) -> dict[str, Any]:
    """Add one question with 3-6 expected points."""
    question, points, titles = _validate_body(body)
    with get_pool().connection() as conn:
        row = conn.execute(
            "INSERT INTO cmap.eval_question "
            "(question, expected_points, expected_source_titles, author, "
            "abstention, recommendation, function) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id::text",
            (
                question,
                points,
                titles,
                user.employee_id,
                body.abstention,
                body.recommendation,
                _clean(body.function or []),
            ),
        ).fetchone()
        conn.commit()
    return {"id": row[0]}


@router.put("/eval/questions/{question_id}")
def edit_question(
    question_id: str,
    body: QuestionBody,
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Edit one question's wording, expected points and sources (plan B1)."""
    del user
    key = _question_key(question_id)
    question, points, titles = _validate_body(body)
    with get_pool().connection() as conn:
        row = conn.execute(
            "UPDATE cmap.eval_question SET question = %s, expected_points = %s, "
            "expected_source_titles = %s, abstention = %s, recommendation = %s, "
            "function = COALESCE(%s, function) "
            "WHERE id = %s RETURNING id",
            (
                question,
                points,
                titles,
                body.abstention,
                body.recommendation,
                _clean(body.function) if body.function is not None else None,
                key,
            ),
        ).fetchone()
        conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="no such question")
    return {"id": key, "edited": True}


@router.post("/eval/questions/{question_id}/approve")
def approve_question(
    question_id: str, user: Annotated[User, Depends(require_admin)]
) -> dict[str, Any]:
    """Stamp ``approved_at``; only approved questions count toward the bar."""
    del user
    key = _question_key(question_id)
    with get_pool().connection() as conn:
        row = conn.execute(
            f"UPDATE cmap.eval_question SET approved_at = COALESCE(approved_at, now()) "
            f"WHERE id = %s RETURNING {_QUESTION_COLUMNS}",
            (key,),
        ).fetchone()
        conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="no such question")
    return _question_dict(row)


@router.post("/eval/questions/{question_id}/retire")
def retire_question(
    question_id: str, user: Annotated[User, Depends(require_admin)]
) -> dict[str, Any]:
    """Stamp ``retired_at``; retired questions never count toward the bar."""
    del user
    key = _question_key(question_id)
    with get_pool().connection() as conn:
        row = conn.execute(
            f"UPDATE cmap.eval_question SET retired_at = COALESCE(retired_at, now()) "
            f"WHERE id = %s RETURNING {_QUESTION_COLUMNS}",
            (key,),
        ).fetchone()
        conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="no such question")
    return _question_dict(row)


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
def queue_eval(
    user: Annotated[User | None, Depends(admin_or_service)],
) -> dict[str, Any]:
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


@router.post("/eval/runs/{run_id}/accept")
def accept_run(
    run_id: str,
    user: Annotated[User | None, Depends(admin_or_service)],
) -> dict[str, Any]:
    """Mark one run accepted (the quality gate's baseline; B3)."""
    del user
    try:
        key = str(UUID(run_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="no such run") from exc
    with get_pool().connection() as conn:
        row = conn.execute(
            "UPDATE cmap.eval_run SET accepted = true WHERE id = %s "
            "RETURNING id::text, mean_score, accepted",
            (key,),
        ).fetchone()
        conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="no such run")
    return {"id": row[0], "mean_score": float(row[1]), "accepted": bool(row[2])}


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
    user: Annotated[User | None, Depends(employee_or_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    """Runs newest first, each with results and the diff against its predecessor."""
    del user
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT id::text, created_at, graph_version, prompt_hashes, results, "
            "mean_score, models, mean_score_legacy, accepted "
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
                "mean_score_legacy": None if row[7] is None else float(row[7]),
                "accepted": bool(row[8]),
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
