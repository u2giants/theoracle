"""Structural blocks with original evidence coordinates.

Every block keeps the source id, a locator back into the original bytes and
whether a human must review it.  Text is data only: nothing here executes,
fetches or follows instructions found inside a source.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Callable

from .limits import ProcessingBudget, SourceRejected, check_bytes, decode_text


@dataclass(frozen=True)
class Block:
    source_id: str
    kind: str
    text: str
    locator: str
    attrs: dict[str, Any] = field(default_factory=dict)
    needs_review: bool = False


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.rows.append([])
        elif tag in ("td", "th"):
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self.rows[-1].append("".join(self._cell).strip())
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _html(source_id: str, text: str, budget: ProcessingBudget) -> list[Block]:
    parser = _TableParser()
    parser.feed(text)
    blocks = []
    for r, row in enumerate(parser.rows, 1):
        for c, cell in enumerate(row, 1):
            budget.take_block()
            blocks.append(Block(source_id, "table_cell", cell, f"row:{r}/col:{c}",
                                {"row": r, "col": c}))
    return blocks


def _docx(source_id: str, text: str, budget: ProcessingBudget) -> list[Block]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise SourceRejected("corrupt_source", str(error)) from error
    blocks = []
    for index, node in enumerate(root, 1):
        tag = node.tag.split("}")[-1]
        if tag == "del":
            continue  # tracked deletion: never admitted as current text
        value = "".join(t.text or "" for t in node.iter() if t.tag.split("}")[-1] == "t")
        budget.take_block()
        blocks.append(Block(source_id, "paragraph", value, f"run:{index}",
                            {"revision": "inserted" if tag == "ins" else "original"}))
    return blocks


def _email(source_id: str, text: str, budget: ProcessingBudget) -> list[Block]:
    head, _, body = text.partition("\n\n")
    sender = next((l[5:].strip() for l in head.splitlines() if l.startswith("From:")), "")
    blocks = []
    for n, line in enumerate(body.splitlines(), 1):
        if not line.strip():
            continue
        budget.take_block()
        quoted = line.startswith(">")
        blocks.append(Block(source_id, "quotation" if quoted else "assertion",
                            line.lstrip("> ").strip(), f"body_line:{n}",
                            {"asserted_by": None if quoted else sender}))
    return blocks


_CUE = re.compile(r"(\d\d:\d\d:\d\d\.\d{3}) --> (\d\d:\d\d:\d\d\.\d{3})")


def _seconds(stamp: str) -> float:
    h, m, s = stamp.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def _vtt(source_id: str, text: str, budget: ProcessingBudget) -> list[Block]:
    cues = []
    for chunk in text.split("\n\n")[1:]:
        lines = chunk.strip().splitlines()
        if not lines or not (m := _CUE.match(lines[0])):
            continue
        speaker, _, said = " ".join(lines[1:]).partition(":")
        cues.append((_seconds(m[1]), _seconds(m[2]), speaker.strip(), said.strip(), lines[0]))
    blocks = []
    for i, (start, end, speaker, said, locator) in enumerate(cues):
        overlap = any(j != i and o[0] < end and start < o[1] for j, o in enumerate(cues))
        budget.take_block()
        blocks.append(Block(source_id, "utterance", said, f"cue:{locator}",
                            {"speaker": speaker, "overlaps": overlap}, needs_review=overlap))
    return blocks


def _plain(source_id: str, text: str, budget: ProcessingBudget) -> list[Block]:
    blocks = []
    for n, line in enumerate(text.splitlines(), 1):
        if line.strip():
            budget.take_block()
            kind = "heading" if line.startswith("#") else "paragraph"
            blocks.append(Block(source_id, kind, line.lstrip("# ").strip(), f"line:{n}",
                                {"inert_source_text": True}))
    return blocks


def _parsers() -> dict[str, Callable[[str, str, ProcessingBudget], list[Block]]]:
    from . import images, spreadsheets

    return {
        "text/html": _html,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document+xml": _docx,
        "message/rfc822": _email,
        "text/vtt": _vtt,
        "text/markdown": _plain,
        "text/plain": _plain,
        "text/csv": spreadsheets.parse_csv,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet+xml": spreadsheets.parse_sheet_xml,
        "application/vnd.oracle.ocr+json": images.parse_ocr,
        "image/svg+xml": images.parse_svg,
    }


def normalize(source_id: str, source_format: str, data: bytes,
              budget: ProcessingBudget | None = None) -> list[Block]:
    """Turn admitted bytes into structural blocks; unknown formats fail visibly."""
    check_bytes(data)
    parser = _parsers().get(source_format)
    if parser is None:
        raise SourceRejected("unsupported_format", source_format)
    return parser(source_id, decode_text(data), budget or ProcessingBudget())
