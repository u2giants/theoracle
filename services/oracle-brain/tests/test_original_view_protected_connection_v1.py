"""Captured viewer keeps actual two closed sockets around private custody.

Recording connections exercise transport boundaries only. These are not actual
SQL/role/RLS or browser acceptance proofs; retained SQL tests remain separate.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time

import pytest

from oracle_brain.hosting.original_view_v1 import (
    OriginalViewerFactoryV1, OriginalViewerUnavailable, OWNER_QUERY,
)
from oracle_brain.operating_model import request_deadline_v1 as window
from test_hosting_boundary import certificates
from test_original_view_settings_v1 import configured_viewer
from test_original_view_service_v1 import recording_sql


@pytest.fixture
def recorded(tmp_path, certificates, monkeypatch):
    f = configured_viewer(tmp_path, certificates)
    recording_sql(f, monkeypatch)
    import psycopg
    old_connect = psycopg.connect
    f.tick = [100.0]
    monkeypatch.setattr(window.time, 'monotonic', lambda: f.tick[0])
    f.calls = []
    f.on_connect = None
    f.on_query = None
    f.before_exit = None
    f.exits = []
    def connect(raw, **kwargs):
        f.calls.append(dict(kwargs))
        connection = old_connect(raw, **kwargs)
        execute = connection.execute
        def guarded_record(q, args=None):
            result = execute(q, args)
            if f.on_query:
                f.on_query(connection, q)
            return result
        connection.execute = guarded_record
        if f.on_connect:
            f.on_connect(connection)
        cls = type(connection)
        old_exit = cls.__exit__
        def exit_record(self, *args):
            f.exits.append(args[0])
            if f.before_exit:
                f.before_exit(self)
            if args[0] is None:
                self.committed = True
            return old_exit(self, *args)
        cls.__exit__ = exit_record
        return connection
    monkeypatch.setattr(psycopg, 'connect', connect)
    f.factory = OriginalViewerFactoryV1(f.settings)
    f.deadline = datetime.now(timezone.utc) + timedelta(seconds=20)
    return f


def read(f):
    ref = f.settings.config.sources[0]
    return f.factory.read_original_v1(ref.source_id, ref.revision, caller_deadline=f.deadline)


def test_protected_actual_close_before_private_then_fresh_current_pass(recorded, monkeypatch):
    f = recorded
    private = f.factory._private
    calls = []
    def custody(*args):
        assert len(f.connections) == 1 and f.connections[0].closed
        calls.append('private')
        return private(*args)
    monkeypatch.setattr(f.factory, '_private', custody)
    with window._request_fence_v1(110.0):
        result = read(f)
    assert result.data == f.data and calls == ['private']
    assert len(f.connections) == 2 and f.caps == 4
    assert all(c.closed and c.committed for c in f.connections)
    assert len([q for q, _ in f.queries if q == 'BEGIN ISOLATION LEVEL READ COMMITTED']) == 2
    assert not any('set_config' in q for q, _ in f.queries)
    for kwargs in f.calls:
        assert kwargs['connect_timeout'] == 2 and kwargs['autocommit'] is True
        assert kwargs['hostaddr'] == '127.0.0.1'
        assert 'statement_timeout=2000ms' in kwargs['options']
        assert kwargs['sslmode'] == 'verify-full'


@pytest.mark.parametrize('key', ['PGHOSTADDR', 'PGSERVICE', 'PGOPTIONS'])
def test_environment_override_refused_before_socket(recorded, monkeypatch, key):
    monkeypatch.setenv(key, 'invented-unused')
    with window._request_fence_v1(110.0), pytest.raises(OriginalViewerUnavailable):
        read(recorded)
    assert not recorded.calls


def test_libpq_two_second_floor_refuses_before_socket(recorded):
    with window._request_fence_v1(101.9), pytest.raises(OriginalViewerUnavailable):
        read(recorded)
    assert not recorded.calls


def test_stalled_connect_cannot_send_begin_or_read_private(recorded):
    f = recorded
    f.on_connect = lambda _: f.tick.__setitem__(0, 108.5)
    with window._request_fence_v1(110.0), pytest.raises(OriginalViewerUnavailable):
        read(f)
    assert len(f.connections) == 1 and f.connections[0].closed
    assert not f.queries and not f.connections[0].committed


@pytest.mark.parametrize('boundary', ['catalog', 'capability', 'commit'])
def test_late_sql_or_guarded_commit_has_no_next_send_or_private(recorded, monkeypatch, boundary):
    f = recorded
    owners = [0]
    def after(c, q):
        if q == OWNER_QUERY:
            owners[0] += 1
        if ((boundary == 'catalog' and q.startswith('SELECT session_user'))
                or (boundary == 'capability' and q.startswith('SELECT oracle2.original_revision_view_v1'))):
            f.tick[0] = 110.1
        elif boundary == 'commit' and q == OWNER_QUERY and owners[0] == 2:
            f.tick[0] = 108.2  # unexpired, but old armed timeout cannot fit COMMIT
    f.on_query = after
    monkeypatch.setattr(f.factory, '_private', lambda *a: pytest.fail('private read after late SQL'))
    with window._request_fence_v1(110.0), pytest.raises(OriginalViewerUnavailable):
        read(f)
    assert len(f.connections) == 1 and f.connections[0].closed
    assert not f.connections[0].committed


@pytest.mark.parametrize('boundary', ['first', 'second'])
def test_actual_close_failure_never_returns_or_retries(recorded, boundary):
    f = recorded
    f.before_exit = lambda c: setattr(f, 'close_error', c.number == (1 if boundary == 'first' else 2))
    with window._request_fence_v1(110.0), pytest.raises(OriginalViewerUnavailable):
        read(f)
    assert len(f.connections) == (1 if boundary == 'first' else 2)
    assert all(c.closed for c in f.connections)


@pytest.mark.parametrize('boundary', ['first', 'second'])
def test_original_fence_expiry_at_actual_close_withholds_bytes(recorded, boundary):
    f = recorded
    def close(number):
        if number == (1 if boundary == 'first' else 2):
            f.tick[0] = 110.1
    f.after_close = close
    with window._request_fence_v1(110.0), pytest.raises(OriginalViewerUnavailable):
        read(f)
    assert len(f.connections) == (1 if boundary == 'first' else 2)


def test_pin_revoked_at_actual_close_withholds_private_bytes(recorded, monkeypatch):
    f = recorded
    def close(_):
        p = Path(f.settings.config_input.path)
        p.write_bytes(p.read_bytes() + b' ')
    f.after_close = close
    monkeypatch.setattr(f.factory, '_private', lambda *a: pytest.fail('private read after pin change'))
    with window._request_fence_v1(110.0), pytest.raises(OriginalViewerUnavailable):
        read(f)
    assert len(f.connections) == 1


def test_source_withdrawal_after_private_requires_fresh_sql_denial(recorded, monkeypatch):
    f = recorded
    private = f.factory._private
    def custody(*args):
        value = private(*args)
        f.cap_changes = {'principal_id': '00000000-0000-0000-0000-000000000000'}
        return value
    monkeypatch.setattr(f.factory, '_private', custody)
    with window._request_fence_v1(110.0), pytest.raises(OriginalViewerUnavailable):
        read(f)
    assert len(f.connections) == 2 and all(c.closed for c in f.connections)
    assert f.caps == 3


def test_foreign_preheld_connection_cannot_borrow_captured_context(recorded):
    class Foreign:
        def execute(self, *args): pytest.fail('foreign connection sent SQL')
    with window._request_fence_v1(110.0), pytest.raises(PermissionError, match='prearmed'):
        recorded.factory._query(Foreign(), recorded.deadline, 'SELECT forbidden')


def test_uncaptured_api_keeps_old_connection_setters_and_pdf_behavior(recorded):
    f = recorded
    assert read(f).data == f.data
    assert len(f.connections) == 2
    assert all(not call.get('autocommit', False) for call in f.calls)
    assert any('set_config' in q for q, _ in f.queries)


@pytest.mark.parametrize('fault', ['no_ssl', 'wrong_owner', 'wrong_login', 'extra_group'])
def test_captured_actual_target_and_role_checks_remain_mandatory(recorded, fault):
    f = recorded
    setattr(f, fault, True)
    with window._request_fence_v1(110.0), pytest.raises(OriginalViewerUnavailable):
        read(f)
    assert len(f.connections) == 1 and f.caps == 0
    assert f.connections[0].closed


@pytest.mark.parametrize('missing', ['host', 'port', 'dbname', 'user'])
def test_incomplete_pinned_dsn_refused_before_socket(tmp_path, certificates, monkeypatch, missing):
    target = dict(host='127.0.0.1', port='5432', dbname='invented_viewer_db',
                  user='invented_viewer', password='invented-only', sslmode='verify-full')
    del target[missing]
    f = configured_viewer(tmp_path, certificates, sql_target=target)
    recording_sql(f, monkeypatch)
    factory = OriginalViewerFactoryV1(f.settings)
    r = f.settings.config.sources[0]
    with window._request_fence_v1(float(time.monotonic() + 10)), pytest.raises(OriginalViewerUnavailable):
        factory.read_original_v1(r.source_id, r.revision,
            caller_deadline=datetime.now(timezone.utc) + timedelta(seconds=20))
    assert not f.connections


def test_short_returned_capability_cannot_fit_next_query_under_old_armed_timeout(recorded):
    f = recorded
    f.cap_changes = {'valid_until': (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()}
    with window._request_fence_v1(110.0), pytest.raises(OriginalViewerUnavailable):
        read(f)
    assert f.caps == 1 and len(f.connections) == 1
    assert f.connections[0].closed and not f.connections[0].committed
