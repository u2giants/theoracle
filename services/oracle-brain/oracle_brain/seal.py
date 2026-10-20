"""Purpose-tagged HMAC seal with a runtime-provided secret.

The secret is never committed to source and never importable as a value.
It is loaded once from the environment variable ``ORACLE2_SEAL_SECRET``
into a closure at first use. There is no installer: the environment is
the only source.

MAC creation exists only inside the seal closure. Sealed factories receive
a bound internal mint/verify callable from that closure and close over
them; the mint helper is never a module attribute and cannot be imported
or getattr'd. Verification-side ``verify_mac`` is the admission check at
every use site. Both are purpose-tagged so a MAC issued for one purpose
never satisfies another.
"""
from __future__ import annotations

import hashlib
import hmac
import os

# Documented runtime provider name. Production/host wiring sets this
# environment variable to the real secret; tests inject via the fixture
# before first seal use.
SEAL_SECRET_ENV = 'ORACLE2_SEAL_SECRET'

__all__ = ('SEAL_SECRET_ENV', 'verify_mac')


def _install_seal_api():
    """Create the seal with a closure-held secret and MAC helpers.

    The secret lives only inside this factory, loaded lazily from the
    environment on first use. The mint helper is bound only into sealed
    factories installed through this closure; it is never returned and
    never a module attribute, so no import or getattr can retrieve it.
    """
    _holder: list = []

    def _require_secret() -> bytes:
        if not _holder:
            env_raw = os.environ.get(SEAL_SECRET_ENV, '')
            if not env_raw:
                raise PermissionError(
                    'seal secret not installed; set ORACLE2_SEAL_SECRET')
            raw = env_raw.encode('utf-8')
            if len(raw) < 32:
                raise ValueError('seal secret must be at least 32 bytes')
            _holder.append(raw)
        return _holder[0]

    def _message(purpose: str, fields: tuple) -> bytes:
        if not purpose or not isinstance(purpose, str):
            raise ValueError('seal purpose required')
        parts = [purpose]
        for f in fields:
            iso = getattr(f, 'isoformat', None)
            parts.append(iso() if callable(iso) else str(f))
        return '|'.join(parts).encode('utf-8')

    def _mint_mac(purpose: str, *fields) -> str:
        """Internal purpose-tagged HMAC. Sealed factories only.

        Lives only inside this closure. Not returned, not a module
        attribute, not importable and not getattr-able from outside.
        """
        secret = _require_secret()
        return hmac.new(
            secret, _message(purpose, fields), hashlib.sha256
        ).hexdigest()

    def verify_mac(purpose: str, mac: str, *fields) -> None:
        """Verify a purpose-tagged HMAC. Fail closed on any mismatch."""
        if not isinstance(mac, str) or not mac:
            raise PermissionError('seal MAC required')
        expected = _mint_mac(purpose, *fields)
        if not hmac.compare_digest(expected, mac):
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
            mint=_mint_mac, verify=verify_mac)

    _wire_sealed_factories()
    return verify_mac


# Only the verification-side callable is a module attribute. The mint
# helper and the factory wire stay locals of the install closure.
verify_mac = _install_seal_api()
