"""Step 1.6 gate: kept thread becomes one dated, packed transcript source.

Synthetic data only. Pure tests at the top; database tests use the shared
fixtures (CI has Postgres).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from conftest import fake_embeddings

from brain.config import get_settings
from brain.intake import ingest
from brain.read.pipeline import handle_read_source
from brain.read.transcript import parse_turns, read_message_thread

NOW = datetime(2026, 11, 19, 12, tzinfo=UTC)


def row(text: str, minutes: int, who: str = "Pat Example", **kw: Any) -> dict[str, Any]:
    r = {
        "author_ref": "u1",
        "sent_at": NOW - timedelta(hours=1) + timedelta(minutes=minutes),
        "body_text": text,
        "raw": {"from": {"user": {"displayName": who}}},
        "drop_reason": None,
        "collected_at": NOW,
    }
    r.update(kw)
    return r


def test_rendered_thread_round_trips_parse_turns() -> None:
    rows = [
        row(
            "Ship Friday: confirmed", 0, who="Dr. Pat Q. Example-Long Name The Third Jr"
        ),
        row("Ok 10:30 works", 1, who="Lee: Ops"),
    ]
    turns = parse_turns(ingest.render_thread(rows, "teams_chat", NOW))
    assert [t.speaker for t in turns] == [
        "Dr. Pat Q. Example-Long Name The Third Jr",
        "Lee: Ops",
    ]
    assert [t.text for t in turns] == ["Ship Friday: confirmed", "Ok 10:30 works"]
    assert turns[0].t0 == rows[0]["sent_at"].isoformat()


def test_short_messages_packed_into_full_passages() -> None:
    rows = [
        row(f"short note number {i} about the order", i % 50, who="AB"[i % 2])
        for i in range(400)
    ]
    rendered = ingest.render_thread(rows, "teams_chat", NOW)
    chunks = read_message_thread(rendered)
    tokens = sum(c.token_count for c in chunks)
    assert len(chunks) <= tokens // 400 + 2
    assert all(c.token_count <= 400 for c in chunks)
    # Every message is whole in exactly one passage.
    body = "\n".join(c.text for c in chunks)
    for i in range(400):
        assert body.count(f"short note number {i} about") == 1


def test_bad_timestamp_falls_back_to_collected_at_never_future() -> None:
    future = NOW + timedelta(days=400)
    assert ingest.safe_time(None, NOW - timedelta(days=1), NOW) == NOW - timedelta(
        days=1
    )
    assert ingest.safe_time(future, NOW, NOW) == NOW


def test_secret_message_is_a_marker_turn() -> None:
    rows = [row("first", 0), row("", 1, drop_reason="secret")]
    turns = json.loads(ingest.render_thread(rows, "teams_chat", NOW))
    assert (
        turns[1]["text"] == ingest.REMOVED_MARKER
        and turns[1]["speaker"] == "Pat Example"
    )


def test_speakers_per_origin() -> None:
    assert (
        ingest.speaker_of("email", None, {"from": {"emailAddress": {"name": "Pat  E"}}})
        == "Pat E"
    )
    assert ingest.speaker_of("clickup", "ClickUp", {}) == "ClickUp"
    assert ingest.speaker_of("clickup", "9", {"user": {"username": "lee"}}) == "lee"
    assert ingest.speaker_of("teams_chat", None, {}) == "Unknown"


def test_handle_intake_ingest_forwards_thread_prefix_and_days(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Any, ...]] = []
    fake_settings = object()
    monkeypatch.setattr(ingest, "get_settings", lambda: fake_settings)

    def _fake_run(
        settings: Any,
        origin: str | None = None,
        limit: int | None = None,
        *,
        thread_prefix: str | None = None,
        days: int | None = None,
    ) -> dict[str, Any]:
        calls.append((settings, origin, limit, thread_prefix, days))
        return {"created": 1}

    monkeypatch.setattr(ingest, "run", _fake_run)
    ingest.handle_intake_ingest(
        {
            "payload": {
                "origin": "email",
                "limit": "25",
                "days": "14",
                "thread_prefix": "pilot-",
            }
        }
    )
    assert calls == [(fake_settings, "email", 25, "pilot-", 14)]


@pytest.mark.parametrize("bad_days", ["abc", True, False, 0, -3, 1.5])
def test_handle_intake_ingest_rejects_malformed_days(
    bad_days: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ingest, "run", lambda *a, **k: pytest.fail("run must not be called"))
    with pytest.raises(ValueError, match="days must be a positive integer"):
        ingest.handle_intake_ingest({"payload": {"days": bad_days}})


@pytest.mark.parametrize("bad_limit", ["xyz", True, False, 0, -1, 2.5])
def test_handle_intake_ingest_rejects_malformed_limit(
    bad_limit: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ingest, "run", lambda *a, **k: pytest.fail("run must not be called"))
    with pytest.raises(ValueError, match="limit must be a positive integer"):
        ingest.handle_intake_ingest({"payload": {"limit": bad_limit}})


# --- database ------------------------------------------------------------


def _seed(db: Any, key: str, texts: list[str]) -> None:
    db.execute(
        "INSERT INTO cmap.intake_thread (origin, thread_key, title, started_at) "
        "VALUES ('teams_chat', %s, 'synthetic chat', now()) ON CONFLICT DO NOTHING",
        (key,),
    )
    for i, t in enumerate(texts):
        db.execute(
            "INSERT INTO cmap.intake_item (origin, external_id, thread_key, author_ref, sent_at, "
            "body_text, raw, content_hash) VALUES ('teams_chat', %s, %s, 'u1', "
            "'2026-11-10T14:00:00Z'::timestamptz + make_interval(mins => %s), %s, "
            '\'{"from": {"user": {"displayName": "Pat Example"}}}\'::jsonb, \'h\') '
            "ON CONFLICT DO NOTHING",
            (f"{key}-{i}", key, i, t),
        )
    db.commit()


@pytest.fixture(autouse=True)
def _fresh_intake(request: pytest.FixtureRequest) -> None:
    """DB tests start with empty intake staging (TRUNCATE of sources may not reach it)."""
    if "db" not in request.fixturenames:
        return
    db = request.getfixturevalue("db")
    db.execute("TRUNCATE cmap.intake_item, cmap.intake_thread")
    db.commit()


@pytest.fixture()
def capped(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("BRAIN_INTAKE_MAX_USD", "5")
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


def test_thread_becomes_one_dated_source_and_reingest_versions(
    db: Any, storage: Any, capped: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from brain.read import dates

    called: list[int] = []
    monkeypatch.setattr(dates, "document_text_date", lambda *a, **k: called.append(1))
    _seed(
        db,
        "syn-chat-1",
        ["The art proof goes to the licensor first.", "Then the factory."],
    )
    out = ingest.run(capped)
    assert out["created"] == 1
    src = db.execute(
        "SELECT id, kind, origin, external_ref, effective_date, date_origin FROM cmap.source"
    ).fetchall()
    assert len(src) == 1
    sid, kind, origin, ref, eff, dorigin = src[0]
    assert (kind, origin, ref, dorigin) == (
        "transcript",
        "teams_chat",
        "syn-chat-1",
        "message_record",
    )
    assert str(eff) == "2026-11-10"
    # Unchanged thread: no second source.
    assert ingest.run(capped).get("unchanged") == 1
    # Thread gained a message: a new source that supersedes the old one.
    _seed(
        db,
        "syn-chat-1",
        ["The art proof goes to the licensor first.", "Then the factory.", "Then QA."],
    )
    assert ingest.run(capped).get("versioned") == 1
    n, versions = db.execute(
        "SELECT (SELECT count(*) FROM cmap.source), "
        "(SELECT count(*) FROM cmap.source_version WHERE supersedes_source_id = %s "
        "AND origin = 'intake_update')",
        (sid,),
    ).fetchone()
    assert (n, versions) == (2, 1)
    # The date is resolved without a date-model call.
    row_ = db.execute(
        "SELECT id, kind, original_filename, storage_path, effective_date, date_origin, created_at "
        "FROM cmap.source WHERE id = %s",
        (sid,),
    ).fetchone()
    eff2, origin2 = dates.resolve_and_store(db, row_, data=None, settings=capped)
    assert (str(eff2), origin2) == ("2026-11-10", "message_record") and not called


def test_cli_scope_ignores_threads_outside_literal_prefix(
    db: Any, storage: Any, capped: Any
) -> None:
    _seed(db, "pilot%_one", ["Approval goes to the supplier."])
    _seed(db, "pilotxyone", ["Use the vendor’s size chart."])
    _seed(db, "other-pilot", ["The factory creates the final proof."])

    ingest.main(["--thread-prefix", "pilot%_"])

    assert db.execute("SELECT external_ref FROM cmap.source").fetchall() == [
        ("pilot%_one",)
    ]
    assert db.execute(
        "SELECT count(*) FROM cmap.job WHERE kind = 'read_source'"
    ).fetchone() == (1,)


def test_spend_cap_stops_queueing(
    db: Any, storage: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BRAIN_INTAKE_MAX_USD", "0.0015")
    get_settings.cache_clear()
    for k in ("cap-a", "cap-b", "cap-c"):
        _seed(db, k, [f"The vendor needs the final artwork approved first ({k})."])
    out = ingest.run(get_settings())
    get_settings.cache_clear()
    assert out["created"] == 1 and out.get("stopped_at_cap")
    assert db.execute("SELECT count(*) FROM cmap.source").fetchone()[0] == 1


def test_no_cap_no_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BRAIN_INTAKE_MAX_USD", raising=False)
    get_settings.cache_clear()
    with pytest.raises(RuntimeError):
        ingest.run(get_settings())
    get_settings.cache_clear()


def test_sweep_disabled_by_default() -> None:
    assert ingest.maybe_queue_intake() is False


def test_days_window_and_3pass_cost_rate(
    db: Any, storage: Any, capped: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--days filters staged threads by recency so the 14-day pilot never drains
    older staged backlog, and estimated_usd_per_passage reflects 3-pass batch vs sync."""
    del storage
    _seed(db, "old-thread", ["Old factory tooling note."])
    db.execute(
        "UPDATE cmap.intake_thread SET started_at = now() - interval '45 days', "
        "ended_at = now() - interval '45 days', updated_at = now() - interval '45 days' "
        "WHERE thread_key = 'old-thread'"
    )
    _seed(db, "recent-thread", ["Recent sample room approval note."])
    db.execute(
        "UPDATE cmap.intake_thread SET started_at = now() - interval '5 days', "
        "ended_at = now() - interval '3 days' WHERE thread_key = 'recent-thread'"
    )
    db.commit()

    monkeypatch.setenv("BRAIN_MESSAGE_RELATIONS_MODEL", "openai/gpt-6-luna")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-batch")
    get_settings.cache_clear()
    s_batch = get_settings()
    assert ingest.estimated_usd_per_passage(s_batch) == pytest.approx(0.0018)

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    s_sync = get_settings()
    assert ingest.estimated_usd_per_passage(s_sync) == pytest.approx(0.0032)

    out = ingest.run(capped, days=14)
    get_settings.cache_clear()
    assert out["created"] == 1
    assert db.execute("SELECT external_ref FROM cmap.source").fetchall() == [
        ("recent-thread",)
    ]


