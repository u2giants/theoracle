"""DOCX, XLSX, PPTX and delimited-text (CSV/TSV) reading.

The zip/XML parsing core is copied from
``services/oracle-brain/oracle_brain/ingest/binary_documents.py`` (the working
hand-written OOXML parser): same package-safety checks, same paragraph, cell
and slide extraction, re-emitted as chunks instead of native blocks.

Packages that carry embedded objects or external links are read: members
under ``embeddings/`` are never opened and external relationships are never
resolved or fetched. XML is parsed as a stream bounded by bytes. Tables
(sheets, CSV files, DOCX tables) become Markdown tables whose header is
repeated in every chunk; pictures go through the vision reader.
"""

from __future__ import annotations

import csv
import io
import logging
import math
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable, Iterator, Sequence
from datetime import date, timedelta
from typing import Any

from PIL import Image

from brain.read.chunk import (
    WINDOW_TOKENS,
    Chunk,
    count_tokens,
    pack_units,
    window_chunks,
)
from brain.read.detect import KIND_TSV, MAX_OFFICE_UNCOMPRESSED_BYTES
from brain.read.vision import VisionError, build_visual_text, visual_read

logger = logging.getLogger(__name__)

# One limit shared by intake (detect.verify_office_zip) and by reading.
MAX_EXPANDED_BYTES = MAX_OFFICE_UNCOMPRESSED_BYTES
MAX_PARTS = 2000
# Parts held as a whole tree (document, slide, relationships, styles).
MAX_TREE_XML_BYTES = 8 * 1024 * 1024
MAX_XML_DEPTH = 128
# Rendered cells one sheet or delimited file may produce (sparse-sheet guard).
MAX_TABLE_CELLS = 5_000_000
PICTURE_GAP = "[picture could not be read]"

_XML_DECLARATION = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.I)
_SPAN_KEY = "_span"
_VISION_MEDIA_TYPES = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "GIF": "image/gif",
    "WEBP": "image/webp",
}
_BUILTIN_DATE_FORMATS = frozenset(
    [*range(14, 23), *range(27, 37), *range(45, 48), *range(50, 59)]
)
_FORMAT_LITERALS = re.compile(r'"[^"]*"|\\.|\[[^\]]*\]|_.|\*.')

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "v": "urn:schemas-microsoft-com:vml",
}

_W_P = f'{{{NS["w"]}}}p'
_W_T = f'{{{NS["w"]}}}t'
_W_TAB = f'{{{NS["w"]}}}tab'
_W_BR = f'{{{NS["w"]}}}br'
_W_TBL = f'{{{NS["w"]}}}tbl'
_W_VAL = f'{{{NS["w"]}}}val'
_A_BLIP = f'{{{NS["a"]}}}blip'
_V_IMAGEDATA = f'{{{NS["v"]}}}imagedata'
_MC_FALLBACK = f'{{{NS["mc"]}}}Fallback'
_R_EMBED = f'{{{NS["r"]}}}embed'
_R_LINK = f'{{{NS["r"]}}}link'
_R_ID = f'{{{NS["r"]}}}id'
_S_ROW = f'{{{NS["s"]}}}row'
_S_T = f'{{{NS["s"]}}}t'
_S_SHEET_DATA = f'{{{NS["s"]}}}sheetData'


class OfficeReadError(ValueError):
    """Raised when an office container cannot be read safely."""


