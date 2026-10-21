"""Oracle offline CI owns this isolated legacy SDK schema profile.

Canonical RLS remains in the main test database. Consolidate/retire this helper
when retained browser journeys adopt the current hosted admission contract.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import sys
import signal
import subprocess
import time
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from scripts.oracle2.init_local_stores import owned_fixture_admin_url, setup_checkpoint_tables, ROOT
from dev.oracle2.test_tls_bootstrap import postgres_uri, owned_postgres_fixture

PROFILE = ('001_foundation.sql', '002_pilot.sql', '004_workflow_integrity.sql')

class LegacyCleanupBlocked(RuntimeError):
    """An owned worker could not be reaped; preserve its database and receipt."""


def _group_alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError as error:
        raise LegacyCleanupBlocked('owned process group state is unknown') from error


def stop_owned_process(process):
    """Prove the owned session group absent, even after its leader has exited."""
    if process is None:
        return
    pgid = process.pid  # Captured Popen identity; every caller starts a new session.
    if not _group_alive(pgid):
        try: process.wait(timeout=8)
        except (subprocess.TimeoutExpired, OSError) as error:
            raise LegacyCleanupBlocked('owned process could not be reaped') from error
        return
    for action in (signal.SIGTERM, signal.SIGKILL):
        try: os.killpg(pgid, action)
        except ProcessLookupError: pass
        except OSError as error:
            raise LegacyCleanupBlocked('owned process group could not be stopped') from error
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            try: process.poll()  # Reap the leader without mistaking it for the whole group.
            except OSError as error:
                raise LegacyCleanupBlocked('owned process state is unknown') from error
            if not _group_alive(pgid):
                try: process.wait(timeout=8)
                except (subprocess.TimeoutExpired, OSError) as error:
                    raise LegacyCleanupBlocked('owned process could not be reaped') from error
                return
            time.sleep(0.05)
    raise LegacyCleanupBlocked('owned process group is still present')


def _identity(connection, name):
    return connection.execute("SELECT oid,pg_get_userbyid(datdba),obj_description(oid,'pg_database') FROM pg_database WHERE datname=%s", (name,)).fetchone()


def _read_receipt(path, expected_hash):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 or info.st_size > 16384:
            raise PermissionError('private legacy ownership receipt required')
        body = stream.read(16385)
    if hashlib.sha256(body).hexdigest() != expected_hash:
        raise PermissionError('legacy ownership receipt changed')
    return json.loads(body)


def validate_legacy_database(url, receipt_path, receipt_hash):
    base = owned_fixture_admin_url()
    parts = psycopg.conninfo.conninfo_to_dict(base)
    details = owned_postgres_fixture(os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER'], base)
    receipt = _read_receipt(receipt_path, receipt_hash)
    name = receipt.get('database', '')
    if not re.fullmatch(r'oracle_legacy_[0-9a-f]{32}', name) or len(name.encode()) > 63:
        raise PermissionError('exact fresh legacy database required')
    expected = {**parts, 'dbname': name}
    actual = postgres_uri(url, sslrootcert=parts['sslrootcert'])
    if psycopg.conninfo.conninfo_to_dict(actual) != expected:
        raise PermissionError('legacy target differs from owned parent')
    if receipt.get('container_id') != details['Id'] or receipt.get('project') != os.environ['COMPOSE_PROJECT_NAME'] or receipt.get('port') != parts['port'] or receipt.get('ca_sha256') != hashlib.sha256(Path(parts['sslrootcert']).read_bytes()).hexdigest():
        raise PermissionError('legacy container or CA differs')
    with psycopg.connect(actual) as connection:
        if not connection.pgconn.ssl_in_use or connection.info.get_parameters().get('sslmode') != 'verify-full':
            raise PermissionError('legacy verified TLS required')
        if connection.execute('SELECT current_database(),session_user').fetchone() != (name, parts['user']):
            raise PermissionError('legacy session identity differs')
        if _identity(connection, name) != (receipt['oid'], parts['user'], 'oracle-legacy-fixture:' + receipt['nonce']):
            raise PermissionError('legacy database ownership differs')
    return actual


@dataclass(frozen=True)
class LegacyDatabase:
    url: str = field(repr=False)
    receipt_path: str
    receipt_hash: str

    def environment(self):
        return {'ORACLE2_LEGACY_DATABASE_RECEIPT': self.receipt_path,
                'ORACLE2_LEGACY_DATABASE_RECEIPT_SHA256': self.receipt_hash}


@contextmanager
def owned_legacy_database():
    base = owned_fixture_admin_url()
    parts = psycopg.conninfo.conninfo_to_dict(base)
    details = owned_postgres_fixture(os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER'], base)
    name, nonce = 'oracle_legacy_' + uuid4().hex, uuid4().hex
    ca_hash = hashlib.sha256(Path(parts['sslrootcert']).read_bytes()).hexdigest()
    private = Path(tempfile.mkdtemp(prefix='oracle-legacy-db-', dir=os.environ.get('TMPDIR')))
    private.chmod(0o700)
    recovery = dict(database=name, nonce=nonce, container_id=details['Id'],
                    project=os.environ['COMPOSE_PROJECT_NAME'], port=parts['port'], ca_sha256=ca_hash)
    recovery_path = private / 'recovery.json'
    with os.fdopen(os.open(recovery_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
        json.dump(recovery, stream, sort_keys=True)
    created = False
    receipt = None
    cleaned = False
    try:
        with psycopg.connect(base, autocommit=True) as host:
            if _identity(host, name) is not None:
                raise PermissionError('legacy database already exists')
            host.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
            created = True
            initial = _identity(host, name)
            recovery['oid'] = initial[0] if initial else None
            recovery_path.write_text(json.dumps(recovery, sort_keys=True))
            host.execute(sql.SQL('COMMENT ON DATABASE {} IS {}').format(sql.Identifier(name), sql.Literal('oracle-legacy-fixture:' + nonce)))
            oid, owner, marker = _identity(host, name)
            if owner != parts['user'] or marker != 'oracle-legacy-fixture:' + nonce:
                raise PermissionError('new legacy ownership differs')
        url = postgres_uri(psycopg.conninfo.make_conninfo(**{**parts, 'dbname': name}), sslrootcert=parts['sslrootcert'])
        receipt = dict(database=name, oid=oid, nonce=nonce, container_id=details['Id'],
            project=os.environ['COMPOSE_PROJECT_NAME'], port=parts['port'],
            ca_sha256=ca_hash)
        body = json.dumps(receipt, sort_keys=True).encode()
        path = private / 'ownership.json'
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream: stream.write(body)
        handle = LegacyDatabase(url, str(path), hashlib.sha256(body).hexdigest())
        validate_legacy_database(url, handle.receipt_path, handle.receipt_hash)
        with psycopg.connect(url) as connection:
            for migration in PROFILE:
                connection.execute((ROOT / 'services/oracle-brain/sql' / migration).read_text())
        with psycopg.connect(url, autocommit=True, prepare_threshold=0, row_factory=dict_row) as connection:
            setup_checkpoint_tables(connection)
        yield handle
    finally:
        if isinstance(sys.exc_info()[1], LegacyCleanupBlocked):
            raise LegacyCleanupBlocked('owned worker still active; legacy database receipt retained')
        if created:
            # Reprove the container and captured object before dropping anything.
            if owned_fixture_admin_url() != base:
                raise PermissionError('legacy cleanup parent changed')
            current = owned_postgres_fixture(os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER'], base)
            if current['Id'] != details['Id'] or hashlib.sha256(Path(parts['sslrootcert']).read_bytes()).hexdigest() != ca_hash:
                raise PermissionError('legacy cleanup container or CA changed; recovery evidence retained')
            with psycopg.connect(base, autocommit=True) as host:
                expected = (receipt['oid'], parts['user'], 'oracle-legacy-fixture:' + nonce) if receipt else None
                if expected is None or _identity(host, name) != expected:
                    raise PermissionError(f'legacy cleanup ownership changed; recovery evidence retained at {private}')
                host.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
        cleaned = True
        if cleaned: shutil.rmtree(private)
