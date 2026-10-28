"""Source intake endpoints (plan step 2).

Upload, transcript paste, bulk bucket import and folder import all land in
``cmap.source`` with a queued ``read_source`` job. Nothing here gates reading
or indexing on approval; the only permission check is the plan §8 admin flag
on upload, delete and run.
"""

from __future__ import annotations

import hashlib
import io
import mimetypes
import re
from datetime import date
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from starlette.datastructures import UploadFile

from brain import storage as storage_mod
from brain.api.deps import User, current_user, require_admin
from brain.config import get_settings
from brain.db import enqueue_job, get_pool
from brain.read.detect import (
    KIND_DOCX,
    KIND_PPTX,
    KIND_XLSX,
    DetectError,
    detect_kind,
    verify_office_zip,
)

router = APIRouter()

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
MAX_TRANSCRIPT_LINES = 200_000

_ZIP_KINDS = frozenset({KIND_DOCX, KIND_XLSX, KIND_PPTX})

_SOURCE_COLUMNS = (
    "id, kind, title, original_filename, storage_path, sha256, bytes, "
    "department_hint, effective_date, uploaded_by, created_at, read_state, read_error"
)


class TranscriptBody(BaseModel):
    """A pasted transcript (VTT, Teams JSON, Recall JSON or speaker lines)."""

    text: str
    title: str | None = None
    department_hint: str | None = None
    effective_date: str | None = None


class ImportFolderBody(BaseModel):
    """A mounted-folder import request."""

    path: str


def _safe_name(filename: str) -> str:
    """Return a single safe path segment for a storage key."""
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    name = name.strip("._")
    if not name:
        name = "upload"
    return name[:120]


def _upload_size(request: Request, file: UploadFile) -> int:
    """Return the upload size, preferring the declared content length."""
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            return int(declared)
        except ValueError:
            pass
    size = getattr(file, "size", None)
    if size is not None:
        return int(size)
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    return int(size)


def _declared_size(request: Request) -> int | None:
    """Return the request's declared body size, when it has one."""
    declared = request.headers.get("content-length")
    if declared is None:
        return None
    try:
        return int(declared)
    except ValueError:
        return None


def _read_upload(file: UploadFile) -> bytes:
    """Read the whole upload into memory (size already capped)."""
    file.file.seek(0)
    data = file.file.read()
    file.file.seek(0)
    return data


def _parse_effective_date(raw: str | None) -> date | None:
    """Parse an optional YYYY-MM-DD date; unknown stays NULL."""
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="effective_date must be YYYY-MM-DD",
        ) from exc


def _find_by_sha256(sha: str) -> str | None:
    """Return the id of the source already holding ``sha``, if any."""
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT id::text FROM cmap.source WHERE sha256 = %s",
            (sha,),
        ).fetchone()
    if row is None:
        return None
    return row[0]


def _insert_source(
    *,
    source_id: str,
    kind: str,
    title: str,
    original_filename: str | None,
    storage_path: str,
    sha: str,
    data_len: int,
    department_hint: str | None,
    effective_date: date | None,
    uploaded_by: str,
) -> dict[str, Any]:
    """Insert one ``cmap.source`` row and queue its ``read_source`` job."""
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            f"INSERT INTO cmap.source ({_SOURCE_COLUMNS}) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), 'queued', NULL) "
            "RETURNING " + _SOURCE_COLUMNS,
            (
                source_id,
                kind,
                title,
                original_filename,
                storage_path,
                sha,
                data_len,
                department_hint,
                effective_date,
                uploaded_by,
            ),
        ).fetchone()
        conn.commit()
    enqueue_job("read_source", {"source_id": source_id})
    return _row_to_dict(row)