class _Package:
    """An OOXML zip package checked for safe, bounded expansion."""

    def __init__(self, data: bytes) -> None:
        try:
            self.zip = zipfile.ZipFile(io.BytesIO(data))
        except (zipfile.BadZipFile, ValueError) as exc:
            raise OfficeReadError("invalid OOXML package") from exc
        try:
            self._validate()
        except Exception:
            self.zip.close()
            raise

    def _validate(self) -> None:
        parts = self.zip.infolist()
        names = [info.filename for info in parts]
        if len(parts) > MAX_PARTS or len(names) != len(set(names)):
            raise OfficeReadError("duplicate or excessive package parts")
        total = 0
        for info in parts:
            name = info.filename
            unsafe = (
                "\\" in name
                or name.startswith("/")
                or posixpath.normpath(name) != name.rstrip("/")
                or any(part in {"", "..", "."} for part in name.rstrip("/").split("/"))
            )
            if unsafe:
                raise OfficeReadError("unsafe package path")
            if info.flag_bits & 1:
                raise OfficeReadError("encrypted package unsupported")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise OfficeReadError("package symlink denied")
            total += info.file_size
            ratio_bomb = info.file_size > 1024 * 1024 and info.file_size > 200 * max(
                1, info.compress_size
            )
            if total > MAX_EXPANDED_BYTES or ratio_bomb:
                raise OfficeReadError("package expansion limit exceeded")
            lowered = name.lower()
            if any(x in lowered for x in ("vbaproject", "activex/")):
                raise OfficeReadError("active content unsupported")
        # Embedded objects (a chart's workbook, an OLE file) are skipped: they
        # count toward the size limits above but are never opened or parsed.
        self.names = {name for name in names if "embeddings/" not in name.lower()}
        self.xml("[Content_Types].xml")

    def read(self, name: str) -> bytes:
        if name not in self.names:
            raise OfficeReadError("required package part missing")
        try:
            return self.zip.read(name)
        except (zipfile.BadZipFile, RuntimeError, KeyError, NotImplementedError, OSError) as exc:
            raise OfficeReadError("corrupt or unsupported package part") from exc

    def events(self, name: str, limit: int) -> Iterator[tuple[str, ET.Element]]:
        """Stream the ``start``/``end`` events of one XML part.

        The part is fed to the parser block by block and refused once it
        passes ``limit`` bytes, nests deeper than ``MAX_XML_DEPTH``, or
        declares a DOCTYPE or entity.
        """
        if name not in self.names:
            raise OfficeReadError("required package part missing")
        parser = ET.XMLPullParser(("start", "end"))
        depth = 0
        seen = 0
        tail = b""
        try:
            with self.zip.open(name) as stream:
                while True:
                    block = stream.read(65536)
                    if not block:
                        break
                    seen += len(block)
                    if seen > limit or b"\0" in block:
                        raise OfficeReadError("XML size or encoding unsupported")
                    if _XML_DECLARATION.search(tail + block):
                        raise OfficeReadError("XML declarations with entities denied")
                    tail = block[-32:]
                    parser.feed(block)
                    for event, node in parser.read_events():
                        depth += 1 if event == "start" else -1
                        if depth > MAX_XML_DEPTH:
                            raise OfficeReadError("XML structure limit exceeded")
                        yield event, node
            parser.close()
            yield from parser.read_events()
        except ET.ParseError as exc:
            raise OfficeReadError("malformed package XML") from exc
        except (zipfile.BadZipFile, RuntimeError, KeyError, NotImplementedError, OSError) as exc:
            raise OfficeReadError("corrupt or unsupported package part") from exc

    def xml(self, name: str) -> ET.Element:
        """Return one small XML part as a whole tree."""
        root: ET.Element | None = None
        for _event, node in self.events(name, MAX_TREE_XML_BYTES):
            if root is None:
                root = node
        if root is None:
            raise OfficeReadError("malformed package XML")
        return root

    def relations(self, part: str) -> list[tuple[str, str, str]]:
        """Return ``(id, type, target part)`` for in-package relationships.

        External relationships (hyperlinks, linked pictures, linked
        workbooks) are ignored and never fetched; so are targets that are
        skipped or absent. A target that climbs out of the package is refused.
        """
        rel = posixpath.join(
            posixpath.dirname(part),
            "_rels",
            posixpath.basename(part) + ".rels",
        )
        if rel not in self.names:
            return []
        found: list[tuple[str, str, str]] = []
        for relation in self.xml(rel):
            if relation.get("TargetMode", "").lower() == "external":
                continue
            target = relation.get("Target", "")
            if target.startswith("/"):
                resolved = posixpath.normpath(target[1:])
            else:
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(part), target))
            if resolved == ".." or resolved.startswith("../") or resolved.startswith("/"):
                raise OfficeReadError("relationship outside package")
            if resolved in self.names:
                found.append((relation.get("Id", ""), relation.get("Type", ""), resolved))
        return found

    def target(self, part: str, identifier: str) -> str:
        matches = [r for r in self.relations(part) if r[0] == identifier]
        if len(matches) != 1:
            raise OfficeReadError("ambiguous or missing package relationship")
        return matches[0][2]

    def require_type(self, part: str, content_type: str) -> None:
        types = self.xml("[Content_Types].xml")
        found = [x.get("ContentType") for x in types if x.get("PartName") == "/" + part]
        if found != [content_type]:
            raise OfficeReadError("package content type mismatch")


