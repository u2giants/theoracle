from __future__ import annotations

import hashlib
import hmac
import os
import secrets as _secrets
from pathlib import Path

import psycopg
import pytest

# Windows: directories always report mode 0o777, so FileBlobStore's Unix
# mode-bit check cannot pass. ACLs govern privacy here; keep the production
# check for POSIX test hosts.
import sys as _sys
if _sys.platform == "win32":
    import oracle_brain.operating_model.artifact_storage as _ast

    def _win_blob_init(self, root):
        self._original_root_alias = root.is_symlink()
        self.root = root.resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)

    _ast.FileBlobStore.__init__ = _win_blob_init


class _TestSeal:
    """Test-only HMAC helper bound to the injected test secret.

    Stands in for the host/identity service and the catalog reader so
    tests can produce real MACs and forged ones with a known-wrong secret.
    """

    def __init__(self, secret: bytes):
        self._secret = secret

    def mac(self, purpose: str, *fields) -> str:
        parts = [purpose]
        for f in fields:
            iso = getattr(f, 'isoformat', None)
            parts.append(iso() if callable(iso) else str(f))
        message = '|'.join(parts).encode('utf-8')
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()

    def forged_mac(self, purpose: str, *fields) -> str:
        """MAC computed with a different secret — must never verify."""
        wrong = hmac.new(b'wrong-secret-not-the-test-secret-000', purpose.encode(), hashlib.sha256).digest()
        parts = [purpose]
        for f in fields:
            iso = getattr(f, 'isoformat', None)
            parts.append(iso() if callable(iso) else str(f))
        message = '|'.join(parts).encode('utf-8')
        return hmac.new(wrong, message, hashlib.sha256).hexdigest()


@pytest.fixture(autouse=True)
def seal_secret():
    """Inject a random test secret into the runtime seal. Test-only path.

    Generates a fresh 32-byte secret per test (never committed), installs
    it into ``oracle_brain.seal``, and yields the raw bytes so tests can
    compute host-style MACs via ``oracle_brain.seal.seal_mac``.
    """
    from oracle_brain.seal import install_seal_secret
    secret = _secrets.token_bytes(32)
    install_seal_secret(secret)
    yield secret


@pytest.fixture()
def test_seal(seal_secret):
    """Test seal helper: produce valid and forged MACs for assertions."""
    return _TestSeal(seal_secret)


@pytest.fixture(scope="session")
def admin_url() -> str:
    url = os.environ.get("ORACLE2_TEST_ADMIN_URL", "")
    if not url:
        pytest.fail("real local Postgres URL required for S02 store tests")
    with psycopg.connect(url) as connection:
        connection.execute("SELECT 1")
    # Ensure pilot tables exist (002_pilot.sql is idempotent).
    sql_dir = Path(__file__).resolve().parents[1] / "sql"
    for sql_file in ("001_foundation.sql", "002_pilot.sql"):
        path = sql_dir / sql_file
        if path.is_file():
            with psycopg.connect(url, autocommit=True) as conn:
                conn.execute(path.read_text())
    return url


@pytest.fixture(scope="session")
def candidate_url() -> str:
    url = os.environ.get("ORACLE2_TEST_CANDIDATE_URL", "")
    if not url:
        pytest.fail("real local candidate FalkorDB URL required")
    return url


@pytest.fixture(scope="session")
def confirmed_url() -> str:
    url = os.environ.get("ORACLE2_TEST_CONFIRMED_URL", "")
    if not url:
        pytest.fail("real local confirmed FalkorDB URL required")
    return url
