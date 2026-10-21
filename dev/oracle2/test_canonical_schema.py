"""Canonical invented test schema owner, shared by pytest fixture consumers.

The W10 verifier's explicit migration tuple remains the single inventory. This
helper retires per-fixture replay of superseded function definitions; it never
installs a target application schema or repairs drift after tests have begun.
"""
import ast
import hashlib
import json
import os
import re
import stat
from pathlib import Path

import psycopg
from dev.oracle2.test_worker_postgres_fixture import owned_worker_database

ROOT = Path(__file__).resolve().parents[2]
_SIGNATURES = (
    'oracle2.commit_processing_candidate(jsonb,bytea,bytea,bytea,jsonb,text,text,timestamptz)',
    'oracle2.ack_processing_projection(uuid,uuid,uuid,integer,jsonb,text,text,text,timestamptz)',
    'oracle2.finalize_source_revision_v1(uuid,integer,jsonb)',
)
_RECEIPTS = {}


def canonical_synthetic_migrations():
    tree = ast.parse((ROOT/'scripts/oracle2/verify_workflow_integrity.py').read_text())
    assignments = [n for n in tree.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'SYNTHETIC_MIGRATIONS' for t in n.targets)]
    augmented = any(isinstance(n, (ast.AugAssign, ast.AnnAssign))
        and isinstance(n.target, ast.Name) and n.target.id == 'SYNTHETIC_MIGRATIONS' for n in tree.body)
    if len(assignments) != 1 or augmented:
        raise PermissionError('one explicit canonical synthetic migration inventory required')
    names = ast.literal_eval(assignments[0].value)
    if (type(names) is not tuple or not names or len(set(names)) != len(names)
            or any(type(n) is not str or not re.fullmatch(r'[0-9]{3}_[a-z0-9_]+\.sql', n) for n in names)
            or any(n in names for n in ('015_native_trigger_proof.sql', '016_native_trigger_proof_v2.sql'))):
        raise PermissionError('closed canonical synthetic migration inventory required')
    files = tuple(ROOT/'services/oracle-brain/sql'/n for n in names)
    if any(not p.is_file() or p.is_symlink() for p in files):
        raise PermissionError('actual regular canonical synthetic migrations required')
    return files


def _inventory_digest(files):
    return hashlib.sha256(b''.join(p.name.encode()+b'\0'+hashlib.sha256(p.read_bytes()).digest() for p in files)).hexdigest()


def _catalog(connection):
    result = []
    for signature in _SIGNATURES:
        row = connection.execute('''SELECT oid::text,pg_get_functiondef(oid),pg_get_userbyid(proowner),
            prosecdef,proconfig,proacl::text FROM pg_proc WHERE oid=to_regprocedure(%s)''', (signature,)).fetchone()
        if row is None:
            raise PermissionError('complete canonical test capability catalog required')
        result.append((signature, row))
    return hashlib.sha256(json.dumps(result, separators=(',', ':')).encode()).hexdigest()


def _key(url):
    return hashlib.sha256(url.encode()).hexdigest()


def assert_canonical_test_schema(connection, url):
    """Refuse stale fixture DDL; never silently replay an extension to repair it."""
    receipt = _RECEIPTS.get(_key(url))
    if (receipt is None or _inventory_digest(canonical_synthetic_migrations()) != receipt['inventory']
            or _catalog(connection) != receipt['catalog']):
        raise PermissionError('canonical test schema changed; no fixture downgrade or automatic repair')


