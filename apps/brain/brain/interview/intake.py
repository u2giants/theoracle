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

from psycopg.types.json import Json

from brain.api.sources import ingest_bytes
from brain.db import get_pool

logger = logging.getLogger(__name__)

SILENCE_MINUTES = 20
MIN_CONTRIBUTION_WORDS = 12

REPLY_INTRO = (
    "Hi, I'm The Oracle. I learn how POP Creations works from the people who do "
    "the work. Tell me about something you handle (who you get it from, what "
    "you do, who you pass it to) and I'll add it to the Company Map."
)
REPLY_ACK = "Got it — keep going, or say done."
REPLY_DONE = "Thanks, that's recorded. Message me any time you have more."
REPLY_NOTHING_OPEN = "There is nothing open to finish. Tell me how something works and I'll record it."

_GREETINGS = {
    "hi", "hello", "hey", "hiya", "yo", "hi there", "hello there", "hey there",
    "good morning", "good afternoon", "good evening", "morning", "howdy",
    "hi oracle", "hello oracle", "hey oracle", "hi the oracle", "hello the oracle",
}
_DONE = {"done", "that s all", "thats all", "that is all", "finished", "end", "i m done", "im done"}
_JOIN = re.compile(r"^(join|listen|start|bring oracle in)\b", re.IGNORECASE)
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
    return len(text.split())


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


def _transcript(turns: list[dict[str, Any]]) -> str:
    lines = []
    for turn in turns:
        speaker = " ".join(str(turn.get("speaker", "")).replace(":", " ").split()) or "Employee"
        text = " ".join(str(turn.get("text", "")).split())
        if text:
            lines.append(f"{speaker}: {text}")
    return "\n".join(lines) + "\n"


def close_thread(thread_id: str) -> str | None:
    """Claim, ingest and close one thread; return the new source id.

    The claim (``open`` → ``closing``) is atomic so the worker sweep and an
    inbound "done" never ingest the same thread twice.
    """
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE cmap.teams_intake t SET state = 'closing' WHERE id = %s AND state = 'open' "
            "RETURNING t.employee_id::text, t.started_at, t.turns, "
            "(SELECT COALESCE(e.name, e.email) FROM public.employees e WHERE e.id = t.employee_id)",
            (thread_id,),
        ).fetchone()
        conn.commit()
    if row is None:
        return None
    employee_id, started_at, turns, employee_name = row
    name = str(employee_name or "Employee")
    day = started_at.astimezone().date().isoformat()
    try:
        source = ingest_bytes(
            kind="transcript",
            title=f"Teams contribution — {name} — {day}",
            original_filename=f"teams-contribution-{thread_id}.txt",
            data=_transcript(list(turns or [])).encode("utf-8"),
            department_hint=None,
            effective_date=None,
            uploaded_by=None,
        )
    except Exception as exc:
        logger.warning("teams intake %s ingest failed: %s", thread_id, exc)
        with pool.connection() as conn:
            conn.execute(
                "UPDATE cmap.teams_intake SET state = 'failed', error = %s, closed_at = now() WHERE id = %s",
                (str(exc)[:500], thread_id),
            )
            conn.commit()
        return None
    with pool.connection() as conn:
        conn.execute(
            "UPDATE cmap.teams_intake SET state = 'closed', source_id = %s, closed_at = now() WHERE id = %s",
            (source["id"], thread_id),
        )
        conn.commit()
    logger.info("teams intake %s for %s became source %s", thread_id, employee_id, source["id"])
    return str(source["id"])


def close_stale_threads() -> list[str]:
    """Close every thread quiet for ``SILENCE_MINUTES``; called by the worker loop."""
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT id::text FROM cmap.teams_intake WHERE state = 'open' "
            "AND last_at < now() - make_interval(mins => %s)",
            (SILENCE_MINUTES,),
        ).fetchall()
    closed = []
    for (thread_id,) in rows:
        source_id = close_thread(str(thread_id))
        if source_id:
            closed.append(source_id)
    return closed
