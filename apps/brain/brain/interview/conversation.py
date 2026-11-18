"""Serial interview conversations (issue #604): all conversation and turn SQL.

One conversation per employee is open at a time (the partial unique index in
``034_interview_conversation.sql``). Each Oracle message is an ``out`` turn
carrying its Teams message id; each employee message is an ``in`` turn. An
answer is ingested as a source and processed in the interview fast lane;
only when its ``relations`` step has finished (or the chain failed for good)
is ``interview_reply`` queued to compose the next message.

This module imports nothing heavier than the database helpers, because the
extraction steps call :func:`source_chain_ended`.
"""

from __future__ import annotations

import logging
from typing import Any

from psycopg import errors as pg_errors
from psycopg.types.json import Json

from brain.db import INTERVIEW_LANE, get_pool, lane_for

logger = logging.getLogger(__name__)

STUCK_SENDING_MINUTES = 5
STUCK_PROCESSING_MINUTES = 15
DEFAULT_ANSWER_WAIT_HOURS = 24

_TURN_COLUMNS = (
    "t.id::text, t.conversation_id::text, t.seq, t.direction, t.kind, t.text, "
    "t.teams_activity_id, t.quoted_activity_id, t.question_id::text, t.source_id::text, "
    "t.in_reply_to::text, t.processed, t.meta, t.created_at"
)
_TURN_KEYS = (
    "id",
    "conversation_id",
    "seq",
    "direction",
    "kind",
    "text",
    "teams_activity_id",
    "quoted_activity_id",
    "question_id",
    "source_id",
    "in_reply_to",
    "processed",
    "meta",
    "created_at",
)
_CONV_COLUMNS = (
    "id::text, employee_id::text, state, opened_at, last_activity_at, closed_at, "
    "close_reason, exchanges, lang, processing_since"
)
_CONV_KEYS = (
    "id",
    "employee_id",
    "state",
    "opened_at",
    "last_activity_at",
    "closed_at",
    "close_reason",
    "exchanges",
    "lang",
    "processing_since",
)


def _turn(row: Any) -> dict[str, Any]:
    turn = dict(zip(_TURN_KEYS, row, strict=True))
    turn["meta"] = dict(turn["meta"] or {})
    return turn


def _conv(row: Any) -> dict[str, Any]:
    return dict(zip(_CONV_KEYS, row, strict=True))


def mark_sent(conn: Any, turn_id: str, activity_id: str | None) -> None:
    """The message for a ``sending`` turn went out."""
    conn.execute(
        "UPDATE cmap.interview_turn SET send_state = 'sent', teams_activity_id = %s "
        "WHERE id = %s",
        (activity_id, turn_id),
    )
    conn.commit()


def mark_send_failed(conn: Any, turn_id: str, error: str) -> None:
    """A send raised: never resent automatically (a duplicate is worse than late)."""
    conn.execute(
        "UPDATE cmap.interview_turn SET send_state = 'failed', "
        "meta = meta || jsonb_build_object('send_error', %s::text) WHERE id = %s",
        (error[:500], turn_id),
    )
    conn.commit()


def answer_wait_hours(conn: Any) -> int:
    """How long an unanswered question waits before the sitting closes."""
    row = conn.execute(
        "SELECT answer_wait_hours FROM cmap.interview_setting WHERE id"
    ).fetchone()
    return int(row[0]) if row else DEFAULT_ANSWER_WAIT_HOURS


def current_conversation(conn: Any, employee_id: str) -> dict[str, Any] | None:
    """The employee's conversation that is not closed, if any."""
    row = conn.execute(
        f"SELECT {_CONV_COLUMNS} FROM cmap.interview_conversation "
        "WHERE employee_id = %s AND state <> 'closed'",
        (employee_id,),
    ).fetchone()
    return _conv(row) if row else None


