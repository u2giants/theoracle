"""Document ingestion: text to structural blocks with evidence coordinates."""

from __future__ import annotations

from dataclasses import dataclass
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
    """Split document text into paragraph blocks with character-offset spans.

    Each block records its original character range so that any claim made from
    the block can cite the exact source region. Empty paragraphs are skipped.
    """
    if not text or not text.strip():
        raise ValueError("document text must be non-empty")
    blocks: list[SourceBlock] = []
    offset = 0
    for index, paragraph in enumerate(text.split("\n\n")):
        stripped = paragraph.strip()
        if not stripped:
            offset += len(paragraph) + 2  # account for the separator
            continue
        start = text.index(stripped, offset)
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
        offset = end
    return blocks
