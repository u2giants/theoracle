"""The ``read_source`` job: read, chunk, embed, mark read (plan step 3).

Every source becomes chunks in ``cmap.chunk``, embedded and ready for the
``classify_extract`` job this handler enqueues. Nothing here gates reading on
approval: a source either becomes chunks or fails with its error recorded.
"""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Json

from brain import storage as storage_mod
from brain.db import enqueue_job, get_pool
from brain.embed import embed_and_store
from brain.read.chunk import Chunk, window_chunks
from brain.read.detect import (
    KIND_DOCX,
    KIND_IMAGE,
    KIND_PDF,
    KIND_PPTX,
    KIND_TEXT,
    KIND_TRANSCRIPT,
    KIND_XLSX,
)
from brain.read.image import read_image
from brain.read.office import read_docx, read_pptx, read_xlsx
from brain.read.pdf import read_pdf
from brain.read.transcript import read_transcript

MAX_READ_ERROR_CHARS = 2000


def _decode_text(data: bytes) -> str:
    """Decode a text source, tolerating a UTF-8 BOM."""
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
    if kind == KIND_TEXT:
        return window_chunks(_decode_text(data), {})
    raise ValueError(f"unsupported source kind {kind!r}")


def _store_chunks(source_id: str, chunks: list[Chunk]) -> list[tuple[str, str]]:
    """Replace the source's chunks and return ``(chunk_id, text)`` pairs."""
    pool = get_pool()
    pairs: list[tuple[str, str]] = []
    with pool.connection() as conn:
        conn.execute("DELETE FROM cmap.chunk WHERE source_id = %s", (source_id,))
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


def _set_read_state(source_id: str, state: str, error: str | None) -> None:
    """Record the source's read outcome."""
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(
            "UPDATE cmap.source SET read_state = %s, read_error = %s WHERE id = %s",
            (state, error, source_id),
        )
        conn.commit()


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


def handle_read_source(job: dict[str, Any]) -> None:
    """Read one source end to end: chunk, embed, mark read, queue extraction."""
    payload = job.get("payload") or {}
    source_id = str(payload.get("source_id") or "")
    if not source_id:
        raise ValueError("read_source job has no source_id")
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT kind, storage_path FROM cmap.source WHERE id = %s",
            (source_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"source {source_id} not found")
    kind, storage_path = row
    usage: dict[str, int] = {}
    try:
        data = storage_mod.get_storage().download(storage_path)
        chunks = read_chunks(kind, data, usage)
        pairs = _store_chunks(source_id, chunks)
        embed_and_store(pairs, usage=usage)
        _set_read_state(source_id, "read", None)
    except Exception as exc:
        _set_read_state(source_id, "failed", str(exc)[:MAX_READ_ERROR_CHARS])
        raise
    enqueue_job("classify_extract", {"source_id": source_id})
    _record_usage(job.get("id"), usage)
