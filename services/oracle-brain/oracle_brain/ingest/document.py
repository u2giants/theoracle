"""Document ingestion: text to structural blocks with evidence coordinates."""

from __future__ import annotations

from dataclasses import dataclass
import re
from uuid import UUID, uuid4


@dataclass(frozen=True)
class SourceBlock:
    block_id: UUID
    source_id: UUID
    block_index: int
    kind: str
    text: str
    span_start: int
    span_end: int


def parse_text_to_blocks(text: str, *, source_id: UUID) -> list[SourceBlock]:
    """Split document text into structural blocks with character-offset spans.

    Paragraphs are split on blank lines. Process-table rows and numbered steps
    are line-oriented so each step stays independently correctable. Each block
    records its original character range so that any claim made from the block
    can cite the exact source region.
    """
    if not text or not text.strip():
        raise ValueError("document text must be non-empty")
    blocks: list[SourceBlock] = []
    offset = 0
    current: list[str] = []
    current_start = 0

    def flush() -> None:
        nonlocal current
        raw = "\n".join(current)
        stripped = raw.strip()
        if stripped:
            start = text.index(stripped, current_start)
            end = start + len(stripped)
            blocks.append(SourceBlock(
                block_id=uuid4(),
                source_id=source_id,
                block_index=len(blocks),
                kind="paragraph",
                text=stripped,
                span_start=start,
                span_end=end,
            ))
        current = []

    for line in text.split("\n"):
        stripped_line = line.strip()
        is_row = (
            "|" in line
            or bool(re.match(r"(?i)^\s*(step\s+)?\d+\s*[.)|:\-]", stripped_line))
            or bool(re.match(r"(?i)^step[_ ]id", stripped_line))
        )
        if not current:
            current_start = offset
        if not stripped_line:
            flush()
        elif is_row:
            flush()
            current_start = offset
            current = [line]
        else:
            current.append(line)
        offset += len(line) + 1
    flush()
    return blocks
