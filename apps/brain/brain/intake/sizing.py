"""Size the project-manager intake and forecast its cost (plan step 0.1).

Run: ``python -m brain.intake.sizing --days 90 --people <first>,<first>``

Pages ClickUp and Microsoft Graph for the named managers and prints COUNTS
ONLY: records, threads, tokens, the share each free rule removes, and a
cost forecast per relations candidate from live OpenRouter list prices.
It never prints, logs or stores message text, names, ids or addresses, and
makes no paid model call.

Environment: DATABASE_URL (to resolve the two people from the directory),
CLICKUP_API_TOKEN, AZURE_TENANT_ID, AZURE_GRAPH_CLIENT_ID,
AZURE_GRAPH_CLIENT_SECRET.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import os
import re
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from brain.read.chunk import count_tokens

CLICKUP = "https://api.clickup.com/api/v2"
GRAPH = "https://graph.microsoft.com/v1.0"
OPENROUTER_MODELS = "https://openrouter.ai/api/v1/models"

PASSAGE_TOKENS = 400  # packed passage size (plan 1.6)
MIN_THREAD_TOKENS = 40  # too_short rule (plan 1.4)
THREAD_GAP = timedelta(hours=4)  # O2 default
# Output tokens assumed per call; replaced by measured numbers in the pilot.
OUT_FLAT, OUT_REL, OUT_FUNC = 250, 350, 40
# The four relations candidates the owner named (plan L8). Matched against
# OpenRouter's live catalogue by these substrings; never used as a seat.
# OpenRouter catalogue ids, read only for list prices; never used as a seat.
CANDIDATES = (
    "openai/gpt-6-luna",
    "anthropic/claude-haiku-5.5",
    "z-ai/glm-5.3-flash",
    "deepseek/deepseek-v4.1-flash",
)

_TAG = re.compile(r"<[^>]+>")
_REACTION = re.compile(r"^\W{0,4}$")


def html_text(body: str) -> str:
    """Rough HTML to text, for counting only."""
    return html.unescape(_TAG.sub(" ", body or "")).strip()


@dataclass
class Tally:
    records: int = 0
    tokens: int = 0
    dropped: dict[str, list[int]] = field(
        default_factory=dict
    )  # rule -> [items, tokens]
    threads: int = 0
    threads_kept: int = 0
    kept_tokens: int = 0
    passages: int = 0
    scanned: int = 0  # ClickUp tasks scanned / Teams chats refused
    seen: set[str] = field(default_factory=set)

    def drop(self, rule: str, tokens: int) -> None:
        d = self.dropped.setdefault(rule, [0, 0])
        d[0] += 1
        d[1] += tokens

    def message(self, text: str) -> int:
        """Count one message; return kept tokens (0 if a free rule drops it)."""
        self.records += 1
        n = count_tokens(text) if text else 0
        self.tokens += n
        if not text.strip():
            self.drop("empty", n)
            return 0
        if _REACTION.match(text.strip()):
            self.drop("reaction", n)
            return 0
        h = hashlib.sha256(text.encode()).hexdigest()
        if h in self.seen:
            self.drop("duplicate", n)
            return 0
        self.seen.add(h)
        return n

    def thread(self, kept: int) -> None:
        self.threads += 1
        if kept < MIN_THREAD_TOKENS:
            self.drop("too_short_thread", kept)
            return
        self.threads_kept += 1
        self.kept_tokens += kept
        self.passages += -(-kept // PASSAGE_TOKENS)


def _get(client: httpx.Client, url: str, **kw: Any) -> httpx.Response:
    for attempt in range(8):
        r = client.get(url, **kw)
        if r.status_code != 429 and r.status_code < 500:
            r.raise_for_status()
            return r
        wait = r.headers.get("Retry-After")
        reset = r.headers.get("X-RateLimit-Reset")
        if wait:
            delay = min(max(float(wait), 1.0), 60.0)
        elif reset:
            delay = min(max(float(reset) - time.time(), 1.0), 60.0)
        else:
            delay = min(2**attempt, 60)
        time.sleep(delay)
    r.raise_for_status()
    return r


def resolve_people(firsts: list[str]) -> list[tuple[str, str]]:
    """(email, name) of each first name holding a project-manager title; exactly one each."""
    import psycopg

    out = []
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        for first in firsts:
            # Directory titles are not always current (one of the two owner-named
            # managers carries another title), so the title only breaks ties.
            rows = conn.execute(
                "SELECT e.email, e.name, (e.role ILIKE '%%project manag%%' OR f.job_title ILIKE '%%project manag%%') "
                "FROM public.employees e LEFT JOIN cmap.employee_flags f ON f.employee_id = e.id "
                "WHERE e.disabled_at IS NULL AND split_part(e.name, ' ', 1) ILIKE %s",
                (first,),
            ).fetchall()
            if len(rows) > 1:
                rows = [r for r in rows if r[2]]
            if len(rows) != 1:
                sys.exit(
                    f"person {len(out) + 1}: expected one directory match, found {len(rows)}"
                )
            out.append((rows[0][0], rows[0][1]))
    return out


def clickup_member(members: list[dict], email: str, name: str) -> int | None:
    """ClickUp user id: same email, else same full name, else a unique first-name match."""
    users = [m["user"] for m in members]
    for test in (
        lambda u: (u.get("email") or "").lower() == email.lower(),
        lambda u: (u.get("username") or "").lower() == name.lower(),
        lambda u: (
            (u.get("username") or "").lower().split(" ")[0]
            == name.lower().split(" ")[0]
        ),
    ):
        hits = [u for u in users if test(u)]
        if len(hits) == 1:
            return hits[0]["id"]
    return None


def window_tasks(c: httpx.Client, team_id: str, since: datetime) -> Iterator[dict]:
    """Every ClickUp task of one team updated after ``since``, all pages, in API order."""
    page = 0
    while True:
        params = {
            "date_updated_gt": int(since.timestamp() * 1000),
            "include_closed": "true",
            "subtasks": "true",
            "page": page,
        }
        tasks = (
            _get(c, f"{CLICKUP}/team/{team_id}/task", params=params)
            .json()
            .get("tasks", [])
        )
        yield from tasks
        if len(tasks) < 100:
            return
        page += 1


def involves(task: dict, wanted: set[str]) -> bool:
    """True when a wanted user is assignee, watcher or creator of the task."""
    people_on = {
        u.get("id") for u in task.get("assignees", []) + task.get("watchers", [])
    }
    people_on.add((task.get("creator") or {}).get("id"))
    return bool(people_on & wanted)


def size_clickup(people: list[tuple[str, str]], since: datetime, t: Tally) -> None:
    h = {"Authorization": os.environ["CLICKUP_API_TOKEN"]}
    with httpx.Client(headers=h, timeout=60) as c:
        teams = _get(c, f"{CLICKUP}/team").json()["teams"]
        seen_tasks: set[str] = set()
        for team in teams:
            uids = [clickup_member(team.get("members", []), e, n) for e, n in people]
            if None in uids:
                sys.exit(
                    f"ClickUp: {uids.count(None)} person(s) not matched to exactly one member"
                )
            wanted = set(uids)
            # Kept when either person is assignee, creator or watcher (comment
            # authorship is seen only after fetching comments, so it widens the
            # pilot, not this count).
            for task in window_tasks(c, team["id"], since):
                t.scanned += 1
                if task["id"] in seen_tasks or not involves(task, wanted):
                    continue
                seen_tasks.add(task["id"])
                header = "\n".join(
                    str(x or "")
                    for x in (
                        task.get("name"),
                        (task.get("list") or {}).get("name"),
                        (task.get("status") or {}).get("status"),
                        task.get("due_date"),
                    )
                )
                kept = t.message(header) + t.message(task.get("text_content") or "")
                comments = (
                    _get(c, f"{CLICKUP}/task/{task['id']}/comment")
                    .json()
                    .get("comments", [])
                )
                for cm in comments:
                    kept += t.message(cm.get("comment_text") or "")
                t.thread(kept)


def _graph_token() -> str:
    r = httpx.post(
        f"https://login.microsoftonline.com/{os.environ['AZURE_TENANT_ID']}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": os.environ["AZURE_GRAPH_CLIENT_ID"],
            "client_secret": os.environ["AZURE_GRAPH_CLIENT_SECRET"],
            "scope": "https://graph.microsoft.com/.default",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _pages(c: httpx.Client, url: str, params: dict | None = None):
    seen: set[str] = set()
    while url:
        if url in seen:
            raise RuntimeError("Graph paging loop")
        seen.add(url)
        body = _get(c, url, params=params).json()
        params = None
        yield from body.get("value", [])
        url = body.get("@odata.nextLink")


def _chat_messages(
    c: httpx.Client, chat_id: str, since: datetime
) -> list[tuple[datetime, str]]:
    """Human messages of one chat inside the window, oldest first."""
    msgs = []
    for m in _pages(c, f"{GRAPH}/chats/{chat_id}/messages", {"$top": 50}):
        sent = datetime.fromisoformat(m["createdDateTime"].replace("Z", "+00:00"))
        if sent < since:
            break
        if m.get("messageType") != "message" or m.get("deletedDateTime"):
            continue
        if (m.get("from") or {}).get("application"):
            continue
        msgs.append((sent, html_text((m.get("body") or {}).get("content", ""))))
    return sorted(msgs)


def size_teams(people: list[tuple[str, str]], since: datetime, t: Tally) -> None:
    h = {"Authorization": f"Bearer {_graph_token()}"}
    done_chats: set[str] = set()
    with httpx.Client(headers=h, timeout=60) as c:
        for email, _ in people:
            for chat in _pages(c, f"{GRAPH}/users/{email}/chats", {"$top": 50}):
                if chat["id"] in done_chats:
                    continue  # a chat both managers are in is counted once
                done_chats.add(chat["id"])
                last = chat.get("lastUpdatedDateTime")
                if last and datetime.fromisoformat(last.replace("Z", "+00:00")) < since:
                    continue
                msgs = []
                try:
                    msgs = _chat_messages(c, chat["id"], since)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 403:
                        raise
                    t.scanned += 1  # chat the app may not read (some meeting chats)
                    continue
                msgs.sort()
                kept, prev = 0, None
                for sent, text in msgs:
                    if prev and sent - prev > THREAD_GAP:
                        t.thread(kept)
                        kept = 0
                    kept += t.message(text)
                    prev = sent
                if msgs:
                    t.thread(kept)


def prices() -> dict[str, tuple[float, float]]:
    """Live USD per token (prompt, completion) for each candidate and its ``:batch`` listing."""
    data = {
        m["id"]: m["pricing"]
        for m in httpx.get(OPENROUTER_MODELS, timeout=30).json()["data"]
    }
    out = {}
    for cand in CANDIDATES:
        for mid in (cand, f"{cand}:batch"):
            if mid in data:
                out[mid] = (float(data[mid]["prompt"]), float(data[mid]["completion"]))
    return out


def prompt_tokens(name: str) -> int:
    return count_tokens(
        (Path(__file__).parent.parent / "prompts" / f"{name}.md").read_text(
            encoding="utf-8"
        )
    )


def report(name: str, t: Tally) -> None:
    print(f"\n## {name}")
    print(
        f"records {t.records}  tokens {t.tokens}  threads {t.threads}  "
        f"kept threads {t.threads_kept}  kept tokens {t.kept_tokens}  passages {t.passages}  "
        f"{'tasks scanned' if name == 'clickup' else 'chats refused (403)'} {t.scanned}"
    )
    for rule, (n, tok) in sorted(t.dropped.items()):
        share = tok / t.tokens * 100 if t.tokens else 0
        print(f"  dropped by {rule}: {n} items, {tok} tokens ({share:.1f}% of tokens)")


def forecast(passages: int) -> None:
    flat_in = prompt_tokens("flat_extract") + PASSAGE_TOKENS
    rel_in = (
        prompt_tokens("relations") + PASSAGE_TOKENS * 2
    )  # anchor + previous passage
    func_in = prompt_tokens("function_assign") + PASSAGE_TOKENS
    print(
        f"\n## Forecast: {passages} packed passages, three paid calls each (flat, relations, function sort)"
    )
    print("OpenRouter listing | USD per token in / out | forecast USD")
    for mid, (pi, po) in prices().items():
        usd = passages * (
            (flat_in * pi + OUT_FLAT * po)
            + (rel_in * pi + OUT_REL * po)
            + (func_in * pi + OUT_FUNC * po)
        )
        print(f"{mid} | {pi:.3g} / {po:.3g} | {usd:.2f}")
    print(f"ScaleDown classify calls (about one per passage): {passages}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--people", required=True, help="comma-separated first names")
    ap.add_argument("--only", choices=["clickup", "teams"])
    a = ap.parse_args(argv)
    since = datetime.now(UTC) - timedelta(days=a.days)
    people = resolve_people([p.strip() for p in a.people.split(",")])
    print(f"# Intake sizing, last {a.days} days, {len(people)} people")
    passages = 0
    for name, fn in (("clickup", size_clickup), ("teams", size_teams)):
        if a.only and a.only != name:
            continue
        t = Tally()
        fn(people, since, t)
        report(name, t)
        passages += t.passages
    forecast(passages)


if __name__ == "__main__":
    main()
