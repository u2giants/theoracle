"""Purpose-tagged HMAC seal with a runtime-provided secret.

The secret is never committed to source and never importable as a value.
It is loaded from the environment variable ``ORACLE2_SEAL_SECRET`` or
injected via ``install_seal_secret`` (host wiring at startup, or the
test-only fixture in ``tests/conftest.py``).

Issuer-side ``seal_mac`` is available to trusted readers that must seal
their own output (e.g. the Q2b catalog reader). Verification-side
``verify_mac`` is the admission check at every use site. Both are
purpose-tagged so a MAC issued for one purpose never satisfies another.
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

    def install_seal_secret(secret) -> None:
        """Install the seal secret. Host wiring or test fixture only.

        The secret must be at least 32 bytes of high-entropy material.
        Installing replaces any previously installed secret (rotation).
        """
        if not isinstance(secret, (bytes, bytearray)):
            raise ValueError('seal secret must be bytes')
        raw = bytes(secret)
        if len(raw) < 32:
            raise ValueError('seal secret must be at least 32 bytes')
        _holder.clear()
        _holder.append(raw)

    def _require_secret() -> bytes:
        if not _holder:
            env_raw = os.environ.get(SEAL_SECRET_ENV, '')
            if env_raw:
                install_seal_secret(env_raw.encode('utf-8'))
        if not _holder:
            raise PermissionError(
                'seal secret not installed; set ORACLE2_SEAL_SECRET or '
                'call install_seal_secret')
        return _holder[0]

    def _message(purpose: str, fields: tuple) -> bytes:
        if not purpose or not isinstance(purpose, str):
            raise ValueError('seal purpose required')
        parts = [purpose]
        for f in fields:
            iso = getattr(f, 'isoformat', None)
            parts.append(iso() if callable(iso) else str(f))
        return '|'.join(parts).encode('utf-8')

    def seal_mac(purpose: str, *fields) -> str:
        """Produce a purpose-tagged HMAC hex digest.

        Trusted issuer use only (catalog readers, host-authorized proof
        factories). Callers who can invoke this hold the seal capability;
        external input never reaches it directly.
        """
        secret = _require_secret()
        return hmac.new(secret, _message(purpose, fields), hashlib.sha256).hexdigest()

    def verify_mac(purpose: str, mac: str, *fields) -> None:
        """Verify a purpose-tagged HMAC. Fail closed on any mismatch."""
        if not isinstance(mac, str) or not mac:
            raise PermissionError('seal MAC required')
        secret = _require_secret()
        expected = hmac.new(secret, _message(purpose, fields), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, mac):
            raise PermissionError('seal MAC mismatch')

    return install_seal_secret, seal_mac, verify_mac


install_seal_secret, seal_mac, verify_mac = _install_seal_api()
