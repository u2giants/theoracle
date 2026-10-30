"""Interview endpoints (plan step 12).

Service routes (shared token only) serve the Teams bot: incoming messages and
the stored conversation reference for proactive sends. Admin routes back the
``/map/questions`` page: the queue, who each question will go to, the
asked/answered history, the per-employee pause switch and the global switch.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from brain.api.deps import User, require_admin, require_service
from brain.config import get_settings
from brain.db import enqueue_job, get_pool
from brain.interview.inbound import handle_inbound
from brain.interview.tick import interviews_enabled, reachable_employees, select_target

router = APIRouter()


class InboundBody(BaseModel):
    """One Teams message forwarded by the bot route."""

    email: str | None = None
    conversation_ref: dict[str, Any] | None = None
    text: str = ""


class SwitchBody(BaseModel):
    """An on/off switch value."""

    enabled: bool


class PauseBody(BaseModel):
    """Per-employee pause value."""

    paused: bool


class RouteBody(BaseModel):
    """Manual routing of one question; ``None`` clears it."""

    employee_id: str | None = None


def _uuid(value: str, field: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid {field}") from exc


@router.post("/interview/teams/inbound", dependencies=[Depends(require_service)])
def teams_inbound(body: InboundBody) -> dict[str, Any]:
    """Handle stop/skip/answers; ``handled=false`` means fall through to join."""
    return handle_inbound(
        email=body.email,
        conversation_ref=body.conversation_ref,
        text=body.text,
    )


@router.get(
    "/interview/teams/conversation/{employee_id}",
    dependencies=[Depends(require_service)],
)
def teams_conversation(employee_id: str) -> dict[str, Any]:
    """Stored conversation reference; 404 when the employee never wrote first."""
    employee_id = _uuid(employee_id, "employee_id")
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT conversation_ref FROM cmap.teams_conversation WHERE employee_id = %s",
            (employee_id,),
        ).fetchone()
        enabled = interviews_enabled(conn, get_settings())
    if not enabled:
        raise HTTPException(status_code=409, detail="interviews are turned off")
    if row is None:
        raise HTTPException(status_code=404, detail="employee has not messaged the bot")
    return {"employee_id": employee_id, "conversation_ref": row[0]}


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


@router.get("/interview/overview")
def overview(user: Annotated[User, Depends(require_admin)]) -> dict[str, Any]:
    """Everything the admin questions page shows."""
    del user
    settings = get_settings()
    pool = get_pool()
    with pool.connection() as conn:
        switch = conn.execute("SELECT enabled FROM cmap.interview_setting WHERE id").fetchone()
        reachable = reachable_employees(conn, settings.brain_interview_weekly_cap)
        names = {
            str(eid): str(name)
            for eid, name in conn.execute(
                "SELECT id::text, COALESCE(name, email) FROM public.employees"
            ).fetchall()
        }
        questions = []
        for row in conn.execute(
            "SELECT id::text, question, why, entity_ids, target_employee_id::text, state, "
            "asked_at, answer, answered_at, answer_source_id::text, skipped_by, created_at "
            "FROM cmap.open_question ORDER BY "
            "CASE state WHEN 'open' THEN 0 WHEN 'asked' THEN 1 ELSE 2 END, "
            "COALESCE(answered_at, asked_at, created_at) DESC LIMIT 500"
        ).fetchall():
            (qid, question, why, entity_ids, target, state, asked_at, answer,
             answered_at, source_id, skipped, created_at) = row
            next_target = None
            if state == "open":
                picked = select_target(
                    conn,
                    {"entity_ids": entity_ids, "target_employee_id": target, "skipped_by": skipped},
                    reachable,
                )
                if picked is not None:
                    next_target = {"employee_id": picked.employee_id, "name": picked.name}
            questions.append({
                "id": qid,
                "question": question,
                "why": why,
                "state": state,
                "target_employee_id": target,
                "target_name": names.get(target) if target else None,
                "next_target": next_target,
                "asked_at": _iso(asked_at),
                "answer": answer,
                "answered_at": _iso(answered_at),
                "answer_source_id": source_id,
                "created_at": _iso(created_at),
            })
        employees = [
            {
                "employee_id": eid,
                "name": name,
                "paused": bool(paused),
                "connected": bool(connected),
                "asked_last_7_days": int(asked),
            }
            for eid, name, paused, connected, asked in conn.execute(
                """
                SELECT e.id::text, COALESCE(e.name, e.email),
                       COALESCE(f.interviews_paused, false),
                       tc.employee_id IS NOT NULL,
                       (SELECT count(*) FROM cmap.open_question q
                        WHERE q.target_employee_id = e.id
                          AND q.asked_at > now() - interval '7 days')
                FROM public.employees e
                LEFT JOIN cmap.employee_flags f ON f.employee_id = e.id
                LEFT JOIN cmap.teams_conversation tc ON tc.employee_id = e.id
                WHERE e.disabled_at IS NULL
                ORDER BY tc.employee_id IS NULL, COALESCE(e.name, e.email)
                """
            ).fetchall()
        ]
    return {
        "env_enabled": settings.brain_interview_enabled,
        "switch_enabled": bool(switch[0]) if switch else False,
        "weekly_cap": settings.brain_interview_weekly_cap,
        "questions": questions,
        "employees": employees,
    }


@router.post("/interview/settings")
def set_switch(body: SwitchBody, user: Annotated[User, Depends(require_admin)]) -> dict[str, Any]:
    """Global on/off switch on the admin page."""
    del user
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(
            "UPDATE cmap.interview_setting SET enabled = %s, updated_at = now() WHERE id",
            (body.enabled,),
        )
        conn.commit()
    return {"switch_enabled": body.enabled}


@router.post("/interview/employees/{employee_id}/pause")
def set_pause(
    employee_id: str,
    body: PauseBody,
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Pause or resume interview questions for one employee."""
    del user
    employee_id = _uuid(employee_id, "employee_id")
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO cmap.employee_flags (employee_id, interviews_paused) VALUES (%s, %s) "
            "ON CONFLICT (employee_id) DO UPDATE SET interviews_paused = EXCLUDED.interviews_paused",
            (employee_id, body.paused),
        )
        conn.commit()
    return {"employee_id": employee_id, "paused": body.paused}


@router.post("/interview/questions/{question_id}/route")
def route_question(
    question_id: str,
    body: RouteBody,
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Send an open question to a chosen employee on the next tick."""
    del user
    question_id = _uuid(question_id, "question_id")
    employee_id = _uuid(body.employee_id, "employee_id") if body.employee_id else None
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE cmap.open_question SET target_employee_id = %s "
            "WHERE id = %s AND state = 'open' RETURNING id",
            (employee_id, question_id),
        ).fetchone()
        conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="no open question with that id")
    return {"id": question_id, "target_employee_id": employee_id}


@router.post("/interview/questions/{question_id}/dismiss")
def dismiss_question(
    question_id: str,
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Drop a question nobody should be asked."""
    del user
    question_id = _uuid(question_id, "question_id")
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE cmap.open_question SET state = 'dismissed' "
            "WHERE id = %s AND state IN ('open','asked') RETURNING id",
            (question_id,),
        ).fetchone()
        conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="no open or asked question with that id")
    return {"id": question_id, "state": "dismissed"}


@router.post("/interview/tick")
def queue_tick(user: Annotated[User, Depends(require_admin)]) -> dict[str, Any]:
    """Queue an interview tick now instead of waiting for the hourly one."""
    del user
    job_id = enqueue_job("interview_tick", {})
    return {"job_id": job_id}