def _read_receipt(path, seal):
    p=Path(path)
    if not p.is_absolute() or p.parent.resolve()!=p.parent or not re.fullmatch('[0-9a-f]{64}',seal):
        raise PermissionError('fixed protected canonical schema receipt required')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid() or before.st_nlink!=1 or before.st_mode&0o077 or before.st_size>4096:
            raise PermissionError('private owned canonical schema receipt required')
        raw=os.read(fd,4097)
        identity=lambda x:(x.st_dev,x.st_ino,x.st_mode,x.st_uid,x.st_nlink,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
        if identity(before)!=identity(os.fstat(fd)) or identity(before)!=identity(p.lstat()) or hashlib.sha256(raw).hexdigest()!=seal:
            raise PermissionError('canonical schema receipt changed')
    finally:os.close(fd)
    value=json.loads(raw)
    if json.dumps(value,sort_keys=True,separators=(',',':')).encode()!=raw:raise PermissionError('canonical schema receipt bytes required')
    if type(value) is not dict or set(value)!={'schema_version','database_key','inventory','catalog'} or type(value['schema_version']) is not int or value['schema_version']!=1 or any(type(value[k]) is not str or not re.fullmatch('[0-9a-f]{64}',value[k]) for k in ('database_key','inventory','catalog')):
        raise PermissionError('closed canonical schema receipt required')
    return value


def _write_receipt(path, key, receipt):
    p=Path(path)
    if not p.is_absolute() or p.parent.resolve()!=p.parent:
        raise PermissionError('exact canonical schema receipt destination required')
    raw=json.dumps({'schema_version':1,'database_key':key,**receipt},sort_keys=True,separators=(',',':')).encode()
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    directory=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(directory)
    finally:os.close(directory)
    seal=hashlib.sha256(raw).hexdigest()
    if _read_receipt(p,seal)!={'schema_version':1,'database_key':key,**receipt}:
        raise PermissionError('canonical schema receipt readback differs')
    return seal


def bootstrap_canonical_test_schema(url,*,container_id=None,receipt_path=None):
    container = container_id or os.environ.get('ORACLE2_SYNTHETIC_POSTGRES_CONTAINER', '')
    if not container:
        raise PermissionError('exact owned synthetic PostgreSQL identity required')
    owned_worker_database(container, url)
    files = canonical_synthetic_migrations()
    key = _key(url)
    source_path=os.environ.get('ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT')
    source_seal=os.environ.get('ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT_SHA256')
    if receipt_path is None and (source_path or source_seal):
        if not source_path or not source_seal:raise PermissionError('complete canonical schema receipt pins required')
        observed=_read_receipt(source_path,source_seal)
        if observed['database_key']!=key or observed['inventory']!=_inventory_digest(files):
            raise PermissionError('canonical schema receipt target or inventory differs')
        with psycopg.connect(url) as connection:
            if _catalog(connection)!=observed['catalog']:
                raise PermissionError('canonical test schema changed; no fixture downgrade or automatic repair')
        receipt={k:observed[k] for k in ('inventory','catalog')}
        if key in _RECEIPTS and _RECEIPTS[key]!=receipt:raise PermissionError('canonical schema receipt changed after admission')
        _RECEIPTS[key]=receipt
        return
    if key in _RECEIPTS:
        with psycopg.connect(url) as connection:assert_canonical_test_schema(connection, url)
        return _write_receipt(receipt_path,key,_RECEIPTS[key]) if receipt_path is not None else None
    inventory = _inventory_digest(files)
    with psycopg.connect(url) as connection:
        for path in files:connection.execute(path.read_text())
        catalog = _catalog(connection)
    # Return and remember only after actual DDL transaction commit/close and a
    # fresh exact ownership check. This invented-test receipt is never app authority.
    owned_worker_database(container, url)
    with psycopg.connect(url) as connection:
        if _catalog(connection) != catalog or _inventory_digest(files) != inventory:
            raise PermissionError('canonical test schema changed during bootstrap')
    _RECEIPTS[key] = {'inventory': inventory, 'catalog': catalog}
    return _write_receipt(receipt_path,key,_RECEIPTS[key]) if receipt_path is not None else None


# Phase fixtures use a fresh UUID namespace even when CI supplies its owned
# Compose base. Reuse the existing exact database cleanup owner; no shared target.
from contextlib import contextmanager
from uuid import uuid4


@contextmanager
def owned_phase_database(admin_url,container,directory):
    from psycopg import sql
    from scripts.oracle2.verify_workflow_integrity import cleanup_test_databases
    owned_worker_database(container,admin_url)
    parts=psycopg.conninfo.conninfo_to_dict(admin_url)
    name='oracle_operating_model_test_'+uuid4().hex
    created=False
    try:
        with psycopg.connect(admin_url,autocommit=True) as connection:
            if connection.execute('SELECT session_user,current_database()').fetchone()!=('oracle2_admin',parts['dbname']):
                raise PermissionError('actual owned phase administrator differs')
            connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
            created=True
        target=psycopg.conninfo.make_conninfo(**(parts|{'dbname':name}))
        owned_worker_database(container,target)
        receipt=Path(directory).resolve()/'canonical-schema.json'
        seal=bootstrap_canonical_test_schema(target,container_id=container,receipt_path=receipt)
        yield {**os.environ,'ORACLE2_TEST_ADMIN_URL':target,
            'ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT':str(receipt),
            'ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT_SHA256':seal}
    finally:
        if created:
            owned_worker_database(container,admin_url)
            errors=cleanup_test_databases(admin_url,parts,[name])
            if errors:raise PermissionError('exact owned phase database cleanup failed')
