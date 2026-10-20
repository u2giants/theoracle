"""Isolated Ed25519 seal signing helper.

This module is the only place that loads the seal private key. It is
never imported by ``oracle_brain.seal`` or any verify-only consumer.
Ordinary verify-path code cannot reach a signing capability through the
seal module; signing is reached only by importing this helper (tests,
or the CLI child used as a process boundary).

Key sources — both UNKNOWN until host wiring:

- ``ORACLE2_SEAL_PRIVATE_KEY``: hex-encoded 32-byte Ed25519 private key.
- ``ORACLE2_SEAL_PRIVATE_KEY_FILE``: path to a file holding that hex key.

The parent process never loads the private key when minting goes through
``python -m oracle_brain.seal_signer`` (see ``oracle_brain.seal``).
"""
from __future__ import annotations

import json
import os
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

SEAL_PRIVATE_KEY_ENV = 'ORACLE2_SEAL_PRIVATE_KEY'
SEAL_PRIVATE_KEY_FILE_ENV = 'ORACLE2_SEAL_PRIVATE_KEY_FILE'

__all__ = (
    'SEAL_PRIVATE_KEY_ENV',
    'SEAL_PRIVATE_KEY_FILE_ENV',
    'sign',
    'sign_seal',
)


def _load_private_key() -> Ed25519PrivateKey:
    """Load the seal private key from env or key file. Fail closed."""
    hex_key = os.environ.get(SEAL_PRIVATE_KEY_ENV, '')
    if not hex_key:
        path = os.environ.get(SEAL_PRIVATE_KEY_FILE_ENV, '')
        if not path:
            raise PermissionError(
                'seal private key not configured; set '
                f'{SEAL_PRIVATE_KEY_ENV} or {SEAL_PRIVATE_KEY_FILE_ENV}')
        try:
            with open(path, encoding='ascii') as handle:
                hex_key = handle.read().strip()
        except OSError as error:
            raise PermissionError('seal private key file unreadable') from error
    try:
        raw = bytes.fromhex(hex_key)
    except ValueError as error:
        raise ValueError('seal private key must be hex-encoded') from error
    if len(raw) != 32:
        raise ValueError('seal private key must be 32 bytes')
    return Ed25519PrivateKey.from_private_bytes(raw)


def sign(payload: bytes) -> str:
    """Sign raw payload bytes. Returns a hex-encoded Ed25519 signature."""
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError('seal payload must be bytes')
    return _load_private_key().sign(bytes(payload)).hex()


def sign_seal(purpose: str, *fields) -> str:
    """Purpose-tagged seal signature over the canonical field wire."""
    from oracle_brain.seal import seal_payload
    return sign(seal_payload(purpose, *fields))


def main() -> int:
    """CLI child: stdin ``{"payload_hex": "..."} `` → stdout ``{"signature": "..."} ``.

    The child is the process boundary for private-key use. The parent
    sends only the payload; the private key is loaded here and never
    returned.
    """
    try:
        request = json.loads(sys.stdin.read() or '{}')
        payload = bytes.fromhex(request.get('payload_hex', ''))
        signature = sign(payload)
    except Exception as error:  # noqa: BLE001 — child must fail closed
        sys.stdout.write(json.dumps({'error': str(error)}))
        return 1
    sys.stdout.write(json.dumps({'signature': signature}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
