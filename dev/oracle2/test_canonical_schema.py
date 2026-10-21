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


def bootstrap_canonical_test_schema(url):
    container = os.environ.get('ORACLE2_SYNTHETIC_POSTGRES_CONTAINER', '')
    if not container:
        raise PermissionError('exact owned synthetic PostgreSQL identity required')
    owned_worker_database(container, url)
    files = canonical_synthetic_migrations()
    key = _key(url)
    if key in _RECEIPTS:
        with psycopg.connect(url) as connection:
            assert_canonical_test_schema(connection, url)
        return
    inventory = _inventory_digest(files)
    with psycopg.connect(url) as connection:
        for path in files:
            connection.execute(path.read_text())
        catalog = _catalog(connection)
    # Return and remember only after actual DDL transaction commit/close and a
    # fresh exact ownership check. No test may use this receipt as app authority.
    owned_worker_database(container, url)
    with psycopg.connect(url) as connection:
        if _catalog(connection) != catalog or _inventory_digest(files) != inventory:
            raise PermissionError('canonical test schema changed during bootstrap')
    _RECEIPTS[key] = {'inventory': inventory, 'catalog': catalog}