def _paragraph_text(node: ET.Element) -> str:
    """Return the visible text of one OOXML paragraph node."""
    result: list[str] = []
    pending = list(reversed(list(node)))
    while pending:
        child = pending.pop()
        if child.tag in {f'{{{NS["w"]}}}p', f'{{{NS["a"]}}}p'}:
            continue
        if child.tag in {f'{{{NS["w"]}}}t', f'{{{NS["a"]}}}t'}:
            result.append(child.text or "")
        elif child.tag == f'{{{NS["w"]}}}tab':
            result.append("\t")
        elif child.tag in {f'{{{NS["w"]}}}br', f'{{{NS["a"]}}}br'}:
            result.append("\n")
        else:
            pending.extend(reversed(list(child)))
    return "".join(result)


def _column_letters(number: int) -> str:
    """Return the spreadsheet column name for a 1-based column number."""
    letters = ""
    while number > 0:
        number, remainder = divmod(number - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters or "A"


# --------------------------------------------------------------------------
# Pictures
# --------------------------------------------------------------------------


def _vision_image(data: bytes) -> tuple[bytes, str]:
    """Return picture bytes and their true media type, as vision accepts them.

    The type comes from the bytes, never from the file name. Formats the
    vision reader does not take (BMP, TIFF) are re-encoded as PNG.
    """
    try:
        with Image.open(io.BytesIO(data)) as image:
            media_type = _VISION_MEDIA_TYPES.get(image.format or "")
            if media_type is not None:
                return data, media_type
            out = io.BytesIO()
            image.convert("RGBA").save(out, format="PNG")
            return out.getvalue(), "image/png"
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise OfficeReadError("picture is not a readable image") from exc


def _picture_text(
    package: _Package,
    target: str | None,
    usage: dict[str, int] | None,
) -> str:
    """Return the vision reading of one embedded picture, or a noted gap.

    A picture that is linked rather than embedded, is not a readable image,
    or that the vision reader fails on becomes ``PICTURE_GAP`` in the text
    (logged, and counted in ``usage``) instead of failing the document.
    """
    try:
        if target is None:
            raise OfficeReadError("picture is not embedded in the file")
        payload, media_type = _vision_image(package.read(target))
        return build_visual_text(visual_read(payload, media_type, usage=usage))
    except (OfficeReadError, VisionError) as exc:
        logger.warning("office picture could not be read: %s", exc)
        if usage is not None:
            usage["picture_gaps"] = usage.get("picture_gaps", 0) + 1
        return PICTURE_GAP


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------


def _md_cell(value: str) -> str:
    """Return one cell's text safe for a single Markdown table cell."""
    return " ".join(value.replace("|", "\\|").split())


def _md_row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _table_parts(
    rows: Sequence[Sequence[str]],
    fallback: Sequence[str] | None = None,
) -> tuple[str | None, list[str], bool]:
    """Render ``rows`` as Markdown: ``(header block, data rows, first row used)``.

    The first row is the header. Every row is padded to the same width so
    empty cells keep their place. A first row too long to repeat in every
    chunk (over half a window) stays a data row; ``fallback`` names then head
    the table when given.
    """
    width = max(len(row) for row in rows)
    rendered = [
        _md_row([_md_cell(cell) for cell in row] + [""] * (width - len(row)))
        for row in rows
    ]
    separator = _md_row(["---"] * width)
    if count_tokens(rendered[0]) <= WINDOW_TOKENS // 2:
        return f"{rendered[0]}\n{separator}", rendered[1:], True
    if fallback is not None:
        return f"{_md_row(list(fallback))}\n{separator}", rendered, False
    return None, rendered, False


def _pack_with_headers(
    units: Sequence[str],
    headers: Sequence[str | None],
    locator_for: Callable[[int, int], dict[str, Any]],
) -> list[Chunk]:
    """Pack whole units and repeat each table's header in every chunk.

    ``headers[i]`` is the Markdown header block of the table that unit ``i``
    is a row of, or ``None`` for ordinary text. Packing is ``pack_units``:
    a row is never split unless it alone is larger than the window.
    """

    def spanned(first: int, last: int) -> dict[str, Any]:
        locator = locator_for(first, last)
        locator[_SPAN_KEY] = (first, last)
        return locator

    chunks: list[Chunk] = []
    for chunk in pack_units(units, spanned):
        locator = dict(chunk.locator)
        first, last = locator.pop(_SPAN_KEY)
        if first == last and chunk.text != units[first].strip():
            # A piece of one unit that alone is larger than the window.
            header = headers[first]
            text = f"{header}\n{chunk.text}" if header else chunk.text
        else:
            lines: list[str] = []
            for index in range(first, last + 1):
                header = headers[index]
                if header and (index == first or headers[index - 1] != header):
                    lines.append(header)
                lines.append(units[index])
            text = "\n".join(lines).strip()
        chunks.append(Chunk(locator, text, count_tokens(text)))
    return chunks


def _grid_chunks(
    rows: Sequence[Sequence[str]],
    numbers: Sequence[int],
    column_names: Sequence[str],
    base_locator: dict[str, Any],
) -> list[Chunk]:
    """Chunk one grid (a sheet or a delimited file) as header-repeating tables.

    ``numbers`` are the rows' numbers in the file and ``column_names`` the
    column letters; both go into each chunk's ``range`` locator.
    """
    if not rows:
        return []
    if len(rows) * len(column_names) > MAX_TABLE_CELLS:
        raise OfficeReadError("table is too large or too sparse to read")
    header, units, first_row_is_header = _table_parts(rows, column_names)
    offset = 1 if first_row_is_header else 0
    first_column, last_column = column_names[0], column_names[-1]

    def locator(first: int, last: int) -> dict[str, Any]:
        top = numbers[0] if first == 0 else numbers[first + offset]
        bottom = numbers[last + offset]
        return {**base_locator, "range": f"{first_column}{top}:{last_column}{bottom}"}

    if not units:
        text = header or ""
        only = f"{first_column}{numbers[0]}:{last_column}{numbers[0]}"
        return [Chunk({**base_locator, "range": only}, text, count_tokens(text))]
    return _pack_with_headers(units, [header] * len(units), locator)


# --------------------------------------------------------------------------
# DOCX
# --------------------------------------------------------------------------


class _DocxReader:
    """Walk DOCX parts in reading order into text units.

    A paragraph is one unit; a table is rendered as a Markdown table in
    place, one unit per row; an embedded picture is read by the vision
    reader and its text inserted where the picture sits.
    """

    def __init__(self, package: _Package, usage: dict[str, int] | None) -> None:
        self.package = package
        self.usage = usage
        self.units: list[str] = []
        self.headers: list[str | None] = []
        self.visual: set[int] = set()
        self._part = ""
        self._pictures: dict[str, str] = {}
        self._picture_count = 0

    def read_part(self, part: str) -> None:
        self._part = part
        self._blocks(self.package.xml(part))

    def _blocks(self, node: ET.Element) -> None:
        for child in node:
            if child.tag == _W_P:
                before = self._picture_count
                self.units.append(self._paragraph(child))
                self.headers.append(None)
                if self._picture_count > before:
                    self.visual.add(len(self.units) - 1)
            elif child.tag == _W_TBL:
                self._table(child)
            elif child.tag != _MC_FALLBACK:
                self._blocks(child)

    def _table(self, node: ET.Element) -> None:
        before = self._picture_count
        rows: list[list[str]] = []
        for row in node.findall("w:tr", NS):
            cells: list[str] = []
            for cell in row.findall("w:tc", NS):
                texts: list[str] = []
                self._cell_paragraphs(cell, texts)
                cells.append(" ".join(text for text in texts if text.strip()))
                span = cell.find("w:tcPr/w:gridSpan", NS)
                width = span.get(_W_VAL, "1") if span is not None else "1"
                if width.isdigit():
                    cells.extend([""] * (min(int(width), 63) - 1))
            if cells:
                rows.append(cells)
        if not rows:
            return
        start = len(self.units)
        header, data, _first_row_is_header = _table_parts(rows)
        if header is not None and not data:
            self.units.append(header)
            self.headers.append(None)
        else:
            self.units.extend(data)
            self.headers.extend([header] * len(data))
        if self._picture_count > before:
            self.visual.update(range(start, len(self.units)))

    def _cell_paragraphs(self, node: ET.Element, sink: list[str]) -> None:
        for child in node:
            if child.tag == _W_P:
                sink.append(self._paragraph(child))
            elif child.tag != _MC_FALLBACK:
                self._cell_paragraphs(child, sink)

    def _paragraph(self, node: ET.Element) -> str:
        """Return a paragraph's text with picture readings at their positions."""
        result: list[str] = []
        inserted = False
        pending = list(reversed(list(node)))
        while pending:
            child = pending.pop()
            tag = child.tag
            if tag == _MC_FALLBACK:
                continue
            if tag == _W_P:
                # A text box anchored in this paragraph.
                result.append("\n" + self._paragraph(child) + "\n")
                inserted = True
            elif tag == _W_T:
                result.append(child.text or "")
            elif tag == _W_TAB:
                result.append("\t")
            elif tag == _W_BR:
                result.append("\n")
            elif tag in (_A_BLIP, _V_IMAGEDATA):
                embedded = child.get(_R_EMBED) or child.get(_R_ID)
                if embedded or child.get(_R_LINK):
                    result.append("\n" + self._picture(embedded) + "\n")
                    inserted = True
            else:
                pending.extend(reversed(list(child)))
        text = "".join(result)
        if inserted:
            text = re.sub(r"\n{2,}", "\n", text).strip("\n")
        return text

    def _picture(self, identifier: str | None) -> str:
        self._picture_count += 1
        target: str | None = None
        if identifier:
            try:
                target = self.package.target(self._part, identifier)
            except OfficeReadError:
                target = None
        if target is None:
            return _picture_text(self.package, None, self.usage)
        if target not in self._pictures:
            self._pictures[target] = _picture_text(self.package, target, self.usage)
        return self._pictures[target]


def read_docx(data: bytes, usage: dict[str, int] | None = None) -> list[Chunk]:
    """Read a DOCX into chunks of whole paragraphs and table rows.

    Tables are Markdown tables in place (header repeated per chunk) and
    embedded pictures are read by the vision reader at their position.
    """
    package = _Package(data)
    try:
        package.require_type(
            "word/document.xml",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
        )
        parts = ["word/document.xml"] + sorted(
            name
            for name in package.names
            if re.fullmatch(
                r"word/(header\d+|footer\d+|footnotes|endnotes|comments)\.xml", name
            )
        )
        reader = _DocxReader(package, usage)
        for part in parts:
            reader.read_part(part)
    finally:
        package.zip.close()
    if not reader.units:
        return []

    def locator(first: int, last: int) -> dict[str, Any]:
        found: dict[str, Any] = {"paragraph": f"{first + 1}-{last + 1}"}
        if any(index in reader.visual for index in range(first, last + 1)):
            found["visual"] = True
        return found

    return _pack_with_headers(reader.units, reader.headers, locator)


# --------------------------------------------------------------------------
# XLSX
# --------------------------------------------------------------------------


def _is_date_format(format_id: int, code: str | None) -> bool:
    """True when a number format shows its value as a date or time."""
    if code is None:
        return format_id in _BUILTIN_DATE_FORMATS
    stripped = _FORMAT_LITERALS.sub("", code).lower()
    return "general" not in stripped and re.search(r"[dmyhs]", stripped) is not None


def _date_styles(package: _Package) -> list[bool]:
    """Return, per cell style index, whether that style formats a date."""
    if "xl/styles.xml" not in package.names:
        return []
    root = package.xml("xl/styles.xml")
    custom = {
        fmt.get("numFmtId", ""): fmt.get("formatCode", "")
        for fmt in root.findall("s:numFmts/s:numFmt", NS)
    }
    styles: list[bool] = []
    for xf in root.findall("s:cellXfs/s:xf", NS):
        raw = xf.get("numFmtId", "0")
        format_id = int(raw) if raw.isdigit() else 0
        styles.append(_is_date_format(format_id, custom.get(raw)))
    return styles


def _serial_to_iso(value: str, date1904: bool) -> str | None:
    """Convert a spreadsheet date serial number to an ISO date or time."""
    try:
        serial = float(value)
    except ValueError:
        return None
    if not math.isfinite(serial) or serial < 0 or serial >= 2958466:
        return None
    days = int(serial)
    seconds = round((serial - days) * 86400)
    if seconds >= 86400:
        days, seconds = days + 1, 0
    clock = f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
    if days == 0:
        return clock if seconds else None
    if date1904:
        epoch = date(1904, 1, 1)
    elif days < 60:
        epoch = date(1899, 12, 31)
    else:
        # The 1900 system counts a 29 February 1900 that never existed.
        epoch = date(1899, 12, 30)
    day = (epoch + timedelta(days=days)).isoformat()
    return f"{day}T{clock}" if seconds else day


def _shared_strings(package: _Package) -> list[str]:
    """Stream the workbook's shared strings."""
    if "xl/sharedStrings.xml" not in package.names:
        return []
    shared: list[str] = []
    stack: list[ET.Element] = []
    for event, node in package.events("xl/sharedStrings.xml", MAX_EXPANDED_BYTES):
        if event == "start":
            stack.append(node)
            continue
        stack.pop()
        if len(stack) == 1:
            shared.append("".join(t.text or "" for t in node.iter(_S_T)))
            stack[0].remove(node)
    return shared


def _cell_value(
    cell: ET.Element,
    shared: list[str],
    date_styles: list[bool],
    date1904: bool,
) -> str:
    """Return one cell's text; date-styled numbers become ISO dates."""
    value_node = cell.find("s:v", NS)
    value = value_node.text or "" if value_node is not None else ""
    kind = cell.get("t", "n")
    if kind == "s":
        if not re.fullmatch(r"[0-9]+", value):
            raise OfficeReadError("invalid shared string index")
        try:
            return shared[int(value)]
        except (ValueError, IndexError) as exc:
            raise OfficeReadError("invalid shared string index") from exc
    if kind == "inlineStr":
        return "".join(t.text or "" for t in cell.findall(".//s:t", NS))
    if kind == "b":
        return {"1": "TRUE", "0": "FALSE"}.get(value, value)
    if kind == "n" and value:
        style = cell.get("s", "")
        if style.isdigit() and int(style) < len(date_styles) and date_styles[int(style)]:
            return _serial_to_iso(value, date1904) or value
    return value


def _sheet_rows(
    package: _Package,
    part: str,
    shared: list[str],
    date_styles: list[bool],
    date1904: bool,
) -> tuple[list[dict[int, str]], list[int]]:
    """Stream one sheet: its non-empty rows as ``{column: text}`` and row numbers.

    Rows are taken from the parser one at a time and dropped from the tree
    once read, so a large sheet is bounded by its bytes, not its node count.
    """
    rows: list[dict[int, str]] = []
    row_numbers: list[int] = []
    stack: list[ET.Element] = []
    position = 0
    for event, node in package.events(part, MAX_EXPANDED_BYTES):
        if event == "start":
            stack.append(node)
            continue
        stack.pop()
        if node.tag != _S_ROW or not stack or stack[-1].tag != _S_SHEET_DATA:
            continue
        position += 1
        cells: dict[int, str] = {}
        column = 0
        for cell in node.findall("s:c", NS):
            ref = cell.get("r")
            if ref is None:
                column += 1
            else:
                coordinate = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]{0,6})", ref)
                if coordinate is None:
                    raise OfficeReadError("invalid cell coordinate")
                column = 0
                for letter in coordinate.group(1):
                    column = column * 26 + ord(letter) - ord("A") + 1
                if int(coordinate.group(2)) > 1048576:
                    raise OfficeReadError("invalid cell coordinate")
            if column > 16384:
                raise OfficeReadError("invalid cell coordinate")
            value = _cell_value(cell, shared, date_styles, date1904)
            if value.strip():
                cells[column] = value
        if cells:
            declared = node.get("r")
            rows.append(cells)
            row_numbers.append(int(declared) if declared and declared.isdigit() else position)
        stack[-1].remove(node)
    return rows, row_numbers


