"""Isolated Ed25519 seal signing entrypoint (process boundary).

This module is a process entrypoint, not a signing library. All signing
logic lives under the ``__main__`` guard, so ``import
oracle_brain.seal_signer`` never yields a usable ``sign()``: application
code and the verify path cannot reach a signing capability through this
import surface. Signing is reached only by launching this module as a
one-shot child process.

Launch and handshake (one-shot, process-per-signature):

    python -m oracle_brain.seal_signer
    stdin:  {"purpose": "<purpose>", "fields": ["...", ...]}
    stdout: {"signature": "<hex ed25519 signature>"}

The signer only signs structured payloads whose purpose is in the fixed
allowlist (``oracle_brain.seal_wire.SEAL_PURPOSE_ALLOWLIST``). Unknown
purpose, free-form ``payload_hex`` bytes, or a malformed request are
refused before any key use. Fields are plain strings; the canonical wire
is ``purpose|field|field|...``.

Key source (signer child only — never the parent process):

- ``ORACLE2_SEAL_SIGNER_KEY_FILE``: path to a file holding a hex-encoded
  32-byte Ed25519 private key. The parent process knows only this path
  string and never reads the file into Python objects. The signer child
  is spawned with an explicit clean environment that carries the path;
  the key material is loaded here, inside the child, and never returned.

Remaining trust boundary (honest): the key file is readable by the same
OS user that runs the signer process. Restricting file ACLs or running
the signer as a separate OS user is a host-wiring concern outside this
offline leaf. Until host wiring lands, treat the key file as the
production secret store and do not commit key material.
"""
from __future__ import annotations

import json
import os
import sys

from oracle_brain.seal_wire import require_allowed_purpose, seal_payload

SEAL_SIGNER_KEY_FILE_ENV = 'ORACLE2_SEAL_SIGNER_KEY_FILE'

__all__ = ('SEAL_SIGNER_KEY_FILE_ENV',)


def _parse_sign_request(raw: str) -> bytes:
    """Parse and validate a structured sign request into canonical bytes.

    Refuses free-form payload bytes, unknown purposes and malformed
    field lists. Never loads any key. Pure validation + wire encoding.
    """
    try:
        request = json.loads(raw or '{}')
    except ValueError as error:
        raise PermissionError('seal signer request must be JSON') from error
    if not isinstance(request, dict):
        raise PermissionError('seal signer request must be a JSON object')
    if 'payload_hex' in request or 'payload' in request:
        raise PermissionError('seal signer refuses free-form payload bytes')
    purpose = request.get('purpose')
    fields = request.get('fields')
    if not isinstance(purpose, str) or not purpose:
        raise PermissionError('seal signer purpose required')
    require_allowed_purpose(purpose)
    if not isinstance(fields, list):
        raise PermissionError('seal signer fields must be a list')
    for item in fields:
        if not isinstance(item, str):
            raise PermissionError('seal signer fields must be strings')
    return seal_payload(purpose, *fields)


# Everything below runs only when this module is the process entrypoint.
# Importing the module defines no signing helper, no key loader and no
# main() — there is nothing for application code to call. The request
# parser above is pure and keyless.
if __name__ == '__main__':
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )

    def _load_private_key() -> Ed25519PrivateKey:
        """Read the seal private key from the configured key file. Fail closed."""
        path = os.environ.get(SEAL_SIGNER_KEY_FILE_ENV, '')
        if not path:
            raise PermissionError(
                'seal signer key file not configured; set '
                f'{SEAL_SIGNER_KEY_FILE_ENV}')
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

    def main() -> int:
        """CLI child: stdin structured request → stdout signature response.

        The child is the process boundary for private-key use. The parent
        sends only a purpose-tagged structured request; the private key
        is loaded here and never returned.
        """
        try:
            payload = _parse_sign_request(sys.stdin.read())
            signature = _load_private_key().sign(payload).hex()
        except Exception as error:  # noqa: BLE001 — child must fail closed
            sys.stdout.write(json.dumps({'error': str(error)}))
            return 1
        sys.stdout.write(json.dumps({'signature': signature}))
        return 0

    raise SystemExit(main())
