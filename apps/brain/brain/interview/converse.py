"""Compose the next interview message after an answer was processed (issue #604).

``interview_reply`` runs in the interview lane once the employee's answer
went through read_source -> classify_extract -> relations (or failed for
good). It writes exactly one next message: a reflection of what the employee
said plus a follow-up, the next queued question, or a close. Code, not the
model, enforces the rules: no invented names, a follow-up cap, next questions
only from the employee's own queue, and a sitting length.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from brain.answer.answer import parse_model_json
from brain.config import Settings, get_settings
from brain.db import INTERVIEW_LANE, current_lane, get_pool
from brain.interview import conversation as conv_mod
from brain.interview import followup, profile
from brain.interview.strings import strings
from brain.llm import message_content, post_chat_with_rescue
from brain.read.dates import ORIGIN_INTERVIEW
from brain.seats import stage_model

logger = logging.getLogger(__name__)

EASTERN = ZoneInfo("America/New_York")
ORACLE_SPEAKER = "The Oracle"
CONVERSE_PROMPT = (
    Path(__file__).resolve().parents[1] / "prompts" / "interview_converse.md"
)
CLARIFY_PROMPT = (
    Path(__file__).resolve().parents[1] / "prompts" / "interview_clarify.md"
)
CONVERSE_TIMEOUT_SECONDS = 45.0
CONVERSE_MAX_TOKENS = 500
MAX_FOLLOWUPS = followup.MAX_FOLLOWUPS
MAX_FACTS = 20
HELD_KIND = "held"
ACTIONS = ("followup", "next_question", "close")


# ---------------------------------------------------------------- ingest


def transcript_text(question: str, employee_name: str, answer: str) -> str:
    """The Q and A as two speaker turns the transcript reader understands."""
    question_line = " ".join(question.split())
    answer_line = " ".join(answer.split())
    speaker = " ".join(employee_name.replace(":", " ").split())
    return f"{ORACLE_SPEAKER}: {question_line}\n{speaker}: {answer_line}\n"


def ingest_answer(
    conversation_id: str,
    employee_id: str,
    employee_name: str,
    question: str,
    answer: str,
    turn_ids: list[str],
    question_id: str | None,
) -> str:
    """Store the answer as a source processed in the interview lane.

    The turns get the source id so the chain's end finds this conversation.
    A duplicate (same bytes already stored) has no chain to wait for, so the
    reply is queued straight away.
    """
    from brain.api.sources import ingest_bytes  # noqa: PLC0415 - heavy import

    day = datetime.now(EASTERN).date()
    token = current_lane.set(INTERVIEW_LANE)
    try:
        source = ingest_bytes(
            kind="transcript",
            title=f"Interview answer — {employee_name} — {day.isoformat()}",
            original_filename=f"interview-answer-{turn_ids[0]}.txt",
            data=(
                profile.transcript_header(employee_id, employee_name)
                + transcript_text(question, employee_name, answer)
            ).encode("utf-8"),
            department_hint=profile.department_hint(employee_id),
            effective_date=day,
            date_origin=ORIGIN_INTERVIEW,
            uploaded_by=None,
        )
    finally:
        current_lane.reset(token)
    source_id = str(source["id"])
    with get_pool().connection() as conn:
        conn.execute(
            "UPDATE cmap.interview_turn SET source_id = %s, kind = CASE WHEN kind = %s "
            "THEN 'answer' ELSE kind END WHERE id = ANY(%s::uuid[])",
            (source_id, HELD_KIND, turn_ids),
        )
        if question_id:
            conn.execute(
                "UPDATE cmap.open_question SET state = 'answered', answer = %s, "
                "answered_at = now(), answer_source_id = %s WHERE id = %s",
                (answer, source_id, question_id),
            )
        conn.commit()
        conv_mod.set_state(conn, conversation_id, "processing")
        if source.get("duplicate"):
            conn.execute(
                "UPDATE cmap.interview_turn SET processed = true WHERE id = ANY(%s::uuid[])",
                (turn_ids,),
            )
            conn.commit()
            conv_mod._queue_reply(
                conn, conversation_id, {"conversation_id": conversation_id}
            )
    return source_id


# ---------------------------------------------------------------- helpers


def _employee(conn: Any, employee_id: str) -> tuple[str, str]:
    row = conn.execute(
        "SELECT COALESCE(name, email, ''), COALESCE(locale, '') "
        "FROM public.employees WHERE id = %s",
        (employee_id,),
    ).fetchone()
    return (str(row[0]), str(row[1])) if row else ("", "")


def extracted_facts(conn: Any, source_ids: list[str]) -> list[str]:
    """What the brain extracted from these sources: things and links, plain lines."""
    if not source_ids:
        return []
    lines = [
        f"{name} ({etype})"
        for name, etype in conn.execute(
            "SELECT DISTINCT m.surface_name, m.entity_type FROM cmap.mention m "
            "JOIN cmap.chunk c ON c.id = m.chunk_id WHERE c.source_id = ANY(%s::uuid[]) "
            "LIMIT %s",
            (source_ids, MAX_FACTS),
        ).fetchall()
    ]
    lines += [
        f"{a} {rel} {b}: {desc}"
        for a, rel, b, desc in conn.execute(
            "SELECT fm.surface_name, r.rel_type, tm.surface_name, r.description "
            "FROM cmap.relation r JOIN cmap.chunk c ON c.id = r.chunk_id "
            "JOIN cmap.mention fm ON fm.id = r.from_mention_id "
            "JOIN cmap.mention tm ON tm.id = r.to_mention_id "
            "WHERE c.source_id = ANY(%s::uuid[]) LIMIT %s",
            (source_ids, MAX_FACTS),
        ).fetchall()
    ]
    return lines


def _call(
    prompt: str, settings: Settings, max_tokens: int, label: str
) -> dict[str, Any]:
    model = stage_model(settings, "converse")
    if not model or not settings.openrouter_api_key:
        return {}
    body = post_chat_with_rescue(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.3,
        },
        settings=settings,
        timeout=CONVERSE_TIMEOUT_SECONDS,
        error_cls=RuntimeError,
        label=label,
    )
    return parse_model_json(message_content(body), ())


def _lang_name(lang: str) -> str:
    return "Simplified Chinese" if lang == "zh-CN" else "English"


def _transcript(tlist: list[dict[str, Any]], employee_name: str) -> str:
    return "\n".join(
        f"{ORACLE_SPEAKER if t['direction'] == 'out' else employee_name}: "
        f"{' '.join(str(t['text']).split())}"
        for t in tlist
    )


# ---------------------------------------------------------------- composer


def compose_next(
    conn: Any,
    conv: dict[str, Any],
    tlist: list[dict[str, Any]],
    queue: list[tuple[str, str, str]],
    settings: Settings,
) -> dict[str, Any]:
    """The next message after an answer: ``{action, text, question_id, path}``.

    ``queue`` holds ``(question_id, stored_text, localized_text)``. The model
    proposes; code checks names, the follow-up cap and the queue, and falls
    back to a fixed string when the model fails twice.
    """
    lang = conv["lang"] or "en"
    s = strings(lang)
    employee_name, _ = _employee(conn, conv["employee_id"])
    employee_name = employee_name or "Employee"
    exchanges_allowed, _ = conv_mod.sitting_settings(conn)
    exchanges_used = int(conv["exchanges"] or 0)
    followups_used = sum(
        1
        for t in tlist
        if t["direction"] == "out"
        and t["kind"] == "followup"
        and t["seq"]
        > max(
            (
                x["seq"]
                for x in tlist
                if x["direction"] == "out" and x["kind"] == "question"
            ),
            default=0,
        )
    )
    must_close = exchanges_used + 1 >= exchanges_allowed
    if must_close:
        return {
            "action": "close",
            "text": s.close,
            "question_id": None,
            "path": "limit",
        }
    employee_text = " ".join(str(t["text"]) for t in tlist if t["direction"] == "in")
    source_ids = sorted({t["source_id"] for t in tlist if t["source_id"]})
    facts = extracted_facts(conn, source_ids)
    context = followup.map_context(conn, employee_text)
    prompt = (
        CONVERSE_PROMPT.read_text(encoding="utf-8")
        .replace("{{language}}", _lang_name(lang))
        .replace("{{employee}}", employee_name)
        .replace("{{exchanges_used}}", str(exchanges_used))
        .replace("{{exchanges_allowed}}", str(exchanges_allowed))
        .replace("{{followups_used}}", str(followups_used))
        .replace("{{followups_allowed}}", str(MAX_FOLLOWUPS))
        .replace("{{conversation}}", _transcript(tlist, employee_name))
        .replace("{{extracted}}", "\n".join(facts) or "(nothing extracted)")
        .replace("{{map_context}}", "\n".join(context) or "(nothing)")
        .replace(
            "{{queue}}",
            "\n".join(f"{i}. {loc}" for i, (_, _, loc) in enumerate(queue, 1))
            or "(none)",
        )
    )
    allowed_names = f"{employee_text}\n{employee_name}"
    for attempt, max_tokens in enumerate(
        (CONVERSE_MAX_TOKENS, CONVERSE_MAX_TOKENS * 2)
    ):
        try:
            out = _call(prompt, settings, max_tokens, "interview converse")
        except Exception as exc:  # noqa: BLE001 - fall back to a fixed message
            logger.warning("interview converse call failed: %s", exc)
            out = {}
        checked = _check(out, queue, allowed_names, followups_used)
        if checked is not None:
            checked["path"] = "model" if attempt == 0 else "model_retry"
            return checked
    if queue:
        qid, _, loc = queue[0]
        return {
            "action": "next_question",
            "text": s.next_question.format(question=loc),
            "question_id": qid,
            "path": "fallback",
        }
    return {"action": "close", "text": s.close, "question_id": None, "path": "fallback"}


def _check(
    out: dict[str, Any],
    queue: list[tuple[str, str, str]],
    allowed_names: str,
    followups_used: int,
) -> dict[str, Any] | None:
    action = str(out.get("action") or "")
    reflect = " ".join(str(out.get("reflect") or "").split())
    text = " ".join(str(out.get("text") or "").split())
    if action not in ACTIONS or not text or len(text) > 600 or len(reflect) > 400:
        return None
    if (
        followup.invented_names(f"{reflect} {text}", allowed_names)
        and action == "followup"
    ):
        logger.info("interview converse dropped: invented names in a follow-up")
        return None
    if followup.invented_names(reflect, allowed_names):
        reflect = ""
    question_id = None
    if action == "followup" and followups_used >= MAX_FOLLOWUPS:
        action = "next_question" if queue else "close"
        text = ""
    if action == "next_question":
        if not queue:
            return None
        try:
            index = int(out.get("question_index") or 1)
        except (TypeError, ValueError):
            index = 1
        if not 1 <= index <= len(queue):
            index = 1
        question_id, _, loc = queue[index - 1]
        if " ".join(loc.split()) not in text:
            text = f"{text} {loc}".strip() if text else loc
    if action == "close" and not text:
        return None
    full = f"{reflect} {text}".strip() if reflect else text
    return {
        "action": action,
        "text": full,
        "question_id": question_id,
        "reflect": reflect,
    }


def _clarified(
    conn: Any, question_id: str | None, lang: str, settings: Settings
) -> str:
    question = conv_mod.question_text(conn, question_id)
    if not question:
        return ""
    row = conn.execute(
        "SELECT COALESCE(why, '') FROM cmap.open_question WHERE id = %s", (question_id,)
    ).fetchone()
    why = str(row[0]) if row else ""
    prompt = (
        CLARIFY_PROMPT.read_text(encoding="utf-8")
        .replace("{{language}}", _lang_name(lang))
        .replace("{{question}}", question)
        .replace("{{why}}", why)
        .replace("{{evidence}}", why)
    )
    try:
        text = " ".join(
            str(
                _call(prompt, settings, 300, "interview clarify").get("text") or ""
            ).split()
        )
    except Exception as exc:  # noqa: BLE001 - restate instead
        logger.warning("interview clarify failed: %s", exc)
        text = ""
    if (
        not text
        or len(text) > 500
        or followup.invented_names(text, f"{question} {why}")
    ):
        return ""
    return text


# ---------------------------------------------------------------- the job


def _queue(
    conn: Any, employee_id: str, lang: str, settings: Settings
) -> list[tuple[str, str, str]]:
    from brain.interview import tick  # noqa: PLC0415 - tick imports inbound

    return [
        (qid, text, tick._localized_question(conn, qid, text, lang, settings))
        for qid, text in tick.queued_for(conn, employee_id, 3, settings)
    ]


def _send(
    conn: Any,
    conv: dict[str, Any],
    kind: str,
    text: str,
    settings: Settings,
    *,
    question_id: str | None = None,
    close_reason: str | None = None,
    meta: dict[str, Any] | None = None,
) -> str | None:
    from brain.interview import tick  # noqa: PLC0415 - tick imports inbound

    activity_id = tick._post_proactive(conv["employee_id"], text, settings)
    turn_id = conv_mod.add_turn(
        conn,
        conv["id"],
        "out",
        kind,
        text,
        teams_activity_id=activity_id,
        question_id=question_id,
        meta=meta or {},
    )
    conn.execute(
        "UPDATE cmap.interview_conversation SET exchanges = exchanges + 1 WHERE id = %s",
        (conv["id"],),
    )
    conn.commit()
    if kind == "question" and question_id:
        tick.mark_asked(conn, conv["employee_id"], question_id)
    if close_reason:
        conv_mod.close_conversation(conn, conv["id"], close_reason)
    else:
        conv_mod.set_state(conn, conv["id"], "awaiting_answer")
    return turn_id


def _held_turns(tlist: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        t
        for t in tlist
        if t["direction"] == "in" and t["kind"] == HELD_KIND and not t["source_id"]
    ]


def run_interview_reply(
    conversation_id: str,
    settings: Settings | None = None,
    processing_failed: bool = False,
) -> dict[str, Any]:
    """Write the one next message of a conversation that is processing."""
    cfg = settings if settings is not None else get_settings()
    with get_pool(cfg).connection() as conn:
        conv = conv_mod.get_conversation(conn, conversation_id)
        if conv is None or conv["state"] != "processing":
            return {"sent": False, "reason": "not_processing"}
        lang = conv["lang"] or "en"
        s = strings(lang)
        tlist = conv_mod.turns(conn, conversation_id)
        last_out = next((t for t in reversed(tlist) if t["direction"] == "out"), None)
        question_id = last_out["question_id"] if last_out else None
        held = _held_turns(tlist)
        if held:
            # Messages sent while the previous answer was being processed are
            # one combined answer to the same question (plan 9a B2).
            name, _ = _employee(conn, conv["employee_id"])
            question = conv_mod.question_text(conn, question_id) or (
                last_out or {}
            ).get("text", "")
            ingest_answer(
                conversation_id,
                conv["employee_id"],
                name or "Employee",
                question,
                "\n".join(t["text"] for t in held),
                [t["id"] for t in held],
                question_id
                if not any(
                    t["source_id"]
                    for t in tlist
                    if t["direction"] == "in" and t["question_id"] == question_id
                )
                else None,
            )
            return {"sent": False, "reason": "ingesting_held"}
        last_in = next((t for t in reversed(tlist) if t["direction"] == "in"), None)
        kind = last_in["kind"] if last_in else "answer"
        since_question = [
            t for t in tlist if last_out is None or t["seq"] > _question_seq(tlist)
        ]
        if kind == "unclear":
            clarified_before = any(
                t["direction"] == "out" and t["kind"] == "clarify"
                for t in since_question
            )
            if clarified_before or not question_id:
                if question_id:
                    conn.execute(
                        "UPDATE cmap.open_question SET state = 'dismissed', "
                        "why = why || ' [dismissed: unclear_to_employee]' WHERE id = %s",
                        (question_id,),
                    )
                    conn.commit()
                return _move_on(
                    conn, conv, tlist, cfg, s.unclear_dropped, "unclear_dropped"
                )
            text = _clarified(conn, question_id, lang, cfg)
            body = (
                s.clarify.format(question=text)
                if text
                else s.restate.format(question=_localized(conn, question_id, lang, cfg))
            )
            _send(
                conn,
                conv,
                "clarify",
                body,
                cfg,
                question_id=question_id,
                meta={"path": "clarify" if text else "restate"},
            )
            return {"sent": True, "action": "clarify"}
        if kind == "dont_know":
            if question_id:
                conv_mod.release_question(
                    conn, question_id, conv["employee_id"], skipped=True
                )
            if last_out and last_out["kind"] == "who_would_know":
                return _move_on(conn, conv, tlist, cfg, "", "dont_know")
            _send(
                conn,
                conv,
                "who_would_know",
                s.who_would_know,
                cfg,
                meta={"path": "fixed", "about_question": question_id},
            )
            return {"sent": True, "action": "who_would_know"}
        if kind == "request":
            loc = _localized(conn, question_id, lang, cfg)
            text = s.capabilities + (
                "\n\n" + s.restate.format(question=loc) if loc else ""
            )
            _send(
                conn,
                conv,
                "request",
                text,
                cfg,
                question_id=question_id,
                meta={"path": "fixed"},
            )
            return {"sent": True, "action": "request"}
        if processing_failed or (last_in and last_in["meta"].get("processing_failed")):
            nxt = _queue(conn, conv["employee_id"], lang, cfg)
            if (
                nxt
                and int(conv["exchanges"] or 0) + 1 < conv_mod.sitting_settings(conn)[0]
            ):
                qid, _, loc = nxt[0]
                text = f"{s.processing_failed} {s.next_question.format(question=loc)}"
                _send(
                    conn,
                    conv,
                    "question",
                    text,
                    cfg,
                    question_id=qid,
                    meta={"path": "processing_failed"},
                )
            else:
                _send(
                    conn,
                    conv,
                    "close",
                    f"{s.processing_failed} {s.close}",
                    cfg,
                    close_reason="exchanges",
                    meta={"path": "processing_failed"},
                )
            return {"sent": True, "action": "processing_failed"}
        if last_in and last_in["meta"].get("done"):
            _send(
                conn,
                conv,
                "close",
                s.close,
                cfg,
                close_reason="done",
                meta={"path": "done"},
            )
            return {"sent": True, "action": "close"}
        queue = _queue(conn, conv["employee_id"], lang, cfg)
        nxt = compose_next(conn, conv, tlist, queue, cfg)
        meta = {"path": nxt["path"], "reflect": nxt.get("reflect", "")}
        if nxt["action"] == "close":
            _send(
                conn,
                conv,
                "close",
                nxt["text"],
                cfg,
                close_reason="exchanges",
                meta=meta,
            )
        elif nxt["action"] == "next_question":
            _send(
                conn,
                conv,
                "question",
                nxt["text"],
                cfg,
                question_id=nxt["question_id"],
                meta=meta,
            )
        else:
            _send(
                conn,
                conv,
                "followup",
                nxt["text"],
                cfg,
                question_id=question_id,
                meta=meta,
            )
        return {"sent": True, "action": nxt["action"], "path": nxt["path"]}


def _question_seq(tlist: list[dict[str, Any]]) -> int:
    return max(
        (
            t["seq"]
            for t in tlist
            if t["direction"] == "out" and t["kind"] == "question"
        ),
        default=0,
    )


def _localized(
    conn: Any, question_id: str | None, lang: str, settings: Settings
) -> str:
    from brain.interview import tick  # noqa: PLC0415 - tick imports inbound

    text = conv_mod.question_text(conn, question_id)
    return (
        tick._localized_question(conn, question_id, text, lang, settings)
        if text
        else ""
    )


def _move_on(
    conn: Any,
    conv: dict[str, Any],
    tlist: list[dict[str, Any]],
    settings: Settings,
    prefix: str,
    path: str,
) -> dict[str, Any]:
    s = strings(conv["lang"] or "en")
    queue = _queue(conn, conv["employee_id"], conv["lang"] or "en", settings)
    limit = int(conv["exchanges"] or 0) + 1 >= conv_mod.sitting_settings(conn)[0]
    if queue and not limit:
        qid, _, loc = queue[0]
        text = f"{prefix} {s.next_question.format(question=loc)}".strip()
        _send(
            conn, conv, "question", text, settings, question_id=qid, meta={"path": path}
        )
        return {"sent": True, "action": "next_question", "path": path}
    _send(
        conn,
        conv,
        "close",
        f"{prefix} {s.close}".strip(),
        settings,
        close_reason="exchanges",
        meta={"path": path},
    )
    return {"sent": True, "action": "close", "path": path}


def handle_interview_reply(job: dict[str, Any]) -> None:
    """Worker handler for ``interview_reply`` jobs (interview lane)."""
    payload = job.get("payload") or {}
    conversation_id = str(payload.get("conversation_id") or "")
    if not conversation_id:
        return
    result = run_interview_reply(
        conversation_id, processing_failed=bool(payload.get("processing_failed"))
    )
    logger.info("interview_reply %s: %s", job.get("id"), result)
