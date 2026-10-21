"""Pure owned-database lifecycle and child-proof checks; no database writes."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dev.oracle2 import legacy_database_fixture as fixture


@pytest.fixture
def host(monkeypatch, tmp_path):
    ca = tmp_path / 'ca.pem'; ca.write_text('invented-ca')
    base = 'postgresql://oracle2_admin:oracle2_local_admin_only@127.0.0.1:5432/oracle2?sslmode=verify-full&sslrootcert=' + str(ca)
    state, events = {}, []
    container = {'Id': 'a' * 64}
    monkeypatch.setenv('COMPOSE_PROJECT_NAME', 'oracle2-ci-pure')
    monkeypatch.setenv('ORACLE2_SYNTHETIC_POSTGRES_CONTAINER', 'a' * 64)
    monkeypatch.setenv('TMPDIR', str(tmp_path))
    monkeypatch.setattr(fixture, 'owned_fixture_admin_url', lambda: base)
    monkeypatch.setattr(fixture, 'owned_postgres_fixture', lambda *args: dict(container))
    monkeypatch.setattr(fixture, '_identity', lambda connection, name: state.get(name))
    monkeypatch.setattr(fixture, 'setup_checkpoint_tables', lambda connection: events.append('checkpoint'))

    class Connection:
        pgconn = SimpleNamespace(ssl_in_use=True)
        info = SimpleNamespace(get_parameters=lambda: {'sslmode': 'verify-full'})
        def __init__(self, url): self.name = fixture.psycopg.conninfo.conninfo_to_dict(url)['dbname']
        def execute(self, query, args=()):
            text = query if isinstance(query, str) else query.as_string(None)
            events.append(text)
            if text.startswith('CREATE DATABASE'):
                name = re.search(r'"([^"]+)"', text).group(1)
                state[name] = (42, 'oracle2_admin', None)
            elif text.startswith('COMMENT ON DATABASE'):
                name = re.search(r'"([^"]+)"', text).group(1)
                marker = re.search(r"IS '(.*)'", text).group(1)
                state[name] = (42, 'oracle2_admin', marker)
            elif text.startswith('DROP DATABASE'):
                name = re.search(r'"([^"]+)"', text).group(1)
                state.pop(name)
            return SimpleNamespace(fetchone=lambda: (self.name, 'oracle2_admin'))

    @contextmanager
    def connect(url, **kwargs):
        yield Connection(url)
    monkeypatch.setattr(fixture.psycopg, 'connect', connect)
    return SimpleNamespace(base=base, state=state, events=events, container=container, ca=ca)


def test_fresh_profile_child_proof_and_exact_cleanup(host):
    with fixture.owned_legacy_database() as handle:
        proof = json.loads(Path(handle.receipt_path).read_text())
        assert len(proof['database'].encode()) <= 63
        assert proof['database'].startswith('oracle_legacy_')
        assert proof['database'] in host.state
        assert fixture.validate_legacy_database(handle.url, handle.receipt_path, handle.receipt_hash) == handle.url
        assert Path(handle.receipt_path).stat().st_mode & 0o777 == 0o600
        assert handle.environment()['ORACLE2_LEGACY_DATABASE_RECEIPT_SHA256'] == handle.receipt_hash
        assert 'checkpoint' in host.events
    assert host.state == {}
    assert not Path(handle.receipt_path).exists()
    assert len([event for event in host.events if event.startswith('CREATE DATABASE')]) == 1
    assert len([event for event in host.events if event.startswith('DROP DATABASE')]) == 1
    assert fixture.PROFILE == ('001_foundation.sql', '002_pilot.sql', '004_workflow_integrity.sql')


def test_body_failure_still_cleans_only_captured_database(host):
    with pytest.raises(RuntimeError, match='invented body failure'):
        with fixture.owned_legacy_database(): raise RuntimeError('invented body failure')
    assert not host.state


@pytest.mark.parametrize('mutation', ['container', 'ca', 'oid', 'marker'])
def test_changed_target_refuses_cleanup_and_retains_recovery(host, mutation):
    with pytest.raises(PermissionError):
        with fixture.owned_legacy_database() as handle:
            name = json.loads(Path(handle.receipt_path).read_text())['database']
            if mutation == 'container': host.container['Id'] = 'b' * 64
            elif mutation == 'ca': host.ca.write_text('changed-invented-ca')
            elif mutation == 'oid': host.state[name] = (43, *host.state[name][1:])
            else: host.state[name] = (*host.state[name][:2], 'other marker')
    assert name in host.state
    assert Path(handle.receipt_path).exists()
    assert not any(event.startswith('DROP DATABASE') for event in host.events)


@pytest.mark.parametrize('mutation', ['hash', 'mode', 'link', 'url', 'oid'])
def test_child_rejects_changed_receipt_or_target(host, tmp_path, mutation):
    with fixture.owned_legacy_database() as handle:
        path, expected, url = handle.receipt_path, handle.receipt_hash, handle.url
        if mutation == 'hash': expected = '0' * 64
        elif mutation == 'mode': os.chmod(path, 0o644)
        elif mutation == 'link': os.link(path, tmp_path / 'linked-proof')
        elif mutation == 'url': url = url.replace('127.0.0.1', 'outside.example')
        else:
            name = json.loads(Path(path).read_text())['database']
            previous = host.state[name]; host.state[name] = (43, *previous[1:])
        try:
            with pytest.raises(PermissionError): fixture.validate_legacy_database(url, path, expected)
        finally:
            if mutation == 'oid': host.state[name] = previous


def test_unreaped_worker_keeps_database_and_ownership_proof(host):
    with pytest.raises(fixture.LegacyCleanupBlocked):
        with fixture.owned_legacy_database() as handle: raise fixture.LegacyCleanupBlocked('invented worker')
    assert host.state and Path(handle.receipt_path).exists()



def test_exited_leader_does_not_hide_live_descendant(monkeypatch):
    from unittest.mock import Mock
    process = Mock(pid=123, poll=Mock(return_value=0))
    present = iter([True, True, False])
    monkeypatch.setattr(fixture, '_group_alive', lambda pgid: next(present))
    monkeypatch.setattr(fixture.time, 'sleep', lambda seconds: None)
    signals = []
    monkeypatch.setattr(fixture.os, 'killpg', lambda pid, action: signals.append((pid, action)))
    fixture.stop_owned_process(process)
    assert signals == [(123, fixture.signal.SIGTERM)]
    process.wait.assert_called_once_with(timeout=8)


def test_normal_absent_group_only_reaps_owned_leader(monkeypatch):
    from unittest.mock import Mock
    process = Mock(pid=123)
    monkeypatch.setattr(fixture, '_group_alive', lambda pgid: False)
    signal = Mock()
    monkeypatch.setattr(fixture.os, 'killpg', signal)
    fixture.stop_owned_process(process)
    signal.assert_not_called()
    process.wait.assert_called_once_with(timeout=8)


def test_post_kill_live_group_fails_closed(monkeypatch):
    from unittest.mock import Mock
    process = Mock(pid=123, poll=Mock(return_value=0))
    monkeypatch.setattr(fixture, '_group_alive', lambda pgid: True)
    ticks = iter(range(100))
    monkeypatch.setattr(fixture.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(fixture.time, 'sleep', lambda seconds: None)
    signals = []
    monkeypatch.setattr(fixture.os, 'killpg', lambda pid, action: signals.append((pid, action)))
    with pytest.raises(fixture.LegacyCleanupBlocked, match='still present'):
        fixture.stop_owned_process(process)
    assert signals == [(123, fixture.signal.SIGTERM), (123, fixture.signal.SIGKILL)]


def test_unknown_group_permission_fails_closed(monkeypatch):
    def deny(*args):raise PermissionError('invented denial')
    monkeypatch.setattr(fixture.os, 'killpg', deny)
    with pytest.raises(fixture.LegacyCleanupBlocked, match='unknown'):
        fixture._group_alive(123)


def test_holistic_browser_checks_group_after_leader_success(monkeypatch):
    import io
    from unittest.mock import Mock
    import verify_holistic_browser as browser
    process = Mock(returncode=0, stdout=io.BytesIO(b'invented browser output'))
    monkeypatch.setattr(browser.subprocess, 'Popen', lambda *args, **kwargs: process)
    stopped = []
    monkeypatch.setattr(browser, '_terminate', lambda child: stopped.append(child))
    result = browser._browser_run(['invented'], cwd=ROOT, env={}, timeout=100)
    assert result.returncode == 0 and stopped == [process]


def test_holistic_browser_cleanup_failure_is_not_consumed(monkeypatch):
    import io
    from unittest.mock import Mock
    import verify_holistic_browser as browser
    process = Mock(returncode=0, stdout=io.BytesIO(b''))
    monkeypatch.setattr(browser.subprocess, 'Popen', lambda *args, **kwargs: process)
    def denied(child): raise fixture.LegacyCleanupBlocked('invented descendant alive')
    monkeypatch.setattr(browser, '_terminate', denied)
    with pytest.raises(fixture.LegacyCleanupBlocked):
        browser._browser_run(['invented'], cwd=ROOT, env={}, timeout=100)
