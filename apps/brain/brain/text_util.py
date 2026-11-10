"""CJK-safe text utilities: sentence splitting, unit counting, key folding.

Pure functions, no model calls. English behaviour matches the historical
regexes except where those were the bug (no full-width terminators, no CJK
survival in folds); Chinese text stops being destroyed or ignored.
"""

from __future__ import annotations

import re

from brain.lang import is_cjk

# ASCII terminators need whitespace (or end of text) after them, matching the
# historical `(?<=[.!?])\s+` behaviour; full-width terminators form a boundary
# with zero or more whitespace after them, because Chinese writes none.
_ASCII_TERMINATORS = ".!?;"
_FULLWIDTH_TERMINATORS = "。！？；…"
_ALL_TERMINATORS = set(_ASCII_TERMINATORS + _FULLWIDTH_TERMINATORS)

_OPEN_TO_CLOSE = {
    "(": ")",
    "[": "]",
    "{": "}",
    "（": "）",
    "【": "】",
    "「": "」",
    "『": "』",
    "“": "”",
    "‘": "’",
    "《": "》",
    "〈": "〉",
}
_CLOSES = set(_OPEN_TO_CLOSE.values())
_CLOSER_CHARS = _CLOSES | {'"', "'"}

_WHITESPACE_RUN = re.compile(r" +")


def _advance_state(text: str, i: int, depth: int, straight: str | None) -> tuple[int, str | None]:
    """Update bracket depth / straight-quote state for text[i]."""
    ch = text[i]
    if straight is not None:
        return depth, (None if ch == straight else straight)
    if ch in ('"', "'") and not (
        ch == "'" and i > 0 and i + 1 < len(text) and text[i - 1].isalnum() and text[i + 1].isalnum()
    ):
        return depth, ch
    if ch in _OPEN_TO_CLOSE:
        return depth + 1, straight
    if ch in _CLOSES:
        return max(depth - 1, 0), straight
    return depth, straight


def _scan_sentences(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end, separator) per sentence; separator is the
    whitespace that followed its terminator (kept so slices round-trip)."""
    spans: list[tuple[int, int, str]] = []
    depth = 0
    straight: str | None = None
    n = len(text)
    start = 0
    while start < n and text[start].isspace():
        start += 1
    i = start
    while i < n:
        ch = text[i]
        boundary: int | None = None
        if ch in _ALL_TERMINATORS:
            # A terminator before closing quotes/brackets ends the sentence
            # after those closers (and after the outer sentence's own stop).
            j = i + 1
            while j < n and text[j] in _CLOSER_CHARS:
                j += 1
            if j > i + 1:
                k = j
                if k < n and text[k] in _ALL_TERMINATORS:
                    k += 1
                    while k < n and text[k] in _CLOSER_CHARS:
                        k += 1
                boundary = k
            elif depth == 0 and straight is None:
                if ch in _FULLWIDTH_TERMINATORS or i + 1 == n or text[i + 1].isspace():
                    boundary = i + 1
        if boundary is not None:
            j = boundary
            while j < n and text[j].isspace():
                j += 1
            while i < boundary:
                depth, straight = _advance_state(text, i, depth, straight)
                i += 1
            spans.append((start, boundary, text[boundary:j]))
            start = j
            i = j
            continue
        depth, straight = _advance_state(text, i, depth, straight)
        i += 1
    if start < n:
        spans.append((start, n, ""))
    return spans


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Start/end offsets of each sentence inside ``text``."""
    return [(start, end) for start, end, _ in _scan_sentences(text)]


def sentence_slices(text: str) -> list[tuple[str, str]]:
    """Split into (sentence, separator) pairs, keeping the whitespace."""
    return [(text[start:end], sep) for start, end, sep in _scan_sentences(text)]


def split_sentences(text: str) -> list[str]:
    """Split text into sentences at ASCII or full-width terminators.

    Never splits inside quotes or brackets; mixed zh/en text splits at both
    scripts' terminators. Empty sentences are dropped.
    """
    return [sentence for sentence, _ in sentence_slices(text) if sentence.strip()]


def count_units(text: str) -> int:
    """Whitespace words for Latin, one per CJK character."""
    cjk = 0
    rest: list[str] = []
    for ch in text:
        if is_cjk(ch):
            cjk += 1
            rest.append(" ")
        else:
            rest.append(ch)
    return cjk + len("".join(rest).split())


def fold_key(text: str) -> str:
    """Casefold and strip punctuation, keeping CJK codepoints and spaces.

    Punctuation (ASCII and full-width) becomes a space; CJK ideographs
    survive so Chinese alias matching is possible at all.
    """
    folded = text.casefold().replace("'", "").replace("’", "")
    out: list[str] = []
    for ch in folded:
        if ("a" <= ch <= "z") or ("0" <= ch <= "9") or ch == " ":
            out.append(ch)
        elif is_cjk(ch):
            out.append(ch)
        else:
            out.append(" ")
    return _WHITESPACE_RUN.sub(" ", "".join(out)).strip()