def read_xlsx(data: bytes, usage: dict[str, int] | None = None) -> list[Chunk]:
    """Read an XLSX into per-sheet Markdown-table chunks.

    The first non-empty row of a sheet is its header and is repeated in every
    chunk; empty cells keep their column; rows are never split; date-styled
    cells are ISO dates. Locators carry the sheet and cell range.
    """
    del usage
    package = _Package(data)
    try:
        package.require_type(
            "xl/workbook.xml",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
        )
        workbook = package.xml("xl/workbook.xml")
        properties = workbook.find("s:workbookPr", NS)
        date1904 = properties is not None and properties.get("date1904", "0") in ("1", "true")
        shared = _shared_strings(package)
        date_styles = _date_styles(package)
        seen: set[str] = set()
        chunks: list[Chunk] = []
        for sheet in workbook.findall("s:sheets/s:sheet", NS):
            name = sheet.get("name", "")
            part = package.target("xl/workbook.xml", sheet.get(_R_ID, ""))
            if part in seen:
                raise OfficeReadError("duplicate worksheet target")
            seen.add(part)
            rows, row_numbers = _sheet_rows(package, part, shared, date_styles, date1904)
            columns = sorted({column for row in rows for column in row})
            if len(rows) * len(columns) > MAX_TABLE_CELLS:
                raise OfficeReadError("table is too large or too sparse to read")
            grid = [[row.get(column, "") for column in columns] for row in rows]
            letters = [_column_letters(column) for column in columns]
            chunks.extend(_grid_chunks(grid, row_numbers, letters, {"sheet": name}))
    finally:
        package.zip.close()
    return chunks


