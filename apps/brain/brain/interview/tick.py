"""Interview tick (plan step 12): route open questions to employees over Teams.

The worker loop queues one ``interview_tick`` job per hour. Each tick looks at
every ``open_question`` in state ``open``, picks the Person entity most
connected (summed edge weight) to the question's entities who maps to an
employee the bot can reach, and asks them through the Next.js proactive route.

Guardrail: nothing is sent unless ``BRAIN_INTERVIEW_ENABLED`` is true. The
employee does not have to message first — when no conversation is stored yet
(Teams never delivered a conversation update and they never opened the chat),
the web layer opens the 1:1 chat itself on first send. Weekly cap per
employee: ``BRAIN_INTERVIEW_WEEKLY_CAP``. Questions with no reachable target
stay open and show on the admin page for manual routing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import psycopg

from brain.config import Settings, get_settings
from brain.db import get_pool
from brain.extract.normalize import normalize_name
from brain.interview.strings import reply_language, strings

logger = logging.getLogger(__name__)

# English kept as the module constant (tests and callers reference it);
# sends choose strings(lang) per employee (plan step 2.1).
MESSAGE_TEMPLATE = strings("en").message_template

TICK_INTERVAL_SECONDS = 3600

# Build-out phase 3: never message people 8 PM–8 AM New York time or on weekends.
EASTERN = ZoneInfo("America/New_York")
QUIET_START_HOUR = 20
QUIET_END_HOUR = 8


def in_quiet_hours(now: datetime | None = None) -> bool:
    """True on Saturday/Sunday and from 8 PM to 8 AM New York time."""
    local = (now or datetime.now(EASTERN)).astimezone(EASTERN)
    if local.weekday() >= 5:
        return True
    return local.hour >= QUIET_START_HOUR or local.hour < QUIET_END_HOUR

# Summed edge weight between each Person entity and the question's entities.
# Edge weight is the number of distinct sources asserting the relation, the
# same rule step 7 projects into FalkorDB. A Person that is itself one of the
# question's entities gets a bonus so it ranks first.
_PERSON_WEIGHT_SQL = """
WITH rel AS (
  SELECT fm.entity_id AS a, tm.entity_id AS b, ch.source_id
  FROM cmap.relation r
  JOIN cmap.mention fm ON fm.id = r.from_mention_id
  JOIN cmap.mention tm ON tm.id = r.to_mention_id
  JOIN cmap.chunk ch ON ch.id = r.chunk_id
  WHERE fm.entity_id IS NOT NULL AND tm.entity_id IS NOT NULL
),
pairs AS (
  SELECT a AS person, b AS other, source_id FROM rel
  UNION ALL
  SELECT b AS person, a AS other, source_id FROM rel
),
weights AS (
  SELECT person, other, count(DISTINCT source_id) AS weight
  FROM pairs WHERE other = ANY(%(ids)s::uuid[]) AND person <> other
  GROUP BY person, other
)
SELECT e.id::text, e.canonical_name,
       COALESCE((SELECT sum(w.weight) FROM weights w WHERE w.person = e.id), 0)
       + CASE WHEN e.id = ANY(%(ids)s::uuid[]) THEN 1000 ELSE 0 END AS score
FROM cmap.entity e
WHERE e.entity_type = 'Person'
  AND (e.id = ANY(%(ids)s::uuid[]) OR EXISTS (SELECT 1 FROM weights w WHERE w.person = e.id))
