"""Spreadsheet structure without execution.

Formulas are recorded as text beside the supplied cached value; they are never
evaluated.  Merged headers stay attached to every cell they span.
"""
from __future__ import annotations

import csv
import io
import re
import xml.etree.ElementTree as ET

from .limits import ProcessingBudget, SourceRejected
from .normalize import Block

_REF = re.compile(r"([A-Z]+)(\d+)")


def _col(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def _ref(ref: str) -> tuple[int, int]:
    m = _REF.fullmatch(ref)
    if not m:
        raise SourceRejected("corrupt_source", f"bad cell ref {ref!r}")
    return int(m[2]), _col(m[1])


def parse_csv(source_id: str, text: str, budget: ProcessingBudget) -> list[Block]:
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error as error:
        raise SourceRejected("corrupt_source", str(error)) from error
    if not rows:
        return []
    header, data = rows[0], rows[1:]
    blocks = []
    for r, row in enumerate(data, 2):
        budget.take_block()
        blocks.append(Block(source_id, "table_row", " | ".join(row), f"record:{r}",
                            {"cells": dict(zip(header, row))}))
    return blocks


def parse_sheet_xml(source_id: str, text: str, budget: ProcessingBudget) -> list[Block]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise SourceRejected("corrupt_source", str(error)) from error
    merges = []
    for m in root.iter("mergeCell"):
        a, _, b = m.get("ref", "").partition(":")
        merges.append((_ref(a), _ref(b or a)))
    values: dict[tuple[int, int], str] = {}
    parsed = []
    for c in root.iter("c"):
        pos = _ref(c.get("r", ""))
        f, v = c.find("f"), c.find("v")
        cached = v.text if v is not None else None
        values[pos] = cached or ""
        attrs: dict = {"row": pos[0], "col": pos[1]}
        if f is not None:
            attrs.update(formula=f.text, cached_value=cached, executed=False,
                         cached_value_trusted=False)
        parsed.append((pos, attrs, cached or ""))
    blocks = []
    for pos, attrs, value in parsed:
        headers = [values.get(start, "") for start, end in merges
                   if start[0] < pos[0] and start[1] <= pos[1] <= end[1]]
        if headers:
            attrs["headers"] = headers
        for start, end in merges:
            if start == pos:
                attrs["merged_span"] = [start[1], end[1]]
        budget.take_block()
        kind = "formula_cell" if "formula" in attrs else "table_cell"
        blocks.append(Block(source_id, kind, value, f"cell:R{pos[0]}C{pos[1]}", attrs))
    return blocks
