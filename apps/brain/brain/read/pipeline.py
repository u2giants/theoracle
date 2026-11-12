"""The ``read_source`` job: read, chunk, embed, hand to extraction (plan step 3).

Every source becomes chunks in ``cmap.chunk``, embedded and ready for the
``classify_extract`` job this handler enqueues. Nothing here gates reading on
approval: a source either becomes chunks or fails with its error recorded.
"""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Json

from brain import storage as storage_mod
from brain.config import get_settings
from brain.db import enqueue_job, get_pool
from brain.embed import embed_and_store
from brain.read.chunk import Chunk, window_chunks
from brain.read.cleanup import drop_orphaned, touched_entities
from brain.read.dates import resolve_and_store, upload_floor
from brain.read.detect import (
    KIND_CSV,
    KIND_DOCX,
    KIND_IMAGE,
    KIND_PDF,
    KIND_PPTX,
    KIND_TEXT,
    KIND_TRANSCRIPT,
    KIND_TSV,
    KIND_XLSX,
    read_kind,
)
from brain.read.image import read_image
from brain.read.office import read_delimited, read_docx, read_pptx, read_xlsx
from brain.read.pdf import read_pdf
from brain.read.state import NO_CONTENT_ERROR, set_read_state
from brain.read.transcript import read_transcript
from brain.read.vision import start_read_notes

MAX_READ_ERROR_CHARS = 2000


def _decode_text(data: bytes) -> str:
    """Decode a text source: UTF-8 (with BOM), then GB18030, then replace."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("gb18030")
    except UnicodeDecodeError:
        return data.decode("utf-8-sig", errors="replace")


def read_chunks(kind: str, data: bytes, usage: dict[str, int] | None = None) -> list[Chunk]:
    """Read one stored source into its chunks, whatever the kind."""
    if kind == KIND_PDF:
        return read_pdf(data, usage)
    if kind == KIND_IMAGE:
        return read_image(data, usage)
    if kind == KIND_DOCX:
        return read_docx(data, usage)
    if kind == KIND_XLSX:
        return read_xlsx(data, usage)
    if kind == KIND_PPTX:
        return read_pptx(data, usage)
    if kind == KIND_TRANSCRIPT:
        return read_transcript(_decode_text(data))
    if kind in (KIND_CSV, KIND_TSV):
        return read_delimited(_decode_text(data), kind)
    if kind == KIND_TEXT:
        return window_chunks(_decode_text(data), {})
    raise ValueError(f"unsupported source kind {kind!r}")


def _store_chunks(source_id: str, chunks: list[Chunk]) -> list[tuple[str, str]]:
    """Replace the source's chunks and return ``(chunk_id, text)`` pairs."""
    pool = get_pool()
    pairs: list[tuple[str, str]] = []
    with pool.connection() as conn:
        # A re-read replaces the old passages; whatever only they supported
        # (entities with no mention left, aliases) goes with them (repair A7).
        touched = touched_entities(conn, source_id)
        conn.execute("DELETE FROM cmap.chunk WHERE source_id = %s", (source_id,))
        drop_orphaned(conn, touched)
        for ordinal, chunk in enumerate(chunks):
            row = conn.execute(
                "INSERT INTO cmap.chunk (source_id, ordinal, locator, text, token_count) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (
                    source_id,
                    ordinal,
                    Json(chunk.locator),
                    chunk.text,
                    chunk.token_count,
                ),
            ).fetchone()
            pairs.append((str(row[0]), chunk.text))
        conn.commit()
    return pairs


def _record_usage(job_id: Any, usage: dict[str, int]) -> None:
    """Log the job's model usage into ``cmap.job.payload.usage`` (plan §11)."""
    if not usage:
        return
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(
            "UPDATE cmap.job SET payload = jsonb_set(payload, '{usage}', %s::jsonb) "
            "WHERE id = %s",
            (Json(usage), job_id),
        )
        conn.commit()


def _record_read_notes(source_id: str, notes: list[dict[str, Any]]) -> None:
    """Store what the readers could not read on the source (repair plan A6)."""
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(
            "UPDATE cmap.source SET read_notes = %s WHERE id = %s",
            (Json({"unreadable_regions": notes} if notes else {}), source_id),
        )
        conn.commit()


def handle_read_source(job: dict[str, Any]) -> None:
    """Read one source: chunk, embed, mark extracting, queue extraction."""
    payload = job.get("payload") or {}
    source_id = str(payload.get("source_id") or "")
    if not source_id:
        raise ValueError("read_source job has no source_id")
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT id, kind, original_filename, storage_path, effective_date, "
            "date_origin, created_at FROM cmap.source WHERE id = %s",
            (source_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"source {source_id} not found")
    kind, storage_path = row[1], row[3]
    usage: dict[str, int] = {}
    with pool.connection() as conn:
        # D1: a source is never left undated, even when reading fails later.
        conn.execute(
            "UPDATE cmap.source SET date_origin = 'admin' WHERE id = %s "
            "AND effective_date IS NOT NULL AND date_origin IS NULL",
            (source_id,),
        )
        conn.execute(
            "UPDATE cmap.source SET effective_date = %s, date_origin = 'upload_time' "
            "WHERE id = %s AND effective_date IS NULL",
            (upload_floor(row[6]), source_id),
        )
        conn.commit()
    set_read_state(source_id, "reading", None)
    notes = start_read_notes()
    try:
        data = storage_mod.get_storage().download(storage_path)
        chunks = read_chunks(read_kind(kind, storage_path), data, usage)
        _record_read_notes(source_id, notes)
        pairs = _store_chunks(source_id, chunks)
        with pool.connection() as conn:
            resolve_and_store(conn, row, data=data, settings=get_settings(), usage=usage)
            conn.commit()
        if not pairs:
            # Nothing to extract: never show an empty source as read.
            set_read_state(source_id, "failed", NO_CONTENT_ERROR)
            _record_usage(job.get("id"), usage)
            return
        embed_and_store(pairs, usage=usage)
        # "read" is set only when extraction has finished (relations job).
        set_read_state(source_id, "extracting", None)
    except Exception as exc:
        set_read_state(source_id, "failed", str(exc)[:MAX_READ_ERROR_CHARS])
        raise
    enqueue_job("classify_extract", {"source_id": source_id})
    _record_usage(job.get("id"), usage)