# --------------------------------------------------------------------------
# CSV / TSV
# --------------------------------------------------------------------------


def _delimiter(text: str, kind: str) -> str:
    """Pick the delimiter: tab for TSV, else comma unless the header has none."""
    if kind == KIND_TSV:
        return "\t"
    first = next((line for line in text.splitlines() if line.strip()), "")
    if "," not in first:
        for candidate in (";", "\t"):
            if candidate in first:
                return candidate
    return ","


def read_delimited(text: str, kind: str) -> list[Chunk]:
    """Read CSV or TSV text into Markdown-table chunks, like a sheet.

    The first non-empty record is the header, repeated in every chunk;
    records are never split and short records are padded so columns line up.
    """
    rows: list[list[str]] = []
    numbers: list[int] = []
    try:
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=_delimiter(text, kind))
        for number, record in enumerate(reader, start=1):
            if any(cell.strip() for cell in record):
                rows.append(record)
                numbers.append(number)
    except csv.Error as exc:
        raise OfficeReadError("malformed delimited text") from exc
    if not rows:
        return []
    width = max(len(row) for row in rows)
    letters = [_column_letters(column) for column in range(1, width + 1)]
    return _grid_chunks(rows, numbers, letters, {})


# --------------------------------------------------------------------------
# PPTX
# --------------------------------------------------------------------------


