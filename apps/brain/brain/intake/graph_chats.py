"""Teams chat collector (plan_pm_message_intake.md step 1.3, issue #607).

Run: ``python -m brain.intake.graph_chats --days 90 --people <first>,<first> [--dry-run]``

For each named manager: lists their chats, reads each chat's messages newest
first until the window edge, skips non-message, deleted and application
messages, and splits what is left into threads on silences over four hours.
A chat that answers 403 is skipped and counted. Kept messages are upserted
into ``cmap.intake_item`` and ``cmap.intake_thread`` (origin ``teams_chat``).
A chat shared by both managers is read once.

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
from brain.intake.clean import html_to_text
from brain.intake.sizing import THREAD_GAP, resolve_people
from brain.read.chunk import count_tokens

ORIGIN = "teams_chat"


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
    chats_listed: int = 0
    chats_read: int = 0
    chats_refused: int = 0  # 403 on a chat's messages: skipped, not fatal
    messages_read: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    messages_kept: int = 0
    threads: int = 0
    tokens: int = 0

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _skip_reason(m: dict[str, Any]) -> str | None:
    if m.get("messageType") != "message":
        return "not_message"
    if m.get("deletedDateTime"):
        return "deleted"
    if (m.get("from") or {}).get("application"):
        return "application"
    return None


def window_messages(
    client: httpx.Client, chat_id: str, since: datetime, stats: Stats
) -> list[dict[str, Any]]:
    """Kept messages of one chat inside the window, oldest first.

    Graph returns newest first, so the first message older than ``since``
    ends the read; the generator is abandoned and no further page is fetched.
    """
    kept: list[dict[str, Any]] = []
    for m in graph_pages(client, f"{GRAPH}/chats/{chat_id}/messages", {"$top": 50}):
        stats.messages_read += 1
        if _parse(m["createdDateTime"]) < since:
            break
        reason = _skip_reason(m)
        if reason:
            stats.skip(reason)
            continue
        kept.append(m)
    kept.reverse()
    return kept


def _item(m: dict[str, Any], thread_key: str) -> Item:
    body = html_to_text((m.get("body") or {}).get("content", ""))
    return Item(
        external_id=m["id"],
        thread_key=thread_key,
        author_ref=((m.get("from") or {}).get("user") or {}).get("id"),
        sent_at=_parse(m["createdDateTime"]),
        body_text=body,
        raw=m,
        content_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
    )


def split_threads(chat: dict[str, Any], msgs: list[dict[str, Any]]) -> list[Thread]:
    """Threads of one chat's messages (oldest first), split on gaps over THREAD_GAP.

    thread_key = chat id + ':' + id of the thread's first message.
    """
    threads: list[Thread] = []
    prev: datetime | None = None
    for m in msgs:
        sent = _parse(m["createdDateTime"])
        if prev is None or sent - prev > THREAD_GAP:
            key = f"{chat['id']}:{m['id']}"
            threads.append(Thread(thread_key=key, title=chat.get("topic")))
        threads[-1].items.append(_item(m, threads[-1].thread_key))
        prev = sent
    return threads


def collect(
    client: httpx.Client,
    people: list[tuple[str, str]],
    since: datetime,
    stats: Stats,
) -> list[Thread]:
    """Threads for every chat the named people belong to, read once per chat."""
    threads: list[Thread] = []
    done: set[str] = set()
    for email, _ in people:
        stats.people += 1
        for chat in graph_pages(client, f"{GRAPH}/users/{email}/chats", {"$top": 50}):
            stats.chats_listed += 1
            if chat["id"] in done:
                continue
            done.add(chat["id"])
            last = chat.get("lastUpdatedDateTime")
            if last and _parse(last) < since:
                continue
            try:
                msgs = window_messages(client, chat["id"], since, stats)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 403:
                    raise
                stats.chats_refused += 1
                continue
            stats.chats_read += 1
            chat_threads = split_threads(chat, msgs)
            stats.threads += len(chat_threads)
            stats.messages_kept += len(msgs)
            threads.extend(chat_threads)
    stats.tokens = sum(t.tokens for t in threads)
    return threads


_ITEM_SQL = """
INSERT INTO cmap.intake_item
  (origin, external_id, thread_key, author_ref, sent_at, body_text, raw, content_hash)
