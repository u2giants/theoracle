"""Unit tests for the Teams transcript sweep (no live Graph or ScaleDown calls)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import psycopg
import pytest

from brain.meetings import sweep

VTT = """WEBVTT

1
00:00:01.000 --> 00:00:03.000
<v Jessica Cortazar>Maria meets the buyer.</v>

2
00:00:03.000 --> 00:00:05.000
<v Jessica Cortazar>Then I assign a designer.</v>

3
00:00:05.000 --> 00:00:06.000
<v Albert Hazan>Okay.</v>
"""


def test_vtt_lines_merge_same_speaker() -> None:
    text, speakers = sweep.vtt_to_lines(VTT)
    assert text == (
        "Jessica Cortazar: Maria meets the buyer. Then I assign a designer.\n"
        "Albert Hazan: Okay."
    )
    assert speakers == ["Jessica Cortazar", "Albert Hazan"]


def test_vtt_without_voice_tags_keeps_text() -> None:
    text, speakers = sweep.vtt_to_lines(
        "WEBVTT\n\n1\n00:00:01.000 --> 00:00:02.000\nHello there\n"
    )
    assert text == "Hello there"
    assert speakers == []


def test_title_names_kind_date_and_first_speakers() -> None:
    start = datetime(2026, 11, 24, 17, 53, tzinfo=UTC)
    assert sweep._title("call", start, ["A", "B", "C", "D", "E"]) == (
        "Teams call — 2026-11-24 — A, B, C +2"
    )


def test_queue_noop_when_graph_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "AZURE_TENANT_ID",
        "AZURE_GRAPH_CLIENT_ID",
        "AZURE_GRAPH_CLIENT_SECRET",
    ):
        monkeypatch.delenv(key, raising=False)
    assert sweep.maybe_queue_meeting_sweep() is False


class _Resp:
    def __init__(self, status: int, body: dict) -> None:
        self.status_code = status
        self._body = body
        self.text = json.dumps(body)

    def json(self) -> dict:
        return self._body


class _Cfg:
    scaledown_api_key = "k"


def test_summarize_parses_scaledown_json(monkeypatch: pytest.MonkeyPatch) -> None:
    content = json.dumps({"summary": "The team agreed who approves designs and when."})
    sent: dict = {}

    def fake_post(url: str, **kw: object) -> _Resp:
        sent.update(kw)
        return _Resp(200, {"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(sweep.httpx, "post", fake_post)
    assert sweep.summarize("x" * 100_000, _Cfg()) == (  # type: ignore[arg-type]
        "The team agreed who approves designs and when."
    )
    body = sent["json"]
    assert body["model"] == "summarize"
    assert len(body["messages"][1]["content"]) == sweep.SUMMARY_INPUT_CHARS


def test_summarize_rejects_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    content = json.dumps({"summary": ""})
    monkeypatch.setattr(
        sweep.httpx,
        "post",
        lambda url, **kw: _Resp(200, {"choices": [{"message": {"content": content}}]}),
    )
    with pytest.raises(RuntimeError):
        sweep.summarize("text", _Cfg())  # type: ignore[arg-type]


def _graph_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://graph.microsoft.com/test")
    return httpx.HTTPStatusError(
        f"Graph returned {status}", request=request, response=httpx.Response(status)
    )


@pytest.mark.parametrize("status", [400, 403, 404, 500])
def test_transcript_refs_skips_only_expected_graph_errors(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    def pages(client, url):
        if "/onlineMeetings/" in url:
            raise _graph_error(status)
        yield {"id": "call"}

    monkeypatch.setattr(sweep, "graph_pages", pages)
    with httpx.Client() as client:
        if status == 500:
            with pytest.raises(httpx.HTTPStatusError, match="500"):
                list(sweep.transcript_refs(client, "organizer"))
        else:
            assert list(sweep.transcript_refs(client, "organizer")) == [
                {"id": "call", "_kind": "call"}
            ]


@pytest.fixture
def sweep_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sweep, "graph_token", lambda: "test-token")
    monkeypatch.setattr(
        sweep, "summarize_pending", lambda cfg: {"summarized": 0, "summary_failed": 0}
    )


@pytest.mark.parametrize("first_download_fails", [False, True])
def test_sweep_deduplicates_and_stops_paging_at_cap(
    monkeypatch: pytest.MonkeyPatch,
    db: psycopg.Connection,
    sweep_graph: None,
    first_download_fails: bool,
) -> None:
    db.execute(
        "INSERT INTO cmap.transcript_candidate (external_ref, source_kind, raw_text) "
        "VALUES ('known', 'graph', 'Existing text')"
    )
    db.commit()
    monkeypatch.setattr(sweep, "MAX_NEW_PER_RUN", 2)
    downloads = []

    def pages(client, url, params=None):
        if url.endswith("/users"):
            yield {"id": "first"}
            yield {"id": "second"}
            return
        assert "/users/first/onlineMeetings/" in url
        for ref in ("known", "one", "one", "two"):
            yield {"id": ref, "transcriptContentUrl": ref}
        pytest.fail("The sweep kept enumerating transcripts after reaching the cap")

    def download(client, url, **kwargs):
        downloads.append(url)
        if url == "one" and first_download_fails:
            raise httpx.ReadTimeout("Graph timed out")
        return httpx.Response(200, text=VTT)

    monkeypatch.setattr(sweep, "graph_pages", pages)
    monkeypatch.setattr(sweep, "get_retry", download)
    counts = sweep.run_sweep()

    assert downloads == ["one", "two"]
    assert (counts["users"], counts["seen"]) == (1, 4)
    assert counts["new"] == (1 if first_download_fails else 2)
    assert counts["failed"] == int(first_download_fails)
    assert db.execute(
        "SELECT external_ref FROM cmap.transcript_candidate ORDER BY external_ref"
    ).fetchall() == [("known",), ("one",), ("two",)]


@pytest.mark.parametrize("error_status", [None, 401, 503])
def test_sweep_retries_failed_download_after_cooldown(
    monkeypatch: pytest.MonkeyPatch,
    db: psycopg.Connection,
    sweep_graph: None,
    error_status: int | None,
) -> None:
    monkeypatch.setattr(sweep, "graph_pages", lambda *a, **kw: iter([{"id": "user"}]))
    monkeypatch.setattr(
        sweep,
        "transcript_refs",
        lambda *a: iter(
            {"id": ref, "transcriptContentUrl": ref, "_kind": "meeting"}
            for ref in ("retry", "retry", "next")
        ),
    )
    downloads = []

    def download(client, url, **kwargs):
        downloads.append(url)
        if downloads == ["retry"]:
            if error_status is None:
                raise httpx.ReadTimeout("Graph timed out")
            raise _graph_error(error_status)
        return httpx.Response(200, text=VTT)

    monkeypatch.setattr(sweep, "get_retry", download)
    assert sweep.run_sweep()["failed"] == 1
    assert downloads == ["retry", "next"]
    row_id, state, raw_text, error = db.execute(
        "SELECT id, state, raw_text, error FROM cmap.transcript_candidate "
        "WHERE external_ref = 'retry'"
    ).fetchone()
    assert (state, raw_text) == ("failed", "")
    assert error
    db.commit()

    assert sweep.run_sweep()["new"] == 0
    assert downloads == ["retry", "next"]
    db.execute(
        "UPDATE cmap.transcript_candidate SET updated_at = now() - interval '7 hours' "
        "WHERE id = %s",
        (row_id,),
    )
    db.commit()

    assert sweep.run_sweep()["new"] == 1
    assert downloads == ["retry", "next", "retry"]
    assert db.execute(
        "SELECT id, state, raw_text, error FROM cmap.transcript_candidate "
        "WHERE external_ref = 'retry'"
    ).fetchone() == (row_id, "new", sweep.vtt_to_lines(VTT)[0], None)


def test_summarize_pending_filters_and_updates_rows(
    monkeypatch: pytest.MonkeyPatch, db: psycopg.Connection
) -> None:
    db.execute(
        "INSERT INTO cmap.transcript_candidate "
        "(external_ref, source_kind, raw_text, state, summarized_at, summary_error) VALUES "
        "('old', 'graph', 'old', 'new', now() - interval '7 hours', 'old error'), "
        "('recent', 'graph', 'recent', 'new', now() - interval '5 hours', 'recent error'), "
        "('failed', 'graph', 'failed', 'failed', NULL, NULL), "
        "('empty', 'graph', '', 'new', NULL, NULL), "
        "('new', 'graph', 'new', 'new', NULL, NULL)"
    )
    db.commit()
    seen = set()

    def summarize(text, cfg):
        seen.add(text)
        if text == "new":
            raise RuntimeError("summarizer unavailable")
        return "A successful meeting summary."

    monkeypatch.setattr(sweep, "summarize", summarize)
    assert sweep.summarize_pending(sweep.get_settings()) == {"summarized": 1, "summary_failed": 1}
    assert seen == {"old", "new"}
    assert db.execute(
        "SELECT external_ref, summary, summary_error, summarized_at = updated_at "
        "FROM cmap.transcript_candidate WHERE external_ref IN ('old', 'new') "
        "ORDER BY external_ref"
    ).fetchall() == [
        ("new", None, "summarizer unavailable", True),
        ("old", "A successful meeting summary.", None, True),
    ]


def test_queue_meeting_sweep_once_per_hour(
    monkeypatch: pytest.MonkeyPatch, db: psycopg.Connection
) -> None:
    for key in ("AZURE_TENANT_ID", "AZURE_GRAPH_CLIENT_ID", "AZURE_GRAPH_CLIENT_SECRET"):
        monkeypatch.setenv(key, "test")

    assert sweep.maybe_queue_meeting_sweep() is True
    assert sweep.maybe_queue_meeting_sweep() is False
    db.execute("UPDATE cmap.job SET state = 'running' WHERE kind = 'meeting_sweep'")
    db.commit()
    assert sweep.maybe_queue_meeting_sweep() is False
    db.execute("UPDATE cmap.job SET state = 'done', finished_at = now() WHERE kind = 'meeting_sweep'")
    db.commit()
    assert sweep.maybe_queue_meeting_sweep() is False
    db.execute("UPDATE cmap.job SET finished_at = now() - interval '61 minutes' WHERE kind = 'meeting_sweep'")
    db.commit()
    assert sweep.maybe_queue_meeting_sweep() is True
    assert db.execute("SELECT count(*) FROM cmap.job WHERE kind = 'meeting_sweep'").fetchone() == (2,)


def test_meetings_api_admin_only_and_hides_text(client, db, admin_headers, user_headers) -> None:  # type: ignore[no-untyped-def]
    db.execute(
        "INSERT INTO cmap.transcript_candidate (external_ref, source_kind, title, raw_text, "
        "summary) VALUES ('t-api-1', 'graph', 'Teams call', 'secret words', 'A summary.')"
    )
    db.commit()
    assert client.get("/meetings").status_code == 401
    assert client.get("/meetings", headers=user_headers).status_code == 403
    r = client.get("/meetings", headers=admin_headers)
    assert r.status_code == 200
    row = next(x for x in r.json() if x["title"] == "Teams call")
    assert row["summary"] == "A summary."
    assert "raw_text" not in row and "secret words" not in json.dumps(row)