def get_conversation(conn: Any, conversation_id: str) -> dict[str, Any] | None:
    """One conversation by id."""
    row = conn.execute(
        f"SELECT {_CONV_COLUMNS} FROM cmap.interview_conversation WHERE id = %s",
        (conversation_id,),
    ).fetchone()
    return _conv(row) if row else None


def open_conversation(conn: Any, employee_id: str, lang: str | None) -> str | None:
    """Open a conversation; ``None`` when one is already open (the serial rule)."""
    try:
        row = conn.execute(
            "INSERT INTO cmap.interview_conversation (employee_id, lang) VALUES (%s, %s) "
            "RETURNING id::text",
            (employee_id, lang),
        ).fetchone()
    except pg_errors.UniqueViolation:
        conn.rollback()
        return None
    conn.commit()
    return str(row[0])


def add_turn(
    conn: Any,
    conversation_id: str,
    direction: str,
    kind: str,
    text: str,
    *,
    teams_activity_id: str | None = None,
    quoted_activity_id: str | None = None,
    question_id: str | None = None,
    source_id: str | None = None,
    in_reply_to: str | None = None,
    meta: dict[str, Any] | None = None,
    send_key: str | None = None,
    send_state: str | None = None,
) -> str | None:
    """Append one turn; ``None`` when this Teams message (or send key) was already stored."""
    try:
        conn.execute(
            "SELECT 1 FROM cmap.interview_conversation WHERE id = %s FOR UPDATE",
            (conversation_id,),
        )
        row = conn.execute(
            "INSERT INTO cmap.interview_turn (conversation_id, seq, direction, kind, text, "
            "teams_activity_id, quoted_activity_id, question_id, source_id, in_reply_to, meta, "
            "send_key, send_state) "
            "SELECT %s, COALESCE(max(seq), 0) + 1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s "
            "FROM cmap.interview_turn WHERE conversation_id = %s RETURNING id::text",
            (
                conversation_id,
                direction,
                kind,
                text,
                teams_activity_id,
                quoted_activity_id,
                question_id,
                source_id,
                in_reply_to,
                Json(meta or {}),
                send_key,
                send_state,
                conversation_id,
            ),
        ).fetchone()
        conn.execute(
            "UPDATE cmap.interview_conversation SET last_activity_at = now() WHERE id = %s",
            (conversation_id,),
        )
    except pg_errors.UniqueViolation:
        conn.rollback()
        return None
    conn.commit()
    return str(row[0])


def turns(conn: Any, conversation_id: str) -> list[dict[str, Any]]:
    """Every turn of a conversation, oldest first."""
    rows = conn.execute(
        f"SELECT {_TURN_COLUMNS} FROM cmap.interview_turn t "
        "WHERE t.conversation_id = %s ORDER BY t.seq",
        (conversation_id,),
    ).fetchall()
    return [_turn(row) for row in rows]


def in_activity_seen(conn: Any, activity_id: str | None) -> bool:
    """True when this Teams message was already stored (Teams redelivery)."""
    if not activity_id:
        return False
    row = conn.execute(
        "SELECT 1 FROM cmap.interview_turn WHERE teams_activity_id = %s AND direction = 'in'",
        (activity_id,),
    ).fetchone()
    return row is not None


def out_turn_by_activity(
    conn: Any, activity_id: str, employee_id: str
) -> dict[str, Any] | None:
    """The Oracle's message with this Teams id, only if it was sent to this employee.

    A quoted id that belongs to another employee's chat is ignored and logged
    (plan 9a A1/A3): ids arriving from Teams are untrusted.
    """
    row = conn.execute(
        f"SELECT {_TURN_COLUMNS}, c.employee_id::text FROM cmap.interview_turn t "
        "JOIN cmap.interview_conversation c ON c.id = t.conversation_id "
        "WHERE t.teams_activity_id = %s AND t.direction = 'out' "
        "ORDER BY t.created_at DESC LIMIT 1",
        (activity_id,),
    ).fetchone()
    if row is None:
        return None
    if str(row[-1]) != employee_id:
        logger.warning("quoted message id belongs to another employee; ignored")
        return None
    return _turn(row[:-1])


