"""ClickUp intake collector (plan_pm_message_intake.md step 1.2, issue #607).

Run: ``python -m brain.intake.clickup --days 90 --people <first>,<first> [--dry-run]``

Stores one intake thread per ClickUp task (``thread_key`` = task id). Each
thread opens with a header turn from speaker ``ClickUp`` whose field values
are copied exactly, one field per line, then the task description and each
comment as their own items with author and timestamp. Rows go to
``cmap.intake_item`` and ``cmap.intake_thread``; both upserts are idempotent.

``--dry-run`` pages and fetches exactly as a real run does, prints COUNTS
ONLY and writes nothing. Environment: DATABASE_URL, CLICKUP_API_TOKEN.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import psycopg
from psycopg.types.json import Jsonb

from brain.config import get_settings
from brain.graph_ms import get_retry
from brain.intake.sizing import (
    CLICKUP,
    clickup_member,
    involves,
    resolve_people,
    task_comments,
    window_tasks,
)
from brain.read.chunk import count_tokens

ORIGIN = "clickup"
SPEAKER = "ClickUp"
logger = logging.getLogger(__name__)


def _one_line(value: Any) -> str:
    """Field value as typed, with line breaks shown as escapes so each field stays on one line."""
    text = "" if value is None else str(value)
    return text.replace("\r", "\\r").replace("\n", "\\n")


def _ms_to_dt(value: Any) -> datetime | None:
    """ClickUp epoch milliseconds (string or int) to an aware UTC datetime; None if absent or malformed."""
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def header_text(task: dict) -> str:
    """The header turn: six labelled fields, one per line, values copied exactly."""
    deps = "; ".join(
        f"{d.get('task_id')} depends on {d.get('depends_on')}"
        for d in task.get("dependencies") or []
    )
    fields = (
        ("Task name", task.get("name")),
        ("List", (task.get("list") or {}).get("name")),
        ("Status", (task.get("status") or {}).get("status")),
        (
            "Assignee",
            ", ".join(
                str(u.get("username") or "") for u in task.get("assignees") or []
            ),
        ),
        ("Due date", task.get("due_date")),
        ("Dependencies", deps),
    )
    return "\n".join(f"{label}: {_one_line(value)}" for label, value in fields)


def _item(
    external_id: str,
    task_id: str,
    author_ref: str | None,
    sent_at: datetime | None,
    body: str,
    raw: dict,
) -> dict:
    return {
        "external_id": external_id,
        "thread_key": task_id,
        "author_ref": author_ref,
        "sent_at": sent_at,
        "body_text": body,
        "raw": raw,
        "content_hash": hashlib.sha256(body.encode()).hexdigest(),
    }


def task_items(task: dict, comments: list[dict]) -> list[dict]:
    """Header, description (when non-empty) and comments of one task, in order."""
    tid = str(task["id"])
    created = _ms_to_dt(task.get("date_created"))
    creator = str((task.get("creator") or {}).get("id") or "") or None
    items = [
        _item(f"task:{tid}:header", tid, SPEAKER, created, header_text(task), task)
    ]
    description = task.get("text_content") or ""
    if description.strip():
        items.append(
            _item(f"task:{tid}:description", tid, creator, created, description, task)
        )
    for cm in comments:
        items.append(
            _item(
                f"comment:{cm['id']}",
                tid,
                str((cm.get("user") or {}).get("id") or "") or None,
                _ms_to_dt(cm.get("date")),
                cm.get("comment_text") or "",
                cm,
            )
        )
    return items


def collect(
    c: httpx.Client,
    people: list[tuple[str, str]],
    since: datetime,
    counts: Counts | None = None,
) -> Iterator[tuple[dict, list[dict]]]:
    """Yield (task, items) for each task in the window where a named person is involved."""
    seen: set[str] = set()
    for team in get_retry(c, f"{CLICKUP}/team").json()["teams"]:
        uids = [clickup_member(team.get("members") or [], e, n) for e, n in people]
        if None in uids:
            raise RuntimeError(
                f"ClickUp: {uids.count(None)} person(s) not matched to exactly one member"
            )
        wanted = {str(u) for u in uids}
        for task in window_tasks(c, team["id"], since):
            tid = str(task["id"])
            if tid in seen:
                continue
            try:
                comments = task_comments(c, tid)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in (403, 404):
                    raise
                logger.warning(
                    "ClickUp comment fetch skipped (HTTP %s)",
                    exc.response.status_code,
                )
                if counts is not None:
                    counts.comment_errors += 1
                comments = []
            if not involves(task, wanted, comments):
                continue
            seen.add(tid)
            yield task, task_items(task, comments)


_UPSERT_ITEM = """
INSERT INTO cmap.intake_item
  (origin, external_id, thread_key, author_ref, sent_at, body_text, raw, content_hash, collected_at)
