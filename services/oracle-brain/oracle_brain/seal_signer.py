"""Isolated Ed25519 seal signing entrypoint (process boundary).

This module is a process entrypoint, not a signing library. All signing
logic lives under the ``__main__`` guard, so ``import
oracle_brain.seal_signer`` never yields a usable ``sign()``: application
code and the verify path cannot reach a signing capability through this
import surface. Signing is reached only by launching this module as a
one-shot child process.

Launch and handshake (one-shot, process-per-signature):

    python -m oracle_brain.seal_signer
    stdin:  {"payload_hex": "<hex bytes>"}
    stdout: {"signature": "<hex ed25519 signature>"}

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

SEAL_SIGNER_KEY_FILE_ENV = 'ORACLE2_SEAL_SIGNER_KEY_FILE'

__all__ = ('SEAL_SIGNER_KEY_FILE_ENV',)


# Everything below runs only when this module is the process entrypoint.
# Importing the module defines no signing helper, no key loader and no
# main() — there is nothing for application code to call.
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
        """CLI child: stdin payload request → stdout signature response.

        The child is the process boundary for private-key use. The parent
        sends only the payload; the private key is loaded here and never
        returned.
        """
        try:
            request = json.loads(sys.stdin.read() or '{}')
            payload = bytes.fromhex(request.get('payload_hex', ''))
            if not isinstance(payload, (bytes, bytearray)):
                raise TypeError('seal payload must be bytes')
            signature = _load_private_key().sign(bytes(payload)).hex()
        except Exception as error:  # noqa: BLE001 — child must fail closed
            sys.stdout.write(json.dumps({'error': str(error)}))
            return 1
        sys.stdout.write(json.dumps({'signature': signature}))
        return 0

    raise SystemExit(main())
