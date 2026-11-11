"""Token counting and chunking for source text (plan step 3).

Documents become windows of at most 400 tokens with about 60 tokens of
overlap, never crossing a page, slide or sheet boundary, and never dropping
text (repair plan A3). Row- and paragraph-shaped sources are packed
whole-unit so their locators keep pointing at real rows and paragraphs.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import tiktoken

from brain.text_util import sentence_spans

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


def _token_starts(text: str) -> list[int]:
    """Character offset where each token of ``text`` starts, plus the end."""
    tokens = _TOKENIZER.encode(text)
    decoded, offsets = _TOKENIZER.decode_with_offsets(tokens)
    if decoded != text:
        # Unpaired surrogates and the like: fall back to one "token" per
        # four characters, which only ever makes windows smaller.
        offsets = list(range(0, len(text), 4))
    starts = sorted(set(offsets))
    starts.append(len(text))
    return starts


def _boundaries(text: str) -> list[list[int]]:
    """Cut positions by preference: paragraph, line, sentence, whitespace."""
    paragraphs: list[int] = []
    lines: list[int] = []
    spaces: list[int] = []
    previous_newline = False
    run_has_blank = False
    for index, ch in enumerate(text):
        if ch == "\n":
            if previous_newline:
                run_has_blank = True
            previous_newline = True
            continue
        if previous_newline and not ch.isspace():
            (paragraphs if run_has_blank else lines).append(index)
            previous_newline = False
            run_has_blank = False
        elif previous_newline:
            continue
        if ch.isspace():
            spaces.append(index + 1)
    sentences = [end for _start, end in sentence_spans(text) if end < len(text)]
    return [paragraphs, lines + paragraphs, sentences, spaces]


def _last_between(positions: list[int], low: int, high: int) -> int | None:
    """The largest position in ``(low, high]``, or None."""
    index = bisect_right(positions, high)
    if index and positions[index - 1] > low:
        return positions[index - 1]
    return None


def _first_between(positions: list[int], low: int, high: int) -> int | None:
    """The smallest position in ``[low, high)``, or None."""
    index = bisect_left(positions, low)
    if index < len(positions) and positions[index] < high:
        return positions[index]
    return None


def window_spans(text: str) -> list[tuple[int, int]]:
    """``(start, end)`` character spans of the windows over ``text``.

    Invariant: the spans cover every character. The first starts at 0, the
    last ends at ``len(text)``, and each span starts at or before the end of
    the one before it (the difference is the overlap). A span ends at the
    best boundary in the second half of its 400-token budget, in this order:
    paragraph break, line break, sentence end (ASCII or full-width),
    whitespace; with none of those, at the token limit. Nothing is skipped.
    """
    starts = _token_starts(text)
    total_tokens = len(starts) - 1
    if total_tokens <= WINDOW_TOKENS:
        return [(0, len(text))]
    classes = [sorted(set(group)) for group in _boundaries(text)]
    line_starts = classes[1]

    def token_at(position: int) -> int:
        return bisect_right(starts, position) - 1

    def fits(start: int, end: int) -> bool:
        return count_tokens(text[start:end]) <= WINDOW_TOKENS

    def limit_from(start: int) -> int:
        """The furthest end that keeps ``text[start:end]`` within the window."""
        index = min(token_at(start) + WINDOW_TOKENS, total_tokens)
        while index > token_at(start) + 1 and not fits(start, starts[index]):
            index -= 1
        return starts[index]

    spans: list[tuple[int, int]] = []
    start = 0
    while True:
        hard_end = limit_from(start)
        if hard_end >= len(text):
            spans.append((start, len(text)))
            break
        floor = starts[(token_at(start) + token_at(hard_end)) // 2]
        end = hard_end
        for positions in classes:
            found = _last_between(positions, floor, hard_end)
            if found is not None:
                end = found
                break
        spans.append((start, end))
        # Next window: step back about 60 tokens, starting at a clean edge.
        back = starts[max(token_at(end) - OVERLAP_TOKENS, token_at(start) + 1)]
        next_start = end
        for positions in classes[1:]:
            found = _first_between(positions, back, end)
            if found is not None:
                next_start = found
                break
        else:
            next_start = back
        # The overlap must never cost the next line its place: if the line
        # that begins at ``end`` fits a window on its own but not after the
        # overlap, shrink the overlap until it does.
        line_end = _first_between(line_starts, end + 1, len(text) + 1) or len(text)
        while next_start < end and not fits(next_start, line_end) and fits(end, line_end):
            moved = _first_between(line_starts, next_start + 1, end + 1)
            next_start = end if moved is None else moved
        start = max(next_start, start + 1)
    return spans


def window_chunks(text: str, locator: dict[str, Any]) -> list[Chunk]:
    """Split ``text`` into windows of at most 400 tokens, about 60 shared.

    Every chunk carries a copy of ``locator``. No text is ever dropped (see
    :func:`window_spans`); only whitespace at a chunk's own edges is trimmed.
    """
    stripped = text.strip()
    if not stripped:
        return []
    chunks: list[Chunk] = []
    for start, end in window_spans(stripped):
        piece = stripped[start:end].strip()
        if piece:
            chunks.append(Chunk(dict(locator), piece, count_tokens(piece)))
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