ORDER BY score DESC, e.canonical_name
"""


@dataclass(frozen=True)
class Target:
    """A reachable employee picked for one question."""

    employee_id: str
    name: str
    conversation_ref: dict[str, Any] | None


class InterviewSendError(RuntimeError):
    """Raised when the proactive Teams send fails."""


class InterviewUnreachableError(InterviewSendError):
    """Raised when the bot cannot open any Teams chat for this employee."""


def interviews_enabled(conn: psycopg.Connection, settings: Settings) -> bool:
    """Return True only when the env flag and the admin page switch are both on."""
    if not settings.brain_interview_enabled:
        return False
    row = conn.execute("SELECT enabled FROM cmap.interview_setting WHERE id").fetchone()
    return bool(row[0]) if row else False


def _person_names(conn: psycopg.Connection, entity_id: str, canonical: str) -> set[str]:
    """Every normalised name the Person entity is known by."""
    names = {normalize_name(canonical, "Person")}
    for (alias,) in conn.execute(
        "SELECT normalized_name FROM cmap.entity_alias WHERE entity_id = %s",
        (entity_id,),
    ).fetchall():
        names.add(str(alias))
    return names


def reachable_employees(conn: psycopg.Connection, cap: int) -> dict[str, Target]:
    """Employees the bot may write to now, keyed by normalised name.

    Reachable = not paused, and asked fewer than ``cap`` questions sent in the
    last 7 days (skipped ones included, from ``cmap.interview_send``). The
    conversation reference is optional: without one the web layer opens the
    chat at first send (measured 2026-11-04: 11 Teams-licensed employees kept
    the app but never got questions because their install conversation update
    never arrived).
    """
    rows = conn.execute(
        """
        SELECT e.id::text, e.name, tc.conversation_ref
        FROM public.employees e
        LEFT JOIN cmap.teams_conversation tc ON tc.employee_id = e.id
        LEFT JOIN cmap.employee_flags f ON f.employee_id = e.id
        WHERE e.disabled_at IS NULL AND e.name IS NOT NULL
          AND NOT COALESCE(f.interviews_paused, false)
          AND (SELECT count(*) FROM cmap.interview_send s
               WHERE s.employee_id = e.id AND s.sent_at > now() - interval '7 days') < %s
        """,
        (cap,),
    ).fetchall()
    out: dict[str, Target] = {}
    for employee_id, name, ref in rows:
        out[normalize_name(str(name), "Person")] = Target(
            employee_id=employee_id,
            name=str(name),
            conversation_ref=dict(ref) if ref is not None else None,
        )
    return out


def select_target(
    conn: psycopg.Connection,
    question: dict[str, Any],
    reachable: dict[str, Target],
) -> Target | None:
    """Pick the most connected reachable Person for one open question."""
    skipped = {str(item) for item in question.get("skipped_by") or []}
    manual = question.get("target_employee_id")
    if manual:
        for target in reachable.values():
            if target.employee_id == str(manual) and target.employee_id not in skipped:
                return target
        return None
    ids = [str(item) for item in question.get("entity_ids") or []]
    if not ids:
        return None
    for entity_id, canonical, _score in conn.execute(
        _PERSON_WEIGHT_SQL, {"ids": ids}
    ).fetchall():
        for name in _person_names(conn, entity_id, str(canonical)):
            target = reachable.get(name)
            if target is not None and target.employee_id not in skipped:
                return target
    return None


def _post_proactive(employee_id: str, text: str, settings: Settings) -> None:
    """POST ``{employee_id, text}`` to the Next.js proactive Teams route."""
    base = settings.brain_web_base_url
    token = settings.brain_shared_token
    if not base or not token:
        raise InterviewSendError("BRAIN_WEB_BASE_URL and BRAIN_SHARED_TOKEN must be set")
    response = httpx.post(
        f"{base.rstrip('/')}/api/teams/bot/proactive",
        json={"employee_id": employee_id, "text": text},
        headers={"x-brain-token": token},
        timeout=30.0,
    )
    if response.status_code == 404:
        raise InterviewUnreachableError(
            f"no Teams chat reachable for {employee_id}: {response.text[:300]}"
        )
    if response.status_code >= 300:
        raise InterviewSendError(
            f"proactive send failed ({response.status_code}): {response.text[:300]}"
        )


def run_interview_tick(settings: Settings | None = None) -> dict[str, Any]:
    """Ask every open question that has a reachable target; return counts."""
    cfg = settings if settings is not None else get_settings()
    result: dict[str, Any] = {"enabled": False, "asked": 0, "unrouted": 0, "failed": 0}
    pool = get_pool(cfg)
    with pool.connection() as conn:
        if not interviews_enabled(conn, cfg):
            return result
        result["enabled"] = True
        if in_quiet_hours():
            result["quiet_hours"] = True
            return result
        questions = conn.execute(
            "SELECT id::text, question, entity_ids, target_employee_id::text, skipped_by "
            "FROM cmap.open_question WHERE state = 'open' ORDER BY created_at, id"
        ).fetchall()
        for qid, text, entity_ids, manual, skipped in questions:
            reachable = reachable_employees(conn, cfg.brain_interview_weekly_cap)
            target = select_target(
                conn,
                {
                    "entity_ids": entity_ids,
                    "target_employee_id": manual,
                    "skipped_by": skipped,
                },
                reachable,
            )
            if target is None:
                result["unrouted"] += 1
                continue
            try:
                locale_row = conn.execute(
                    "SELECT locale FROM public.employees WHERE id = %s",
                    (target.employee_id,),
                ).fetchone()
                lang = reply_language(
                    str(locale_row[0]) if locale_row and locale_row[0] else None
                )
                _post_proactive(
                    target.employee_id,
                    strings(lang).message_template.format(question=text),
                    cfg,
                )
            except InterviewUnreachableError as exc:
                logger.warning("interview target %s unreachable: %s", target.employee_id, exc)
                conn.execute(
                    "UPDATE cmap.open_question SET skipped_by = array_append(skipped_by, %s::uuid) "
                    "WHERE id = %s",
                    (target.employee_id, qid),
                )
                conn.commit()
                result["failed"] += 1
                continue
            except (InterviewSendError, httpx.HTTPError) as exc:
                logger.warning("interview send to %s failed: %s", target.employee_id, exc)
                result["failed"] += 1
                continue
            conn.execute(
                "UPDATE cmap.open_question SET state = 'asked', asked_at = now(), "
                "target_employee_id = %s WHERE id = %s",
                (target.employee_id, qid),
            )
            conn.execute(
                "INSERT INTO cmap.interview_send (employee_id, question_id) VALUES (%s, %s)",
                (target.employee_id, qid),
            )
            conn.commit()
            result["asked"] += 1
        conn.commit()
    return result


def handle_interview_tick(job: dict[str, Any]) -> None:
    """Worker handler for ``interview_tick`` jobs."""
    result = run_interview_tick()
    logger.info("interview_tick %s: %s", job.get("id"), result)


def maybe_queue_interview_tick(settings: Settings | None = None) -> bool:
    """Queue one ``interview_tick`` when none was queued in the last hour.

    Does nothing while interviews are disabled by env, so the job table stays
    quiet until Albert turns interviews on.
    """
    cfg = settings if settings is not None else get_settings()
    if not cfg.brain_interview_enabled:
        return False
    pool = get_pool(cfg)
    with pool.connection() as conn:
        row = conn.execute(
            "INSERT INTO cmap.job (kind, payload) SELECT 'interview_tick', '{}'::jsonb "
            "WHERE NOT EXISTS (SELECT 1 FROM cmap.job WHERE kind = 'interview_tick' "
            "AND created_at > now() - make_interval(secs => %s)) RETURNING id",
            (TICK_INTERVAL_SECONDS,),
        ).fetchone()
        conn.commit()
    return row is not None
