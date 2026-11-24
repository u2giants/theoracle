"""Step 5.1 gate: email collector on synthetic Graph fixtures (no live calls)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from brain import graph_ms
from brain.graph_ms import GraphPagingError
from brain.intake import graph_mail
from brain.migrate import migrate


@pytest.fixture(scope="session", autouse=True)
def _brain_env() -> None:
    """No database needed for the pure tests in this module."""


@pytest.fixture(autouse=True)
def _clean_cmap() -> None:
    """Nothing here truncates tables."""


SINCE = datetime(2026, 11, 1, tzinfo=UTC)
BOX_A = "person-a@example.test"
BOX_B = "person-b@example.test"


def mail(
    mid: str, conv: str, when: str, text: str = "synthetic words", **kw: Any
) -> dict[str, Any]:
    m = {
        "id": mid,
        "internetMessageId": f"<{mid}@example.test>",
        "conversationId": conv,
        "subject": "synthetic subject",
        "from": {"emailAddress": {"address": "Sender@Example.test"}},
        "receivedDateTime": when,
        "sentDateTime": when,
        "isDraft": False,
        "uniqueBody": {"contentType": "text", "content": text + "\r\nsecond line"},
    }
    m.update(kw)
    return m


def make_client(
    routes: dict[str, list[dict[str, Any]]], record: list[httpx.Request] | None = None
) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if record is not None:
            record.append(request)
        pages = routes.get(request.url.path)
        if pages is None:
            return httpx.Response(404, json={})
        i = int(request.url.params.get("page", "0"))
        body = dict(pages[i])
        if i + 1 < len(pages):
            body["@odata.nextLink"] = (
                f"https://graph.microsoft.com{request.url.path}?page={i + 1}"
            )
        return httpx.Response(200, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_only_named_mailboxes_and_window_filter_requested() -> None:
    seen: list[httpx.Request] = []
    client = make_client(
        {
            f"/v1.0/users/{BOX_A}/messages": [{"value": []}],
            f"/v1.0/users/{BOX_B}/messages": [{"value": []}],
        },
        seen,
    )
    graph_mail.collect(client, [(BOX_A, "a"), (BOX_B, "b")], SINCE, graph_mail.Stats())
    msg_reqs = [r for r in seen if r.url.path.endswith("/messages")]
    assert {r.url.path for r in msg_reqs} == {
        f"/v1.0/users/{BOX_A}/messages",
        f"/v1.0/users/{BOX_B}/messages",
    }
    assert all(
        r.url.path.startswith((f"/v1.0/users/{BOX_A}/", f"/v1.0/users/{BOX_B}/"))
        for r in seen
    )
    for r in msg_reqs:
        assert r.url.params["$filter"] == "receivedDateTime ge 2026-11-01T00:00:00Z"
        assert "uniqueBody" in r.url.params["$select"]
        assert "internetMessageHeaders" in r.url.params["$select"]
        assert "parentFolderId" in r.url.params["$select"]
        # Subtype-only eventMessage property causes Graph HTTP 400 on /messages.
        assert "meetingMessageType" not in r.url.params["$select"]


def test_junk_and_deleted_folder_messages_are_skipped() -> None:
    client = make_client(
        {
            f"/v1.0/users/{BOX_A}/mailFolders/junkemail": [{"id": "junk-fid"}],
            f"/v1.0/users/{BOX_A}/mailFolders/deleteditems": [{"id": "del-fid"}],
            f"/v1.0/users/{BOX_A}/messages": [
                {
                    "value": [
                        mail("ok1", "conv-ok", "2026-11-06T10:00:00Z", parentFolderId="inbox-fid"),
                        mail("sp1", "conv-sp", "2026-11-06T09:00:00Z", parentFolderId="junk-fid"),
                        mail("dl1", "conv-dl", "2026-11-06T08:00:00Z", parentFolderId="del-fid"),
                    ]
                }
            ],
        }
    )
    stats = graph_mail.Stats()
    threads = graph_mail.collect(client, [(BOX_A, "a")], SINCE, stats)
    assert [t.thread_key for t in threads] == ["conv-ok"]
    assert stats.skipped == {"junk_or_deleted": 2}


def test_threads_by_conversation_paging_drafts_and_both_mailboxes() -> None:
    shared = mail("s1", "conv-1", "2026-11-05T10:00:00Z")
    client = make_client(
        {
            f"/v1.0/users/{BOX_A}/messages": [
                {"value": [mail("a2", "conv-1", "2026-11-06T10:00:00Z"), shared]},
                {
                    "value": [
                        mail("a1", "conv-2", "2026-11-04T10:00:00Z"),
                        mail("d1", "conv-2", "2026-11-03T10:00:00Z", isDraft=True),
                        mail("old", "conv-3", "2026-10-01T10:00:00Z"),
                    ]
                },
            ],
            f"/v1.0/users/{BOX_B}/messages": [
                {"value": [dict(shared, id="other-copy")]}
            ],
        }
    )
    stats = graph_mail.Stats()
    threads = graph_mail.collect(client, [(BOX_A, "a"), (BOX_B, "b")], SINCE, stats)
    by_key = {t.thread_key: t for t in threads}
    assert set(by_key) == {"conv-1", "conv-2"}
    assert [i.external_id for i in by_key["conv-1"].items] == [
        "<s1@example.test>",
        "<a2@example.test>",
    ]
    assert stats.skipped == {"draft": 1, "in_both_mailboxes": 1}
    assert stats.messages_kept == 3 and stats.threads == 2


def test_item_keeps_plain_text_and_original() -> None:
    m = mail("x1", "conv-9", "2026-11-05T10:00:00Z", text="hello")
    it = graph_mail._item(m)
    assert it.body_text == "hello\nsecond line"
    assert it.raw is m and it.author_ref == "sender@example.test"
    assert it.sent_at == datetime(2026, 11, 5, 10, tzinfo=UTC)


def test_retry_after_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(graph_ms.time, "sleep", sleeps.append)
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "9999"}, json={})
        return httpx.Response(
            200, json={"value": [mail("r1", "c", "2026-11-05T10:00:00Z")]}
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    threads = graph_mail.collect(client, [(BOX_A, "a")], SINCE, graph_mail.Stats())
    assert len(threads) == 1 and sleeps == [60.0]


def test_paging_loop_detected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "value": [],
                "@odata.nextLink": f"https://graph.microsoft.com/v1.0/users/{BOX_A}/messages?loop=1",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(GraphPagingError):
        graph_mail.collect(client, [(BOX_A, "a")], SINCE, graph_mail.Stats())


def test_store_upserts_are_idempotent(db: Any) -> None:
    migrate()
    threads = [
        graph_mail.Thread(
            "syn-conv-db",
            "s",
            [graph_mail._item(mail("dbm1", "syn-conv-db", "2026-11-05T10:00:00Z"))],
        )
    ]

    def cleanup() -> None:
        db.execute(
            "DELETE FROM cmap.intake_item WHERE origin = 'email' AND thread_key = 'syn-conv-db'"
        )
        db.execute(
            "DELETE FROM cmap.intake_thread WHERE origin = 'email' AND thread_key = 'syn-conv-db'"
        )
        db.commit()

    cleanup()
    try:
        graph_mail.store(db, threads)
        graph_mail.store(db, threads)
        n = db.execute(
            "SELECT count(*) FROM cmap.intake_item WHERE origin = 'email' AND thread_key = 'syn-conv-db'"
        ).fetchone()[0]
        rows = db.execute(
            "SELECT item_count, verdict FROM cmap.intake_thread WHERE origin = 'email' AND thread_key = 'syn-conv-db'"
        ).fetchall()
        assert n == 1 and rows == [(1, "pending")]
    finally:
        cleanup()
