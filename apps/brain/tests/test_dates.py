"""D1 gate: every source has an effective_date and a date_origin.

One test per origin (admin / meeting start / interview answer / document text /
file metadata / upload time floor), plus backfill idempotency, the never-NULL
invariant and the ``cmap.relation_dated`` view.
"""

from __future__ import annotations

import io
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from conftest import FIXTURES_DIR, fake_embeddings, fake_vision
from fastapi.testclient import TestClient

from brain.config import get_settings
from brain.interview import inbound as inbound_mod
from brain.interview.inbound import handle_inbound
from brain.read import dates as dates_mod
from brain.read.dates import (
    ORIGIN_ADMIN,
    ORIGIN_DOCUMENT,
    ORIGIN_FILE_META,
    ORIGIN_INTERVIEW,
    ORIGIN_MEETING,
    ORIGIN_UPLOAD,
    file_metadata_date,
    handle_backfill_dates,
    upload_floor,
)
from brain.read.pipeline import handle_read_source
from brain.read.transcript import meeting_start_date

EASTERN = ZoneInfo("America/New_York")

TEAMS_METADATA_TRANSCRIPT = (
    '{"startDateTime": "2026-03-14T10:00:00Z", "transcript": ['
    '{"speaker": "Ilona", "text": "Morning all, let us start."},'
    '{"speaker": "Marco", "text": "Morning."}]}'
)


def _upload(
    client: TestClient,
    headers: dict[str, str],
    name: str,
    data: bytes,
) -> Any:
    return client.post(
        "/sources",
        headers=headers,
        files={"file": (name, data, "application/octet-stream")},
    )


def _run_read(db: Any, monkeypatch: pytest.MonkeyPatch, source_id: str) -> None:
    """Run the queued ``read_source`` job for one source."""
    fake_embeddings(monkeypatch)
    job = db.execute(
        "SELECT id, kind, payload FROM cmap.job WHERE kind = 'read_source' "
        "AND payload->>'source_id' = %s",
        (source_id,),
    ).fetchone()
    assert job is not None, f"no read_source job queued for {source_id}"
    handle_read_source({"id": job[0], "kind": job[1], "payload": job[2]})


def _no_date_model(monkeypatch: pytest.MonkeyPatch) -> list[list[dict[str, Any]]]:
    """Replay a flat-seat answer that finds no printed date; return the log."""
    calls: list[list[dict[str, Any]]] = []

    def _post(messages: list[dict[str, Any]], settings: Any) -> dict[str, Any]:
        del settings
        calls.append(messages)
        return {
            "choices": [{"message": {"content": '{"date": null}'}}],
            "usage": {"total_tokens": 7},
        }

    monkeypatch.setattr(dates_mod, "_post_chat", _post)
    return calls


def _date_row(db: Any, source_id: str) -> tuple[Any, str | None]:
    row = db.execute(
        "SELECT effective_date, date_origin FROM cmap.source WHERE id = %s",
        (source_id,),
    ).fetchone()
    assert row is not None
    return row[0], row[1]


def _docx_with_core(created_iso: str) -> bytes:
    """A minimal docx whose core properties carry ``created_iso``."""
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )
    document = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>Widget checklist</w:t></w:r></w:p></w:body></w:document>"
    )
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/">'
        f"<dcterms:created>{created_iso}</dcterms:created>"
        "</cp:coreProperties>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("[Content_Types].xml", content_types)
        package.writestr("_rels/.rels", rels)
        package.writestr("word/document.xml", document)
        package.writestr("docProps/core.xml", core)
    return buffer.getvalue()