def _slide_pictures(package: _Package, part: str) -> list[str]:
    """Return the image parts a slide embeds (linked pictures are not fetched)."""
    pictures: list[str] = []
    for _identifier, kind, target in package.relations(part):
        if kind.endswith("/image") and target not in pictures:
            pictures.append(target)
    return pictures


def read_pptx(data: bytes, usage: dict[str, int] | None = None) -> list[Chunk]:
    """Read a PPTX into per-slide chunks; pictures go through the vision reader.

    A picture that cannot be read is noted in the slide text as
    ``PICTURE_GAP``; the rest of the deck is still read.
    """
    package = _Package(data)
    chunks: list[Chunk] = []
    try:
        package.require_type(
            "ppt/presentation.xml",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml",
        )
        presentation = package.xml("ppt/presentation.xml")
        seen: set[str] = set()
        for index, slide in enumerate(presentation.findall("p:sldIdLst/p:sldId", NS), 1):
            part = package.target("ppt/presentation.xml", slide.get(_R_ID, ""))
            if part in seen:
                raise OfficeReadError("duplicate slide target")
            seen.add(part)
            lines = [
                _paragraph_text(node)
                for node in package.xml(part).iter(f'{{{NS["a"]}}}p')
            ]
            for _identifier, kind, notes in package.relations(part):
                if kind.endswith("/notesSlide"):
                    for node in package.xml(notes).iter(f'{{{NS["a"]}}}p'):
                        lines.append(_paragraph_text(node))
            locator: dict[str, Any] = {"slide": index}
            for picture in _slide_pictures(package, part):
                lines.append(_picture_text(package, picture, usage))
                locator["visual"] = True
            text = "\n".join(line for line in lines if line.strip())
            chunks.extend(window_chunks(text, locator))
    finally:
        package.zip.close()
    return chunks
