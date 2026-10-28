"""Map an uploaded file to a source kind and reject hostile payloads.

Kind comes from the file extension plus the file's magic bytes; a file whose
bytes disagree with its extension is refused (plan step 2, adversarial table).
Office files are zip containers and are checked for zip-bomb sizes before the
intake accepts them.
"""

from __future__ import annotations

import zipfile
from typing import BinaryIO

KIND_PDF = "pdf"
KIND_DOCX = "docx"
KIND_XLSX = "xlsx"
KIND_PPTX = "pptx"
KIND_TEXT = "text"
KIND_IMAGE = "image"
KIND_TRANSCRIPT = "transcript"

VALID_KINDS = frozenset(
    {
        KIND_PDF,
        KIND_DOCX,
        KIND_XLSX,
        KIND_PPTX,
        KIND_TEXT,
        KIND_IMAGE,
        KIND_TRANSCRIPT,
    }
)

MAX_OFFICE_UNCOMPRESSED_BYTES = 100 * 1024 * 1024

_EXTENSION_KINDS: dict[str, str] = {
    ".pdf": KIND_PDF,
    ".docx": KIND_DOCX,
    ".xlsx": KIND_XLSX,
    ".pptx": KIND_PPTX,
    ".txt": KIND_TEXT,
    ".md": KIND_TEXT,
    ".csv": KIND_TEXT,
    ".json": KIND_TEXT,
    ".log": KIND_TEXT,
    ".png": KIND_IMAGE,
    ".jpg": KIND_IMAGE,
    ".jpeg": KIND_IMAGE,
    ".gif": KIND_IMAGE,
    ".webp": KIND_IMAGE,
    ".svg": KIND_IMAGE,
    ".vtt": KIND_TRANSCRIPT,
}

_ZIP_KINDS = frozenset({KIND_DOCX, KIND_XLSX, KIND_PPTX})

_ZIP_MEMBER_PREFIX = {
    KIND_DOCX: "word/",
    KIND_XLSX: "xl/",
    KIND_PPTX: "ppt/",
}


class DetectError(ValueError):
    """Raised when a payload cannot be accepted as its declared kind."""


def _extension(filename: str) -> str:
    """Return the lowercased extension of ``filename``."""
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    dot = name.rfind(".")
    if dot <= 0:
        return ""
    return name[dot:].lower()


def _is_zip(head: bytes) -> bool:
    """True when the bytes start a zip archive."""
    return head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06")


def _is_image(head: bytes) -> bool:
    """True when the bytes start a supported raster image or an SVG."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if head.startswith(b"\xff\xd8\xff"):
        return True
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return True
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return True
    probe = head.lstrip(b"\xef\xbb\xbf \t\r\n")
    lowered = probe[:512].lower()
    if lowered.startswith(b"<svg") or (
        lowered.startswith(b"<?xml") and b"<svg" in lowered
    ):
        return True
    return False


def _is_text(head: bytes) -> bool:
    """True when the bytes look like decodable text rather than a binary."""
    if head.startswith(b"\xef\xbb\xbf"):
        body = head[3:]
    else:
        body = head
    for magic in (b"%PDF", b"PK\x03\x04", b"MZ", b"\x7fELF", b"\x89PNG"):
        if body.startswith(magic):
            return False
    try:
        body.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def detect_kind(filename: str, head: bytes) -> str:
    """Return the source kind for ``filename`` carrying ``head`` bytes.

    ``head`` is the first bytes of the file. The extension picks the expected
    kind and the bytes must confirm it; a mismatch raises :class:`DetectError`.
    """
    ext = _extension(filename)
    kind = _EXTENSION_KINDS.get(ext)
    if kind is None:
        raise DetectError(f"unsupported file extension {ext or '(none)'!r}")
    if kind == KIND_PDF:
        if not head.startswith(b"%PDF"):
            raise DetectError("file extension is .pdf but the bytes are not a PDF")
        return kind
    if kind in _ZIP_KINDS:
        if not _is_zip(head):
            raise DetectError(
                f"file extension is {ext} but the bytes are not a zip container"
            )
        return kind
    if kind == KIND_IMAGE:
        if not _is_image(head):
            raise DetectError(
                f"file extension is {ext} but the bytes are not a supported image"
            )
        return kind
    if not _is_text(head):
        raise DetectError(
            f"file extension is {ext} but the bytes are not readable text"
        )
    return kind


def verify_office_zip(stream: BinaryIO, kind: str) -> None:
    """Check an office container for the expected parts and zip-bomb sizes.

    ``stream`` must be seekable and ``kind`` one of docx/xlsx/pptx. Raises
    :class:`DetectError` when the archive does not hold that kind of document,
    or when the members declare more than ``MAX_OFFICE_UNCOMPRESSED_BYTES``
    of uncompressed data.
    """
    prefix = _ZIP_MEMBER_PREFIX.get(kind)
    if prefix is None:
        raise DetectError(f"{kind!r} is not a zip-based office kind")
    stream.seek(0)
    try:
        archive = zipfile.ZipFile(stream)
    except zipfile.BadZipFile as exc:
        raise DetectError("file is not a readable zip container") from exc
    with archive:
        names = archive.namelist()
        total_uncompressed = 0
        for info in archive.infolist():
            total_uncompressed += info.file_size
        if total_uncompressed > MAX_OFFICE_UNCOMPRESSED_BYTES:
            raise DetectError(
                "office file expands to more than "
                f"{MAX_OFFICE_UNCOMPRESSED_BYTES // (1024 * 1024)} MB"
            )
        if not any(name.startswith(prefix) for name in names):
            raise DetectError(
                f"zip container does not hold the {kind} document its extension claims"
            )
    stream.seek(0)
