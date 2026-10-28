"""DOCX, XLSX and PPTX reading.

The zip/XML parsing core is copied from
``services/oracle-brain/oracle_brain/ingest/binary_documents.py`` (the working
hand-written OOXML parser): same package-safety checks, same paragraph, cell
and slide extraction, re-emitted as chunks instead of native blocks. PPTX
slides with pictures also go through the vision reader (plan step 3).
"""

from __future__ import annotations

import io
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import Any

from brain.read.chunk import Chunk, pack_units, window_chunks
from brain.read.vision import build_visual_text, visual_read

MAX_EXPANDED_BYTES = 50 * 1024 * 1024
MAX_PARTS = 2000

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


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
            if any(x in lowered for x in ("vbaproject", "embeddings/", "activex/")):
                raise OfficeReadError("active or embedded content unsupported")
        self.names = set(names)
        self.xml("[Content_Types].xml")
        for name in names:
            if name.endswith(".rels"):
                for relation in self.xml(name):
                    if relation.get("TargetMode", "").lower() == "external":
                        raise OfficeReadError("external package relationship denied")

    def read(self, name: str) -> bytes:
        if name not in self.names:
            raise OfficeReadError("required package part missing")
        try:
            return self.zip.read(name)
        except (zipfile.BadZipFile, RuntimeError, KeyError, NotImplementedError, OSError) as exc:
            raise OfficeReadError("corrupt or unsupported package part") from exc

    def xml(self, name: str) -> ET.Element:
        data = self.read(name)
        if len(data) > 8 * 1024 * 1024 or b"\0" in data:
            raise OfficeReadError("XML size or encoding unsupported")
        if re.search(br"<!\s*(DOCTYPE|ENTITY)", data, re.I):
            raise OfficeReadError("XML declarations with entities denied")
        try:
            root = ET.fromstring(data)
        except ET.ParseError as exc:
            raise OfficeReadError("malformed package XML") from exc
        pending = [(root, 1)]
        count = 0
        while pending:
            node, depth = pending.pop()
            count += 1
            if depth > 128 or count > 100000:
                raise OfficeReadError("XML structure limit exceeded")
            pending.extend((child, depth + 1) for child in node)
        return root

    def target(self, part: str, identifier: str) -> str:
        rel = posixpath.join(
            posixpath.dirname(part),
            "_rels",
            posixpath.basename(part) + ".rels",
        )
        matches = [r for r in self.xml(rel) if r.get("Id") == identifier]
        if len(matches) != 1:
            raise OfficeReadError("ambiguous or missing package relationship")
        joined = posixpath.join(posixpath.dirname(part), matches[0].get("Target", ""))
        resolved = posixpath.normpath(joined)
        if resolved.startswith("../") or resolved.startswith("/") or resolved not in self.names:
            raise OfficeReadError("relationship outside package")
        return resolved

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


def _docx_paragraphs(package: _Package) -> list[str]:
    """Return every DOCX paragraph in reading order."""
    package.require_type(
        "word/document.xml",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
    )
    parts = ["word/document.xml"] + sorted(
        name
        for name in package.names
        if re.fullmatch(r"word/(header\d+|footer\d+|footnotes|endnotes|comments)\.xml", name)
    )
    paragraphs: list[str] = []
    for part in parts:
        root = package.xml(part)
        for node in root.iter(f'{{{NS["w"]}}}p'):
            paragraphs.append(_paragraph_text(node))
    return paragraphs


def read_docx(data: bytes, usage: dict[str, int] | None = None) -> list[Chunk]:
    """Read a DOCX into paragraph-range chunks (plan step 3, office.py)."""
    del usage
    package = _Package(data)
    try:
        paragraphs = _docx_paragraphs(package)
    finally:
        package.zip.close()
    if not paragraphs:
        return []

    def locator(first: int, last: int) -> dict[str, Any]:
        return {"paragraph": f"{first + 1}-{last + 1}"}

    return pack_units(paragraphs, locator)