def _row_to_dict(row: tuple) -> dict[str, Any]:
    """Shape one ``cmap.source`` row as the API returns it."""
    (
        source_id,
        kind,
        title,
        original_filename,
        storage_path,
        sha,
        data_len,
        department_hint,
        effective_date,
        uploaded_by,
        created_at,
        read_state,
        read_error,
    ) = row
    return {
        "id": str(source_id),
        "kind": kind,
        "title": title,
        "original_filename": original_filename,
        "storage_path": storage_path,
        "sha256": sha,
        "bytes": data_len,
        "department_hint": department_hint,
        "effective_date": effective_date.isoformat() if effective_date else None,
        "uploaded_by": str(uploaded_by) if uploaded_by else None,
        "created_at": created_at.isoformat() if created_at else None,
        "read_state": read_state,
        "read_error": read_error,
    }


def _ingest_bytes(
    *,
    kind: str,
    title: str,
    original_filename: str,
    data: bytes,
    department_hint: str | None,
    effective_date: date | None,
    uploaded_by: str,
) -> dict[str, Any]:
    """Store ``data`` as a new source, or report the duplicate sha."""
    sha = hashlib.sha256(data).hexdigest()
    existing = _find_by_sha256(sha)
    if existing is not None:
        return {"id": existing, "duplicate": True}
    source_id = str(uuid4())
    key = f"cmap/{source_id}/{_safe_name(original_filename)}"
    content_type = mimetypes.guess_type(original_filename)[0] or "application/octet-stream"
    store = storage_mod.get_storage()
    store.upload(key, data, content_type)
    try:
        row = _insert_source(
            source_id=source_id,
            kind=kind,
            title=title,
            original_filename=original_filename,
            storage_path=key,
            sha=sha,
            data_len=len(data),
            department_hint=department_hint,
            effective_date=effective_date,
            uploaded_by=uploaded_by,
        )
    except Exception:
        store.delete(key)
        raise
    row["duplicate"] = False
    return row


@router.get("/sources")
def list_sources(user: Annotated[User, Depends(current_user)]) -> dict[str, Any]:
    """List every source with its read state, newest first."""
    pool = get_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            f"SELECT {_SOURCE_COLUMNS} FROM cmap.source ORDER BY created_at DESC LIMIT 500"
        ).fetchall()
    return {"sources": [_row_to_dict(row) for row in rows]}


@router.post("/sources")
async def create_source(
    request: Request,
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Upload one document, diagram or transcript file.

    Multipart fields: ``file`` (required), optional ``title``,
    ``department_hint`` and ``effective_date``. Oversized bodies are refused
    before the multipart is parsed.
    """
    declared = _declared_size(request)
    if declared is not None and declared > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"upload exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB cap",
        )
    form = await request.form()
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise HTTPException(status_code=400, detail="multipart field 'file' is required")
    if _upload_size(request, upload) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"upload exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB cap",
        )
    raw_name = upload.filename or "upload"
    data = _read_upload(upload)
    try:
        kind = detect_kind(raw_name, data[:8192])
    except DetectError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if kind in _ZIP_KINDS:
        try:
            verify_office_zip(io.BytesIO(data), kind)
        except DetectError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc

    def _field(name: str) -> str | None:
        value = form.get(name)
        if isinstance(value, str):
            return value
        return None

    return _ingest_bytes(
        kind=kind,
        title=(_field("title") or "").strip() or _safe_name(raw_name),
        original_filename=raw_name,
        data=data,
        department_hint=(_field("department_hint") or "").strip() or None,
        effective_date=_parse_effective_date(_field("effective_date")),
        uploaded_by=user.auth_user_id,
    )


@router.post("/sources/transcript")
def create_transcript_source(
    body: TranscriptBody,
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Ingest a pasted transcript (VTT, Teams JSON, Recall JSON or speaker lines)."""
    text = body.text or ""
    line_count = text.count("\n") + 1 if text else 0
    if line_count > MAX_TRANSCRIPT_LINES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"transcript has {line_count} lines and the cap is "
                f"{MAX_TRANSCRIPT_LINES}; nothing was ingested"
            ),
        )
    title = (body.title or "").strip() or "Transcript"
    return _ingest_bytes(
        kind="transcript",
        title=title,
        original_filename=f"{_safe_name(title)}.txt",
        data=text.encode("utf-8"),
        department_hint=(body.department_hint or "").strip() or None,
        effective_date=_parse_effective_date(body.effective_date),
        uploaded_by=user.auth_user_id,
    )


