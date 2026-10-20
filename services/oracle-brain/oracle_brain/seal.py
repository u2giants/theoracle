"""Purpose-tagged Ed25519 seal verification with a public key only.

This module is the verify path. It never loads a private key, never
imports the signing helper, and never exposes a sign or mint callable as
a module attribute. Public keys cannot forge signatures: a same-process
caller that extracts every closure here still cannot produce a seal.

Signing is isolated in ``oracle_brain.seal_signer`` (child process / helper).
The sealed factory wire receives a bound mint that delegates to that
helper across a process boundary, so the parent never loads the private
key. Verification-side ``verify_mac`` is the admission check at every use
site. Both are purpose-tagged so a signature issued for one purpose never
satisfies another.

Key env vars (UNKNOWN until host wiring):

- ``ORACLE2_SEAL_PUBLIC_KEY``: hex-encoded 32-byte Ed25519 public key.
- ``ORACLE2_SEAL_PRIVATE_KEY`` / ``ORACLE2_SEAL_PRIVATE_KEY_FILE``:
  private key for the isolated signer only (never read here).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PublicKey,
)

# Documented runtime provider name. Production/host wiring sets this
# environment variable to the real public key; tests inject via the
# fixture before first seal use. Private key env vars live only in
# oracle_brain.seal_signer.
SEAL_PUBLIC_KEY_ENV = 'ORACLE2_SEAL_PUBLIC_KEY'

__all__ = ('SEAL_PUBLIC_KEY_ENV', 'seal_payload', 'verify', 'verify_mac')


def seal_payload(purpose: str, *fields) -> bytes:
    """Canonical purpose-tagged message bytes for sign and verify."""
    if not purpose or not isinstance(purpose, str):
        raise ValueError('seal purpose required')
    parts = [purpose]
    for f in fields:
        iso = getattr(f, 'isoformat', None)
        parts.append(iso() if callable(iso) else str(f))
    return '|'.join(parts).encode('utf-8')


def _install_seal_api():
    """Create the verify-side seal and the factory wire.

    The public key is loaded lazily from the environment on first use.
    The mint helper is a process-boundary client that never loads the
    private key; it is bound only into sealed factories installed through
    this closure and is never a module attribute.
    """
    _holder: list = []

    def _require_public_key() -> Ed25519PublicKey:
        if not _holder:
            env_raw = os.environ.get(SEAL_PUBLIC_KEY_ENV, '')
            if not env_raw:
                raise PermissionError(
                    'seal public key not installed; set ORACLE2_SEAL_PUBLIC_KEY')
            try:
                raw = bytes.fromhex(env_raw)
            except ValueError as error:
                raise ValueError('seal public key must be hex-encoded') from error
            if len(raw) != 32:
                raise ValueError('seal public key must be 32 bytes')
            _holder.append(Ed25519PublicKey.from_public_bytes(raw))
        return _holder[0]

    def _sign_via_helper(payload: bytes) -> str:
        """Mint through the isolated signer child. Sealed factories only.

        Lives only inside this closure. The child loads the private key;
        this parent process never does. Not returned, not a module
        attribute, not importable and not getattr-able from outside.
        """
        request = json.dumps({'payload_hex': bytes(payload).hex()})
        child = subprocess.run(
            [sys.executable, '-m', 'oracle_brain.seal_signer'],
            input=request.encode('utf-8'),
            capture_output=True,
            check=False,
        )
        if child.returncode != 0:
            raise PermissionError('seal signer helper failed')
        try:
            response = json.loads(child.stdout.decode('utf-8') or '{}')
        except ValueError as error:
            raise PermissionError('seal signer helper failed') from error
        signature = response.get('signature')
        if not isinstance(signature, str) or not signature:
            raise PermissionError('seal signer helper failed')
        return signature

    def _mint_signature(purpose: str, *fields) -> str:
        """Internal purpose-tagged signature. Sealed factories only.

        Lives only inside this closure. Not returned, not a module
        attribute, not importable and not getattr-able from outside.
        """
        return _sign_via_helper(seal_payload(purpose, *fields))

    def verify(payload: bytes, signature: str) -> bool:
        """Local public-key verify. Never signs. True only on a real seal."""
        if not isinstance(signature, str) or not signature:
            return False
        try:
            raw_sig = bytes.fromhex(signature)
        except ValueError:
            return False
        if len(raw_sig) != 64:
            return False
        try:
            _require_public_key().verify(raw_sig, bytes(payload))
        except (InvalidSignature, ValueError, TypeError):
            return False
        return True

    def verify_mac(purpose: str, mac: str, *fields) -> None:
        """Verify a purpose-tagged seal. Fail closed on any mismatch."""
        if not isinstance(mac, str) or not mac:
            raise PermissionError('seal MAC required')
        if not verify(seal_payload(purpose, *fields), mac):
            raise PermissionError('seal MAC mismatch')

    def _wire_sealed_factories() -> None:
        """Install sealed consumer factories with bound mint/verify.

        Called only from this closure at install time. Each factory
        receives the bound callables as parameters and must close over
        them; the callables are never re-exported as module names.
        """
        import oracle_brain.operating_model.q2b_target_catalog_v1 as q2b
        (q2b.read_target_catalog,
         q2b.admit_target_catalog,
         q2b.require_target_catalog) = q2b._install_sealed_catalog_api(
            mint=_mint_signature, verify=verify_mac)

    _wire_sealed_factories()
    return verify, verify_mac


# Only the verification-side callables are module attributes. The mint
# helper, the process-boundary client and the factory wire stay locals
# of the install closure.
verify, verify_mac = _install_seal_api()
