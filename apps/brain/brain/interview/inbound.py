"""Incoming Teams messages for interviews (plan step 12).

The Next.js bot route forwards every message here first. This module stores
the employee's conversation reference (so the bot may later write to them)
when — and only when — the chat is personal, handles "stop"/"skip"/"resume",
and turns a reply to an asked question into a ``cmap.source`` transcript that
flows through the normal pipeline. Anything it does not handle falls through
to the bot's existing join-meeting command.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from psycopg.types.json import Json

from brain.answer.answer import parse_model_json
from brain.api.sources import ingest_bytes
from brain.config import get_settings
from brain.db import get_pool
from brain.interview import followup, intake, profile
from brain.interview.strings import reply_language, strings
from brain.llm import message_content, post_chat_with_rescue
from brain.read.dates import ORIGIN_INTERVIEW
from brain.seats import stage_model
from brain.text_util import fold_key

logger = logging.getLogger(__name__)

# One shared window (F4): the same days govern "free for a new question"
# (tick) and "a reply still matches a pending question" (here). It used to be
# 3 vs 7, which let a second question go out while the first was still
# matchable and a late reply land on the wrong one. 7 days keeps the old
# reply-match reach; the free window widens to match it.
QUESTION_WINDOW_DAYS = 7
ORACLE_SPEAKER = "The Oracle"
EASTERN = ZoneInfo("America/New_York")
# Owner ruling 2026-11-02: every employee in the M365 tenant can reach The
# Oracle and feed information in; canonical emails are @popcre.com.
TENANT_EMAIL_DOMAIN = "popcre.com"

# English strings kept as module constants (tests and callers reference them);
# replies are chosen through strings(lang) at the call sites (plan step 2.1).
_EN = strings("en")
REPLY_STOPPED = _EN.reply_stopped
REPLY_SKIPPED = _EN.reply_skipped
REPLY_ANSWERED = _EN.reply_answered

_STOP_COMMANDS = {"stop", "停止", "暂停"}
_RESUME_COMMANDS = {"resume", "continue", "继续", "恢复"}
_SKIP_COMMANDS = {"skip", "跳过"}


REPLY_CHECK_PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "reply_check.md"
INTENT_CHECK_PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "intent_check.md"
REPLY_MATCH_PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "reply_match.md"
REPLY_CHECK_TIMEOUT_SECONDS = 8.0


def classify_reply(question: str, reply: str) -> str:
    """``answer``, ``dont_know`` or ``other`` for a reply to a pending question.

    Unjudged (no model, or the check fails) is never accepted as an answer:
    the reply is held as ``other`` so the question stays pending and the
    message still reaches the thread/volunteer path instead of being lost.
    """
    settings = get_settings()
    model = stage_model(settings, "answer")
    if not model or not settings.openrouter_api_key:
        return "other"
    prompt = (
        REPLY_CHECK_PROMPT.read_text(encoding="utf-8")
        .replace("{{question}}", question)
        .replace("{{reply}}", reply)
    )
    try:
        body = post_chat_with_rescue(
            {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 60,
                "temperature": 0,
            },
            settings=settings,
            timeout=REPLY_CHECK_TIMEOUT_SECONDS,
            error_cls=RuntimeError,
            label="reply check",
        )
        kind = str(parse_model_json(message_content(body), ()).get("kind") or "")
    except Exception:  # noqa: BLE001 - a failed check must hold, not answer
        logger.warning("reply check failed; holding the reply instead of answering")
        return "other"
    return kind if kind in {"answer", "dont_know", "other"} else "other"


def _command(text: str) -> str:
    """Casefold and strip punctuation for stop/skip matching; keeps CJK."""
    return fold_key(text)


def classify_intent(text: str) -> str:
    """``stop``, ``resume`` or ``other``: literal commands first, then meaning.

    "stop"-like phrases are recognised by meaning in both languages through
    the judge (``_judge_intent``); the literal sets are the deterministic
    fast path that keeps working even when the model is down.
    """
    command = _command(text)
    if command in _STOP_COMMANDS:
        return "stop"
    if command in _RESUME_COMMANDS:
        return "resume"
    return _judge_intent(text)


def _judge_intent(text: str) -> str:
    """Meaning-based stop/resume; unjudged messages are never taken as a command."""
    settings = get_settings()
    model = stage_model(settings, "grade")
    if not model or not settings.openrouter_api_key:
        return "other"
    prompt = (
        INTENT_CHECK_PROMPT.read_text(encoding="utf-8").replace("{{message}}", text)
    )
    try:
        body = post_chat_with_rescue(
            {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 20,
                "temperature": 0,
            },
            settings=settings,
            timeout=REPLY_CHECK_TIMEOUT_SECONDS,
            error_cls=RuntimeError,
            label="interview intent check",
        )
        kind = str(parse_model_json(message_content(body), ()).get("kind") or "")
    except Exception:  # noqa: BLE001 - never accept an unjudged message as a command
        logger.warning("intent check failed; not treating the message as a command")
        return "other"
    return kind if kind in {"stop", "resume"} else "other"


def _pending_questions(conn: Any, employee_id: str) -> list[tuple[str, str]]:
    """Up to three asked questions still inside the window, newest first."""
    rows = conn.execute(
        "SELECT id::text, question FROM cmap.open_question "
        "WHERE state = 'asked' AND target_employee_id = %s "
        "AND asked_at > now() - make_interval(days => %s) "
        "ORDER BY asked_at DESC LIMIT 3",
        (employee_id, QUESTION_WINDOW_DAYS),
    ).fetchall()
    return [(str(row[0]), str(row[1])) for row in rows]


def match_reply(questions: list[str], reply: str) -> int | None:
    """Index of the question the reply answers, or ``None`` to hold.

    Model judgement over the candidate questions, never recency. Unjudged
    (no model, or the check fails) matches nothing: the questions stay
    pending rather than one being picked by guess.
    """
    if not questions:
        return None
    if len(questions) == 1:
        return 0
    settings = get_settings()
    model = stage_model(settings, "grade")
    if not model or not settings.openrouter_api_key:
        return None
    listing = "\n".join(
        f"QUESTION {i}:\n<<<\n{question}\n>>>" for i, question in enumerate(questions, 1)
    )
    prompt = (
        REPLY_MATCH_PROMPT.read_text(encoding="utf-8")
        .replace("{{questions}}", listing)
        .replace("{{reply}}", reply)
    )
    try:
        body = post_chat_with_rescue(
            {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 20,
                "temperature": 0,
            },
            settings=settings,
            timeout=REPLY_CHECK_TIMEOUT_SECONDS,
            error_cls=RuntimeError,
            label="reply match",
        )
        index = int(parse_model_json(message_content(body), ()).get("index") or 0)
    except Exception:  # noqa: BLE001 - never pick a question without a judgement
        logger.warning("reply match failed; holding the reply instead of matching")
        return None
    return index - 1 if 1 <= index <= len(questions) else None


def _find_employee(conn: Any, email: str | None) -> tuple[str, str, str | None] | None:
    """Return ``(employee_id, name, locale)`` for an active employee with this email.

    Teams signs people in with their work address while ``employees.email``
    may hold another one, so every linked identity email also matches
    (measured 2026-11-02: an owner "hi" from Teams matched no employee and
    the interview intake recorded nothing).
    """
    if not email:
        return None
    row = conn.execute(
        "SELECT e.id::text, COALESCE(e.name, e.email), e.locale FROM public.employees e "
        "LEFT JOIN public.employee_identities ei ON ei.employee_id = e.id "
        "WHERE e.disabled_at IS NULL AND ("
        "lower(e.email) = lower(%s) OR lower(ei.email) = lower(%s)) "
        "LIMIT 1",
        (email.strip(), email.strip()),
    ).fetchone()
    if row is None:
        return None
    return str(row[0]), str(row[1]), str(row[2]) if row[2] else None


def _ensure_employee(
    conn: Any, email: str | None, name: str | None
) -> tuple[str, str, str | None] | None:
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
    return str(row[0]), display, None


def store_conversation_ref(
    conn: Any, employee_id: str, conversation_ref: dict[str, Any]
) -> None:
    """Upsert the employee's conversation reference (the bot's write-back key).

    F4 chat safety: only a personal (1:1) chat may become the write-back
    target — a group or meeting reference would send later interview
    questions into that chat. Non-personal references are ignored.
    """
    if not intake.is_personal(conversation_ref):
        return
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


def _thread_reply(conn: Any, thread_id: str, lang: str) -> str:
    """A grounded follow-up (kept in the thread) or the plain acknowledgement."""
    s = strings(lang)
    row = conn.execute(
        "SELECT employee_id::text FROM cmap.teams_intake WHERE id = %s", (thread_id,)
    ).fetchone()
    who = profile.get_profile(conn, str(row[0])).label() if row else None
    question = followup.next_followup(conn, intake.thread_turns(conn, thread_id), who)
    if question is None:
        return s.reply_ack
    intake.append_turn(conn, thread_id, followup.ORACLE_SPEAKER, question)
    return s.thread_followup.format(question=question)


def _volunteer(
    conn: Any,
    employee_id: str,
    employee_name: str,
    text: str,
    command: str,
    personal: bool,
    lang: str,
    locale: str | None,
) -> dict[str, Any]:
    """No question pending and no open thread: greeting, new thread, or fall through."""
    s = strings(lang)
    unhandled = {"handled": False, "reply": None, "employee_id": employee_id}
    if not personal or intake.is_join_request(text):
        return unhandled
    if intake.is_greeting(command):
        reply = s.reply_intro
        if not profile.get_profile(conn, employee_id).complete:
            profile.mark_asked(conn, employee_id)
            reply = f"{s.reply_intro_short} {s.profile_question}"
        return {"handled": True, "reply": reply, "employee_id": employee_id}
    if intake.is_done(command):
        return {"handled": True, "reply": s.reply_nothing_open, "employee_id": employee_id}
    if intake.word_count(text) < intake.MIN_CONTRIBUTION_WORDS:
        return unhandled
    # Thread pin: a Chinese opening message keeps the thread Chinese even
    # when the employee's locale is English (plan step 2.1, O1 fallback).
    pinned = lang if lang == "zh-CN" and (locale or "").strip() != "zh-CN" else None
    thread_id = intake.start_thread(
        conn, employee_id, employee_name, text, lang=pinned
    )
    if not profile.get_profile(conn, employee_id).asked:
        profile.mark_asked(conn, employee_id)
        reply = f"{s.reply_keep_going} {s.profile_question}"
    else:
        reply = _thread_reply(conn, thread_id, lang)
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
        employee_id, employee_name, locale = employee
        personal = intake.is_personal(conversation_ref)
        if conversation_ref and personal:
            store_conversation_ref(conn, employee_id, conversation_ref)
        lang = reply_language(locale, text)
        command = _command(text)
        intent = classify_intent(text)
        if intent == "stop":
            conn.execute(
                "INSERT INTO cmap.employee_flags (employee_id, interviews_paused) "
                "VALUES (%s, true) ON CONFLICT (employee_id) DO UPDATE SET "
                "interviews_paused = true",
                (employee_id,),
            )
            conn.commit()
            return {
                "handled": True,
                "reply": strings(lang).reply_stopped,
                "employee_id": employee_id,
            }
        if intent == "resume":
            conn.execute(
                "INSERT INTO cmap.employee_flags (employee_id, interviews_paused) "
                "VALUES (%s, false) ON CONFLICT (employee_id) DO UPDATE SET "
                "interviews_paused = false",
                (employee_id,),
            )
            conn.commit()
            return {
                "handled": True,
                "reply": strings(lang).reply_resumed,
                "employee_id": employee_id,
            }
        candidates = _pending_questions(conn, employee_id)
        if (
            personal
            and not candidates
            and not intake.is_join_request(text)
            and command not in _SKIP_COMMANDS
            and not intake.is_done(command)
        ):
            who = profile.get_profile(conn, employee_id)
            if (
                who.asked
                and not who.complete
                and intake.word_count(text) <= profile.MAX_ANSWER_WORDS
                and profile.is_profile_answer(text)
            ):
                return {
                    "handled": True,
                    "reply": profile.record_answer(conn, employee_id, text, lang=lang),
                    "employee_id": employee_id,
                    "profile": True,
                }
        thread = intake.open_thread(conn, employee_id) if personal else None
        if thread is not None and thread[1]:
            intake.close_thread(thread[0])
            thread = None
        # A reply to a pending question is matched before any open volunteered
        # thread: the thread must never swallow an answer or a skip (F4).
        matched: tuple[str, str] | None = None
        if candidates and not intake.is_join_request(text) and not intake.is_done(command):
            if command in _SKIP_COMMANDS:
                index, kind = 0, "dont_know"
            else:
                index = match_reply([q for _, q in candidates], text)
                kind = "other" if index is None else classify_reply(candidates[index][1], text)
            if kind == "dont_know":
                question_id = candidates[index][0]
                conn.execute(
                    "UPDATE cmap.open_question SET state = 'open', target_employee_id = NULL, "
                    "asked_at = NULL, skipped_by = array_append(skipped_by, %s::uuid) "
                    "WHERE id = %s",
                    (employee_id, question_id),
                )
                conn.commit()
                return {
                    "handled": True,
                    "reply": strings(lang).reply_skipped,
                    "employee_id": employee_id,
                    "question_id": question_id,
                }
            if kind == "answer":
                matched = candidates[index]
        if matched is None:
            if thread is not None:
                thread_id = thread[0]
                pinned = intake.thread_lang(conn, thread_id)
                thread_lang = pinned or lang
                if intake.is_join_request(text):
                    return {"handled": False, "reply": None, "employee_id": employee_id}
                if intake.is_done(command):
                    source_id = intake.close_thread(thread_id)
                    return {
                        "handled": True,
                        "reply": strings(thread_lang).reply_done,
                        "employee_id": employee_id,
                        "intake_id": thread_id,
                        "source_id": source_id,
                    }
                intake.append_turn(conn, thread_id, employee_name, text)
                return {
                    "handled": True,
                    "reply": _thread_reply(conn, thread_id, thread_lang),
                    "employee_id": employee_id,
                    "intake_id": thread_id,
                }
            return _volunteer(
                conn, employee_id, employee_name, text, command, personal, lang, locale
            )
        question_id, question = matched
    answer = text.strip()
    day_date = datetime.now(EASTERN).date()
    source = ingest_bytes(
        kind="transcript",
        title=f"Interview answer — {employee_name} — {day_date.isoformat()}",
        original_filename=f"interview-answer-{question_id}.txt",
        data=(profile.transcript_header(employee_id, employee_name)
              + _transcript_text(question, employee_name, answer)).encode("utf-8"),
        department_hint=profile.department_hint(employee_id),
        effective_date=day_date,
        date_origin=ORIGIN_INTERVIEW,
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
        "reply": strings(lang).reply_answered,
        "employee_id": employee_id,
        "question_id": question_id,
        "source_id": source["id"],
    }
