"""Actual owned synthetic TLS/SCRAM requester integration; no production targets."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import os
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest

from dev.oracle2.test_tls_bootstrap import owned_postgres_fixture
from oracle_brain.operating_model.contracts import canonical_bytes, digest
from oracle_brain.hosting.original_intake_v1 import load_original_intake_settings_v1
from oracle_brain.hosting.replacement_requester_v1 import (
    ReplacementRequesterFactoryV1, ReplacementRequesterUnavailable,
)
from test_original_intake_v1 import settings as intake_settings
from test_replacement_source_intake_sql import requester, call, reserve, custody


@pytest.fixture
def admin_url(admin_url):
    # Guard the imported requester fixture's writes. The session admin fixture
    # has already applied foundation migrations; the canonical worker fixture
    # owns and verifies that synthetic cluster before those setup writes.
    owned_postgres_fixture(os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER'], admin_url)
    return admin_url


@contextmanager
def owned_admin(x):
    owned_postgres_fixture(os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER'], x['admin'])
    with psycopg.connect(x['admin']) as connection:
        assert connection.pgconn.ssl_in_use
        assert connection.execute('SELECT SESSION_USER,current_database()').fetchone() == ('oracle2_admin', 'oracle2')
        yield connection


def configured_settings(tmp_path, x, *, url=None, login=None, ca=None, owner=None):
    s = intake_settings(tmp_path)
    ca_path = Path(ca or os.environ['ORACLE2_TEST_TLS_ROOT'])
    db = tmp_path / 'actual-requester-url'; db.write_text(url or x['url']); db.chmod(0o600)
    cert = tmp_path / 'actual-requester-ca'; cert.write_bytes(ca_path.read_bytes()); cert.chmod(0o600)
    # The URL must name this exact pinned CA copy. No application credentials.
    db.write_text(psycopg.conninfo.make_conninfo(db.read_text(), sslrootcert=str(cert)))
    with owned_admin(x) as connection:
        actual_owner = connection.execute("SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='oracle2'").fetchone()[0]
    updates = dict(principal_id=x['actor'], workspace_id=x['workspace'], expected_session_role=login or x['login'],
        expected_owner_role=owner or actual_owner, runtime_hash=x['runtime'], registry_hash=x['registry'],
        database_url=type(s.config.database_url)(path=str(db), sha256=hashlib.sha256(db.read_bytes()).hexdigest()),
        database_ca=type(s.config.database_ca)(path=str(cert), sha256=hashlib.sha256(cert.read_bytes()).hexdigest()))
    c = s.config.model_copy(update=updates)
    raw = canonical_bytes(c.model_dump(mode='json')); s.config_path.write_bytes(raw); seal = hashlib.sha256(raw).hexdigest()
    fields = ('principal_id', 'workspace_id', 'expected_session_role', 'runtime_hash', 'registry_hash')
    a = s.appointment.model_copy(update={**{key: getattr(c, key) for key in fields}, 'config_sha256': seal})
    araw = canonical_bytes(a.model_dump(mode='json')); s.appointment_path.write_bytes(araw)
    return load_original_intake_settings_v1(s.config_path, seal, s.appointment_path,
        hashlib.sha256(araw).hexdigest(), s.expected_issuer_actor, s.expected_reviewer_actor)


@pytest.fixture
def sql_requester(requester, tmp_path):
    x = requester
    first = reserve(x); source = first['reservation']['source_id']
    call(x, 'finalize_source_revision_v1', first['reservation']['reservation_id'], 0, Jsonb(custody(first)))
    with owned_admin(x) as connection:
        connection.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',
            (uuid4(), x['workspace'], x['actor'], 'source-read:' + source, x['owner'], x['root'], x['until']))
    s = configured_settings(tmp_path, x)
    population = digest({'source_refs': [dict(source_id=source, revision=1, original_sha256='c' * 64)]})
    return x | dict(source=source, settings=s, factory=ReplacementRequesterFactoryV1(s), population=population)


def wire(x, operation='reserve', **changes):
    body = dict(schema_version=1, operation=operation, caller_deadline=x['settings'].config.expires_at.isoformat())
    if operation == 'reserve':
        body.update(source_selectors=[dict(source_id=x['source'], revision=1)],
                    population_sha256=x['population'], idempotency_key=str(uuid4()))
    else: body['run_id'] = str(x['run'])
    if operation == 'cancel': body.update(expected_revision=1, reason='Invented cancellation', idempotency_key=str(uuid4()))
    return canonical_bytes(body | changes)


def row_count(x):
    with owned_admin(x) as connection:
        return connection.execute('SELECT count(*) FROM oracle2.processing_journey_runs_v1 WHERE workspace_id=%s', (x['workspace'],)).fetchone()[0]


def test_real_tls_reserve_replay_status_cas_cancel_and_fresh_metadata(sql_requester):
    x = sql_requester; original = wire(x)
    first = x['factory'].execute_v1(original); x['run'] = first.runId
    assert first.controlState == 'pending' and first.journeyRevision == 1
    assert x['factory'].execute_v1(original).runId == first.runId
    assert row_count(x) == 1
    assert x['factory'].execute_v1(wire(x, 'status')).runId == first.runId
    with pytest.raises(ReplacementRequesterUnavailable):
        x['factory'].execute_v1(wire(x, 'cancel', expected_revision=2))
    cancelled = x['factory'].execute_v1(wire(x, 'cancel'))
    assert cancelled.controlState == 'cancelled' and cancelled.journeyRevision == 2 and cancelled.cancelRequested
    assert cancelled.remoteStopProven is False and cancelled.resultAvailable is False
    # Historical idempotency envelope says pending/revision1; actual result must
    # instead expose the fresh SQL state/revision2 from the SAME transaction.
    replayed = x['factory'].execute_v1(original)
    assert replayed.controlState == 'cancelled' and replayed.journeyRevision == 2
    assert row_count(x) == 1


def test_actual_wrong_function_owner_is_denied_before_reserve(sql_requester):
    x = sql_requester; foreign = 'requester_owner_' + uuid4().hex[:12]
    with owned_admin(x) as connection:
        owner = connection.execute("SELECT pg_get_userbyid(proowner) FROM pg_proc WHERE oid='oracle2.reserve_replacement_journey(jsonb,uuid)'::regprocedure").fetchone()[0]
        connection.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(foreign)))
        connection.execute(sql.SQL('ALTER FUNCTION oracle2.reserve_replacement_journey(jsonb,uuid) OWNER TO {}').format(sql.Identifier(foreign)))
    try:
        with pytest.raises(ReplacementRequesterUnavailable): x['factory'].execute_v1(wire(x))
        assert row_count(x) == 0
    finally:
        with owned_admin(x) as connection:
            connection.execute(sql.SQL('ALTER FUNCTION oracle2.reserve_replacement_journey(jsonb,uuid) OWNER TO {}').format(sql.Identifier(owner)))
            connection.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(foreign)))


def test_actual_unappointed_login_cannot_borrow_requester_identity(sql_requester, tmp_path):
    x = sql_requester; foreign = 'unappointed_' + uuid4().hex[:12]
    with owned_admin(x) as connection:
        connection.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(foreign), sql.Literal('invented-unappointed-only')))
        connection.execute(sql.SQL('GRANT oracle2_replacement_requester TO {}').format(sql.Identifier(foreign)))
    try:
        directory = tmp_path / 'foreign'; directory.mkdir()
        s = configured_settings(directory, x, login=foreign,
            url=psycopg.conninfo.make_conninfo(x['url'], user=foreign, password='invented-unappointed-only'))
        with pytest.raises(ReplacementRequesterUnavailable): ReplacementRequesterFactoryV1(s).execute_v1(wire(x))
        assert row_count(x) == 0
    finally:
        with owned_admin(x) as connection: connection.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(foreign)))


def test_actual_tls_rejects_wrong_ca_and_plaintext(sql_requester, tmp_path):
    x = sql_requester
    # The independently issued non-CA leaf is not a replacement trusted root.
    foreign_ca = Path(os.environ['ORACLE2_TEST_TLS_ROOT']).with_name('server.crt')
    directory = tmp_path / 'wrong-ca'; directory.mkdir()
    s = configured_settings(directory, x, ca=foreign_ca)
    with pytest.raises(ReplacementRequesterUnavailable): ReplacementRequesterFactoryV1(s).execute_v1(wire(x))
    with pytest.raises(psycopg.OperationalError): psycopg.connect(psycopg.conninfo.make_conninfo(x['url'], sslmode='disable'))
    assert row_count(x) == 0


def test_actual_expired_runtime_denies_request_and_no_mutation(sql_requester):
    x = sql_requester
    with owned_admin(x) as connection:
        connection.execute("UPDATE oracle2.hosting_role_runtime_admissions SET expires_at=clock_timestamp()-interval '1 second' WHERE role_name=%s", (x['login'],))
    with pytest.raises(ReplacementRequesterUnavailable): x['factory'].execute_v1(wire(x))
    assert row_count(x) == 0


def test_actual_source_withdrawal_denies_new_population_and_invalidates_status(sql_requester):
    x = sql_requester
    before = x['factory'].execute_v1(wire(x)); x['run'] = before.runId
    context = dict(principal_id=str(x['actor']), workspace_id=str(x['workspace']), session_role=x['login'],
                   runtime_hash=x['runtime'], source_registry_hash=x['registry'])
    call(x, 'withdraw_original_revision_v1', x['source'], 1,
        Jsonb(dict(reason='Invented source withdrawal', expected_context=context, caller_deadline=x['until'].isoformat())), uuid4())
    with pytest.raises(ReplacementRequesterUnavailable): x['factory'].execute_v1(wire(x))
    observed = x['factory'].execute_v1(wire(x, 'status'))
    assert observed.controlState == 'error' and observed.journeyRevision == 2
    assert observed.resultAvailable is False and row_count(x) == 1
