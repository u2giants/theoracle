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
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from starlette.datastructures import UploadFile

from brain import storage as storage_mod
from brain.api.deps import User, admin_or_service, current_user, require_admin
from brain.config import get_settings
from brain.db import enqueue_job, get_pool
from brain.read.cleanup import drop_orphaned, touched_entities
from brain.read.dates import (
    DATE_ORIGINS,
    ORIGIN_ADMIN,
    ORIGIN_FILE_META,
    ORIGIN_UPLOAD,
    upload_floor,
)
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

EASTERN = ZoneInfo("America/New_York")

_ZIP_KINDS = frozenset({KIND_DOCX, KIND_XLSX, KIND_PPTX})

_SOURCE_COLUMNS = (
    "id, kind, title, original_filename, storage_path, sha256, bytes, "
    "department_hint, effective_date, date_origin, uploaded_by, created_at, "
    "read_state, read_error"
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
    date_origin: str,
    uploaded_by: str | None,
) -> dict[str, Any]:
    """Insert one ``cmap.source`` row and queue its ``read_source`` job."""
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            f"INSERT INTO cmap.source ({_SOURCE_COLUMNS}) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), 'queued', NULL) "
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
                date_origin,
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
        date_origin,
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
        "date_origin": date_origin,
        "uploaded_by": str(uploaded_by) if uploaded_by else None,
        "created_at": created_at.isoformat() if created_at else None,
        "read_state": read_state,
        "read_error": read_error,
    }


def ingest_bytes(
    *,
    kind: str,
    title: str,
    original_filename: str,
    data: bytes,
    department_hint: str | None,
    effective_date: date | None,
    date_origin: str,
    uploaded_by: str | None,
) -> dict[str, Any]:
    """Store ``data`` as a new source, or report the duplicate sha.

    ``date_origin`` names where ``effective_date`` came from (D1). A missing
    date is only legal with the ``upload_time`` floor, which is stamped here
    so no source is ever created undated.
    """
    if date_origin not in DATE_ORIGINS:
        raise ValueError(f"unknown date_origin {date_origin!r}")
    if effective_date is None:
        if date_origin != ORIGIN_UPLOAD:
            raise ValueError(f"date_origin {date_origin!r} needs an effective_date")
        effective_date = upload_floor()
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
            date_origin=date_origin,
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

    effective = _parse_effective_date(_field("effective_date"))
    return ingest_bytes(
        kind=kind,
        title=(_field("title") or "").strip() or _safe_name(raw_name),
        original_filename=raw_name,
        data=data,
        department_hint=(_field("department_hint") or "").strip() or None,
        effective_date=effective,
        date_origin=ORIGIN_ADMIN if effective is not None else ORIGIN_UPLOAD,
        uploaded_by=user.auth_user_id,
    )


