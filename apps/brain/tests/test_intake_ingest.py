"""Step 1.6 gate: kept thread becomes one dated, packed transcript source.

Synthetic data only. Pure tests at the top; database tests use the shared
fixtures (CI has Postgres).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.config import get_settings
from brain.intake import ingest
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
