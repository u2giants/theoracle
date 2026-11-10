"""Department and job title for each employee who talks to the Teams bot.

Owner direction 2026-11-03 (verbatim): "have it also ask them what department
they're in and their job title. that's very important context for anything the
system discusses with them, so it routed to the correct domain(s)."

The first time an employee reaches the bot in a 1:1 chat (greeting, install,
or a first contribution), the reply asks for both. Their next message is taken
as the answer: the conversation model splits it into department and job title
(raw text is always kept, and used whole if the model is unavailable). The
profile then rides along with everything they contribute: it heads every
transcript, sets the source's department hint, and is given to the
follow-up model.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from brain.config import get_settings
from brain.db import get_pool
from brain.interview.strings import strings
from brain.llm import message_content, post_chat_with_rescue
from brain.seats import stage_model

logger = logging.getLogger(__name__)

# English strings kept as module constants (tests and callers reference them);
# replies are chosen through strings(lang) at the call sites (plan step 2.1).
_EN = strings("en")
PROFILE_QUESTION = _EN.profile_question
REPLY_PROFILE_THANKS = _EN.profile_thanks
REPLY_PROFILE_THANKS_RAW = _EN.profile_thanks_raw
MODEL_TIMEOUT_SECONDS = 8.0
# A longer reply to the profile question is a contribution, not an answer.
MAX_ANSWER_WORDS = 25

_SPLIT_PROMPT = (
    "An employee was asked for their department and job title. Return only JSON "
    '{"department": "...", "job_title": "..."} using their own words; use null '
    "for anything they did not say. Do not guess. The employee may answer in "
    "any language; return English department/job-title keys where possible, "
    "else the original words."
)


@dataclass(frozen=True)
class Profile:
    department: str | None
    job_title: str | None
    raw: str | None
    asked: bool

    @property
    def complete(self) -> bool:
        return bool(self.raw or (self.department and self.job_title))

    def label(self) -> str | None:
        parts = [p for p in (self.job_title, self.department) if p]
        if parts:
            return ", ".join(parts)
        return self.raw


def get_profile(conn: Any, employee_id: str) -> Profile:
    row = conn.execute(
        "SELECT department, job_title, profile_answer, profile_asked_at IS NOT NULL "
        "FROM cmap.employee_flags WHERE employee_id = %s",
        (employee_id,),
    ).fetchone()
    if row is None:
        return Profile(None, None, None, False)
    return Profile(row[0], row[1], row[2], bool(row[3]))


def mark_asked(conn: Any, employee_id: str) -> None:
    conn.execute(
        "INSERT INTO cmap.employee_flags (employee_id, profile_asked_at) VALUES (%s, now()) "
        "ON CONFLICT (employee_id) DO UPDATE SET profile_asked_at = now()",
        (employee_id,),
    )
    conn.commit()


def _split(text: str) -> tuple[str | None, str | None]:
    settings = get_settings()
    model = stage_model(settings, "answer")
    if not model or not settings.openrouter_api_key:
        return None, None
    try:
        body = post_chat_with_rescue(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": _SPLIT_PROMPT},
                    {"role": "user", "content": text},
                ],
                "max_tokens": 200,
                "temperature": 0,
            },
            settings=settings,
            timeout=MODEL_TIMEOUT_SECONDS,
            error_cls=RuntimeError,
            label="teams profile",
        )
        raw = message_content(body).strip().strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
    except Exception as exc:  # noqa: BLE001 - raw answer is still kept
        logger.warning("teams profile split failed: %s", exc)
        return None, None

    def clean(value: Any) -> str | None:
        text_value = " ".join(str(value).split()) if value else ""
        return text_value[:120] or None

    return clean(data.get("department")), clean(data.get("job_title"))


def record_answer(conn: Any, employee_id: str, text: str, lang: str = "en") -> str:
    """Store the employee's answer; return the bot's thank-you reply."""
    raw = " ".join(text.split())[:300]
    department, job_title = _split(raw)
    conn.execute(
        "INSERT INTO cmap.employee_flags (employee_id, department, job_title, profile_answer, "
        "profile_updated_at) VALUES (%s, %s, %s, %s, now()) ON CONFLICT (employee_id) DO UPDATE SET "
        "department = EXCLUDED.department, job_title = EXCLUDED.job_title, "
        "profile_answer = EXCLUDED.profile_answer, profile_updated_at = now()",
        (employee_id, department, job_title, raw),
    )
    conn.commit()
    s = strings(lang)
    if department and job_title:
        return s.profile_thanks.format(title=job_title, department=department)
    return s.profile_thanks_raw


def _lookup(employee_id: str) -> Profile:
    with get_pool().connection() as conn:
        return get_profile(conn, employee_id)


def department_hint(employee_id: str) -> str | None:
    """The source's department hint: the employee's department, else their raw answer."""
    who = _lookup(employee_id)
    return who.department or who.raw


def transcript_header(employee_id: str, name: str) -> str:
    """The profile question and the employee's own answer, as two real turns."""
    who = _lookup(employee_id)
    answer = who.raw or who.label()
    if not answer:
        return ""
    speaker = " ".join(name.replace(":", " ").split())
    return f"The Oracle: {PROFILE_QUESTION}\n{speaker}: {' '.join(answer.split())}\n"