@router.post("/sources/transcript")
def create_transcript_source(
    body: TranscriptBody,
    user: Annotated[User | None, Depends(admin_or_service)],
) -> dict[str, Any]:
    """Ingest a pasted transcript (VTT, Teams JSON, Recall JSON or speaker lines).

    Admins call this from the Sources page; the Recall.ai meeting route calls
    it as a service (shared token, no user) when a meeting transcript is done.
    """
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
    effective = _parse_effective_date(body.effective_date)
    return ingest_bytes(
        kind="transcript",
        title=title,
        original_filename=f"{_safe_name(title)}.txt",
        data=text.encode("utf-8"),
        department_hint=(body.department_hint or "").strip() or None,
        effective_date=effective,
        date_origin=ORIGIN_ADMIN if effective is not None else ORIGIN_UPLOAD,
        uploaded_by=user.auth_user_id if user is not None else None,
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
        result = ingest_bytes(
            kind=kind,
            title=name,
            original_filename=name,
            data=data,
            department_hint=None,
            effective_date=None,
            date_origin=ORIGIN_UPLOAD,
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
            stat = file_path.stat()
            if stat.st_size > MAX_UPLOAD_BYTES:
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
        # The file's own mtime is the upload-payload metadata date (D1).
        modified = datetime.fromtimestamp(stat.st_mtime, EASTERN).date()
        result = ingest_bytes(
            kind=kind,
            title=file_path.name,
            original_filename=file_path.name,
            data=data,
            department_hint=department_hint,
            effective_date=modified,
            date_origin=ORIGIN_FILE_META,
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
        touched = touched_entities(conn, str(source_id))
        conn.execute("DELETE FROM cmap.source WHERE id = %s", (str(source_id),))
        # Scoped to this source's entities on purpose: mention-less orphans from
        # earlier deletions stay until the owner's keep-vs-hide decision (#255).
        drop_orphaned(conn, touched)
        conn.commit()
    try:
        storage_mod.get_storage().delete(storage_path)
    except storage_mod.StorageError:
        pass
    enqueue_job("project", {"removed_source_id": str(source_id)})
    return {"id": str(source_id), "deleted": True}


def _queue_reread(conn: Any, source_ids: list[str]) -> int:
    """Queue ``read_source`` for each source that has none waiting or running."""
    queued = 0
    for source_id in source_ids:
        row = conn.execute(
            "INSERT INTO cmap.job (kind, payload) "
            "SELECT 'read_source', jsonb_build_object('source_id', %s::text) "
            "WHERE NOT EXISTS (SELECT 1 FROM cmap.job WHERE kind = 'read_source' "
            "AND payload->>'source_id' = %s AND state IN ('queued', 'running')) RETURNING id",
            (source_id, source_id),
        ).fetchone()
        if row is not None:
            conn.execute(
                "UPDATE cmap.source SET read_state = 'queued', read_error = NULL WHERE id = %s",
                (source_id,),
            )
            queued += 1
    return queued


@router.post("/sources/reread-all")
def reread_all_sources(
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Queue a fresh read of every source (repair plan A8).

    The single worker reads them one at a time, so this is throttled by
    construction; each source's old passages and what was extracted from
    them are replaced, never duplicated.
    """
    del user
    with get_pool().connection() as conn:
        ids = [
            str(row[0])
            for row in conn.execute("SELECT id FROM cmap.source ORDER BY created_at").fetchall()
        ]
        queued = _queue_reread(conn, ids)
        conn.commit()
    return {"sources": len(ids), "queued": queued}


@router.post("/sources/{source_id}/reread")
def reread_source(
    source_id: UUID,
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Queue a fresh read of one source (the sources page "retry" button)."""
    del user
    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM cmap.source WHERE id = %s", (str(source_id),)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="source not found")
        queued = _queue_reread(conn, [str(source_id)])
        conn.commit()
    return {"id": str(source_id), "queued": bool(queued)}


@router.post("/sources/backfill-dates")
def backfill_dates(user: Annotated[User, Depends(require_admin)]) -> dict[str, Any]:
    """Stamp D1 dates on sources that predate ``date_origin`` (idempotent).

    Legacy rows holding an admin-entered date are stamped ``admin`` here;
    every other undated source is resolved by the ``backfill_dates`` job
    (full precedence chain, always ending dated). Rows already carrying a
    date and origin are left alone, so a second run is a no-op.
    """
    del user
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(
            "UPDATE cmap.source SET date_origin = %s "
            "WHERE effective_date IS NOT NULL AND date_origin IS NULL",
            (ORIGIN_ADMIN,),
        )
        pending = int(
            conn.execute(
                "SELECT count(*) FROM cmap.source WHERE effective_date IS NULL"
            ).fetchone()[0]
        )
        queued = 0
        if pending:
            row = conn.execute(
                "INSERT INTO cmap.job (kind, payload) "
                "SELECT 'backfill_dates', '{}'::jsonb "
                "WHERE NOT EXISTS (SELECT 1 FROM cmap.job WHERE kind = 'backfill_dates' "
                "AND state IN ('queued', 'running')) RETURNING id"
            ).fetchone()
            queued = 1 if row is not None else 0
        conn.commit()
    return {"pending": pending, "queued": bool(queued)}


@router.post("/jobs/retry-failed")
def retry_failed_jobs(
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Put every failed job back on the queue with its retries restored."""
    del user
    with get_pool().connection() as conn:
        rows = conn.execute(
            "UPDATE cmap.job SET state = 'queued', attempts = 0, run_after = now(), "
            "started_at = NULL, finished_at = NULL WHERE state = 'failed' RETURNING kind"
        ).fetchall()
        conn.commit()
    kinds: dict[str, int] = {}
    for (kind,) in rows:
        kinds[str(kind)] = kinds.get(str(kind), 0) + 1
    return {"requeued": len(rows), "by_kind": kinds}


_SOURCE_STATES = ("queued", "reading", "extracting", "read", "partial", "failed")
_HEALTH_LIST_CAP = 200
_NY_DAY_START_SQL = "((now() AT TIME ZONE 'America/New_York')::date) AT TIME ZONE 'America/New_York'"


def _job_row(row: tuple) -> dict[str, Any]:
    """Shape one ``cmap.job`` row for the health panel."""
    return {
        "id": str(row[0]),
        "kind": row[1],
        "payload": row[2],
        "state": row[3],
        "attempts": int(row[4]),
        "error": row[5],
        "created_at": row[6].isoformat() if row[6] else None,
        "started_at": row[7].isoformat() if row[7] else None,
        "finished_at": row[8].isoformat() if row[8] else None,
    }


@router.get("/sources/health")
def sources_health(user: Annotated[User, Depends(require_admin)]) -> dict[str, Any]:
    """Pipeline health for the sources admin panel (repair plan B4).

    Everything the panel shows is existing state, read four ways:

    - ``sources_by_state`` counts every ``read_state`` (including zero counts).
    - ``jobs.failed`` is ``cmap.job`` rows in ``failed``; ``jobs.retrying`` is
      rows back on the queue with their error kept and ``run_after`` in the
      future (``worker.finish_job``). Error text is returned verbatim.
    - ``failed_extractions`` is ``cmap.extraction`` rows with ``error`` set
      (repair A2: a passage whose model call failed after its retries).
    - ``last_build`` is the newest ``cmap.graph_version`` row, which is written
      only after a successful projection, plus ``map_version`` — the version
      the map pages read (``brain.graph.version.current_graph_version``).
    - ``spend_today`` sums the model usage counters each job records in
      ``payload.usage`` for jobs created in the New York day. There is no
      dollar-cost store in the system; ``usage`` is kept per counter so
      nothing is hidden.
    """
    del user
    pool = get_pool()
    with pool.connection() as conn:
        state_rows = conn.execute(
            "SELECT read_state, count(*) FROM cmap.source GROUP BY read_state"
        ).fetchall()
        states = {state: 0 for state in _SOURCE_STATES}
        for state, count in state_rows:
            states[str(state)] = int(count)

        job_columns = "id, kind, payload, state, attempts, error, created_at, started_at, finished_at"
        failed_jobs = [
            _job_row(row)
            for row in conn.execute(
                f"SELECT {job_columns} FROM cmap.job WHERE state = 'failed' "
                f"ORDER BY created_at DESC LIMIT {_HEALTH_LIST_CAP}"
            ).fetchall()
        ]
        retry_rows = conn.execute(
            "SELECT id, kind, payload, state, attempts, error, created_at, started_at, run_after "
            "FROM cmap.job WHERE state = 'queued' AND error IS NOT NULL "
            f"ORDER BY created_at DESC LIMIT {_HEALTH_LIST_CAP}"
        ).fetchall()
        retrying_jobs = [
            {
                "id": str(row[0]),
                "kind": row[1],
                "payload": row[2],
                "state": row[3],
                "attempts": int(row[4]),
                "error": row[5],
                "created_at": row[6].isoformat() if row[6] else None,
                "started_at": row[7].isoformat() if row[7] else None,
                "run_after": row[8].isoformat() if row[8] else None,
            }
            for row in retry_rows
        ]

        failed_extractions = [
            {
                "chunk_id": str(row[0]),
                "source_id": str(row[1]),
                "source_title": row[2],
                "ordinal": int(row[3]),
                "locator": row[4],
                "stage": row[5],
                "error": row[6],
            }
            for row in conn.execute(
                "SELECT c.id, c.source_id, s.title, c.ordinal, c.locator, e.stage, e.error "
                "FROM cmap.extraction e "
                "JOIN cmap.chunk c ON c.id = e.chunk_id "
                "JOIN cmap.source s ON s.id = c.source_id "
                "WHERE e.error IS NOT NULL "
                f"ORDER BY s.title, c.ordinal LIMIT {_HEALTH_LIST_CAP}"
            ).fetchall()
        ]

        build_row = conn.execute(
            "SELECT version, projected_at, node_count, edge_count FROM cmap.graph_version "
            "ORDER BY version DESC LIMIT 1"
        ).fetchone()
        map_version_row = conn.execute(
            "SELECT MAX(graph_version) FROM cmap.community"
        ).fetchone()
        last_build = None
        if build_row is not None:
            last_build = {
                "version": int(build_row[0]),
                "projected_at": build_row[1].isoformat() if build_row[1] else None,
                "node_count": int(build_row[2]) if build_row[2] is not None else None,
                "edge_count": int(build_row[3]) if build_row[3] is not None else None,
                "map_version": (
                    int(map_version_row[0]) if map_version_row[0] is not None else None
                ),
            }

        day_row = conn.execute(
            "SELECT (now() AT TIME ZONE 'America/New_York')::date::text"
        ).fetchone()
        usage_rows = conn.execute(
            "SELECT payload -> 'usage' FROM cmap.job "
            f"WHERE created_at >= {_NY_DAY_START_SQL}"
        ).fetchall()

    usage_totals: dict[str, float] = {}
    for (usage,) in usage_rows:
        if not isinstance(usage, dict):
            continue
        for key, value in usage.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                usage_totals[key] = usage_totals.get(key, 0) + value
    tokens = int(
        sum(value for key, value in usage_totals.items() if key.endswith("_tokens"))
    )
    calls = int(
        sum(value for key, value in usage_totals.items() if key.endswith("_calls"))
    )

    return {
        "sources_by_state": states,
        "jobs": {"failed": failed_jobs, "retrying": retrying_jobs},
        "failed_extractions": failed_extractions,
        "last_build": last_build,
        "spend_today": {
            "day": str(day_row[0]),
            "timezone": "America/New_York",
            "tokens": tokens,
            "calls": calls,
            "usage": usage_totals,
        },
    }
