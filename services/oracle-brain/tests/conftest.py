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


@pytest.fixture(scope="session", autouse=True)
def seal_keys(tmp_path_factory):
    """Ephemeral Ed25519 keypair before first seal use. Test-only path.

    Generates a random keypair (never committed). The public key is the
    only key material the parent process ever loads. The private key is
    written to a key file and the parent holds only the path string
    (``ORACLE2_SEAL_SIGNER_KEY_FILE``); the signer child reads the file.
    The parent environment never contains ``ORACLE2_SEAL_PRIVATE_KEY*``
    variables or the key material itself. Tests that need a host-issued
    signature call ``seal_testkit.sign_seal``, which invokes the signer
    CLI entrypoint — never an in-process sign helper.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    private_key = Ed25519PrivateKey.generate()
    public_raw = private_key.public_key().public_bytes_raw()
    key_path = tmp_path_factory.mktemp('seal') / 'seal-private.key'
    key_path.write_text(private_key.private_bytes_raw().hex(), encoding='ascii')
    os.environ['ORACLE2_SEAL_PUBLIC_KEY'] = public_raw.hex()
    os.environ['ORACLE2_SEAL_SIGNER_KEY_FILE'] = str(key_path)
    yield str(key_path)
    for name in (
        'ORACLE2_SEAL_PUBLIC_KEY',
        'ORACLE2_SEAL_SIGNER_KEY_FILE',
    ):
        os.environ.pop(name, None)


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
