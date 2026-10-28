"""Step 2 gate: source intake takes the fixture corpus and rejects hostile input."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from uuid import uuid4

from conftest import FIXTURES_DIR
from fastapi.testclient import TestClient

from brain.config import get_settings

FIXTURE_FILES = [
    "licensing-approval-procedure.pdf",
    "licensing-approval-flowchart.png",
    "sample-room-checklist.docx",
    "open-po-exceptions.xlsx",
]


def _upload(
    client: TestClient,
    headers: dict[str, str],
    name: str,
    data: bytes,
    **form: str,
):
    return client.post(
        "/sources",
        headers=headers,
        files={"file": (name, data, "application/octet-stream")},
        data=form,
    )


def _list_sources(client: TestClient, headers: dict[str, str]) -> list[dict]:
    response = client.get("/sources", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["sources"]


def test_five_fixtures_produce_five_queued_rows(
    client: TestClient,
    admin_headers: dict[str, str],
    db,
) -> None:
    """Uploading the fixture set lands five sources queued for reading."""
    for name in FIXTURE_FILES:
        data = (FIXTURES_DIR / name).read_bytes()
        response = _upload(client, admin_headers, name, data)
        assert response.status_code == 200, response.text
        assert response.json()["duplicate"] is False
    transcript = (FIXTURES_DIR / "teams-approval-2026-03-14.txt").read_text(
        encoding="utf-8"
    )
    response = client.post(
        "/sources/transcript",
        headers=admin_headers,
        json={"text": transcript, "title": "Teams approval 2026-03-14"},
    )
    assert response.status_code == 200, response.text

    rows = _list_sources(client, admin_headers)
    assert len(rows) == 5
    assert sorted(row["kind"] for row in rows) == [
        "docx",
        "image",
        "pdf",
        "transcript",
        "xlsx",
    ]
    assert all(row["read_state"] == "queued" for row in rows)

    job_count = db.execute(
        "SELECT count(*) FROM cmap.job WHERE kind = 'read_source'"
    ).fetchone()
    assert job_count[0] == 5


def test_duplicate_upload_returns_same_id(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    """A byte-identical re-upload returns the first id and adds no row."""
    data = (FIXTURES_DIR / "licensing-approval-procedure.pdf").read_bytes()
    first = _upload(client, admin_headers, "licensing-approval-procedure.pdf", data)
    assert first.status_code == 200, first.text
    second = _upload(client, admin_headers, "licensing-approval-procedure.pdf", data)
    assert second.status_code == 200, second.text
    assert second.json()["duplicate"] is True
    assert second.json()["id"] == first.json()["id"]
    assert len(_list_sources(client, admin_headers)) == 1


def test_rejects_over_200mb(
    client: TestClient,
    admin_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    """An upload larger than the 200 MB cap is refused with HTTP 413."""
    big = tmp_path / "big.pdf"
    with open(big, "wb") as handle:
        for _ in range(201):
            handle.write(b"\0" * (1024 * 1024))
    with open(big, "rb") as handle:
        response = client.post(
            "/sources",
            headers=admin_headers,
            files={"file": ("big.pdf", handle, "application/octet-stream")},
        )
    assert response.status_code == 413, response.text


def test_rejects_mismatched_magic(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    """An executable renamed .pdf is refused because the bytes disagree."""
    response = _upload(
        client,
        admin_headers,
        "fake.pdf",
        b"MZ\x90\x00 this is not a pdf",
    )
    assert response.status_code == 400, response.text


def test_office_zip_ratio_limit(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    """A zip-bomb .docx that expands past 100 MB is aborted with HTTP 413."""
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", b"\0" * (101 * 1024 * 1024))
    response = _upload(client, admin_headers, "bomb.docx", payload.getvalue())
    assert response.status_code == 413, response.text


def test_transcript_line_cap(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    """A transcript over 200,000 lines is refused with a message."""
    text = "Ilona: filler line\n" * 200_001
    response = client.post(
        "/sources/transcript",
        headers=admin_headers,
        json={"text": text},
    )
    assert response.status_code == 413, response.text
    assert "200000" in response.json()["detail"]


def test_storage_key_is_uuid_based(
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    """A traversal filename can never escape the uuid-based storage key."""
    data = (FIXTURES_DIR / "licensing-approval-procedure.pdf").read_bytes()
    response = _upload(client, admin_headers, "../../etc/passwd.pdf", data)
    assert response.status_code == 200, response.text
    key = response.json()["storage_path"]
    assert re.fullmatch(
        r"cmap/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
        r"/passwd\.pdf",
        key,
    )
    assert ".." not in key

    no_extension = _upload(client, admin_headers, "../../etc/passwd", data)
    assert no_extension.status_code == 400


def test_import_bucket_ingests_existing_objects(
    client: TestClient,
    admin_headers: dict[str, str],
    storage,
) -> None:
    """Bucket import pulls Oracle 1 uploads and dedupes on a second run."""
    storage.objects["admin/abc/old-upload.pdf"] = (
        FIXTURES_DIR / "licensing-approval-procedure.pdf"
    ).read_bytes()
    first = client.post("/sources/import-bucket", headers=admin_headers)
    assert first.status_code == 200, first.text
    assert first.json() == {"imported": 1, "duplicates": 0, "errors": []}
    rows = _list_sources(client, admin_headers)
    assert rows[0]["original_filename"] == "old-upload.pdf"

    second = client.post("/sources/import-bucket", headers=admin_headers)
    assert second.json() == {"imported": 0, "duplicates": 1, "errors": []}


def test_import_folder_sets_department_hint(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Folder import uses the first folder level as the department hint."""
    department = tmp_path / "Licensing"
    department.mkdir()
    (department / "policy.pdf").write_bytes(b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n")
    (tmp_path / "notes.txt").write_bytes(b"plain notes")
    monkeypatch.setattr(
        get_settings(), "brain_import_dir", str(tmp_path), raising=False
    )

    response = client.post(
        "/sources/import-folder",
        headers=admin_headers,
        json={"path": str(tmp_path)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["imported"] == 2
    hints = {
        row["original_filename"]: row["department_hint"]
        for row in _list_sources(client, admin_headers)
    }
    assert hints["policy.pdf"] == "Licensing"
    assert hints["notes.txt"] is None

    outside = client.post(
        "/sources/import-folder",
        headers=admin_headers,
        json={"path": "C:/Windows"},
    )
    assert outside.status_code == 400


def test_delete_removes_source_and_queues_project(
    client: TestClient,
    admin_headers: dict[str, str],
    db,
) -> None:
    """Delete drops the row and enqueues the graph rebuild."""
    data = (FIXTURES_DIR / "sample-room-checklist.docx").read_bytes()
    created = _upload(client, admin_headers, "sample-room-checklist.docx", data)
    source_id = created.json()["id"]

    response = client.delete(f"/sources/{source_id}", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"id": source_id, "deleted": True}
    assert _list_sources(client, admin_headers) == []
    queued = db.execute(
        "SELECT payload FROM cmap.job WHERE kind = 'project'"
    ).fetchone()
    assert queued is not None
    assert queued[0]["removed_source_id"] == source_id

    missing = client.delete(f"/sources/{uuid4()}", headers=admin_headers)
    assert missing.status_code == 404


def test_mutations_require_admin(
    client: TestClient,
    user_headers: dict[str, str],
) -> None:
    """Upload, import and delete are closed to non-admin employees."""
    data = (FIXTURES_DIR / "licensing-approval-procedure.pdf").read_bytes()
    upload = _upload(client, user_headers, "licensing-approval-procedure.pdf", data)
    assert upload.status_code == 403
    bucket = client.post("/sources/import-bucket", headers=user_headers)
    assert bucket.status_code == 403
    folder = client.post(
        "/sources/import-folder", headers=user_headers, json={"path": "/data/import"}
    )
    assert folder.status_code == 403
    transcript = client.post(
        "/sources/transcript", headers=user_headers, json={"text": "Ilona: hello"}
    )
    assert transcript.status_code == 403
    delete = client.delete(f"/sources/{uuid4()}", headers=user_headers)
    assert delete.status_code == 403


def test_requires_shared_token(client: TestClient) -> None:
    """Without the proxy's shared token nothing is served."""
    response = client.get("/sources")
    assert response.status_code == 401
