"""Token counting and chunking for source text (plan step 3).

Documents become 400-token windows with 60-token overlap, never crossing a
page, slide or sheet boundary. Row- and paragraph-shaped sources are packed
whole-unit so their locators keep pointing at real rows and paragraphs.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import tiktoken

WINDOW_TOKENS = 400
OVERLAP_TOKENS = 60

_TOKENIZER = tiktoken.get_encoding("cl100k_base")


@dataclass(frozen=True)
class Chunk:
    """One indexed piece of a source, with its in-document location."""

    locator: dict[str, Any]
    text: str
    token_count: int


def count_tokens(text: str) -> int:
    """Return the cl100k_base token count of ``text``."""
    return len(_TOKENIZER.encode(text))


def _decode(tokens: Sequence[int]) -> str:
    return _TOKENIZER.decode(list(tokens))


def window_chunks(text: str, locator: dict[str, Any]) -> list[Chunk]:
    """Split ``text`` into 400-token windows with 60-token overlap.

    Every chunk carries a copy of ``locator``. Window edges snap to whitespace
    so no chunk starts or ends in the middle of a word; the final window holds
    the tail of the text.
    """
    stripped = text.strip()
    if not stripped:
        return []
    tokens = _TOKENIZER.encode(stripped)
    if len(tokens) <= WINDOW_TOKENS:
        return [Chunk(dict(locator), stripped, len(tokens))]
    chunks: list[Chunk] = []
    step = WINDOW_TOKENS - OVERLAP_TOKENS
    total = len(tokens)
    start = 0
    while start < total:
        end = min(start + WINDOW_TOKENS, total)
        piece = _decode(tokens[start:end])
        if start > 0:
            space = piece.find(" ")
            if 0 <= space < len(piece) - 1:
                piece = piece[space + 1 :]
        if end < total:
            space = piece.rfind(" ")
            if space > 0:
                piece = piece[:space]
        piece = piece.strip()
        if piece:
            chunks.append(Chunk(dict(locator), piece, count_tokens(piece)))
        if end >= total:
            break
        start += step
    return chunks


def pack_units(
    units: Sequence[str],
    locator_for: Callable[[int, int], dict[str, Any]],
) -> list[Chunk]:
    """Pack whole ``units`` into chunks of at most 400 tokens.

    ``locator_for(first, last)`` receives inclusive unit indices. Consecutive
    chunks repeat trailing units until 60 tokens of overlap are covered, so no
    unit is split across a chunk boundary. A single unit larger than the window
    is split with :func:`window_chunks` instead.
    """
    counts = [count_tokens(unit) for unit in units]
    chunks: list[Chunk] = []
    total = len(units)
    index = 0
    while index < total:
        if counts[index] > WINDOW_TOKENS:
            chunks.extend(
                window_chunks(units[index], locator_for(index, index)),
            )
            index += 1
            continue
        cursor = index
        tokens = 0
        while cursor < total:
            add = counts[cursor] + (1 if cursor > index else 0)
            if cursor > index and tokens + add > WINDOW_TOKENS:
                break
            tokens += add
            cursor += 1
        text = "\n".join(units[index:cursor]).strip()
        if text:
            chunks.append(Chunk(locator_for(index, cursor - 1), text, count_tokens(text)))
        if cursor >= total:
            break
        back = 0
        shared = 0
        while cursor - back - 1 >= index and shared < OVERLAP_TOKENS:
            back += 1
            shared += counts[cursor - back] + 1
        index = cursor - back
    return chunks
