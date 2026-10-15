"""Image, OCR and diagram regions.

OCR text below the confidence floor routes to review instead of being trusted.
Diagram edges come from explicit arrow geometry only, never from proximity.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET

from .limits import ProcessingBudget, SourceRejected
from .normalize import Block

OCR_REVIEW_FLOOR = 0.85
_SVG = "{http://www.w3.org/2000/svg}"
_PATH = re.compile(r"M\s*(-?[\d.]+)[ ,](-?[\d.]+)\s*L\s*(-?[\d.]+)[ ,](-?[\d.]+)")


def parse_ocr(source_id: str, text: str, budget: ProcessingBudget) -> list[Block]:
    blocks = []
    for n, line in enumerate(l for l in text.splitlines() if l.strip()):
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            raise SourceRejected("corrupt_source", str(error)) from error
        confidence = float(item.get("confidence", 0.0))
        budget.take_block()
        blocks.append(Block(
            source_id, "ocr_region", item.get("text", ""), f"region:{n}",
            {"bbox": item.get("bbox"), "page": item.get("page"),
             "rotation": item.get("rotation", 0), "confidence": confidence,
             "label": item.get("image_label")},
            needs_review=confidence < OCR_REVIEW_FLOOR))
    return blocks


def parse_svg(source_id: str, text: str, budget: ProcessingBudget) -> list[Block]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise SourceRejected("corrupt_source", str(error)) from error
    labels = [(float(t.get("x", 0)), float(t.get("y", 0)), t.text or "")
              for t in root.iter(f"{_SVG}text")]
    blocks = []
    for x, y, label in labels:
        budget.take_block()
        blocks.append(Block(source_id, "diagram_node", label, f"point:{x:g},{y:g}",
                            {"x": x, "y": y}))

    def nearest(px: float, py: float) -> str:
        return min(labels, key=lambda l: (l[0] - px) ** 2 + (l[1] - py) ** 2)[2]

    for i, path in enumerate(root.iter(f"{_SVG}path")):
        m = _PATH.match(path.get("d", ""))
        if not m or not labels:
            continue
        x1, y1, x2, y2 = map(float, m.groups())
        directed = bool(path.get("marker-end"))
        src, dst = nearest(x1, y1), nearest(x2, y2)
        budget.take_block()
        blocks.append(Block(source_id, "diagram_edge", f"{src} -> {dst}", f"path:{i}",
                            {"from": src, "to": dst, "directed": directed},
                            needs_review=not directed))
    return blocks
