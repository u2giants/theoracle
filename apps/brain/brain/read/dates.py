"""Effective-date resolution for sources (repair plan D1).

Every source carries an ``effective_date`` and a ``date_origin`` naming the
rule that won. Precedence, first hit wins:

1. ``admin`` — entered on upload or transcript intake.
2. ``meeting_start`` — Teams/Recall meeting metadata in a transcript payload.
3. ``interview_answer`` — the answer/interview timestamp (stamped at creation).
4. ``document_text`` — a date printed in the document's own header, footer or
   revision table (one model call on the first and last page, flat seat).
5. ``file_metadata`` — file metadata dates (folder upload payload mtime, Office
   ``docProps/core.xml``, PDF document info).
6. ``upload_time`` — the floor: the New York date of ``created_at``. A source
   is never undated.
"""

from __future__ import annotations

import io
import json
import logging
import re
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import pypdfium2 as pdfium

from brain import storage as storage_mod
from brain.config import Settings, get_settings
from brain.db import get_pool
from brain.llm import message_content, post_chat_with_rescue
from brain.read.detect import (
    KIND_DOCX,
    KIND_PDF,
    KIND_PPTX,
    KIND_TRANSCRIPT,
    KIND_XLSX,
    read_kind,
)
from brain.read.transcript import meeting_start_date
from brain.seats import stage_model

logger = logging.getLogger(__name__)

EASTERN = ZoneInfo("America/New_York")

ORIGIN_ADMIN = "admin"
ORIGIN_MEETING = "meeting_start"
ORIGIN_INTERVIEW = "interview_answer"
ORIGIN_DOCUMENT = "document_text"
ORIGIN_FILE_META = "file_metadata"
ORIGIN_UPLOAD = "upload_time"

DATE_ORIGINS = (
    ORIGIN_ADMIN,
    ORIGIN_MEETING,
    ORIGIN_INTERVIEW,
    ORIGIN_DOCUMENT,
    ORIGIN_FILE_META,
    ORIGIN_UPLOAD,
)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "source_date.md"

_DCTERMS_NS = "http://purl.org/dc/terms/"
_PDF_DATE_RE = re.compile(r"^D:(\d{4})(\d{2})(\d{2})")


class DateError(RuntimeError):
    """Raised when the document-text date call cannot run or parse."""


def upload_floor(uploaded_at: datetime | None = None) -> date:
    """Return the New York calendar date of ``uploaded_at`` (default now)."""
    moment = uploaded_at or datetime.now(EASTERN)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=EASTERN)
    return moment.astimezone(EASTERN).date()


def parse_date_value(value: Any) -> date | None:
    """Parse an ISO date/datetime (or PDF ``D:YYYYMMDD...``) into a date."""
    if value is None or isinstance(value, bool) or isinstance(value, int | float):
        return None
    text = str(value).strip()
    if not text:
        return None
    pdf_form = _PDF_DATE_RE.match(text)
    if pdf_form:
        try:
            return date(int(pdf_form.group(1)), int(pdf_form.group(2)), int(pdf_form.group(3)))
        except ValueError:
            return None
    try:
        if len(text) == 10 and text[4] == "-" and text[7] == "-":
            return date.fromisoformat(text)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(EASTERN).date()
    return parsed.date()


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


def _office_core_date(data: bytes) -> date | None:
    """Return the created/modified date in an Office ``docProps/core.xml``."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            try:
                xml = package.read("docProps/core.xml")
            except KeyError:
                return None
    except zipfile.BadZipFile:
        return None
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        return None
    for tag in ("created", "modified"):
        node = root.find(f"{{{_DCTERMS_NS}}}{tag}")
        if node is not None and node.text:
            found = parse_date_value(node.text)
            if found is not None:
                return found
    return None


def _pdf_info_date(data: bytes) -> date | None:
    """Return the CreationDate/ModDate in a PDF's document info."""
    try:
        document = pdfium.PdfDocument(data)
    except Exception:
        return None
    try:
        info = document.get_metadata_dict()
    finally:
        document.close()
    if not isinstance(info, dict):
        return None
    for key in ("CreationDate", "ModDate"):
        found = parse_date_value(info.get(key))
        if found is not None:
            return found
    return None


