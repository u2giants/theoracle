"""Invented fixture host signing. Never imported by application code.

These keys model the independent host, not an installed OS trust boundary.
"""
from __future__ import annotations
from oracle_brain.seal_wire import require_allowed_purpose, seal_payload

_fixture_key = None


def sign_seal(purpose: str, *fields) -> str:
    require_allowed_purpose(purpose)
    if _fixture_key is None:
        raise RuntimeError('fixture host not configured')
    return _fixture_key.sign(seal_payload(purpose, *fields)).hex()