def last_out_turn(conn: Any, conversation_id: str) -> dict[str, Any] | None:
    """The conversation's latest Oracle message."""
    row = conn.execute(
        f"SELECT {_TURN_COLUMNS} FROM cmap.interview_turn t "
        "WHERE t.conversation_id = %s AND t.direction = 'out' ORDER BY t.seq DESC LIMIT 1",
        (conversation_id,),
    ).fetchone()
    return _turn(row) if row else None


def question_text(conn: Any, question_id: str | None) -> str:
    """The stored text of an open question."""
    if not question_id:
        return ""
    row = conn.execute(
        "SELECT question FROM cmap.open_question WHERE id = %s", (question_id,)
    ).fetchone()
    return str(row[0]) if row else ""


def set_state(conn: Any, conversation_id: str, state: str) -> None:
    """Move a conversation between awaiting_answer and processing."""
    conn.execute(
        "UPDATE cmap.interview_conversation SET state = %s, last_activity_at = now(), "
        "processing_since = CASE WHEN %s = 'processing' THEN now() ELSE NULL END "
        "WHERE id = %s AND state <> 'closed'",
        (state, state, conversation_id),
    )
    conn.commit()


def release_question(
    conn: Any, question_id: str, employee_id: str | None, skipped: bool
) -> None:
    """Return an asked question to ``open`` so routing can send it again."""
    conn.execute(
        "UPDATE cmap.open_question SET state = 'open', asked_at = NULL, "
        "target_employee_id = NULL, "
        "skipped_by = CASE WHEN %s AND %s::uuid IS NOT NULL "
        "  THEN array_append(skipped_by, %s::uuid) ELSE skipped_by END "
        "WHERE id = %s AND state = 'asked'",
        (skipped, employee_id, employee_id, question_id),
    )
    conn.commit()


def close_conversation(conn: Any, conversation_id: str, reason: str) -> None:
    """Close a conversation; a question still in flight goes back to ``open``."""
    conv = get_conversation(conn, conversation_id)
    if conv is None or conv["state"] == "closed":
        return
    last = last_out_turn(conn, conversation_id)
    conn.execute(
        "UPDATE cmap.interview_conversation SET state = 'closed', closed_at = now(), "
        "close_reason = %s, processing_since = NULL WHERE id = %s",
        (reason, conversation_id),
    )
    conn.commit()
    if last is not None and last["question_id"] and reason in {"no_answer", "stopped"}:
        release_question(conn, last["question_id"], None, skipped=False)


def _queue_reply(conn: Any, conversation_id: str, payload: dict[str, Any]) -> bool:
    """Queue one ``interview_reply`` unless one is already waiting."""
    row = conn.execute(
        "INSERT INTO cmap.job (kind, payload, lane) SELECT 'interview_reply', %s, %s "
        "WHERE NOT EXISTS (SELECT 1 FROM cmap.job WHERE kind = 'interview_reply' "
        "AND state = 'queued' AND payload->>'conversation_id' = %s) RETURNING id",
        (Json(payload), lane_for("interview_reply", INTERVIEW_LANE), conversation_id),
    ).fetchone()
    conn.commit()
    return row is not None


def queue_reply(conversation_id: str, **extra: Any) -> bool:
    """Queue the reply composer for a conversation in the interview lane."""
    with get_pool().connection() as conn:
        return _queue_reply(
            conn, conversation_id, {"conversation_id": conversation_id, **extra}
        )


def awaits_reply(source_id: str) -> bool:
    """True when this source is the answer of a conversation in processing."""
    with get_pool().connection() as conn:
        return (
            conn.execute(
                "SELECT 1 FROM cmap.interview_turn t "
                "JOIN cmap.interview_conversation c ON c.id = t.conversation_id "
                "WHERE t.source_id = %s AND c.state = 'processing' LIMIT 1",
                (source_id,),
            ).fetchone()
            is not None
        )