def file_metadata_date(routed_kind: str, data: bytes | None) -> date | None:
    """Return the date carried in the file's own metadata, or None.

    Dispatches on the routed kind (``read_kind``), so a ``text`` source named
    .csv/.tsv reaches the table reader's kind and never an Office parser.
    Office containers yield ``docProps/core.xml``; PDFs yield document info.
    """
    if data is None:
        return None
    if routed_kind in (KIND_DOCX, KIND_XLSX, KIND_PPTX):
        return _office_core_date(data)
    if routed_kind == KIND_PDF:
        return _pdf_info_date(data)
    return None


def load_date_prompt() -> str:
    """Return the document-date prompt (its DATA wrapper is the guard)."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def _post_chat(messages: list[dict[str, Any]], settings: Settings) -> dict[str, Any]:
    """POST one flat-seat chat request and return the response body."""
    model = stage_model(settings, "flat")
    if model is None:
        raise DateError("no flat model seat is configured")
    return post_chat_with_rescue(
        {
            "model": model,
            "messages": messages,
            "temperature": 0,
        },
        settings=settings,
        timeout=60.0,
        error_cls=DateError,
        label="source date",
    )


def _parse_date_payload(content: str) -> date | None:
    """Parse the model's ``{"date": ...}`` answer, tolerating a code fence."""
    text = content.strip()
    fenced = re.fullmatch(r"```[a-zA-Z]*\n(.*?)\n?```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DateError("date model response is not valid JSON") from exc
    if not isinstance(value, dict):
        raise DateError("date model response is not a JSON object")
    return parse_date_value(value.get("date"))


def document_text_date(
    first_page: str,
    last_page: str,
    settings: Settings,
    usage: dict[str, int] | None = None,
) -> date | None:
    """Ask the flat seat for a date printed in the document's header/footer.

    Returns None when the pages carry no such date. A failed call raises
    :class:`DateError` for the caller to log.
    """
    if not first_page.strip() and not last_page.strip():
        return None
    prompt = load_date_prompt().replace("{{first_page}}", first_page).replace(
        "{{last_page}}", last_page
    )
    body = _post_chat([{"role": "user", "content": prompt}], settings)
    if usage is not None:
        call_usage = body.get("usage") or {}
        usage["date_calls"] = usage.get("date_calls", 0) + 1
        total = call_usage.get("total_tokens")
        if isinstance(total, int | float):
            usage["date_tokens"] = usage.get("date_tokens", 0) + int(total)
    return _parse_date_payload(message_content(body))


def _page_texts(chunks: list[tuple[dict[str, Any], str]]) -> tuple[str, str]:
    """Return ``(first_page, last_page)`` text from ordered ``(locator, text)``.

    A paged locator (page/slide/sheet) groups its chunks into one page; other
    sources fall back to their first and last chunk.
    """
    if not chunks:
        return "", ""
    key = next(
        (name for name in ("page", "slide", "sheet") if name in chunks[0][0]),
        None,
    )
    if key is None:
        return chunks[0][1], chunks[-1][1]
    first_value = chunks[0][0].get(key)
    last_value = chunks[-1][0].get(key)
    first_parts = [text for locator, text in chunks if locator.get(key) == first_value]
    last_parts = [text for locator, text in chunks if locator.get(key) == last_value]
    return "\n".join(first_parts), "\n".join(last_parts)


def resolve_source_date(
    *,
    routed_kind: str,
    data: bytes | None,
    chunks: list[tuple[dict[str, Any], str]] | None,
    stored_date: date | None,
    stored_origin: str | None,
    uploaded_at: datetime | None,
    settings: Settings,
    usage: dict[str, int] | None = None,
) -> tuple[date, str]:
    """Return ``(effective_date, date_origin)`` by first-hit precedence."""
    if stored_origin == ORIGIN_ADMIN and stored_date is not None:
        return stored_date, stored_origin

    meeting: date | None = None
    if data is not None and routed_kind == KIND_TRANSCRIPT:
        meeting = meeting_start_date(_decode_text(data))
    if meeting is None and stored_origin == ORIGIN_MEETING:
        meeting = stored_date
    if meeting is not None:
        return meeting, ORIGIN_MEETING

    if stored_origin == ORIGIN_INTERVIEW and stored_date is not None:
        return stored_date, ORIGIN_INTERVIEW

    pages = _page_texts(chunks or [])
    if stored_origin == ORIGIN_DOCUMENT and stored_date is not None:
        return stored_date, ORIGIN_DOCUMENT
    if routed_kind != KIND_TRANSCRIPT:
        try:
            printed = document_text_date(pages[0], pages[1], settings, usage=usage)
        except DateError as exc:
            logger.warning("source date: document text step unavailable: %s", exc)
            printed = None
        if printed is not None:
            return printed, ORIGIN_DOCUMENT

    meta = file_metadata_date(routed_kind, data)
    if meta is None and stored_origin == ORIGIN_FILE_META:
        meta = stored_date
    if meta is not None:
        return meta, ORIGIN_FILE_META

    return upload_floor(uploaded_at), ORIGIN_UPLOAD


def set_source_date(
    conn: Any,
    source_id: str,
    effective_date: date,
    date_origin: str,
) -> None:
    """Write one source's resolved date and origin."""
    conn.execute(
        "UPDATE cmap.source SET effective_date = %s, date_origin = %s WHERE id = %s",
        (effective_date, date_origin, source_id),
    )


def _source_chunks(conn: Any, source_id: str) -> list[tuple[dict[str, Any], str]]:
    """Return the source's ``(locator, text)`` pairs in reading order."""
    rows = conn.execute(
        "SELECT locator, text FROM cmap.chunk WHERE source_id = %s ORDER BY ordinal",
        (source_id,),
    ).fetchall()
    return [(locator if isinstance(locator, dict) else {}, str(text)) for locator, text in rows]


def resolve_and_store(
    conn: Any,
    row: tuple[Any, ...],
    *,
    data: bytes | None,
    settings: Settings,
    usage: dict[str, int] | None = None,
) -> tuple[date, str]:
    """Resolve one source row and write the winner; return it.

    ``row`` is ``(id, kind, original_filename, storage_path, effective_date,
    date_origin, created_at)``. Legacy rows with a date but no origin took it
    from the admin field, so they are stamped ``admin``.
    """
    (
        source_id,
        kind,
        _original_filename,
        storage_path,
        stored_date,
        stored_origin,
        created_at,
    ) = row
    source_id = str(source_id)
    if stored_date is not None and stored_origin is None:
        set_source_date(conn, source_id, stored_date, ORIGIN_ADMIN)
        return stored_date, ORIGIN_ADMIN
    routed = read_kind(str(kind), str(storage_path))
    effective, origin = resolve_source_date(
        routed_kind=routed,
        data=data,
        chunks=_source_chunks(conn, source_id),
        stored_date=stored_date,
        stored_origin=str(stored_origin) if stored_origin else None,
        uploaded_at=created_at,
        settings=settings,
        usage=usage,
    )
    set_source_date(conn, source_id, effective, origin)
    return effective, origin


_BACKFILL_COLUMNS = (
    "id, kind, original_filename, storage_path, effective_date, date_origin, created_at"
)


def handle_backfill_dates(job: dict[str, Any]) -> None:
    """Stamp dates on sources that predate D1 (idempotent).

    Rows already carrying a date and origin are left alone; a legacy row with
    an admin-entered date and no origin becomes ``admin``. Everything else
    runs the full precedence chain and always ends dated.
    """
    del job
    settings = get_settings()

    with get_pool().connection() as conn:
        rows = conn.execute(
            f"SELECT {_BACKFILL_COLUMNS} FROM cmap.source "
            "WHERE effective_date IS NULL OR date_origin IS NULL ORDER BY created_at"
        ).fetchall()
    resolved = 0
    for row in rows:
        source_id = str(row[0])
        if row[4] is not None and row[5] is None:
            with get_pool().connection() as conn:
                set_source_date(conn, source_id, row[4], ORIGIN_ADMIN)
                conn.commit()
            resolved += 1
            continue
        data: bytes | None
        try:
            data = storage_mod.get_storage().download(str(row[3]))
        except Exception as exc:  # storage error: the floor still dates it
            logger.warning("backfill dates: %s unreadable (%s)", source_id, exc)
            data = None
        with get_pool().connection() as conn:
            effective, origin = resolve_and_store(
                conn, row, data=data, settings=settings
            )
            conn.commit()
        resolved += 1
        logger.info("backfill dates: %s -> %s (%s)", source_id, effective, origin)
    logger.info("backfill dates: %d source(s) resolved", resolved)