def _sheet_rows(package: _Package, part: str) -> tuple[list[str], list[int], int]:
    """Return one sheet's row texts, their sheet row numbers, and widest column."""
    root = package.xml(part)
    shared: list[str] = []
    if "xl/sharedStrings.xml" in package.names:
        shared = [
            "".join(t.text or "" for t in si.iter(f'{{{NS["s"]}}}t'))
            for si in package.xml("xl/sharedStrings.xml")
        ]
    rows: list[str] = []
    row_numbers: list[int] = []
    max_column = 1
    for position, row in enumerate(
        root.findall(".//s:sheetData/s:row", NS),
        start=1,
    ):
        values: list[str] = []
        for cell in row.findall("s:c", NS):
            ref = cell.get("r", "")
            coordinate = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]{0,6})", ref)
            if coordinate is None:
                raise OfficeReadError("invalid cell coordinate")
            column = 0
            for letter in coordinate.group(1):
                column = column * 26 + ord(letter) - ord("A") + 1
            if column > 16384 or int(coordinate.group(2)) > 1048576:
                raise OfficeReadError("invalid cell coordinate")
            max_column = max(max_column, column)
            value_node = cell.find("s:v", NS)
            value = value_node.text or "" if value_node is not None else ""
            if cell.get("t") == "s":
                if not re.fullmatch(r"[0-9]+", value):
                    raise OfficeReadError("invalid shared string index")
                try:
                    value = shared[int(value)]
                except (ValueError, IndexError) as exc:
                    raise OfficeReadError("invalid shared string index") from exc
            elif cell.get("t") == "inlineStr":
                value = "".join(t.text or "" for t in cell.findall(".//s:t", NS))
            values.append(value)
        rows.append("\t".join(values).rstrip("\t"))
        declared = row.get("r")
        row_numbers.append(int(declared) if declared and declared.isdigit() else position)
    return rows, row_numbers, max_column


def read_xlsx(data: bytes, usage: dict[str, int] | None = None) -> list[Chunk]:
    """Read an XLSX into per-sheet row-range chunks with sheet/range locators."""
    del usage
    package = _Package(data)
    try:
        package.require_type(
            "xl/workbook.xml",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
        )
        workbook = package.xml("xl/workbook.xml")
        seen: set[str] = set()
        chunks: list[Chunk] = []
        for sheet in workbook.findall("s:sheets/s:sheet", NS):
            name = sheet.get("name", "")
            part = package.target("xl/workbook.xml", sheet.get(f'{{{NS["r"]}}}id', ""))
            if part in seen:
                raise OfficeReadError("duplicate worksheet target")
            seen.add(part)
            rows, row_numbers, max_column = _sheet_rows(package, part)
            last_column = _column_letters(max_column)

            def locator(
                first: int,
                last: int,
                sheet_name: str = name,
                column: str = last_column,
                numbers: list[int] = row_numbers,
            ) -> dict[str, Any]:
                return {
                    "sheet": sheet_name,
                    "range": f"A{numbers[first]}:{column}{numbers[last]}",
                }

            chunks.extend(pack_units(rows, locator))
    finally:
        package.zip.close()
    return chunks


def _slide_pictures(package: _Package, part: str) -> list[bytes]:
    """Return the image parts a slide embeds."""
    rel = posixpath.join(
        posixpath.dirname(part),
        "_rels",
        posixpath.basename(part) + ".rels",
    )
    if rel not in package.names:
        return []
    pictures: list[bytes] = []
    for relation in package.xml(rel):
        if not relation.get("Type", "").endswith("/image"):
            continue
        pictures.append(package.read(package.target(part, relation.get("Id", ""))))
    return pictures


def read_pptx(data: bytes, usage: dict[str, int] | None = None) -> list[Chunk]:
    """Read a PPTX into per-slide chunks; pictures go through the vision reader."""
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
            part = package.target("ppt/presentation.xml", slide.get(f'{{{NS["r"]}}}id', ""))
            if part in seen:
                raise OfficeReadError("duplicate slide target")
            seen.add(part)
            lines = [
                _paragraph_text(node)
                for node in package.xml(part).iter(f'{{{NS["a"]}}}p')
            ]
            rel = posixpath.join(
                posixpath.dirname(part),
                "_rels",
                posixpath.basename(part) + ".rels",
            )
            if rel in package.names:
                for relation in package.xml(rel):
                    if relation.get("Type", "").endswith("/notesSlide"):
                        notes = package.target(part, relation.get("Id", ""))
                        for node in package.xml(notes).iter(f'{{{NS["a"]}}}p'):
                            lines.append(_paragraph_text(node))
            locator: dict[str, Any] = {"slide": index}
            for picture in _slide_pictures(package, part):
                visual = visual_read(picture, usage=usage)
                lines.append(build_visual_text(visual))
                locator["visual"] = True
            text = "\n".join(line for line in lines if line.strip())
            chunks.extend(window_chunks(text, locator))
    finally:
        package.zip.close()
    return chunks
