"""Knowledge an employee volunteers to the Teams bot (build-out phase 1).

When no interview question is pending, a message of real content opens an
intake thread for that employee. Later messages extend the thread; it closes
after ``SILENCE_MINUTES`` of quiet or when the employee says "done", and the
whole thread is ingested as one ``cmap.source`` transcript that flows through
the normal read pipeline. Short greetings get a one-line intro instead.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

import httpx
from psycopg import OperationalError
from psycopg.types.json import Json

from brain import storage as storage_mod
from brain.api.sources import ingest_bytes
from brain.db import get_pool
from brain.interview import profile
from brain.text_util import count_units

logger = logging.getLogger(__name__)

SILENCE_MINUTES = 20
MIN_CONTRIBUTION_WORDS = 12
MAX_ATTEMPTS = 5

REPLY_INTRO = (
    "Hi, I'm The Oracle. I learn how POP Creations works from the people who do "
    "the work. Tell me about something you handle (who you get it from, what "
    "you do, who you pass it to) and I'll add it to the Company Map."
)
REPLY_INTRO_SHORT = (
    "Hi, I'm The Oracle. I learn how POP Creations works from the people who do "
    "the work and add it to the Company Map."
)
REPLY_ACK = "Got it — keep going, or say done."
REPLY_DONE = "Thanks, that's recorded. Message me any time you have more."
REPLY_NOTHING_OPEN = "There is nothing open to finish. Tell me how something works and I'll record it."

_GREETINGS = {
    "hi", "hello", "hey", "hiya", "yo", "hi there", "hello there", "hey there",
    "good morning", "good afternoon", "good evening", "morning", "howdy",
    "hi oracle", "hello oracle", "hey oracle", "hi the oracle", "hello the oracle",
    "你好", "您好", "在吗", "你在吗", "你好呀", "嗨", "哈喽",
    "你好 oracle", "oracle 你好",
}
_DONE = {
    "done", "that s all", "thats all", "that is all", "finished", "end",
    "i m done", "im done",
    "完成", "完成了", "好了", "说完了", "结束", "就这些", "做完了", "就这样",
}
_JOIN = re.compile(r"^(?:join\b|listen\b|start\b|bring oracle in\b|加入|拉我进|开始)", re.IGNORECASE)
_TEAMS_URL = re.compile(r"https://teams\.microsoft\.com/", re.IGNORECASE)


def is_join_request(text: str) -> bool:
    """Same rule as the Next.js bot route: those go to the meeting helper."""
    stripped = text.strip()
    return bool(_JOIN.match(stripped) or _TEAMS_URL.search(stripped))


def is_greeting(command: str) -> bool:
    """``command`` is the lower-cased, punctuation-free message."""
    return command in _GREETINGS


def is_done(command: str) -> bool:
    return command in _DONE


def word_count(text: str) -> int:
    return count_units(text)


def is_personal(conversation_ref: dict[str, Any] | None) -> bool:
    """Only 1:1 chats feed intake; group/meeting chats keep the join helper."""
    if not conversation_ref:
        return True
    kind = (conversation_ref.get("conversation") or {}).get("conversationType")
    return kind in (None, "personal")


def _turn(speaker: str, text: str) -> dict[str, str]:
    return {"speaker": speaker, "text": " ".join(text.split()), "at": datetime.now().astimezone().isoformat()}


def open_thread(conn: Any, employee_id: str) -> tuple[str, bool] | None:
    """Return ``(thread_id, stale)`` for the employee's open thread, if any."""
    row = conn.execute(
        "SELECT id::text, last_at < now() - make_interval(mins => %s) FROM cmap.teams_intake "
        "WHERE employee_id = %s AND state = 'open'",
        (SILENCE_MINUTES, employee_id),
    ).fetchone()
    if row is None:
        return None
    return str(row[0]), bool(row[1])


def start_thread(conn: Any, employee_id: str, speaker: str, text: str) -> str:
    row = conn.execute(
        "INSERT INTO cmap.teams_intake (employee_id, turns) VALUES (%s, %s) RETURNING id::text",
        (employee_id, Json([_turn(speaker, text)])),
    ).fetchone()
    conn.commit()
    return str(row[0])


def append_turn(conn: Any, thread_id: str, speaker: str, text: str) -> None:
    conn.execute(
        "UPDATE cmap.teams_intake SET turns = turns || %s::jsonb, last_at = now() WHERE id = %s",
        (Json([_turn(speaker, text)]), thread_id),
    )
    conn.commit()


