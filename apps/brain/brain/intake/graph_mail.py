"""Email collector (plan_pm_message_intake.md step 5.1, issue #607).

Run: ``python -m brain.intake.graph_mail --days 90 --people <first>,<first> [--dry-run]``

Reads ONLY the mailboxes of the named people (resolved strictly, exactly one
match each): messages received inside the window, newest first, with the
plain-text ``uniqueBody`` (Graph already removes quoted history from it).
Drafts are skipped. A message present in both mailboxes is stored once (keyed
by its internet message id). One thread per ``conversationId``. Items go to
``cmap.intake_item`` / ``cmap.intake_thread`` with origin ``email``; cleaning
(step 1.4) runs afterwards.

``--dry-run`` prints COUNTS ONLY and writes nothing. Message text, names,
ids and addresses are never printed or logged.

Environment: DATABASE_URL, AZURE_TENANT_ID, AZURE_GRAPH_CLIENT_ID,
AZURE_GRAPH_CLIENT_SECRET.
"""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import psycopg
from psycopg.types.json import Json

from brain.config import get_settings
from brain.graph_ms import GRAPH, graph_pages, graph_token
from brain.intake.sizing import resolve_people
from brain.read.chunk import count_tokens

ORIGIN = "email"
SELECT = (
    "id,internetMessageId,conversationId,subject,from,sender,toRecipients,"
    "ccRecipients,receivedDateTime,sentDateTime,isDraft,meetingMessageType,uniqueBody"
)
TEXT_BODY = {"Prefer": 'outlook.body-content-type="text"'}


@dataclass
class Item:
    external_id: str
    thread_key: str
    author_ref: str | None
    sent_at: datetime
    body_text: str
    raw: dict[str, Any]
    content_hash: str


@dataclass
class Thread:
    thread_key: str
    title: str | None
    items: list[Item] = field(default_factory=list)

    @property
    def tokens(self) -> int:
        return sum(count_tokens(i.body_text) for i in self.items if i.body_text)


@dataclass
class Stats:
    people: int = 0
    messages_read: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    messages_kept: int = 0
    threads: int = 0
    tokens: int = 0

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _since_param(since: datetime) -> str:
    return since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _item(m: dict[str, Any]) -> Item:
    body = (
        ((m.get("uniqueBody") or {}).get("content") or "").replace("\r\n", "\n").strip()
    )
    sender = ((m.get("from") or {}).get("emailAddress") or {}).get("address")
    return Item(
        external_id=m.get("internetMessageId") or m["id"],
        thread_key=m.get("conversationId") or m["id"],
        author_ref=sender.lower() if sender else None,
        sent_at=_parse(m.get("sentDateTime") or m["receivedDateTime"]),
        body_text=body,
        raw=m,
        content_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
    )


def mailbox_messages(
    client: httpx.Client, mailbox: str, since: datetime, stats: Stats
) -> list[dict[str, Any]]:
    """Non-draft messages of one mailbox received inside the window."""
    kept: list[dict[str, Any]] = []
    params = {
        "$select": SELECT,
        "$filter": f"receivedDateTime ge {_since_param(since)}",
        "$orderby": "receivedDateTime desc",
        "$top": 50,
    }
    for m in graph_pages(client, f"{GRAPH}/users/{mailbox}/messages", params):
        stats.messages_read += 1
        if _parse(m["receivedDateTime"]) < since:
            break
        if m.get("isDraft"):
            stats.skip("draft")
            continue
        kept.append(m)
    return kept


def collect(
    client: httpx.Client, people: list[tuple[str, str]], since: datetime, stats: Stats
) -> list[Thread]:
    """Threads by conversationId across the named mailboxes, oldest first inside each."""
    by_key: dict[str, Thread] = {}
    seen: set[str] = set()
    for mailbox, _ in people:
        stats.people += 1
        for m in mailbox_messages(client, mailbox, since, stats):
            it = _item(m)
            if it.external_id in seen:
                stats.skip("in_both_mailboxes")
                continue
            seen.add(it.external_id)
            th = by_key.setdefault(
                it.thread_key, Thread(it.thread_key, m.get("subject"))
            )
            th.items.append(it)
    threads = list(by_key.values())
    for th in threads:
        th.items.sort(key=lambda i: i.sent_at)
    stats.threads = len(threads)
    stats.messages_kept = sum(len(t.items) for t in threads)
    stats.tokens = sum(t.tokens for t in threads)
    return threads


