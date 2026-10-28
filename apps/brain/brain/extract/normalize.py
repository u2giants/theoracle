"""Normalisation of extracted mention names (plan step 4).

``normalize_name`` is what lets "Jessica's", "the licensor sign-off" and
"Exceptions" meet their other spellings later: casefold, strip punctuation,
collapse spaces, drop a leading "the" and honorifics, and singularise a
trailing "s" for everything except Person names (plan step 4, point 2).
"""

from __future__ import annotations

import re
import string

HONORIFICS = frozenset(
    {"mr", "mrs", "ms", "miss", "mx", "dr", "prof", "sir", "madam"}
)

_PUNCT_TABLE = str.maketrans("", "", string.punctuation)
_WHITESPACE = re.compile(r"\s+")


def _singularise(word: str) -> str:
    """Return the singular of a simple English trailing-s plural.

    Words that merely end in s ("process", "status", "bus") keep their s, so
    normalisation never mangles the entity vocabulary itself.
    """
    if len(word) <= 3:
        return word
    if word.endswith(("ss", "us", "is", "ics")):
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("ses", "xes", "zes", "ches", "shes")):
        return word[:-2]
    if word.endswith("s"):
        return word[:-1]
    return word


def normalize_name(surface: str, entity_type: str) -> str:
    """Return the normalised form of one mention surface name."""
    text = surface.casefold().translate(_PUNCT_TABLE)
    text = _WHITESPACE.sub(" ", text).strip()
    words = text.split()
    while words and words[0] == "the":
        words.pop(0)
    if words and words[0] in HONORIFICS:
        words.pop(0)
    if entity_type != "Person":
        words = [_singularise(word) for word in words]
    return " ".join(words)
