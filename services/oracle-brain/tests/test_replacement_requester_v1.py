"""Recording-connection contracts only; actual SQL/browser admission remains open."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.original_intake_v1 import load_original_intake_settings_v1
from oracle_brain.hosting.replacement_requester_v1 import (
    ReplacementRequesterFactoryV1, ReplacementRequesterUnavailable,
    parse_requester_request_v1, _FUNCTIONS,
)
from test_original_intake_v1 import settings as intake_settings


def fixture(tmp_path, monkeypatch):
    s = intake_settings(tmp_path)
    ca = tmp_path / 'database-ca'; ca.write_bytes(b'invented CA'); ca.chmod(0o600)
    url = tmp_path / 'database-url'
    url.write_text(f'host=invented.invalid dbname=invented user=invented_requester password=invented sslmode=verify-full sslrootcert={ca}')
    url.chmod(0o600)
    c = s.config.model_copy(update={
        'database_url': type(s.config.database_url)(path=str(url), sha256=hashlib.sha256(url.read_bytes()).hexdigest()),
        'database_ca': type(s.config.database_ca)(path=str(ca), sha256=hashlib.sha256(ca.read_bytes()).hexdigest())})
    craw = canonical_bytes(c.model_dump(mode='json')); s.config_path.write_bytes(craw)
    cseal = hashlib.sha256(craw).hexdigest()
    a = s.appointment.model_copy(update={'config_sha256': cseal})
    araw = canonical_bytes(a.model_dump(mode='json')); s.appointment_path.write_bytes(araw)
    s = load_original_intake_settings_v1(s.config_path, cseal, s.appointment_path,
        hashlib.sha256(araw).hexdigest(), s.expected_issuer_actor, s.expected_reviewer_actor)
    run = uuid4(); source = uuid4(); events = []
    now = datetime.now(timezone.utc)
    context = dict(principal_id=str(c.principal_id), workspace_id=str(c.workspace_id),
        session_role=c.expected_session_role, runtime_hash=c.runtime_hash,
        source_registry_hash=c.registry_hash, checked_at=now.isoformat(), valid_until=c.expires_at.isoformat())
    metadata = dict(schema_version=1, run_id=str(run), journey_revision=1, state='pending',
        population_sha256='a' * 64, cancel_requested=False, paid_cost_retained=False, context=context)
    f = SimpleNamespace(s=s, run=run, source=source, events=events, context=context,
        metadata=metadata, owners=[('oracle2', name.split('(', 1)[0].split('.', 1)[1], c.expected_owner_role, True)
                                   for name in _FUNCTIONS],
        login=(c.expected_session_role, c.expected_session_role, c.expected_owner_role),
        reserve_population=True, on_query=None, on_commit=None, on_close=None,
        close_error=False, commit_error=False, reserve_error=False, connects=0,
        actual=SimpleNamespace(host='invented.invalid', dbname='invented', user=c.expected_session_role, port=5432), ssl=True)

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): events.append('cursor-close')
        def execute(self, query, parameters=None):
            events.append((query, parameters))
            self.query = query
            if f.on_query: f.on_query(query)
            if query.startswith('SELECT oracle2.reserve_replacement_journey') and f.reserve_error:
                raise RuntimeError('uncertain SQL execution')
        def fetchall(self): return f.owners
        def fetchone(self):
            if 'SESSION_USER::text' in self.query: return f.login
            if self.query.startswith('SELECT oracle2.reserve_replacement_journey'):
                value = dict(schema_version=1, run_id=str(run), journey_revision=1,
                             state='pending', context=f.context)
                if f.reserve_population: value['population_sha256'] = 'a' * 64
                return (value,)
            if self.query.startswith('SELECT oracle2.request_replacement_cancel'):
                f.metadata.update(state='cancelled', journey_revision=2, cancel_requested=True, paid_cost_retained=True)
                return (dict(schema_version=1, run_id=str(run), journey_revision=2, state='cancelled',
                    cancel_requested=True, paid_cost_retained=True, in_flight_attempt_retained=True,
                    remote_stop_proof=False, message='cancellation requested; in-flight attempt retained', context=f.context),)
            return (f.metadata,)

    class Connection:
        @property
        def info(self): return f.actual
        @property
        def pgconn(self): return SimpleNamespace(ssl_in_use=f.ssl)
        def __enter__(self): events.append('open'); return self
        def __exit__(self, *args):
            events.append('close')
            if f.on_close: f.on_close()
            if f.close_error: raise RuntimeError('uncertain close')
        def cursor(self): return Cursor()
        def commit(self):
            events.append('commit')
            if f.on_commit: f.on_commit()
            if f.commit_error: raise RuntimeError('uncertain commit')

    def connect(*args, **kwargs):
        f.connects += 1
        assert kwargs == {'connect_timeout': 5}
        return Connection()
    monkeypatch.setattr('psycopg.connect', connect)
    f.factory = ReplacementRequesterFactoryV1(s)
    return f


def request(f, operation='reserve', **changes):
    body = dict(schema_version=1, operation=operation, caller_deadline=f.s.config.expires_at.isoformat())
    if operation == 'reserve':
        body.update(source_selectors=[dict(source_id=str(f.source), revision=1)],
                    population_sha256='a' * 64, idempotency_key=str(uuid4()))
    else:
        body['run_id'] = str(f.run)
    if operation == 'cancel':
        body.update(expected_revision=1, reason='Stop this invented operation', idempotency_key=str(uuid4()))
    body.update(changes)
    return canonical_bytes(body)


@pytest.mark.parametrize('operation', ['reserve', 'status', 'cancel'])
def test_exact_fixed_calls_fresh_observation_and_public_metadata_only(tmp_path, monkeypatch, operation):
    f = fixture(tmp_path, monkeypatch)
    result = f.factory.execute_v1(request(f, operation))
    assert result.runId == f.run
    assert result.controlState == ('cancelled' if operation == 'cancel' else 'pending')
    assert result.remoteStopProven is False and result.resultAvailable is False
    assert set(result.model_dump()) == {'runId', 'journeyRevision', 'controlState', 'populationSha256',
                                       'cancelRequested', 'remoteStopProven', 'resultAvailable'}
    queries = [x[0] for x in f.events if isinstance(x, tuple)]
    assert queries[-1] == 'SELECT oracle2.current_replacement_journey_metadata(%s)'
    assert f.events[-3:] == ['cursor-close', 'commit', 'close']
    assert f.connects == 1


def test_historical_reserve_idempotency_reply_is_not_current_status(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); f.reserve_population = False
    f.metadata.update(state='delivered', journey_revision=5)
    raw = request(f)
    result = f.factory.execute_v1(raw)
    assert result.controlState == 'delivered' and result.journeyRevision == 5
    assert result.resultAvailable is False
    reserve = [x for x in f.events if isinstance(x, tuple) and 'reserve_replacement_journey(%s' in x[0]][0]
    assert json.loads(reserve[1][0])['caller_deadline'] == json.loads(raw)['caller_deadline']
    assert set(json.loads(reserve[1][0])['source_selectors'][0]) == {'source_id', 'revision'}


@pytest.mark.parametrize('field', ['actor', 'workspace', 'grant', 'provider', 'job', 'config', 'advance', 'retry'])
def test_unknown_authority_and_replay_fields_rejected_before_connection(tmp_path, monkeypatch, field):
    f = fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError): f.factory.execute_v1(request(f, **{field: 'forged'}))
    assert f.connects == 0


@pytest.mark.parametrize('attack', ['duplicate', 'noncanonical', 'bool-version', 'duplicate-source',
                                    'extra-selector', 'selector-schema', 'bool-revision', 'zero-revision', 'large-revision',
                                    'bad-idempotency', 'wrong-operation', 'long-reason', 'zero-cancel-revision'])
def test_closed_canonical_request_union_before_mutation(tmp_path, monkeypatch, attack):
    f = fixture(tmp_path, monkeypatch); raw = request(f)
    body = json.loads(raw)
    if attack == 'duplicate': raw = raw[:-1] + b',"operation":"reserve"}'
    elif attack == 'noncanonical': raw = b' ' + raw
    else:
        if attack == 'bool-version': body['schema_version'] = True
        elif attack == 'duplicate-source': body['source_selectors'] *= 2
        elif attack == 'extra-selector': body['source_selectors'][0]['workspace_id'] = str(uuid4())
        elif attack == 'selector-schema': body['source_selectors'][0]['schema_version'] = 1
        elif attack == 'bool-revision': body['source_selectors'][0]['revision'] = True
        elif attack == 'zero-revision': body['source_selectors'][0]['revision'] = 0
        elif attack == 'large-revision': body['source_selectors'][0]['revision'] = 2147483648
        elif attack == 'bad-idempotency': body['idempotency_key'] = 'bad'
        elif attack == 'wrong-operation': body['operation'] = 'advance'
        elif attack == 'long-reason': body = json.loads(request(f, 'cancel', reason='x' * 1601))
        elif attack == 'zero-cancel-revision': body = json.loads(request(f, 'cancel', expected_revision=0))
        raw = canonical_bytes(body)
    with pytest.raises(ValueError): f.factory.execute_v1(raw)
    assert f.connects == 0


@pytest.mark.parametrize('attack', ['ssl', 'host', 'database', 'user', 'port', 'owner', 'caller',
                                    'function-owner', 'not-definer', 'numeric-definer', 'missing-function', 'duplicate-function',
                                    'principal', 'workspace', 'runtime', 'registry', 'stale-context',
                                    'foreign-run', 'foreign-population', 'unknown-response-field'])
def test_actual_target_role_function_and_context_must_match(tmp_path, monkeypatch, attack):
    f = fixture(tmp_path, monkeypatch)
    if attack == 'ssl': f.ssl = False
    elif attack in ('host', 'database', 'user', 'port'):
        setattr(f.actual, {'database': 'dbname'}.get(attack, attack), 1234 if attack == 'port' else 'foreign')
    elif attack == 'owner': f.login = (*f.login[:2], 'foreign_owner')
    elif attack == 'caller': f.login = ('foreign_login', *f.login[1:])
    elif attack == 'function-owner': f.owners[0] = (*f.owners[0][:2], 'foreign_owner', True)
    elif attack == 'not-definer': f.owners[0] = (*f.owners[0][:3], False)
    elif attack == 'numeric-definer': f.owners[0] = (*f.owners[0][:3], 1)
    elif attack == 'missing-function': f.owners.pop()
    elif attack == 'duplicate-function': f.owners[-1] = f.owners[0]
    elif attack in ('principal', 'workspace'): f.context[attack + '_id'] = str(uuid4())
    elif attack in ('runtime', 'registry'): f.context[{'runtime': 'runtime_hash', 'registry': 'source_registry_hash'}[attack]] = 'f' * 64
    elif attack == 'stale-context': f.context['valid_until'] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    elif attack == 'foreign-run': f.metadata['run_id'] = str(uuid4())
    elif attack == 'foreign-population': f.metadata['population_sha256'] = 'f' * 64
    else: f.metadata['private_object_key'] = 'forbidden'
    with pytest.raises(ReplacementRequesterUnavailable): f.factory.execute_v1(request(f))
    assert 'commit' not in f.events
    assert f.connects == 1


@pytest.mark.parametrize('attack', ['expired', 'excessive', 'revoked-before-commit', 'revoked-after-close',
                                    'close-error', 'commit-error', 'uncertain-sql'])
def test_horizon_revoke_and_uncertainty_never_retry_or_publish_success(tmp_path, monkeypatch, attack):
    f = fixture(tmp_path, monkeypatch); raw = request(f)
    if attack == 'expired': raw = request(f, caller_deadline=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat())
    elif attack == 'excessive': raw = request(f, caller_deadline=(f.s.config.expires_at + timedelta(seconds=1)).isoformat())
    elif attack == 'revoked-before-commit':
        def hook(query):
            if query.startswith('SELECT oracle2.current_replacement_journey_metadata'):
                f.s.appointment_path.write_bytes(b'{}')
        f.on_query = hook
    elif attack == 'revoked-after-close': f.on_close = lambda: f.s.appointment_path.write_bytes(b'{}')
    elif attack == 'close-error': f.close_error = True
    elif attack == 'commit-error': f.commit_error = True
    elif attack == 'uncertain-sql': f.reserve_error = True
    with pytest.raises(ReplacementRequesterUnavailable): f.factory.execute_v1(raw)
    assert f.connects <= 1
    if attack in ('expired', 'excessive', 'revoked-before-commit', 'uncertain-sql'):
        assert 'commit' not in f.events


def repin_url(f, text):
    path = f.s.config.database_url.path
    from pathlib import Path
    Path(path).write_text(text)
    pin = f.s.config.database_url.model_copy(update={'sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest()})
    config = f.s.config.model_copy(update={'database_url': pin})
    raw = canonical_bytes(config.model_dump(mode='json')); f.s.config_path.write_bytes(raw)
    seal = hashlib.sha256(raw).hexdigest()
    appointment = f.s.appointment.model_copy(update={'config_sha256': seal})
    araw = canonical_bytes(appointment.model_dump(mode='json')); f.s.appointment_path.write_bytes(araw)
    f.s = load_original_intake_settings_v1(f.s.config_path, seal, f.s.appointment_path,
        hashlib.sha256(araw).hexdigest(), f.s.expected_issuer_actor, f.s.expected_reviewer_actor)
    f.factory = ReplacementRequesterFactoryV1(f.s)


@pytest.mark.parametrize('damage', ['weak-tls', 'wrong-ca', 'wrong-user', 'extra-option'])
def test_exact_sealed_database_url_is_still_not_target_authority(tmp_path, monkeypatch, damage):
    f = fixture(tmp_path, monkeypatch)
    from pathlib import Path
    raw = Path(f.s.config.database_url.path).read_text()
    if damage == 'weak-tls': raw = raw.replace('sslmode=verify-full', 'sslmode=require')
    elif damage == 'wrong-ca': raw = raw.replace(f.s.config.database_ca.path, '/foreign/ca')
    elif damage == 'wrong-user': raw = raw.replace('user=invented_requester', 'user=admin')
    else: raw += ' options=--search_path=oracle2'
    repin_url(f, raw)
    with pytest.raises(ReplacementRequesterUnavailable): f.factory.execute_v1(request(f))
    assert f.connects == 0


@pytest.mark.parametrize('phase', ['before-commit', 'after-close'])
@pytest.mark.parametrize('pin', ['database_url', 'database_ca'])
def test_target_pin_mutation_during_operation_denies_even_after_commit(tmp_path, monkeypatch, phase, pin):
    f = fixture(tmp_path, monkeypatch)
    from pathlib import Path
    mutate = lambda: Path(getattr(f.s.config, pin).path).write_bytes(b'changed invented input')
    if phase == 'before-commit':
        def hook(query):
            if query.startswith('SELECT oracle2.current_replacement_journey_metadata'): mutate()
        f.on_query = hook
    else: f.on_close = mutate
    with pytest.raises(ReplacementRequesterUnavailable): f.factory.execute_v1(request(f))
    assert f.connects == 1
    if phase == 'before-commit': assert 'commit' not in f.events


def test_second_explicit_observation_cannot_extend_original_deadline(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    deadline = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()
    raw = request(f, caller_deadline=deadline)
    f.factory.execute_v1(raw)
    f.factory.execute_v1(raw)
    reservations = [entry for entry in f.events if isinstance(entry, tuple)
                    and entry[0].startswith('SELECT oracle2.reserve_replacement_journey')]
    assert len(reservations) == 2
    assert all(json.loads(entry[1][0])['caller_deadline'] == deadline for entry in reservations)


@pytest.mark.parametrize('field', ['cancel_requested', 'paid_cost_retained'])
def test_nonboolean_metadata_is_not_a_control_observation(tmp_path, monkeypatch, field):
    f = fixture(tmp_path, monkeypatch); f.metadata[field] = 1
    with pytest.raises(ReplacementRequesterUnavailable): f.factory.execute_v1(request(f, 'status'))
    assert 'commit' not in f.events


@pytest.mark.parametrize('state', [
    'pending', 'processing', 'delivered', 'revision_pending', 'cancelled', 'error',
    'awaiting-external-authority', 'missing-evidence', 'cancel-requested', 'failed', 'UNKNOWN',
])
def test_every_actual_sql_control_state_remains_metadata_only(tmp_path, monkeypatch, state):
    f = fixture(tmp_path, monkeypatch)
    f.metadata.update(state=state, cancel_requested=state in ('cancel-requested', 'cancelled'))
    result = f.factory.execute_v1(request(f, 'status'))
    assert result.controlState == state
    assert result.remoteStopProven is False and result.resultAvailable is False
    assert 'ready' not in result.model_dump()


@pytest.mark.parametrize('damage', ['foreign-schema', 'foreign-function', 'unqualified-rendering'])
def test_catalog_identity_cannot_be_substituted_by_search_path_or_rendering(tmp_path, monkeypatch, damage):
    f = fixture(tmp_path, monkeypatch)
    if damage == 'foreign-schema':
        f.owners[0] = ('public', *f.owners[0][1:])
    elif damage == 'foreign-function':
        f.owners[0] = (f.owners[0][0], 'other_operation', *f.owners[0][2:])
    else:
        # A regprocedure-rendering-shaped row is not a catalog identity proof.
        f.owners[0] = (f.owners[0][1] + '(jsonb,uuid)', *f.owners[0][1:])
    with pytest.raises(ReplacementRequesterUnavailable): f.factory.execute_v1(request(f))
    assert 'commit' not in f.events
    assert not any(isinstance(x, tuple) and x[0].startswith('SELECT oracle2.reserve_replacement_journey')
                   for x in f.events)


def test_function_lookup_uses_fixed_schema_qualified_oids_not_rendered_names(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    f.factory.execute_v1(request(f, 'status'))
    query = next(x[0] for x in f.events if isinstance(x, tuple) and 'pg_catalog.pg_proc' in x[0])
    assert 'regprocedure::text' not in query
    assert 'n.nspname,p.proname' in query
    assert 'JOIN pg_catalog.pg_namespace' in query
    for signature in _FUNCTIONS:
        assert f"pg_catalog.to_regprocedure('{signature}')" in query
    assert query.count('to_regprocedure(') == 3
