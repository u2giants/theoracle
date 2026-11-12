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
from brain.interview.inbound import handle_inbound, store_conversation_ref
from brain.interview.tick import reachable_employees, select_target

router = APIRouter()


class InboundBody(BaseModel):
    """One Teams message forwarded by the bot route."""

    email: str | None = None
    name: str | None = None
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


class ConversationRefBody(BaseModel):
    """A conversation reference for a chat the web layer opened itself."""

    employee_id: str
    conversation_ref: dict[str, Any]


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
        name=body.name,
    )


@router.get(
    "/interview/teams/conversation/{employee_id}",
    dependencies=[Depends(require_service)],
)
def teams_conversation(employee_id: str) -> dict[str, Any]:
    """Employee identity plus the stored conversation reference (nullable).

    Always readable: this lookup is what lets the web layer write back into a
    Teams chat (two-way communication, owner test 2026-11-02). A null
    ``conversation_ref`` means no chat is stored yet — the web layer then
    opens the 1:1 chat itself before the first send (measured 2026-11-04: 11
    Teams-licensed employees never got questions because their install
    conversation update never arrived). The outbound interview tick gates
    itself on ``interviews_enabled``; the lookup does not.
    """
    employee_id = _uuid(employee_id, "employee_id")
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT e.name, e.email, tc.conversation_ref "
            "FROM public.employees e "
            "LEFT JOIN cmap.teams_conversation tc ON tc.employee_id = e.id "
            "WHERE e.id = %s",
            (employee_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="no such employee")
        name, email, ref = row
        emails: list[str] = []
        if email:
            emails.append(str(email))
        for (alias,) in conn.execute(
            "SELECT email FROM public.employee_identities "
            "WHERE employee_id = %s AND email IS NOT NULL",
            (employee_id,),
        ).fetchall():
            if str(alias) not in emails:
                emails.append(str(alias))
        ref_dict = dict(ref) if ref is not None else None
        service_url = (ref_dict or {}).get("serviceUrl")
        if not service_url:
            hint = conn.execute(
                "SELECT conversation_ref->>'serviceUrl' FROM cmap.teams_conversation LIMIT 1"
            ).fetchone()
            service_url = str(hint[0]) if hint and hint[0] else None
    return {
        "employee_id": employee_id,
        "conversation_ref": ref_dict,
        "name": str(name) if name else None,
        "emails": emails,
        "service_url": service_url,
    }


@router.post("/interview/teams/conversation", dependencies=[Depends(require_service)])
def store_teams_conversation(body: ConversationRefBody) -> dict[str, Any]:
    """Store a conversation reference for a chat the web layer opened."""
    employee_id = _uuid(body.employee_id, "employee_id")
    conversation = body.conversation_ref.get("conversation") or {}
    if not conversation.get("id"):
        raise HTTPException(status_code=400, detail="conversation_ref needs conversation.id")
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM public.employees WHERE id = %s", (employee_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="no such employee")
        store_conversation_ref(conn, employee_id, body.conversation_ref)
    return {"employee_id": employee_id, "stored": True}


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
                    {
                        "question": question,
                        "entity_ids": entity_ids,
                        "target_employee_id": target,
                        "skipped_by": skipped,
                    },
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
                       (SELECT count(*) FROM cmap.interview_send s
               WHERE s.employee_id = e.id AND s.sent_at > now() - interval '7 days')
                FROM public.employees e
                LEFT JOIN cmap.employee_flags f ON f.employee_id = e.id
                LEFT JOIN cmap.teams_conversation tc ON tc.employee_id = e.id
                WHERE e.disabled_at IS NULL
                ORDER BY tc.employee_id IS NULL, COALESCE(e.name, e.email)
                """
            ).fetchall()
        ]
        contributions = [
            {
                "id": tid,
                "employee_id": eid,
                "name": names.get(eid, "Employee"),
                "started_at": _iso(started),
                "last_at": _iso(last),
                "state": state,
                "turns": int(count),
                "preview": " ".join(str(first or "").split())[:200],
                "source_id": source_id,
            }
            for tid, eid, started, last, state, count, first, source_id in conn.execute(
                "SELECT id::text, employee_id::text, started_at, last_at, state, "
                "jsonb_array_length(turns), turns->0->>'text', source_id::text "
                "FROM cmap.teams_intake ORDER BY started_at DESC LIMIT 200"
            ).fetchall()
        ]
    return {
        "env_enabled": settings.brain_interview_enabled,
        "switch_enabled": bool(switch[0]) if switch else False,
        "weekly_cap": settings.brain_interview_weekly_cap,
        "questions": questions,
        "employees": employees,
        "contributions": contributions,
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
