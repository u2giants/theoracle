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
satisfies another. The signer refuses any purpose outside the fixed
allowlist and refuses free-form payload bytes.

Authority is the Ed25519 signature alone. There is no mutable in-process
mint registry anywhere on this path.

Key env vars (UNKNOWN until host wiring):

- ``ORACLE2_SEAL_PUBLIC_KEY``: hex-encoded 32-byte Ed25519 public key.
- ``ORACLE2_SEAL_SIGNER_KEY_FILE``: path string to the signer's private
  key file. The parent never reads that file and never holds key
  material — only this path, used to build the signer child's clean
  environment. There is no ``ORACLE2_SEAL_PRIVATE_KEY*`` variable in
  the parent environment.
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

from oracle_brain.seal_wire import (
    SEAL_PURPOSE_ALLOWLIST,
    require_allowed_purpose,
    seal_payload,
    wire_fields,
)

# Documented runtime provider name. Production/host wiring sets this
# environment variable to the real public key; tests inject via the
# fixture before first seal use. The signer key file path is read only
# to build the signer child's clean environment.
SEAL_PUBLIC_KEY_ENV = 'ORACLE2_SEAL_PUBLIC_KEY'
SEAL_SIGNER_KEY_FILE_ENV = 'ORACLE2_SEAL_SIGNER_KEY_FILE'

__all__ = (
    'SEAL_PUBLIC_KEY_ENV',
    'SEAL_PURPOSE_ALLOWLIST',
    'seal_payload',
    'verify',
    'verify_mac',
)


def _signer_child_env(key_path: str) -> dict:
    """Explicit clean environment for the signer child process.

    Never inherits the parent environment. Carries only the key file
    path and the minimal OS variables the interpreter needs to start.
    No secret from the parent env is passed through.
    """
    env = {SEAL_SIGNER_KEY_FILE_ENV: key_path}
    for name in ('SystemRoot', 'WINDIR', 'PATH', 'PATHEXT', 'COMSPEC',
                 'TMP', 'TEMP', 'HOME', 'USERPROFILE'):
        value = os.environ.get(name)
        if value is not None:
            env[name] = value
    return env


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

    def _sign_via_helper(purpose: str, fields: list) -> str:
        """Mint through the isolated signer child. Sealed factories only.

        Lives only inside this closure. The request is structured: an
        allowlisted purpose plus plain-string fields. Free-form payload
        bytes never cross this boundary. The child loads the private key
        from its key file; this parent process never reads that file and
        never holds key material. The child is spawned with an explicit
        clean environment — never the parent environment — so no secret
        in the parent env is inherited. Not returned, not a module
        attribute, not importable and not getattr-able from outside.
        """
        require_allowed_purpose(purpose)
        request = json.dumps({'purpose': purpose, 'fields': list(fields)})
        key_path = os.environ.get(SEAL_SIGNER_KEY_FILE_ENV, '')
        if not key_path:
            raise PermissionError(
                'seal signer key file not configured; set '
                f'{SEAL_SIGNER_KEY_FILE_ENV}')
        child = subprocess.run(
            [sys.executable, '-m', 'oracle_brain.seal_signer'],
            input=request.encode('utf-8'),
            capture_output=True,
            check=False,
            env=_signer_child_env(key_path),
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
        return _sign_via_helper(purpose, wire_fields(*fields))

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
        """Verify a purpose-tagged seal. Fail closed on any mismatch.

        Unknown purposes are refused before any signature check so a
        signature can never be replayed under a new purpose name.
        """
        require_allowed_purpose(purpose)
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
