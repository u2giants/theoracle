"""Incoming Teams messages for interviews (plan step 12).

The Next.js bot route forwards every message here first. This module stores
the employee's conversation reference (so the bot may later write to them),
handles "stop" and "skip", and turns a reply to an asked question into a
``cmap.source`` transcript that flows through the normal pipeline. Anything
it does not handle falls through to the bot's existing join-meeting command.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from psycopg.types.json import Json

from brain.api.sources import ingest_bytes
from brain.db import get_pool
from brain.interview import followup, intake, profile

ANSWER_WINDOW_DAYS = 7
ORACLE_SPEAKER = "The Oracle"
EASTERN = ZoneInfo("America/New_York")
# Owner ruling 2026-11-02: every employee in the M365 tenant can reach The
# Oracle and feed information in; canonical emails are @popcre.com.
TENANT_EMAIL_DOMAIN = "popcre.com"

REPLY_STOPPED = (
    "Got it, The Oracle will not send you more questions. "
    "Ask an admin to turn them back on any time."
)
REPLY_SKIPPED = "No problem, skipped."
REPLY_ANSWERED = "Thanks, that's recorded."

_WORD = re.compile(r"[^a-z]+")


def _command(text: str) -> str:
    """Lower-case the message and strip punctuation for stop/skip matching."""
    return _WORD.sub(" ", text.casefold()).strip()


def _find_employee(conn: Any, email: str | None) -> tuple[str, str] | None:
    """Return ``(employee_id, name)`` for an active employee with this email.

    Teams signs people in with their work address while ``employees.email``
    may hold another one, so every linked identity email also matches
    (measured 2026-11-02: an owner "hi" from Teams matched no employee and
    the interview intake recorded nothing).
    """
    if not email:
        return None
    row = conn.execute(
        "SELECT e.id::text, COALESCE(e.name, e.email) FROM public.employees e "
        "LEFT JOIN public.employee_identities ei ON ei.employee_id = e.id "
        "WHERE e.disabled_at IS NULL AND ("
        "lower(e.email) = lower(%s) OR lower(ei.email) = lower(%s)) "
        "LIMIT 1",
        (email.strip(), email.strip()),
    ).fetchone()
    if row is None:
        return None
    return str(row[0]), str(row[1])


def _ensure_employee(conn: Any, email: str | None, name: str | None) -> tuple[str, str] | None:
    """Create a minimal employee row for a tenant address that has none.

    Owner ruling 2026-11-02: all employees in the M365 tenant can feed
    information in — a first Teams message from an unknown @popcre.com
    sender registers them. Non-tenant addresses are never auto-registered.
    """
    if not email:
        return None
    address = email.strip()
    if address.casefold().split("@")[-1:] != [TENANT_EMAIL_DOMAIN]:
        return None
    display = (name or "").strip() or address.split("@")[0]
    row = conn.execute(
        "INSERT INTO public.employees (id, email, name) VALUES (%s, %s, %s) "
        "RETURNING id::text",
        (str(uuid.uuid4()), address, display),
    ).fetchone()
    conn.commit()
    return str(row[0]), display


def store_conversation_ref(
    conn: Any, employee_id: str, conversation_ref: dict[str, Any]
) -> None:
    """Upsert the employee's conversation reference (the bot's write-back key)."""
    conn.execute(
        "INSERT INTO cmap.teams_conversation (employee_id, conversation_ref, updated_at) "
        "VALUES (%s, %s, now()) ON CONFLICT (employee_id) DO UPDATE SET "
        "conversation_ref = EXCLUDED.conversation_ref, updated_at = now()",
        (employee_id, Json(conversation_ref)),
    )
    conn.commit()


def _transcript_text(question: str, employee_name: str, answer: str) -> str:
    """The Q and A as two speaker turns the transcript reader understands."""
    question_line = " ".join(question.split())
    answer_line = " ".join(answer.split())
    speaker = " ".join(employee_name.replace(":", " ").split())
    return f"{ORACLE_SPEAKER}: {question_line}\n{speaker}: {answer_line}\n"


def _thread_reply(conn: Any, thread_id: str) -> str:
    """A grounded follow-up (kept in the thread) or the plain acknowledgement."""
    row = conn.execute(
        "SELECT employee_id::text FROM cmap.teams_intake WHERE id = %s", (thread_id,)
    ).fetchone()
    who = profile.get_profile(conn, str(row[0])).label() if row else None
    question = followup.next_followup(conn, intake.thread_turns(conn, thread_id), who)
    if question is None:
        return intake.REPLY_ACK
    intake.append_turn(conn, thread_id, followup.ORACLE_SPEAKER, question)
    return f"Got it. {question} (Or say done.)"


def _volunteer(
    conn: Any, employee_id: str, employee_name: str, text: str, command: str, personal: bool
) -> dict[str, Any]:
    """No question pending and no open thread: greeting, new thread, or fall through."""
    unhandled = {"handled": False, "reply": None, "employee_id": employee_id}
    if not personal or intake.is_join_request(text):
        return unhandled
    if intake.is_greeting(command):
        reply = intake.REPLY_INTRO
        if not profile.get_profile(conn, employee_id).complete:
            profile.mark_asked(conn, employee_id)
            reply = f"{intake.REPLY_INTRO_SHORT} {profile.PROFILE_QUESTION}"
        return {"handled": True, "reply": reply, "employee_id": employee_id}
    if intake.is_done(command):
        return {"handled": True, "reply": intake.REPLY_NOTHING_OPEN, "employee_id": employee_id}
    if intake.word_count(text) < intake.MIN_CONTRIBUTION_WORDS:
        return unhandled
    thread_id = intake.start_thread(conn, employee_id, employee_name, text)
    if not profile.get_profile(conn, employee_id).asked:
        profile.mark_asked(conn, employee_id)
        reply = f"Got it, keep going any time. {profile.PROFILE_QUESTION}"
    else:
        reply = _thread_reply(conn, thread_id)
    return {
        "handled": True,
        "reply": reply,
        "employee_id": employee_id,
        "intake_id": thread_id,
    }


def handle_inbound(
    *,
    email: str | None,
    conversation_ref: dict[str, Any] | None,
    text: str,
    name: str | None = None,
) -> dict[str, Any]:
    """Process one incoming Teams message; return ``{handled, reply, ...}``."""
    pool = get_pool()
    with pool.connection() as conn:
        employee = _find_employee(conn, email)
        if employee is None:
            employee = _ensure_employee(conn, email, name)
        if employee is None:
            return {"handled": False, "reply": None, "employee_id": None}
        employee_id, employee_name = employee
        if conversation_ref:
            store_conversation_ref(conn, employee_id, conversation_ref)
        command = _command(text)
        if command == "stop":
            conn.execute(
                "INSERT INTO cmap.employee_flags (employee_id, interviews_paused) "
                "VALUES (%s, true) ON CONFLICT (employee_id) DO UPDATE SET "
                "interviews_paused = true",
                (employee_id,),
            )
            conn.commit()
            return {"handled": True, "reply": REPLY_STOPPED, "employee_id": employee_id}
        personal = intake.is_personal(conversation_ref)
        if personal and not intake.is_join_request(text) and command not in ("skip", "done"):
            who = profile.get_profile(conn, employee_id)
            pending = conn.execute(
                "SELECT 1 FROM cmap.open_question WHERE state = 'asked' AND target_employee_id = %s "
                "AND asked_at > now() - make_interval(days => %s) LIMIT 1",
                (employee_id, ANSWER_WINDOW_DAYS),
            ).fetchone()
            if (
                pending is None
                and who.asked
                and not who.complete
                and intake.word_count(text) <= profile.MAX_ANSWER_WORDS
            ):
                return {
                    "handled": True,
                    "reply": profile.record_answer(conn, employee_id, text),
                    "employee_id": employee_id,
                    "profile": True,
                }
        thread = intake.open_thread(conn, employee_id) if personal else None
        if thread is not None and not thread[1]:
            thread_id = thread[0]
            if intake.is_join_request(text):
                return {"handled": False, "reply": None, "employee_id": employee_id}
            if intake.is_done(command):
                source_id = intake.close_thread(thread_id)
                return {
                    "handled": True,
                    "reply": intake.REPLY_DONE,
                    "employee_id": employee_id,
                    "intake_id": thread_id,
                    "source_id": source_id,
                }
            intake.append_turn(conn, thread_id, employee_name, text)
            return {
                "handled": True,
                "reply": _thread_reply(conn, thread_id),
                "employee_id": employee_id,
                "intake_id": thread_id,
            }
        if thread is not None:
            intake.close_thread(thread[0])
        row = conn.execute(
            "SELECT id::text, question FROM cmap.open_question "
            "WHERE state = 'asked' AND target_employee_id = %s "
            "AND asked_at > now() - make_interval(days => %s) "
            "ORDER BY asked_at DESC LIMIT 1",
            (employee_id, ANSWER_WINDOW_DAYS),
        ).fetchone()
        if row is None:
            return _volunteer(conn, employee_id, employee_name, text, command, personal)
        question_id, question = str(row[0]), str(row[1])
        if command == "skip":
            conn.execute(
                "UPDATE cmap.open_question SET state = 'open', target_employee_id = NULL, "
                "asked_at = NULL, skipped_by = array_append(skipped_by, %s::uuid) "
                "WHERE id = %s",
                (employee_id, question_id),
            )
            conn.commit()
            return {
                "handled": True,
                "reply": REPLY_SKIPPED,
                "employee_id": employee_id,
                "question_id": question_id,
            }
    answer = text.strip()
    day = datetime.now(EASTERN).date().isoformat()
    source = ingest_bytes(
        kind="transcript",
        title=f"Interview answer — {employee_name} — {day}",
        original_filename=f"interview-answer-{question_id}.txt",
        data=(profile.transcript_header(employee_id, employee_name)
              + _transcript_text(question, employee_name, answer)).encode("utf-8"),
        department_hint=profile.department_hint(employee_id),
        effective_date=None,
        uploaded_by=None,
    )
    with pool.connection() as conn:
        conn.execute(
            "UPDATE cmap.open_question SET state = 'answered', answer = %s, "
            "answered_at = now(), answer_source_id = %s WHERE id = %s",
            (answer, source["id"], question_id),
        )
        conn.commit()
    return {
        "handled": True,
        "reply": REPLY_ANSWERED,
        "employee_id": employee_id,
        "question_id": question_id,
        "source_id": source["id"],
    }
