"""Canonical seal wire and the fixed purpose allowlist.

Shared by the verify path (``oracle_brain.seal``) and the isolated signer
(``oracle_brain.seal_signer``). Pure data: no key material, no signing, no
I/O. Authority is the Ed25519 signature alone; this module only defines
what may be signed and how a signed message is spelled.

A signature is valid only for one purpose. Unknown purpose, free-form
bytes and malformed field lists are refused before any key use.
"""
from __future__ import annotations

from datetime import datetime
import json
import math

__all__ = (
    'SEAL_PURPOSE_ALLOWLIST',
    'seal_payload',
    'require_allowed_purpose',
    'wire_fields',
)

# Fixed allowlist of structured payload purposes. The signer refuses any
# purpose outside this set; verify_mac does the same. Adding a purpose is
# a reviewed code change, never a runtime option.
SEAL_PURPOSE_ALLOWLIST = frozenset({
    'sender-credential:v1',
    'delivery-action:v1',
    'participation-enable:v1',
    'q2b-reader-facts:v1',
    'q2b-admission:v1',
    'q2b-connection:v1',
})


def require_allowed_purpose(purpose: str) -> None:
    """Fail closed unless ``purpose`` is one of the fixed allowlist."""
    if not isinstance(purpose, str) or purpose not in SEAL_PURPOSE_ALLOWLIST:
        raise PermissionError('seal purpose not allowed')


def wire_fields(*fields) -> list[str]:
    """Stringify payload fields the same way on both sides of the wire.

    Datetimes use ``isoformat()``; explicit scalar types use ``str()``.
    Arbitrary objects and their conversion hooks are never accepted.
    Returns the plain string parts after the purpose tag.
    """
    parts: list[str] = []
    for f in fields:
        if type(f) is datetime:
            parts.append(f.isoformat())
        elif type(f) in (str, bool, int, float, type(None)):
            if type(f) is float and not math.isfinite(f):
                raise ValueError('seal field must be finite')
            parts.append(str(f))
        else:
            raise TypeError('seal fields must be strings, datetimes or scalars')
    return parts


def seal_payload(purpose: str, *fields) -> bytes:
    """Canonical purpose-tagged message bytes for sign and verify."""
    require_allowed_purpose(purpose)
    return json.dumps(
        [purpose, wire_fields(*fields)], ensure_ascii=False,
        separators=(',', ':'), allow_nan=False,
    ).encode('utf-8')
