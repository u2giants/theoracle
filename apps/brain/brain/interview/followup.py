"""Follow-up questions inside a Teams intake thread (build-out phase 2).

While an employee's intake thread is open, the conversation model (the
``answer`` seat, which falls back to ``BRAIN_CHAT_MODEL``) asks at most
``MAX_FOLLOWUPS`` short follow-ups grounded in what the Map already knows
about the names the employee mentioned. Every follow-up is kept in the
thread as a turn by "The Oracle", so the ingested transcript stays honest.

A follow-up that names someone or something not in the employee's own words
or the Map context is discarded (the model may not invent names); any model
failure falls back to the plain acknowledgement.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from brain.config import get_settings
from brain.llm import message_content, post_chat_with_rescue
from brain.seats import stage_model

logger = logging.getLogger(__name__)

MAX_FOLLOWUPS = 2
ORACLE_SPEAKER = "The Oracle"
MODEL_TIMEOUT_SECONDS = 8.0
MAX_CONTEXT_ENTITIES = 8
MAX_CONTEXT_RELATIONS = 24

SYSTEM_PROMPT = (
    "You are The Oracle, learning how POP Creations works from an employee in a "
    "Teams chat. Ask ONE short follow-up question (under 25 words) that fills the "
    "biggest gap in what they described: who they get the work from, who they hand "
    "it to, which system records it, how long it takes, or what can go wrong. "
    "Only use names of people, teams, systems or companies that appear in the "
    "employee's messages or in the Map context. Never invent a name. Do not repeat "
    "a question already asked. If nothing useful is left to ask, reply NONE."
)

# Words that start with a capital letter but are not names.
_COMMON = {
    "i", "i'm", "i've", "i'd", "a", "an", "the", "who", "what", "which", "when",
    "where", "why", "how", "do", "does", "did", "is", "are", "was", "were", "can",
    "could", "would", "should", "will", "and", "or", "but", "if", "so", "thanks",
    "thank", "got", "it", "that", "this", "those", "these", "you", "your", "they",
    "their", "them", "he", "she", "we", "our", "after", "before", "once", "then",
    "also", "anyone", "someone", "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday", "oracle", "teams", "map", "company", "ok", "okay",
    "great", "for", "in", "on", "at", "to", "from", "with", "by", "about",
    "roughly", "usually", "typically", "any", "has", "have", "there", "anything",
    "else", "between", "one", "next",
}
_TOKEN = re.compile(r"[A-Za-z][A-Za-z'&.-]*")


def capitalized_names(text: str) -> set[str]:
    """Capitalized words that are not common words: candidate names."""
    return {
        word.casefold()
        for word in (m.group(0).rstrip(".") for m in _TOKEN.finditer(text))
        if word[:1].isupper() and word.casefold() not in _COMMON
    }


def invented_names(question: str, allowed_text: str) -> set[str]:
    """Names in ``question`` that appear nowhere in ``allowed_text``."""
    allowed = {w.casefold().rstrip(".") for w in _TOKEN.findall(allowed_text)}
    return {name for name in capitalized_names(question) if name not in allowed}


def map_context(conn: Any, employee_text: str) -> list[str]:
    """Plain lines about Map entities whose names appear in the employee's words."""
    lowered = f" {' '.join(employee_text.casefold().split())} "
    rows = conn.execute(
        "SELECT e.id::text, e.entity_type, e.canonical_name FROM cmap.entity e "
        "WHERE length(e.canonical_name) >= 3 AND position(lower(e.canonical_name) in %s) > 0 "
        "UNION "
        "SELECT e.id::text, e.entity_type, e.canonical_name FROM cmap.entity_alias a "
        "JOIN cmap.entity e ON e.id = a.entity_id "
        "WHERE length(a.normalized_name) >= 3 AND position(a.normalized_name in %s) > 0 "
        "LIMIT %s",
        (lowered, lowered, MAX_CONTEXT_ENTITIES),
    ).fetchall()
    if not rows:
        return []
    ids = [str(row[0]) for row in rows]
    lines = [f"{row[2]} ({row[1]})" for row in rows]
    relations = conn.execute(
        "SELECT DISTINCT fe.canonical_name, r.rel_type, te.canonical_name "
        "FROM cmap.relation r "
        "JOIN cmap.mention fm ON fm.id = r.from_mention_id "
        "JOIN cmap.mention tm ON tm.id = r.to_mention_id "
        "JOIN cmap.entity fe ON fe.id = fm.entity_id "
        "JOIN cmap.entity te ON te.id = tm.entity_id "
        "WHERE fe.id = ANY(%s::uuid[]) OR te.id = ANY(%s::uuid[]) "
        "LIMIT %s",
        (ids, ids, MAX_CONTEXT_RELATIONS),
    ).fetchall()
    lines.extend(f"{a} {rel} {b}" for a, rel, b in relations)
    return lines


def _call_model(messages: list[dict[str, str]]) -> str:
    settings = get_settings()
    model = stage_model(settings, "answer")
    if not model or not settings.openrouter_api_key:
        return ""
    body = post_chat_with_rescue(
        {"model": model, "messages": messages, "max_tokens": 300, "temperature": 0.2},
        api_key=settings.openrouter_api_key,
        timeout=MODEL_TIMEOUT_SECONDS,
        error_cls=RuntimeError,
        label="teams follow-up",
    )
    return message_content(body)


def next_followup(
    conn: Any, turns: list[dict[str, Any]], who: str | None = None
) -> str | None:
    """One grounded follow-up for this thread, or ``None`` (cap reached / no good question)."""
    asked = sum(1 for turn in turns if turn.get("speaker") == ORACLE_SPEAKER)
    if asked >= MAX_FOLLOWUPS:
        return None
    employee_text = " ".join(
        str(turn.get("text", "")) for turn in turns if turn.get("speaker") != ORACLE_SPEAKER
    )
    context = map_context(conn, employee_text)
    transcript = "\n".join(f"{turn.get('speaker')}: {turn.get('text')}" for turn in turns)
    user = (
        (f"The employee is {who}.\n\n" if who else "")
        + "Map context (what the Company Map already records):\n"
        + ("\n".join(context) if context else "(nothing yet)")
        + "\n\nConversation so far:\n"
        + transcript
    )
    try:
        raw = _call_model(
            [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]
        )
    except Exception as exc:  # noqa: BLE001 - a follow-up is optional; ack instead
        logger.warning("teams follow-up model call failed: %s", exc)
        return None
    question = " ".join(raw.strip().strip('"').split())
    if not question or question.upper().startswith("NONE"):
        return None
    if len(question) > 300:
        return None
    invented = invented_names(question, f"{transcript}\n" + "\n".join(context))
    if invented:
        logger.info("teams follow-up dropped, invented names: %s", sorted(invented))
        return None
    return question
