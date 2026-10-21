from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

# Configure the invented host before pytest imports application modules during
# collection. Real verifier startup cannot depend on a later session fixture.
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
_previous_public_key = os.environ.get('ORACLE2_SEAL_PUBLIC_KEY')
_fixture_host_key = Ed25519PrivateKey.generate()
os.environ['ORACLE2_SEAL_PUBLIC_KEY'] = _fixture_host_key.public_key().public_bytes_raw().hex()
import seal_testkit
seal_testkit._fixture_key = _fixture_host_key

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
def seal_keys():
    """Keep collection-time synthetic host active; never install a real host."""
    yield
    seal_testkit._fixture_key = None
    if _previous_public_key is None:
        os.environ.pop('ORACLE2_SEAL_PUBLIC_KEY', None)
    else:
        os.environ['ORACLE2_SEAL_PUBLIC_KEY'] = _previous_public_key


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