VALUES ('clickup', %(external_id)s, %(thread_key)s, %(author_ref)s, %(sent_at)s,
        %(body_text)s, %(raw)s, %(content_hash)s, now())
ON CONFLICT (origin, external_id) DO UPDATE SET
  thread_key = EXCLUDED.thread_key,
  author_ref = EXCLUDED.author_ref,
  sent_at = EXCLUDED.sent_at,
  body_text = EXCLUDED.body_text,
  raw = EXCLUDED.raw,
  content_hash = EXCLUDED.content_hash,
  collected_at = now()
"""

_UPSERT_THREAD = """
INSERT INTO cmap.intake_thread
  (origin, thread_key, title, started_at, ended_at, item_count, token_count)
VALUES ('clickup', %(thread_key)s, %(title)s, %(started_at)s, %(ended_at)s,
        %(item_count)s, %(token_count)s)
ON CONFLICT (origin, thread_key) DO UPDATE SET
  title = EXCLUDED.title,
  started_at = EXCLUDED.started_at,
  ended_at = EXCLUDED.ended_at,
  item_count = EXCLUDED.item_count,
  token_count = EXCLUDED.token_count,
  updated_at = now()
"""


def store_task(conn: psycopg.Connection, task: dict, items: list[dict]) -> None:
    """Upsert one task's items and its thread; re-running changes nothing new."""
    for it in items:
        conn.execute(_UPSERT_ITEM, {**it, "raw": Jsonb(it["raw"])})
    times = [it["sent_at"] for it in items if it["sent_at"]]
    conn.execute(
        _UPSERT_THREAD,
        {
            "thread_key": str(task["id"]),
            "title": task.get("name"),
            "started_at": min(times, default=None),
            "ended_at": max(times, default=None),
            "item_count": len(items),
            "token_count": sum(count_tokens(it["body_text"]) for it in items),
        },
    )


@dataclass
class Counts:
    tasks: int = 0
    items: int = 0
    tokens: int = 0
    comment_errors: int = 0


def run(
    c: httpx.Client,
    people: list[tuple[str, str]],
    since: datetime,
    conn: psycopg.Connection | None = None,
) -> Counts:
    """Collect every involved task; store it when a connection is given (dry run otherwise)."""
    counts = Counts()
    for task, items in collect(c, people, since, counts=counts):
        counts.tasks += 1
        counts.items += len(items)
        counts.tokens += sum(count_tokens(it["body_text"]) for it in items)
        if conn is not None:
            store_task(conn, task, items)
    return counts


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--people", required=True, help="comma-separated first names")
    ap.add_argument(
        "--dry-run", action="store_true", help="print counts only; write nothing"
    )
    a = ap.parse_args(argv)
    settings = get_settings()
    since = datetime.now(UTC) - timedelta(days=a.days)
    people = resolve_people([p.strip() for p in a.people.split(",")])
    print(f"# ClickUp intake, last {a.days} days, {len(people)} people")
    if not settings.clickup_api_token:
        raise SystemExit("CLICKUP_API_TOKEN is not set")
    headers = {"Authorization": settings.clickup_api_token}
    with httpx.Client(headers=headers, timeout=60) as c:
        if a.dry_run:
            counts = run(c, people, since)
        else:
            with psycopg.connect(settings.database_url) as conn:
                counts = run(c, people, since, conn)
    print(
        f"tasks {counts.tasks}  items {counts.items}  tokens {counts.tokens}"
        f"{'  (dry run, nothing written)' if a.dry_run else '  (stored)'}"
    )
    if counts.comment_errors:
        print(f"  skipped comments (403/404): {counts.comment_errors}")


if __name__ == "__main__":
    main()
