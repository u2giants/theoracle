"""Step 1.3 gate: Teams chat collector on synthetic Graph fixtures (no live calls).

Pure-logic tests use httpx.MockTransport and need no database. The one test
that writes uses the ``db`` fixture and runs in CI, where Postgres is present.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from brain import graph_ms
from brain.graph_ms import GRAPH, GraphPagingError, graph_pages
from brain.intake import graph_chats
from brain.intake.clean import html_to_text
from brain.migrate import migrate


# These replace the shared conftest fixtures of the same name for this module
# only, so the pure-logic tests run without a database. The one test that
# writes migrates the database itself.
@pytest.fixture(scope="session", autouse=True)
def _brain_env() -> None:
    """No database needed for the pure tests in this module."""


@pytest.fixture(autouse=True)
def _clean_cmap() -> None:
    """Nothing here truncates tables."""


SINCE = datetime(2026, 11, 1, tzinfo=UTC)
PERSON_A = "person-a@example.test"
PERSON_B = "person-b@example.test"


def human(mid: str, when: str, text: str = "synthetic words") -> dict[str, Any]:
    return {
        "id": mid,
        "messageType": "message",
        "createdDateTime": when,
        "deletedDateTime": None,
        "from": {"user": {"id": "synthetic-user-1"}},
        "body": {"contentType": "html", "content": f"<p>{text} &amp; more</p>"},
    }


def make_client(
    routes: dict[str, list[dict[str, Any]]],
    forbidden: set[str] | None = None,
    record: list[str] | None = None,
) -> httpx.Client:
    """Serve each path's pages in order; ``page=N`` selects page N."""
    forbidden = forbidden or set()

    def handler(request: httpx.Request) -> httpx.Response:
        if record is not None:
            record.append(str(request.url))
        path = request.url.path
        if path in forbidden:
            return httpx.Response(403, json={"error": {"code": "Forbidden"}})
        pages = routes.get(path)
        if pages is None:
            return httpx.Response(404, json={"error": {"code": "NotFound"}})
        i = int(request.url.params.get("page", "0"))
        body = dict(pages[i])
        if i + 1 < len(pages):
            body["@odata.nextLink"] = f"https://graph.microsoft.com{path}?page={i + 1}"
        return httpx.Response(200, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_graph_pages_follows_next_link():
    client = make_client(
        {
            "/v1.0/synthetic/items": [
                {"value": [{"id": "a"}]},
                {"value": [{"id": "b"}]},
            ]
        }
    )
    ids = [
        x["id"] for x in graph_pages(client, f"{GRAPH}/synthetic/items", {"$top": 1})
    ]
    assert ids == ["a", "b"]


def test_graph_pages_detects_paging_loop():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "value": [{"id": "x"}],
                "@odata.nextLink": f"{GRAPH}/synthetic/loop",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(GraphPagingError, match="loop"):
        list(graph_pages(client, f"{GRAPH}/synthetic/loop"))


def test_graph_pages_skips_repeated_item():
    client = make_client(
        {
            "/v1.0/synthetic/dup": [
                {"value": [{"id": "a"}]},
                {"value": [{"id": "a"}]},
            ]
        }
    )
    assert [i["id"] for i in graph_pages(client, f"{GRAPH}/synthetic/dup")] == ["a"]


def test_429_with_retry_after_is_honoured(monkeypatch: pytest.MonkeyPatch):
    sleeps: list[float] = []
    monkeypatch.setattr(graph_ms.time, "sleep", sleeps.append)
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "3"}, json={})
        return httpx.Response(200, json={"value": [{"id": "a"}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    ids = [x["id"] for x in graph_pages(client, f"{GRAPH}/synthetic/retry")]
    assert ids == ["a"]
    assert sleeps == [3.0]
    assert len(calls) == 2


def test_split_threads_gap_over_four_hours():
    chat = {"id": "synthetic-chat-gap", "topic": None}
    msgs = [
        human("g1", "2026-11-10T08:00:00Z"),
        human("g2", "2026-11-10T12:00:00Z"),  # exactly four hours: same thread
        human("g3", "2026-11-10T16:01:00Z"),  # over four hours: new thread
        human("g4", "2026-11-10T16:05:00Z"),
    ]
    threads = graph_chats.split_threads(chat, msgs)
    assert [t.thread_key for t in threads] == [
        "synthetic-chat-gap:g1",
        "synthetic-chat-gap:g3",
    ]
    assert [[i.external_id for i in t.items] for t in threads] == [
        ["g1", "g2"],
        ["g3", "g4"],
    ]


def _routes() -> dict[str, list[dict[str, Any]]]:
    """Synthetic tenant: two managers, one shared chat, one 403 chat, one stale chat."""
    chat1 = {"id": "synthetic-chat-1", "topic": None}
    deleted = human("m-deleted", "2026-11-10T16:30:00Z")
    deleted["deletedDateTime"] = "2026-11-10T16:31:00Z"
    app = human("m-app", "2026-11-10T16:20:00Z")
    app["from"] = {"application": {"id": "synthetic-app"}}
    system = human("m-system", "2026-11-10T16:10:00Z")
    system["messageType"] = "systemEventMessage"
    chat1_page0 = [
        deleted,
        app,
        system,
        human("m-h4", "2026-11-10T16:05:00Z"),
        human("m-h3", "2026-11-10T16:01:00Z"),
        human("m-h2", "2026-11-10T12:00:00Z"),
        human("m-h1", "2026-11-10T08:00:00Z"),
    ]
    return {
        f"/v1.0/users/{PERSON_A}/chats": [
            {
                "value": [
                    chat1,
                    {"id": "synthetic-chat-403", "topic": None},
                    {"id": "synthetic-chat-shared", "topic": None},
                ]
            }
        ],
        f"/v1.0/users/{PERSON_B}/chats": [
            {
                "value": [
                    {"id": "synthetic-chat-shared", "topic": None},
                    {
                        "id": "synthetic-chat-stale",
                        "topic": None,
                        "lastUpdatedDateTime": "2026-10-01T00:00:00Z",
                    },
                ]
            }
        ],
        "/v1.0/chats/synthetic-chat-1/messages": [
            {"value": chat1_page0},
            # Older than the window: read once, then paging stops.
            {"value": [human("m-old", "2026-10-20T08:00:00Z")]},
            # Must never be requested: the window edge ended the read above.
            {"value": [human("m-older", "2026-09-01T08:00:00Z")]},
        ],
        "/v1.0/chats/synthetic-chat-shared/messages": [
            {"value": [human("m-shared", "2026-11-11T09:00:00Z", "shared text")]}
        ],
    }


def test_collect_filters_splits_and_skips_forbidden_chat():
    record: list[str] = []
    client = make_client(
        _routes(), forbidden={"/v1.0/chats/synthetic-chat-403/messages"}, record=record
    )
    stats = graph_chats.Stats()
    threads = graph_chats.collect(
        client, [(PERSON_A, "A"), (PERSON_B, "B")], SINCE, stats
    )

    keys = {t.thread_key: [i.external_id for i in t.items] for t in threads}
    assert keys == {
        "synthetic-chat-1:m-h1": ["m-h1", "m-h2"],
        "synthetic-chat-1:m-h3": ["m-h3", "m-h4"],
        "synthetic-chat-shared:m-shared": ["m-shared"],
    }
    assert stats.skipped == {"deleted": 1, "application": 1, "not_message": 1}
    assert stats.chats_refused == 1  # the 403 chat was skipped, not fatal
    assert stats.chats_read == 2
    assert stats.people == 2

    # A chat both managers are in is read once.
    shared_reads = [u for u in record if "/chats/synthetic-chat-shared/messages" in u]
    assert len(shared_reads) == 1
    # The stale chat is never opened (its route does not exist; a 404 would raise).
    assert not any("synthetic-chat-stale" in url for url in record)
    # Paging stopped at the window edge: the page after the old message is not fetched.
    assert not any("page=2" in url for url in record)


def test_stored_fields_hold_text_and_original():
    record: list[str] = []
    client = make_client(
        _routes(), forbidden={"/v1.0/chats/synthetic-chat-403/messages"}, record=record
    )
    threads = graph_chats.collect(
        client, [(PERSON_A, "A"), (PERSON_B, "B")], SINCE, graph_chats.Stats()
    )
    shared = next(
        t for t in threads if t.thread_key.startswith("synthetic-chat-shared")
    )
    item = shared.items[0]
    original = _routes()["/v1.0/chats/synthetic-chat-shared/messages"][0]["value"][0]
    assert item.body_text == html_to_text(original["body"]["content"])
    assert "&amp;" not in item.body_text
    assert item.raw == original
    assert len(item.content_hash) == 64
    assert item.author_ref == "synthetic-user-1"
    assert item.sent_at == datetime(2026, 11, 11, 9, 0, tzinfo=UTC)


def test_store_upserts_are_idempotent(db):
    migrate()  # the schema is idempotent; CI already has Postgres
    chat = {"id": "synthetic-chat-db", "topic": "synthetic"}
    msgs = [
        human("db-1", "2026-11-10T08:00:00Z"),
        human("db-2", "2026-11-10T08:10:00Z"),
    ]
    threads = graph_chats.split_threads(chat, msgs)

    def cleanup() -> None:
        db.execute(
            "DELETE FROM cmap.intake_item WHERE origin = 'teams_chat' "
            "AND external_id LIKE 'db-%'"
        )
        db.execute(
            "DELETE FROM cmap.intake_thread WHERE origin = 'teams_chat' "
            "AND thread_key LIKE 'synthetic-chat-db%'"
        )
        db.commit()

    cleanup()
    try:
        graph_chats.store(db, threads)
        graph_chats.store(db, threads)  # second run changes nothing
        items = db.execute(
            "SELECT count(*) FROM cmap.intake_item WHERE origin = 'teams_chat' "
            "AND external_id LIKE 'db-%'"
        ).fetchone()[0]
        rows = db.execute(
            "SELECT item_count, verdict FROM cmap.intake_thread "
            "WHERE origin = 'teams_chat' AND thread_key = %s",
            ("synthetic-chat-db:db-1",),
        ).fetchall()
        assert items == 2
        assert rows == [(2, "pending")]
    finally:
        cleanup()
