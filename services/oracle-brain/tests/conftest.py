from __future__ import annotations

import os
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


def _seal_message(purpose: str, *fields) -> bytes:
    """Canonical purpose-tagged message bytes (same wire as oracle_brain.seal)."""
    parts = [purpose]
    for f in fields:
        iso = getattr(f, 'isoformat', None)
        parts.append(iso() if callable(iso) else str(f))
    return '|'.join(parts).encode('utf-8')


class _TestSeal:
    """Test-only signer bound to the injected ephemeral keypair.

    Stands in for the host/identity service and the isolated signer
    child so tests can produce real signatures and forged ones with a
    known-wrong key. This is the test-fixture side of the process
    boundary: the private key is used here, never by the verify path.
    """

    def __init__(self, private_key):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )
        self._private_key = private_key
        self._wrong_key = Ed25519PrivateKey.generate()

    def mac(self, purpose: str, *fields) -> str:
        return self._private_key.sign(_seal_message(purpose, *fields)).hex()

    def forged_mac(self, purpose: str, *fields) -> str:
        """Signature under a different key — must never verify."""
        return self._wrong_key.sign(_seal_message(purpose, *fields)).hex()


@pytest.fixture(scope="session", autouse=True)
def seal_keys(tmp_path_factory):
    """Ephemeral Ed25519 keypair before first seal use. Test-only path.

    Generates a random keypair (never committed). The public key is the
    only material the verify path loads. The private key is provided to
    the isolated signer (env / key file) and to test helpers that stand
    in for the host. Yields the raw private key bytes so tests can sign
    host-style proofs via ``_TestSeal``.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    private_key = Ed25519PrivateKey.generate()
    private_raw = private_key.private_bytes_raw()
    public_raw = private_key.public_key().public_bytes_raw()
    key_path = tmp_path_factory.mktemp('seal') / 'seal-private.key'
    key_path.write_text(private_raw.hex(), encoding='ascii')
    os.environ['ORACLE2_SEAL_PUBLIC_KEY'] = public_raw.hex()
    os.environ['ORACLE2_SEAL_PRIVATE_KEY'] = private_raw.hex()
    os.environ['ORACLE2_SEAL_PRIVATE_KEY_FILE'] = str(key_path)
    yield private_raw
    for name in (
        'ORACLE2_SEAL_PUBLIC_KEY',
        'ORACLE2_SEAL_PRIVATE_KEY',
        'ORACLE2_SEAL_PRIVATE_KEY_FILE',
    ):
        os.environ.pop(name, None)


@pytest.fixture()
def test_seal(seal_keys):
    """Test seal helper: produce valid and forged signatures for assertions."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    return _TestSeal(Ed25519PrivateKey.from_private_bytes(seal_keys))


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