def thread_turns(conn: Any, thread_id: str) -> list[dict[str, Any]]:
    row = conn.execute("SELECT turns FROM cmap.teams_intake WHERE id = %s", (thread_id,)).fetchone()
    return list(row[0] or []) if row else []


def _transcript(turns: list[dict[str, Any]]) -> str:
    lines = []
    for turn in turns:
        speaker = " ".join(str(turn.get("speaker", "")).replace(":", " ").split()) or "Employee"
        text = " ".join(str(turn.get("text", "")).split())
        if text:
            lines.append(f"{speaker}: {text}")
    return "\n".join(lines) + "\n"


def _is_transient(exc: Exception) -> bool:
    """Network, storage and connection failures are worth retrying; bugs are not."""
    return isinstance(
        exc, (httpx.HTTPError, storage_mod.StorageError, OperationalError, OSError)
    )


def close_thread(thread_id: str) -> str | None:
    """Claim, ingest and close one thread; return the new source id.

    The claim (``open``/``failed`` → ``closing``, with ``retry_count`` bumped)
    is atomic so the worker sweep and an inbound "done" never ingest the same
    thread twice. A transient ingest failure leaves the thread ``failed`` with
    ``next_retry_at`` set so the sweep retries it, up to ``MAX_ATTEMPTS``
    attempts with exponential backoff, then leaves it ``failed`` with the last
    error.
    """
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE cmap.teams_intake t SET state = 'closing', retry_count = retry_count + 1 "
            "WHERE id = %s AND (t.state = 'open' OR (t.state = 'failed' "
            "AND t.next_retry_at IS NOT NULL AND t.next_retry_at <= now() "
            "AND t.retry_count < %s)) "
            "RETURNING t.employee_id::text, t.started_at, t.turns, t.retry_count, "
            "(SELECT COALESCE(e.name, e.email) FROM public.employees e WHERE e.id = t.employee_id)",
            (thread_id, MAX_ATTEMPTS),
        ).fetchone()
        conn.commit()
    if row is None:
        return None
    employee_id, started_at, turns, attempts, employee_name = row
    name = str(employee_name or "Employee")
    day = started_at.astimezone().date().isoformat()
    try:
        source = ingest_bytes(
            kind="transcript",
            title=f"Teams contribution — {name} — {day}",
            original_filename=f"teams-contribution-{thread_id}.txt",
            data=(
                profile.transcript_header(employee_id, name) + _transcript(list(turns or []))
            ).encode("utf-8"),
            department_hint=profile.department_hint(employee_id),
            effective_date=None,
            uploaded_by=None,
        )
    except Exception as exc:
        retrying = _is_transient(exc) and attempts < MAX_ATTEMPTS
        delay = min(2 ** (attempts - 1), 8) if retrying else 0
        logger.warning(
            "teams intake %s ingest failed on attempt %s/%s (%s): %s",
            thread_id, attempts, MAX_ATTEMPTS,
            "will retry" if retrying else "giving up", exc,
        )
        with pool.connection() as conn:
            conn.execute(
                "UPDATE cmap.teams_intake SET state = 'failed', error = %s, "
                "closed_at = CASE WHEN %s THEN NULL ELSE now() END, "
                "next_retry_at = CASE WHEN %s THEN now() + make_interval(mins => %s) ELSE NULL END "
                "WHERE id = %s",
                (str(exc)[:500], retrying, retrying, delay, thread_id),
            )
            conn.commit()
        return None
    with pool.connection() as conn:
        conn.execute(
            "UPDATE cmap.teams_intake SET state = 'closed', source_id = %s, "
            "closed_at = now(), error = NULL, next_retry_at = NULL WHERE id = %s",
            (source["id"], thread_id),
        )
        conn.commit()
    logger.info("teams intake %s for %s became source %s", thread_id, employee_id, source["id"])
    return str(source["id"])


def close_stale_threads() -> list[str]:
    """Close every thread quiet for ``SILENCE_MINUTES``; called by the worker loop.

    Also picks up ``failed`` threads whose retry backoff has elapsed.
    """
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT id::text FROM cmap.teams_intake WHERE "
            "(state = 'open' AND last_at < now() - make_interval(mins => %s)) "
            "OR (state = 'failed' AND next_retry_at IS NOT NULL AND next_retry_at <= now())",
            (SILENCE_MINUTES,),
        ).fetchall()
    closed = []
    for (thread_id,) in rows:
        source_id = close_thread(str(thread_id))
        if source_id:
            closed.append(source_id)
    return closed
