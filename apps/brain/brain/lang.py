"""Language detection for the bilingual (en / zh-CN) Oracle brain.

Deterministic, dependency-free heuristics: no model calls, no network.
Simplified and Traditional Chinese both count as CJK; Japanese kana and
Korean hangul are never reported as zh.
"""

from __future__ import annotations

import re

_CJK_START = 0x4E00
_CJK_END = 0x9FFF  # CJK Unified Ideographs (一-鿿)
_KANA_START = 0x3040
_KANA_END = 0x30FF  # Hiragana + Katakana
_HANGUL_RANGES = ((0x1100, 0x11FF), (0x3130, 0x318F), (0xAC00, 0xD7AF))

#: CJK share of (CJK + Latin) letters at or above which text is zh.
ZH_SHARE_THRESHOLD = 0.4


def is_cjk(ch: str) -> bool:
    """True when ch is a single CJK Unified Ideograph."""
    return len(ch) == 1 and _CJK_START <= ord(ch) <= _CJK_END


def _is_kana(ch: str) -> bool:
    return len(ch) == 1 and _KANA_START <= ord(ch) <= _KANA_END


def _is_hangul(ch: str) -> bool:
    if len(ch) != 1:
        return False
    code = ord(ch)
    return any(start <= code <= end for start, end in _HANGUL_RANGES)


def cjk_ratio(text: str) -> float:
    """CJK letters as a share of letters (CJK + Latin); 0.0 with no letters."""
    cjk = latin = 0
    for ch in text:
        if is_cjk(ch):
            cjk += 1
        elif ("a" <= ch <= "z") or ("A" <= ch <= "Z"):
            latin += 1
    total = cjk + latin
    return cjk / total if total else 0.0


def detect_language(text: str) -> str:
    """Classify text as "zh", "en", "mixed", or "other".

    zh when CJK is at least ZH_SHARE_THRESHOLD of letters; en when there is
    no CJK at all; mixed when both scripts appear below that share; other
    for empty input, punctuation/digits only, and any text containing kana
    or hangul (ja/ko are never reported as zh).
    """
    cjk = latin = kana = hangul = 0
    for ch in text:
        if is_cjk(ch):
            cjk += 1
        elif _is_kana(ch):
            kana += 1
        elif _is_hangul(ch):
            hangul += 1
        elif ("a" <= ch <= "z") or ("A" <= ch <= "Z"):
            latin += 1
    if kana or hangul:
        return "other"
    letters = cjk + latin
    if not letters:
        return "other"
    if cjk / letters >= ZH_SHARE_THRESHOLD:
        return "zh"
    if not cjk:
        return "en"
    return "mixed"


#: Strong English function words: rare as standalone words in other languages.
_EN_STRONG = frozenset(
    "who what when where why how which whose there their they them with from "
    "should would could does the and".split()
)
_EN_WEAK = frozenset(
    "is are was were a an of to in for on at be been have has had not no if "
    "then than it its this that we you he she his her your our us do did can "
    "about after before between by into over under or".split()
)

_LATIN_RANGES = (
    (0x0041, 0x024F),  # Basic Latin + Latin-1 Supplement + Extended-A/B
    (0x1E00, 0x1EFF),  # Latin Extended Additional (Vietnamese, …)
    (0x2C60, 0x2C7F),
    (0xA720, 0xA7FF),
)
_re_word = re.compile(r"[a-z']+")


def _is_latin_letter(ch: str) -> bool:
    return any(start <= ord(ch) <= end for start, end in _LATIN_RANGES)


def contains_non_latin_letters(text: str) -> bool:
    """True when any letter is outside Latin (Cyrillic, CJK, Arabic, …)."""
    for ch in text:
        if ch.isalpha() and not _is_latin_letter(ch):
            return True
    return False


def _has_accented_letters(text: str) -> bool:
    return any(ord(ch) > 127 and (ch.isalpha() or ch in "́̃") for ch in text)


def looks_english(text: str) -> bool | None:
    """Classify question text: True English, False not English, None unsure.

    Deterministic and cheap — the caller translates on False or None. Clear
    English (common function words) short-circuits to True even when a name
    carries an accent (María, Cortázar).
    """
    body = str(text or "").strip()
    if not body:
        return None
    if contains_non_latin_letters(body):
        return False
    words = [w for w in _re_word.findall(body.lower()) if w]
    strong = sum(1 for w in words if w in _EN_STRONG)
    weak = sum(1 for w in words if w in _EN_WEAK)
    if strong >= 2 or (strong >= 1 and weak >= 1) or (weak >= 3 and len(words) >= 5):
        return True
    if _has_accented_letters(body):
        return False
    return None