@router.post("/sources/import-bucket")
def import_bucket(user: Annotated[User, Depends(require_admin)]) -> dict[str, Any]:
    """Ingest every Oracle 1 upload already sitting in the storage bucket."""
    store = storage_mod.get_storage()
    imported = 0
    duplicates = 0
    errors: list[dict[str, str]] = []
    for key in store.list(""):
        if key.startswith("cmap/"):
            continue
        name = key.replace("\\", "/").rsplit("/", 1)[-1]
        try:
            data = store.download(key)
            kind = detect_kind(name, data[:8192])
            if kind in _ZIP_KINDS:
                verify_office_zip(io.BytesIO(data), kind)
        except (DetectError, storage_mod.StorageError) as exc:
            errors.append({"key": key, "error": str(exc)})
            continue
        result = _ingest_bytes(
            kind=kind,
            title=name,
            original_filename=name,
            data=data,
            department_hint=None,
            effective_date=None,
            uploaded_by=user.auth_user_id,
        )
        if result.get("duplicate"):
            duplicates += 1
        else:
            imported += 1
    return {
        "imported": imported,
        "duplicates": duplicates,
        "errors": errors,
    }


@router.post("/sources/import-folder")
def import_folder(
    body: ImportFolderBody,
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Walk a mounted import folder; the first folder level names the department."""
    root = Path(get_settings().brain_import_dir).resolve()
    try:
        target = Path(body.path).expanduser().resolve()
    except OSError as exc:
        raise HTTPException(status_code=400, detail="path could not be resolved") from exc
    if target != root and root not in target.parents:
        raise HTTPException(
            status_code=400,
            detail="path must be inside the configured import directory",
        )
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="path is not a directory")
    imported = 0
    duplicates = 0
    errors: list[dict[str, str]] = []
    for file_path in sorted(target.rglob("*")):
        if not file_path.is_file():
            continue
        relative = file_path.relative_to(target)
        department_hint = relative.parts[0] if len(relative.parts) > 1 else None
        try:
            if file_path.stat().st_size > MAX_UPLOAD_BYTES:
                raise DetectError(
                    f"file exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB cap"
                )
            data = file_path.read_bytes()
            kind = detect_kind(file_path.name, data[:8192])
            if kind in _ZIP_KINDS:
                verify_office_zip(io.BytesIO(data), kind)
        except (DetectError, OSError) as exc:
            errors.append({"key": str(relative), "error": str(exc)})
            continue
        result = _ingest_bytes(
            kind=kind,
            title=file_path.name,
            original_filename=file_path.name,
            data=data,
            department_hint=department_hint,
            effective_date=None,
            uploaded_by=user.auth_user_id,
        )
        if result.get("duplicate"):
            duplicates += 1
        else:
            imported += 1
    return {
        "imported": imported,
        "duplicates": duplicates,
        "errors": errors,
    }


@router.delete("/sources/{source_id}")
def delete_source(
    source_id: UUID,
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Delete one source and queue a graph rebuild so its refs drop."""
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT storage_path FROM cmap.source WHERE id = %s",
            (str(source_id),),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="source not found")
        storage_path = row[0]
        conn.execute("DELETE FROM cmap.source WHERE id = %s", (str(source_id),))
        conn.commit()
    try:
        storage_mod.get_storage().delete(storage_path)
    except storage_mod.StorageError:
        pass
    enqueue_job("project", {"removed_source_id": str(source_id)})
    return {"id": str(source_id), "deleted": True}