_ITEM_SQL = """
INSERT INTO cmap.intake_item
  (origin, external_id, thread_key, author_ref, sent_at, body_text, raw, content_hash)
VALUES ('email', %(external_id)s, %(thread_key)s, %(author_ref)s,
        %(sent_at)s, %(body_text)s, %(raw)s, %(content_hash)s)
ON CONFLICT (origin, external_id) DO UPDATE SET
  thread_key = EXCLUDED.thread_key,
  author_ref = EXCLUDED.author_ref,
  sent_at = EXCLUDED.sent_at,
  body_text = EXCLUDED.body_text,
  raw = EXCLUDED.raw,
  content_hash = EXCLUDED.content_hash,
  collected_at = now()
-- A row blanked by the secret rule (step 1.4) is never written back.
WHERE cmap.intake_item.drop_reason IS DISTINCT FROM 'secret'
"""

_THREAD_SQL = """
INSERT INTO cmap.intake_thread
  (origin, thread_key, title, started_at, ended_at, item_count, token_count, updated_at)
VALUES ('email', %(thread_key)s, %(title)s, %(started_at)s, %(ended_at)s,
        %(item_count)s, %(token_count)s, now())
ON CONFLICT (origin, thread_key) DO UPDATE SET
  title = EXCLUDED.title,
  started_at = LEAST(cmap.intake_thread.started_at, EXCLUDED.started_at),
  ended_at = GREATEST(cmap.intake_thread.ended_at, EXCLUDED.ended_at),
  item_count = EXCLUDED.item_count,
  token_count = EXCLUDED.token_count,
  updated_at = now()
"""


def store(conn: psycopg.Connection, threads: list[Thread]) -> None:
    """Upsert threads and their items in one transaction; re-running is harmless."""
    with conn.cursor() as cur:
        for th in threads:
            for it in th.items:
                cur.execute(
                    _ITEM_SQL,
                    {
                        "external_id": it.external_id,
                        "thread_key": it.thread_key,
                        "author_ref": it.author_ref,
                        "sent_at": it.sent_at,
                        "body_text": it.body_text,
                        "raw": Json(it.raw),
                        "content_hash": it.content_hash,
                    },
                )
            cur.execute(
                _THREAD_SQL,
                {
                    "thread_key": th.thread_key,
                    "title": th.title,
                    "started_at": th.items[0].sent_at,
                    "ended_at": th.items[-1].sent_at,
                    "item_count": len(th.items),
                    "token_count": th.tokens,
                },
            )
    conn.commit()


def _report(stats: Stats, dry_run: bool) -> None:
    print(f"# Email intake ({'dry run, nothing written' if dry_run else 'stored'})")
    print(
        f"mailboxes {stats.people}  messages read {stats.messages_read}  "
        f"kept {stats.messages_kept}  threads {stats.threads}  tokens {stats.tokens}"
    )
    for reason, n in sorted(stats.skipped.items()):
        print(f"  skipped {reason}: {n}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--people", required=True, help="comma-separated first names")
    ap.add_argument("--dry-run", action="store_true", help="print counts only")
    a = ap.parse_args(argv)
    since = datetime.now(UTC) - timedelta(days=a.days)
    people = resolve_people([p.strip() for p in a.people.split(",")])
    stats = Stats()
    with httpx.Client(
        headers={"Authorization": f"Bearer {graph_token()}", **TEXT_BODY}, timeout=60
    ) as client:
        threads = collect(client, people, since, stats)
    if not a.dry_run:
        with psycopg.connect(get_settings().database_url) as conn:
            store(conn, threads)
    _report(stats, a.dry_run)


if __name__ == "__main__":
    main()
