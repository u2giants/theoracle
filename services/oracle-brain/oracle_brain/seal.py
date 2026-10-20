"""Purpose-tagged HMAC seal with a runtime-provided secret.

The secret is never committed to source and never importable as a value.
It is loaded once from the environment variable ``ORACLE2_SEAL_SECRET``
at first use, or via a one-shot host-wiring installer that refuses any
second call or replacement.

MAC creation is available only to sealed factories through an internal
helper that is not exported and not reachable as a module attribute.
Verification-side ``verify_mac`` is the admission check at every use site.
Both are purpose-tagged so a MAC issued for one purpose never satisfies
another.
"""
from __future__ import annotations

import hashlib
import hmac
import os

# Documented runtime provider name. Production/host wiring sets this
# environment variable to the real secret; tests inject via the fixture.
SEAL_SECRET_ENV = 'ORACLE2_SEAL_SECRET'


def _install_seal_api():
    """Create the seal with a closure-held secret.

    The secret lives only inside this factory, captured by the returned
    callables. It is never a module attribute, so no import or getattr
    can retrieve it.
    """
    _holder: list = []
    _installed = False

    def install_seal_secret(secret) -> None:
        """One-shot host-wiring installer. Refuses second calls.

        The secret must be at least 32 bytes of high-entropy material.
        Installing replaces nothing: once installed, any further call
        is denied so a caller cannot swap in a chosen key after init.
        """
        nonlocal _installed
        if _installed:
            raise PermissionError(
                'seal secret already installed; replacement denied')
        if not isinstance(secret, (bytes, bytearray)):
            raise ValueError('seal secret must be bytes')
        raw = bytes(secret)
        if len(raw) < 32:
            raise ValueError('seal secret must be at least 32 bytes')
        _holder.append(raw)
        _installed = True

    def _require_secret() -> bytes:
        nonlocal _installed
        if not _holder:
            env_raw = os.environ.get(SEAL_SECRET_ENV, '')
            if env_raw:
                raw = env_raw.encode('utf-8')
                if len(raw) < 32:
                    raise ValueError(
                        'seal secret must be at least 32 bytes')
                _holder.append(raw)
                _installed = True
        if not _holder:
            raise PermissionError(
                'seal secret not installed; set ORACLE2_SEAL_SECRET')
        return _holder[0]

    def _message(purpose: str, fields: tuple) -> bytes:
        if not purpose or not isinstance(purpose, str):
            raise ValueError('seal purpose required')
        parts = [purpose]
        for f in fields:
            iso = getattr(f, 'isoformat', None)
            parts.append(iso() if callable(iso) else str(f))
        return '|'.join(parts).encode('utf-8')

    def _make_mac(purpose: str, *fields) -> str:
        """Internal purpose-tagged HMAC. Sealed factories only.

        Not exported and not name-accessible from outside this closure
        pair. Arbitrary callers cannot mint proofs with this helper.
        """
        secret = _require_secret()
        return hmac.new(
            secret, _message(purpose, fields), hashlib.sha256
        ).hexdigest()

    def verify_mac(purpose: str, mac: str, *fields) -> None:
        """Verify a purpose-tagged HMAC. Fail closed on any mismatch."""
        if not isinstance(mac, str) or not mac:
            raise PermissionError('seal MAC required')
        expected = _make_mac(purpose, *fields)
        if not hmac.compare_digest(expected, mac):
            raise PermissionError('seal MAC mismatch')

    return install_seal_secret, verify_mac, _make_mac


install_seal_secret, verify_mac, _make_mac = _install_seal_api()
