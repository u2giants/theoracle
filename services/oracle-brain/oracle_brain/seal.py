"""Verification-only authority boundary; signing belongs to a separate host identity.

The application receives public keys and signed evidence. It never receives a
signing-key path, launches a signer, or mints catalog/admission authority.
"""
from __future__ import annotations

import os
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from oracle_brain.seal_wire import SEAL_PURPOSE_ALLOWLIST, require_allowed_purpose, seal_payload

SEAL_PUBLIC_KEY_ENV = 'ORACLE2_SEAL_PUBLIC_KEY'
__all__ = ('SEAL_PUBLIC_KEY_ENV', 'SEAL_PURPOSE_ALLOWLIST', 'seal_payload', 'verify', 'verify_mac')


def _verification_api():
    # Pin trusted startup public-key configuration on first use. Subsequent
    # request code cannot select a different issuer by changing the environment.
    pinned_key = None

    def verify(payload: bytes, signature: str) -> bool:
        nonlocal pinned_key
        if not isinstance(signature, str) or not signature:
            return False
        try:
            if pinned_key is None:
                public_raw = bytes.fromhex(os.environ.get(SEAL_PUBLIC_KEY_ENV, ''))
                if len(public_raw) != 32:
                    return False
                pinned_key = Ed25519PublicKey.from_public_bytes(public_raw)
            raw_sig = bytes.fromhex(signature)
            if len(raw_sig) != 64:
                return False
            pinned_key.verify(raw_sig, bytes(payload))
        except (InvalidSignature, ValueError, TypeError):
            return False
        return True

    return verify


verify = _verification_api()


def verify_mac(purpose: str, mac: str, *fields) -> None:
    require_allowed_purpose(purpose)
    if not isinstance(mac, str) or not mac:
        raise PermissionError('seal MAC required')
    if not verify(seal_payload(purpose, *fields), mac):
        raise PermissionError('seal MAC mismatch')