def source_chain_ended(
    source_id: str, *, failed: bool, resolve: str | None = None
) -> bool:
    """The answer's processing finished (or failed for good): queue the reply.

    Called at the end of ``relations`` and from the worker's failure path.
    Does nothing for sources that are not a conversation's answer.
    """
    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT c.id::text FROM cmap.interview_turn t "
            "JOIN cmap.interview_conversation c ON c.id = t.conversation_id "
            "WHERE t.source_id = %s AND c.state = 'processing' LIMIT 1",
            (source_id,),
        ).fetchone()
        if row is None:
            return False
        conversation_id = str(row[0])
        meta: dict[str, Any] = {"processing_failed": True} if failed else {}
        if resolve is not None:
            meta["resolve"] = resolve
        conn.execute(
            "UPDATE cmap.interview_turn SET processed = true, "
            "meta = meta || %s::jsonb WHERE source_id = %s",
            (Json(meta), source_id),
        )
        conn.commit()
        payload: dict[str, Any] = {
            "conversation_id": conversation_id,
            "source_id": source_id,
        }
        if failed:
            payload["processing_failed"] = True
        return _queue_reply(conn, conversation_id, payload)


def sweep_conversations() -> dict[str, int]:
    """Close idle conversations and heal ones stuck in processing (plan Step 8)."""
    counts = {"closed_idle": 0, "healed": 0, "send_failed": 0}
    with get_pool().connection() as conn:
        # A send left 'sending' (the process died mid-send) is marked failed for
        # a human and never resent: a duplicate message is worse than a late one.
        lost = conn.execute(
            "UPDATE cmap.interview_turn SET send_state = 'failed', "
            'meta = meta || \'{"send_error": "stuck in sending"}\'::jsonb '
            "WHERE send_state = 'sending' AND created_at < now() - make_interval(mins => %s) "
            "RETURNING id::text, conversation_id::text",
            (STUCK_SENDING_MINUTES,),
        ).fetchall()
        conn.commit()
        for turn_id, conversation_id in lost:
            logger.error("interview send %s stuck in sending; marked failed", turn_id)
            close_conversation(conn, str(conversation_id), "send_failed")
            counts["send_failed"] += 1
        wait_hours = answer_wait_hours(conn)
        idle = conn.execute(
            "SELECT id::text FROM cmap.interview_conversation WHERE state = 'awaiting_answer' "
            "AND last_activity_at < now() - make_interval(hours => %s)",
            (wait_hours,),
        ).fetchall()
        for (conversation_id,) in idle:
            close_conversation(conn, str(conversation_id), "no_answer")
            counts["closed_idle"] += 1
        stuck = conn.execute(
            "SELECT c.id::text FROM cmap.interview_conversation c WHERE c.state = 'processing' "
            "AND COALESCE(c.processing_since, c.last_activity_at) "
            "  < now() - make_interval(mins => %s) "
            "AND NOT EXISTS (SELECT 1 FROM cmap.job j WHERE j.lane = %s "
            "  AND j.state IN ('queued','running'))",
            (STUCK_PROCESSING_MINUTES, INTERVIEW_LANE),
        ).fetchall()
        for (conversation_id,) in stuck:
            conn.execute(
                "UPDATE cmap.interview_conversation SET processing_since = now() WHERE id = %s",
                (conversation_id,),
            )
            if _queue_reply(
                conn,
                str(conversation_id),
                {
                    "conversation_id": str(conversation_id),
                    "healed": True,
                },
            ):
                counts["healed"] += 1
    if any(counts.values()):
        logger.info("interview conversation sweep: %s", counts)
    return counts


def sat_today(conn: Any) -> set[str]:
    """Employees who already had a sitting today (New York day) or have one open."""
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT DISTINCT employee_id FROM cmap.interview_conversation "
            "WHERE state <> 'closed' OR (opened_at AT TIME ZONE 'America/New_York')::date = "
            "(now() AT TIME ZONE 'America/New_York')::date"
        ).fetchall()
    }
