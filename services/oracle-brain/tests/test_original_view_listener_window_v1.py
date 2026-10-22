"""Actual loopback mTLS keeps pre-handshake time through fixed viewer SQL.

SQL is recorded, not executed; actual owned SQL proof remains separately gated.
"""
from datetime import datetime, timezone
import threading
import time

import pytest

from oracle_brain.hosting.gateway import MutualTLSServer
from oracle_brain.hosting.original_view_v1 import OriginalViewerFactoryV1
from oracle_brain.operating_model.request_deadline_v1 import request_remaining_v1
from test_hosting_boundary import certificates
from test_original_view_settings_v1 import configured_viewer, PDF
from test_original_view_service_v1 import recording_sql, running, send, wire, client, PATH


def test_same_actual_handshake_occurs_after_original_capture(tmp_path, certificates, monkeypatch):
    f = configured_viewer(tmp_path, certificates)
    recording_sql(f, monkeypatch)
    original = MutualTLSServer.process_request_thread
    observed = []
    def handshake(server, request, address):
        # Parent's actual method immediately calls SSLSocket.do_handshake.
        assert request._oracle_view_original_wall_v1 <= datetime.now(timezone.utc)
        assert request._oracle_view_original_mono_v1 <= time.monotonic()
        assert 0 < request_remaining_v1() <= 30
        observed.append('before actual TLS')
        time.sleep(.45)
        return original(server, request, address)
    monkeypatch.setattr(MutualTLSServer, 'process_request_thread', handshake)
    with running(f) as server:
        assert send(server, certificates, wire(f, seconds=2.4))[:2] == (503, b'')
    assert observed == ['before actual TLS'] and not f.connections
    assert request_remaining_v1(required=False) is None


@pytest.mark.parametrize('boundary', ['headers', 'body'])
def test_actual_header_body_delay_uses_original_caller_window(tmp_path, certificates, monkeypatch, boundary):
    f = configured_viewer(tmp_path, certificates)
    recording_sql(f, monkeypatch)
    with running(f) as server:
        raw = wire(f, seconds=2.4)
        connection = client(server, certificates)
        try:
            connection.connect()
            connection.putrequest('POST', PATH)
            connection.putheader('Content-Type', 'application/json')
            connection.putheader('Content-Length', str(len(raw)))
            if boundary == 'headers':
                time.sleep(.45)
            connection.endheaders()
            if boundary == 'body':
                time.sleep(.45)
            connection.send(raw)
            response = connection.getresponse()
            assert (response.status, response.read()) == (503, b'')
        finally:
            connection.close()
    assert not f.connections


def test_actual_listener_enters_fixed_protected_factory_and_clears_thread_context(tmp_path, certificates, monkeypatch):
    f = configured_viewer(tmp_path, certificates)
    recording_sql(f, monkeypatch)
    original = OriginalViewerFactoryV1._read_original_protected_v1
    seen, cleared = [], []
    def protected(factory, source, revision, deadline):
        assert 2 < request_remaining_v1() <= (deadline-datetime.now(timezone.utc)).total_seconds()+.05
        seen.append(source)
        return original(factory, source, revision, deadline)
    monkeypatch.setattr(OriginalViewerFactoryV1, '_read_original_protected_v1', protected)
    with running(f) as server:
        worker = server.process_request_thread
        def checked(request, address):
            worker(request, address)
            cleared.append(request_remaining_v1(required=False))
        monkeypatch.setattr(server, 'process_request_thread', checked)
        assert send(server, certificates, wire(f))[:2] == (200, PDF)
        assert send(server, certificates, b'{}')[:2] == (503, b'')
        assert send(server, certificates, wire(f))[:2] == (200, PDF)
    assert len(seen) == 2 and cleared == [None, None, None]
    assert len(f.connections) == 4 and all(c.closed and c.committed for c in f.connections)
    assert not any('set_config' in query for query, _ in f.queries)
    assert request_remaining_v1(required=False) is None


def test_original_body_never_renews_thirty_second_accept_window(tmp_path, certificates, monkeypatch):
    f = configured_viewer(tmp_path, certificates)
    recording_sql(f, monkeypatch)
    with running(f) as server:
        assert send(server, certificates, wire(f, seconds=31))[:2] == (503, b'')
    assert not f.connections


def test_handshake_exception_clears_same_thread_fence_and_preserves_listener(tmp_path, certificates, monkeypatch):
    import ssl
    f = configured_viewer(tmp_path, certificates)
    recording_sql(f, monkeypatch)
    cleared, first_done = [], threading.Event()
    with running(f) as server:
        worker = server.process_request_thread
        def checked(request, address):
            worker(request, address)
            cleared.append(request_remaining_v1(required=False))
            first_done.set()
        monkeypatch.setattr(server, 'process_request_thread', checked)
        with pytest.raises((ssl.SSLError, ConnectionError)):
            send(server, certificates, wire(f), identity=None)
        assert first_done.wait(2)
        assert not f.connections and cleared == [None]
        assert send(server, certificates, wire(f))[:2] == (200, PDF)
    assert cleared == [None, None]
    assert all(c.closed for c in f.connections)
