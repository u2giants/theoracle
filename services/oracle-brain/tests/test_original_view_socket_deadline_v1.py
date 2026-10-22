"""Actual owned socket deadlines, with short appointments BEFORE capture.

No post-capture deadline mutation, alternate clock, SQL or authority callback.
"""
from datetime import datetime, timedelta, timezone
import socket
import threading
import time

import pytest

from test_hosting_boundary import certificates
from test_original_view_settings_v1 import configured_viewer
from test_original_view_service_v1 import recording_sql, running, client, wire, send, PDF, PATH


def short_installed(tmp_path, certificates, monkeypatch):
    until=datetime.now(timezone.utc)+timedelta(seconds=.65)
    fields=dict(expires_at=until.isoformat(),original_horizon=until.isoformat())
    f=configured_viewer(tmp_path,certificates,config_changes=fields,appointment_changes=fields,peer_changes=fields)
    recording_sql(f,monkeypatch)
    return f


def assert_cleanup(server,owned):
    assert not server._active and server.socket.fileno()==-1
    assert owned and all(s.fileno()==-1 for s in owned)
    assert all(not s._oracle_view_deadline_timer_v1.is_alive() for s in owned)


@pytest.mark.parametrize('phase',['handshake','headers','body'])
def test_absolute_owned_socket_deadline_stops_idle_or_slow_drip(tmp_path,certificates,monkeypatch,phase):
    f=short_installed(tmp_path,certificates,monkeypatch)
    owned=[]
    started=time.monotonic()
    with running(f) as server:
        original=server.process_request
        def capture(request,address):
            owned.append(request)
            return original(request,address)
        monkeypatch.setattr(server,'process_request',capture)
        if phase=='handshake':
            connection=socket.create_connection(('127.0.0.1',server.server_port),timeout=2)
            connection.settimeout(2)
            try:assert connection.recv(1)==b''
            finally:connection.close()
        else:
            connection=client(server,certificates)
            connection.connect()
            try:
                if phase=='headers':
                    connection.sock.sendall(b'POST '+PATH.encode()+b' HTTP/1.1\r\nHost: ')
                else:
                    raw=wire(f,seconds=.5)
                    connection.putrequest('POST',PATH)
                    connection.putheader('Content-Type','application/json')
                    connection.putheader('Content-Length',str(len(raw)))
                    connection.endheaders()
                # Every drip is faster than the retained5s idle timeout. The
                # original absolute watchdog must close it independently.
                refused=False
                for _ in range(15):
                    try:connection.sock.sendall(b'x')
                    except OSError:refused=True;break
                    time.sleep(.1)
                if not refused:
                    assert connection.sock.recv(4096)==b''
            finally:connection.close()
    assert time.monotonic()-started<2.2
    assert not f.connections
    assert_cleanup(server,owned)


def test_success_cancels_exact_timer_and_keeps_normal_pdf_capability(tmp_path,certificates,monkeypatch):
    f=configured_viewer(tmp_path,certificates);recording_sql(f,monkeypatch)
    owned=[]
    with running(f) as server:
        original=server.process_request
        def capture(request,address):
            owned.append(request);return original(request,address)
        monkeypatch.setattr(server,'process_request',capture)
        assert send(server,certificates,wire(f))[:2]==(200,PDF)
    assert_cleanup(server,owned)
    assert all(c.closed for c in f.connections)


def test_dispatch_failure_cancels_timer_closes_only_owned_socket_and_preserves_capacity(tmp_path,certificates,monkeypatch):
    from http.server import ThreadingHTTPServer
    f=configured_viewer(tmp_path,certificates);recording_sql(f,monkeypatch)
    owned=[];failed=threading.Event()
    with running(f) as server:
        process=server.process_request
        original=ThreadingHTTPServer.process_request
        def capture(request,address):
            owned.append(request);return process(request,address)
        def failure(*args):raise OSError('invented request thread dispatch failure')
        monkeypatch.setattr(server,'process_request',capture)
        monkeypatch.setattr(server,'handle_error',lambda *args:failed.set())
        monkeypatch.setattr(ThreadingHTTPServer,'process_request',failure)
        raw=socket.create_connection(('127.0.0.1',server.server_port),timeout=2)
        try:assert raw.recv(1)==b''
        finally:raw.close()
        assert failed.wait(2)
        assert server._connections._value==32 and not server._active
        assert not owned[0]._oracle_view_deadline_timer_v1.is_alive()
        monkeypatch.setattr(ThreadingHTTPServer,'process_request',original)
        assert send(server,certificates,wire(f))[:2]==(200,PDF)
    assert_cleanup(server,owned)
