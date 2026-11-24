"""Unit tests for the Teams transcript sweep (no live Graph or ScaleDown calls)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

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