def test_admin_entered_date_wins(
    client: TestClient,
    admin_headers: dict[str, str],
    storage: Any,
    monkeypatch: pytest.MonkeyPatch,
    db: Any,
) -> None:
    """A date entered at intake is kept through reading (top of precedence)."""
    _no_date_model(monkeypatch)
    response = client.post(
        "/sources/transcript",
        headers=admin_headers,
        json={
            "text": TEAMS_METADATA_TRANSCRIPT,
            "title": "Kickoff",
            "effective_date": "2026-01-15",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["date_origin"] == ORIGIN_ADMIN
    assert body["effective_date"] == "2026-01-15"

    _run_read(db, monkeypatch, body["id"])
    effective, origin = _date_row(db, body["id"])
    assert effective.isoformat() == "2026-01-15"
    assert origin == ORIGIN_ADMIN


def test_meeting_start_from_transcript_metadata(
    client: TestClient,
    admin_headers: dict[str, str],
    storage: Any,
    monkeypatch: pytest.MonkeyPatch,
    db: Any,
) -> None:
    """Teams/Recall meeting metadata dates a transcript at read time."""
    calls = _no_date_model(monkeypatch)
    response = client.post(
        "/sources/transcript",
        headers=admin_headers,
        json={"text": TEAMS_METADATA_TRANSCRIPT, "title": "Weekly sync"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    # Creation stamps the upload-time floor; reading upgrades it.
    assert body["date_origin"] == ORIGIN_UPLOAD
    assert body["effective_date"] is not None

    _run_read(db, monkeypatch, body["id"])
    effective, origin = _date_row(db, body["id"])
    assert effective.isoformat() == "2026-03-14"
    assert origin == ORIGIN_MEETING
    assert calls == []  # meeting metadata beat the document-text step

    # Nested metadata and an absolute first-turn timestamp also count.
    nested = (
        '{"metadata": {"meeting_started_at": "2026-04-02T13:30:00+02:00"},'
        ' "transcript": [{"speaker": "A", "text": "Hi."}]}'
    )
    assert meeting_start_date(nested).isoformat() == "2026-04-02"
    turn_t0 = (
        '[{"speaker": "A", "t0": "2026-05-09T11:00:00", "text": "Hello."}]'
    )
    assert meeting_start_date(turn_t0).isoformat() == "2026-05-09"
    assert meeting_start_date("Ilona: no metadata here.") is None


def test_interview_answer_timestamp(
    storage: Any,
    monkeypatch: pytest.MonkeyPatch,
    db: Any,
) -> None:
    """An interview answer is dated with its answer timestamp."""
    _no_date_model(monkeypatch)
    monkeypatch.setattr(inbound_mod, "classify_reply", lambda question, reply: "answer")
    employee_id = "00000000-0000-4000-8000-0000000000b1"
    db.execute(
        "INSERT INTO cmap.open_question (question, why, entity_ids, target_employee_id, "
        "state, asked_at) VALUES (%s, %s, %s, %s, 'asked', now())",
        (
            "Who signs licensing approvals?",
            "gap",
            ["00000000-0000-4000-8000-0000000000b1"],
            employee_id,
        ),
    )
    db.commit()

    reply = handle_inbound(
        email="employee@test.invalid",
        conversation_ref=None,
        text="Jessica signs it after Ilona checks the artwork.",
    )
    assert reply["handled"] is True
    source_id = reply["source_id"]
    effective, origin = _date_row(db, source_id)
    assert origin == ORIGIN_INTERVIEW
    assert effective == upload_floor() == datetime.now(EASTERN).date()

    # Reading keeps the interview timestamp.
    _run_read(db, monkeypatch, source_id)
    effective, origin = _date_row(db, source_id)
    assert origin == ORIGIN_INTERVIEW
    assert effective == datetime.now(EASTERN).date()


def test_document_text_date_from_model(
    client: TestClient,
    admin_headers: dict[str, str],
    storage: Any,
    monkeypatch: pytest.MonkeyPatch,
    db: Any,
) -> None:
    """A date printed in the document's header/footer/revision area wins."""
    captured: list[list[dict[str, Any]]] = []

    def _post(messages: list[dict[str, Any]], settings: Any) -> dict[str, Any]:
        del settings
        captured.append(messages)
        return {
            "choices": [{"message": {"content": '{"date": "2026-02-02"}'}}],
            "usage": {"total_tokens": 11},
        }

    monkeypatch.setattr(dates_mod, "_post_chat", _post)
    data = (
        b"Widget Policy Handbook\nHeader: Rev 4 - 2026-02-02\n"
        b"1. Scope\n2. Roles\nFooter: Widget Co internal\n"
    )
    response = _upload(client, admin_headers, "handbook.txt", data)
    assert response.status_code == 200, response.text
    body = response.json()
    _run_read(db, monkeypatch, body["id"])

    effective, origin = _date_row(db, body["id"])
    assert effective.isoformat() == "2026-02-02"
    assert origin == ORIGIN_DOCUMENT
    assert captured, "the document-text model call never ran"
    prompt = str(captured[0][0]["content"])
    assert "Widget Policy Handbook" in prompt
    assert "DATA" in prompt


def test_file_metadata_date(
    client: TestClient,
    admin_headers: dict[str, str],
    storage: Any,
    monkeypatch: pytest.MonkeyPatch,
    db: Any,
) -> None:
    """Office core properties date the file when nothing earlier hits."""
    _no_date_model(monkeypatch)
    data = _docx_with_core("2025-11-30T09:00:00Z")
    response = _upload(client, admin_headers, "checklist.docx", data)
    assert response.status_code == 200, response.text
    body = response.json()
    _run_read(db, monkeypatch, body["id"])

    effective, origin = _date_row(db, body["id"])
    assert effective.isoformat() == "2025-11-30"
    assert origin == ORIGIN_FILE_META

    # Dispatch is on the routed kind: CSV/TSV route out of ``text`` and
    # never reach an Office parser (Phase-A drift).
    assert file_metadata_date("csv", b"a,b\n1,2\n") is None
    assert file_metadata_date("tsv", b"a\tb\n1\t2\n") is None
    assert file_metadata_date("text", b"plain") is None
    assert file_metadata_date("docx", data).isoformat() == "2025-11-30"


def test_upload_time_floor_never_null(
    client: TestClient,
    admin_headers: dict[str, str],
    user_headers: dict[str, str],
    storage: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    db: Any,
) -> None:
    """Upload time is the floor: every creation path leaves a dated source."""
    _no_date_model(monkeypatch)
    fake_vision(monkeypatch, "vision_flowchart.json")

    pdf = (FIXTURES_DIR / "licensing-approval-procedure.pdf").read_bytes()
    assert _upload(client, admin_headers, "licensing-approval-procedure.pdf", pdf).status_code == 200
    assert (
        client.post(
            "/sources/transcript",
            headers=admin_headers,
            json={"text": "Ilona: nothing else to add."},
        ).status_code
        == 200
    )
    storage.objects["old/orphan-notes.txt"] = b"orphan notes with no dates"
    assert client.post("/sources/import-bucket", headers=admin_headers).status_code == 200

    department = tmp_path / "Licensing"
    department.mkdir()
    (department / "notes.txt").write_bytes(b"plain notes")
    monkeypatch.setattr(get_settings(), "brain_import_dir", str(tmp_path), raising=False)
    assert (
        client.post(
            "/sources/import-folder",
            headers=admin_headers,
            json={"path": str(tmp_path)},
        ).status_code
        == 200
    )

    rows = db.execute(
        "SELECT id::text, effective_date, date_origin, kind, original_filename "
        "FROM cmap.source ORDER BY created_at"
    ).fetchall()
    assert rows, "no sources were created"
    for source_id, effective, origin, _kind, _name in rows:
        assert effective is not None, f"{source_id} is undated"
        assert origin is not None, f"{source_id} has no date_origin"
        assert origin == ORIGIN_UPLOAD or origin == ORIGIN_FILE_META

    # Folder imports carry the file's own mtime as the metadata date.
    by_name = {name: (effective, origin) for _id, effective, origin, _k, name in rows}
    assert by_name["notes.txt"][1] == ORIGIN_FILE_META

    # Reading never turns a dated source into an undated one.
    for source_id, _effective, _origin, _kind, _name in rows:
        _run_read(db, monkeypatch, source_id)
        effective, origin = _date_row(db, source_id)
        assert effective is not None and origin is not None

    assert (
        client.post("/sources/import-bucket", headers=user_headers).status_code == 403
    )


def test_backfill_dates_idempotent(
    client: TestClient,
    admin_headers: dict[str, str],
    user_headers: dict[str, str],
    storage: Any,
    monkeypatch: pytest.MonkeyPatch,
    db: Any,
) -> None:
    """The backfill dates every legacy row once and a second run is a no-op."""
    _no_date_model(monkeypatch)
    # Legacy rows as production has them: no date at all, plus one holding an
    # admin-entered date with no origin (pre-D1 writes).
    legacy_ids = {
        "legacy-sync.json": "99999999-9999-4999-8999-999999999001",
        "legacy-notes.txt": "99999999-9999-4999-8999-999999999002",
        "legacy-admin": "99999999-9999-4999-8999-999999999003",
    }
    for name, kind, data in (
        ("legacy-sync.json", "transcript", TEAMS_METADATA_TRANSCRIPT.encode()),
        ("legacy-notes.txt", "text", b"just notes, no dates anywhere"),
    ):
        source_id = legacy_ids[name]
        storage.objects[f"cmap/{source_id}/{name}"] = data
        db.execute(
            "INSERT INTO cmap.source (id, kind, title, storage_path, sha256, bytes) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (source_id, kind, name, f"cmap/{source_id}/{name}", source_id, len(data)),
        )
    admin_id = legacy_ids["legacy-admin"]
    db.execute(
        "INSERT INTO cmap.source (id, kind, title, storage_path, sha256, bytes, effective_date) "
        "VALUES (%s, 'text', 'letter.txt', %s, %s, 4, '2026-01-05')",
        (admin_id, f"cmap/{admin_id}/letter.txt", admin_id),
    )
    storage.objects[f"cmap/{admin_id}/letter.txt"] = b"signed letter"
    db.commit()

    response = client.post("/sources/backfill-dates", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"pending": 2, "queued": True}

    handle_backfill_dates({"id": None, "kind": "backfill_dates", "payload": {}})
    first = {name: _date_row(db, source_id) for name, source_id in legacy_ids.items()}
    assert first["legacy-sync.json"][1] == ORIGIN_MEETING
    assert first["legacy-admin"][1] == ORIGIN_ADMIN
    assert first["legacy-admin"][0].isoformat() == "2026-01-05"
    for name, (effective, origin) in first.items():
        assert effective is not None and origin is not None, name

    second_response = client.post("/sources/backfill-dates", headers=admin_headers)
    assert second_response.json() == {"pending": 0, "queued": False}
    handle_backfill_dates({"id": None, "kind": "backfill_dates", "payload": {}})
    second = {name: _date_row(db, source_id) for name, source_id in legacy_ids.items()}
    assert second == first

    denied = client.post("/sources/backfill-dates", headers=user_headers)
    assert denied.status_code == 403


def test_relation_dated_view_inherits_source_date(db: Any) -> None:
    """Relations and mentions carry their source's date in the view."""
    db.execute(
        "INSERT INTO cmap.source (id, kind, title, storage_path, sha256, bytes, "
        "effective_date, date_origin) VALUES "
        "('11111111-1111-4111-8111-111111111111', 'text', 'dated', 'cmap/d/a.txt', "
        "'d1', 1, '2026-03-14', 'meeting_start')"
    )
    db.execute(
        "INSERT INTO cmap.chunk (id, source_id, ordinal, locator, text, token_count) VALUES "
        "('22222222-2222-4222-8222-222222222222', '11111111-1111-4111-8111-111111111111', "
        "0, '{}'::jsonb, 'chunk', 1)"
    )
    db.execute(
        "INSERT INTO cmap.mention (id, chunk_id, entity_type, surface_name, normalized_name, quote) VALUES "
        "('33333333-3333-4333-8333-333333333333', '22222222-2222-4222-8222-222222222222', "
        "'Person', 'Jessica', 'jessica', 'Jessica signs'), "
        "('44444444-4444-4444-8444-444444444444', '22222222-2222-4222-8222-222222222222', "
        "'Person', 'Ilona', 'ilona', 'Ilona checks')"
    )
    db.execute(
        "INSERT INTO cmap.relation (chunk_id, from_mention_id, to_mention_id, rel_type, "
        "description, stance, confidence, quote) VALUES "
        "('22222222-2222-4222-8222-222222222222', '33333333-3333-4333-8333-333333333333', "
        "'44444444-4444-4444-8444-444444444444', 'APPROVES', 'Jessica approves after Ilona', "
        "'practice', 0.9, 'Jessica signs it')"
    )
    db.commit()

    rows = db.execute(
        "SELECT row_kind, effective_date::text, date_origin FROM cmap.relation_dated"
    ).fetchall()
    by_kind = {row_kind: (effective, origin) for row_kind, effective, origin in rows}
    assert by_kind["relation"] == ("2026-03-14", ORIGIN_MEETING)
    assert by_kind["mention"] == ("2026-03-14", ORIGIN_MEETING)
    assert len(rows) == 3