def test_spend_cap_never_uploads_orphan_objects(
    db: Any, storage: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    uploads: list[str] = []
    real_upload = storage.upload

    def _spy_upload(key: str, data: bytes, content_type: str) -> None:
        uploads.append(key)
        real_upload(key, data, content_type)

    monkeypatch.setattr(storage, "upload", _spy_upload)
    for k in ("orphan-a", "orphan-b", "orphan-c"):
        _seed(db, k, [f"The vendor needs final artwork approved first ({k})."])

    monkeypatch.setenv("BRAIN_INTAKE_MAX_USD", "0.0015")
    get_settings.cache_clear()
    out = ingest.run(get_settings())
    get_settings.cache_clear()

    assert out["created"] == 1 and out.get("stopped_at_cap") is True
    db_paths = [
        r[0]
        for r in db.execute(
            "SELECT storage_path FROM cmap.source ORDER BY storage_path"
        ).fetchall()
    ]
    assert len(uploads) == 1
    assert storage.list() == sorted(db_paths)

    # A second run whose cap cannot afford the next pending thread must still
    # reuse the unchanged thread's sha256 without uploading, then stop cleanly.
    uploads.clear()
    monkeypatch.setenv("BRAIN_INTAKE_MAX_USD", "0.0005")
    get_settings.cache_clear()
    out2 = ingest.run(get_settings())
    get_settings.cache_clear()

    assert out2.get("unchanged") == 1
    assert out2.get("stopped_at_cap") is True
    assert out2.get("created", 0) == 0
    assert uploads == []
    assert storage.list() == sorted(db_paths)


def test_handle_read_source_packs_message_threads_vs_speaker_run_transcripts(
    db: Any, storage: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_embeddings(monkeypatch)
    turns_json = json.dumps(
        [
            {
                "speaker": "Alice",
                "text": "Need approval on the proof.",
                "timestamp": "2026-11-10T14:00:00+00:00",
            },
            {
                "speaker": "Bob",
                "text": "Sent it to the licensor.",
                "timestamp": "2026-11-10T14:01:00+00:00",
            },
            {
                "speaker": "Alice",
                "text": "Great, tell the factory next.",
                "timestamp": "2026-11-10T14:02:00+00:00",
            },
            {
                "speaker": "Bob",
                "text": "Confirmed with factory QA.",
                "timestamp": "2026-11-10T14:03:00+00:00",
            },
        ]
    ).encode("utf-8")

    storage.upload("test/msg-thread.json", turns_json, "application/json")
    storage.upload("test/transcript.json", turns_json, "application/json")

    msg_sid = str(
        db.execute(
            "INSERT INTO cmap.source (kind, title, original_filename, storage_path, "
            "sha256, bytes, effective_date, date_origin, origin, external_ref) "
            "VALUES ('transcript', 'msg', 'thread.json', 'test/msg-thread.json', "
            "'msg-sha', %s, '2026-11-10', 'message_record', 'teams_chat', 'th-1') "
            "RETURNING id",
            (len(turns_json),),
        ).fetchone()[0]
    )
    tr_sid = str(
        db.execute(
            "INSERT INTO cmap.source (kind, title, original_filename, storage_path, "
            "sha256, bytes, effective_date, date_origin, origin, external_ref) "
            "VALUES ('transcript', 'tr', 'transcript.json', 'test/transcript.json', "
            "'tr-sha', %s, '2026-11-10', 'admin', NULL, NULL) "
            "RETURNING id",
            (len(turns_json),),
        ).fetchone()[0]
    )
    db.commit()

    handle_read_source({"id": None, "payload": {"source_id": msg_sid}})
    handle_read_source({"id": None, "payload": {"source_id": tr_sid}})

    msg_chunks = [
        r[0]
        for r in db.execute(
            "SELECT text FROM cmap.chunk WHERE source_id = %s ORDER BY ordinal",
            (msg_sid,),
        ).fetchall()
    ]
    tr_chunks = [
        r[0]
        for r in db.execute(
            "SELECT text FROM cmap.chunk WHERE source_id = %s ORDER BY ordinal",
            (tr_sid,),
        ).fetchall()
    ]

    assert len(msg_chunks) == 1
    assert "Alice: Need approval on the proof." in msg_chunks[0]
    assert "Bob: Confirmed with factory QA." in msg_chunks[0]

    assert tr_chunks == [
        "Alice: Need approval on the proof.",
        "Bob: Sent it to the licensor.",
        "Alice: Great, tell the factory next.",
        "Bob: Confirmed with factory QA.",
    ]