VALUES ('teams_chat', %(external_id)s, %(thread_key)s, %(author_ref)s,
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
VALUES ('teams_chat', %(thread_key)s, %(title)s, %(started_at)s, %(ended_at)s,
        %(item_count)s, %(token_count)s, now())
ON CONFLICT (origin, thread_key) DO UPDATE SET
  title = EXCLUDED.title,
  started_at = EXCLUDED.started_at,
  ended_at = EXCLUDED.ended_at,
  item_count = EXCLUDED.item_count,
  token_count = EXCLUDED.token_count,
  updated_at = now()
"""


def _chat_id(th: Thread) -> str | None:
    if th.items:
        suffix = f":{th.items[0].external_id}"
        if th.thread_key.endswith(suffix):
            return th.thread_key[: -len(suffix)]
    chat_id, sep, _ = th.thread_key.rpartition(":")
    return chat_id if sep else None


def _like_prefix(chat_id: str) -> str:
    escaped = chat_id.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    return f"{escaped}:%"


def store(conn: psycopg.Connection, threads: list[Thread]) -> None:
    """Upsert threads and their items in one transaction; re-running is harmless."""
    touched_chats: list[str] = list(
        dict.fromkeys(cid for th in threads if (cid := _chat_id(th)) is not None)
    )
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
        for chat_id in touched_chats:
            rows = cur.execute(
                "SELECT t.thread_key, t.source_id, i.id IS NOT NULL, "
                "i.body_text, i.sent_at, i.drop_reason "
                "FROM cmap.intake_thread t "
                "LEFT JOIN cmap.intake_item i "
                "  ON i.origin = t.origin AND i.thread_key = t.thread_key "
                "WHERE t.origin = 'teams_chat' AND t.thread_key LIKE %s ESCAPE '!' "
                "ORDER BY t.thread_key, i.sent_at NULLS LAST, i.id NULLS LAST",
                (_like_prefix(chat_id),),
            ).fetchall()
            by_thread: dict[
                str, tuple[Any, list[tuple[str | None, datetime | None, str | None]]]
            ] = {}
            for (
                thread_key,
                source_id,
                has_item,
                body_text,
                sent_at,
                drop_reason,
            ) in rows:
                entry = by_thread.setdefault(thread_key, (source_id, []))
                if has_item:
                    entry[1].append((body_text, sent_at, drop_reason))
            for thread_key, (source_id, items) in by_thread.items():
                if not items:
                    if source_id is None:
                        cur.execute(
                            "DELETE FROM cmap.intake_thread "
                            "WHERE origin = 'teams_chat' AND thread_key = %s "
                            "AND source_id IS NULL",
                            (thread_key,),
                        )
                    continue
                times = [sent_at for _, sent_at, _ in items if sent_at is not None]
                tokens = sum(
                    count_tokens(body_text)
                    for body_text, _, drop_reason in items
                    if body_text and drop_reason is None
                )
                cur.execute(
                    "UPDATE cmap.intake_thread "
                    "SET started_at = COALESCE(%s, started_at), "
                    "    ended_at = COALESCE(%s, ended_at), "
                    "    item_count = %s, token_count = %s, updated_at = now() "
                    "WHERE origin = 'teams_chat' AND thread_key = %s",
                    (
                        min(times) if times else None,
                        max(times) if times else None,
                        len(items),
                        tokens,
                        thread_key,
                    ),
                )
    conn.commit()


def _report(stats: Stats, dry_run: bool) -> None:
    print(
        f"# Teams chat intake ({'dry run, nothing written' if dry_run else 'stored'})"
    )
    print(
        f"people {stats.people}  chats listed {stats.chats_listed}  "
        f"chats read {stats.chats_read}  chats refused (403) {stats.chats_refused}"
    )
    print(
        f"messages read {stats.messages_read}  kept {stats.messages_kept}  "
        f"threads {stats.threads}  tokens {stats.tokens}"
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
        headers={"Authorization": f"Bearer {graph_token()}"}, timeout=60
    ) as client:
        threads = collect(client, people, since, stats)
    if not a.dry_run:
        with psycopg.connect(get_settings().database_url) as conn:
            store(conn, threads)
    _report(stats, a.dry_run)


if __name__ == "__main__":
    main()
