"""Owned TEST ONLY bounded opaque TLS tunnel to one proven local graph.

No Redis parsing, credentials, endpoint selector or production startup route.
The caller owns the exact graph/ACL; closing this tunnel is not graph cleanup.
"""
from contextlib import contextmanager
import hashlib,select,socket,ssl,threading,time
from dev.oracle2.test_readonly_graph_fixture import owned_target

@contextmanager
def owned_graph_tls(container,admin_url,*,server_context,expected_client_uri,diagnostics=None):
    _,target=owned_target(container,admin_url)
    if not isinstance(server_context,ssl.SSLContext) or server_context.verify_mode!=ssl.CERT_REQUIRED:
        raise PermissionError('mutually verified owned graph TLS fixture required')
    listener=socket.socket();listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    listener.bind(('127.0.0.1',0));listener.listen(32);listener.settimeout(.1)
    stop=threading.Event();lock=threading.Lock();active=set();workers=[];overflow=[];limit=threading.BoundedSemaphore(32)
    tls_diagnostics=[] if diagnostics is None else diagnostics
    def track(sock):
        with lock:active.add(sock)
        return sock
    _sem_acquired=0;_sem_released=0;_sem_lock=threading.Lock()
    _conn_track={}  # conn_id -> (acquire_ts, release_ts|None)
    def _sem_acquire(conn_id=None):
        nonlocal _sem_acquired
        ok=limit.acquire(blocking=False)
        if ok:
            with _sem_lock:
                _sem_acquired+=1
                if conn_id is not None:_conn_track[conn_id]=(time.monotonic(),None)
        return ok
    def _sem_release(conn_id=None):
        nonlocal _sem_released
        limit.release()
        with _sem_lock:
            _sem_released+=1
            if conn_id is not None and conn_id in _conn_track:
                _conn_track[conn_id]=(_conn_track[conn_id][0],time.monotonic())
            live=_sem_acquired-_sem_released
    def serve(raw):
        remote=None;client=raw;conn_id=threading.get_ident();track_id=id(raw);released=False
        def _safe_release():
            nonlocal released
            if not released:
                released=True
                _sem_release(track_id)
        # Source-only TLS diagnostic: record the actual numeric peer before any
        # wrap/handshake, and the peer DER hash only when the handshake succeeds.
        # No global SSL patch, no fallback, no retry; existing CA/SNI/pins stay.
        peer_address=None;handshake_done=False
        try:
            peer_address=raw.getpeername()
        except OSError:peer_address='unavailable'
        try:
            raw.settimeout(1)
            hs_start=time.monotonic()
            try:
                client=track(server_context.wrap_socket(raw,server_side=True))
            except (OSError,ValueError) as failure:
                tls_diagnostics.append({'stage':'handshake_failed','peer_address':peer_address,
                    'peer_der_sha256':None,'error_type':type(failure).__name__})
                return
            handshake_done=True
            try:
                peer_der=client.getpeercert(binary_form=True)
                peer_der_sha256=hashlib.sha256(peer_der).hexdigest() if peer_der else None
            except (OSError,ValueError):peer_der_sha256='unavailable'
            tls_diagnostics.append({'stage':'handshake_succeeded','peer_address':peer_address,
                'peer_der_sha256':peer_der_sha256,'expected_client_uri':expected_client_uri})
            uris=[v for k,v in client.getpeercert().get('subjectAltName',()) if k=='URI']
            if uris!=[expected_client_uri]:raise PermissionError('actual graph tunnel client URI differs')
            remote=track(socket.create_connection(('127.0.0.1',target.port),timeout=1))
            client.settimeout(.5);remote.settimeout(.5)
            last_data=time.monotonic()
            while not stop.is_set():
                ready,_,_=select.select([client,remote],[],[],.5)
                if not ready:
                    if time.monotonic()-last_data>10:return
                    continue
                for source in ready:
                    try:data=source.recv(65536)
                    except (socket.timeout,ssl.SSLWantReadError,BlockingIOError):continue
                    except (ConnectionResetError,ConnectionAbortedError,BrokenPipeError):return
                    if not data:return
                    last_data=time.monotonic()
                    dest=remote if source is client else client
                    try:dest.sendall(data)
                    except (socket.timeout,ssl.SSLWantWriteError,BlockingIOError):continue
                    except (ConnectionResetError,ConnectionAbortedError,BrokenPipeError,OSError):return
        except (OSError,ValueError,PermissionError) as failure:
            # Post-handshake settlement failures are distinct from TLS handshake
            # failures; keep the stage honest so diagnostics never blame TLS.
            tls_diagnostics.append({'stage':'post_handshake_failed' if handshake_done else 'handshake_failed',
                'peer_address':peer_address,'peer_der_sha256':None,'error_type':type(failure).__name__})
        finally:
            for sock in (client,remote,raw):
                if sock is not None:
                    with lock:active.discard(sock)
                    try:sock.close()
                    except OSError:pass
            _safe_release()
    def accept():
        while not stop.is_set():
            try:raw,_=listener.accept()
            except socket.timeout:continue
            except OSError as exc:
                if stop.is_set():return
                continue
            if not _sem_acquire(id(raw)):
                raw.close();overflow.append(1);continue

            track(raw);worker=threading.Thread(target=serve,args=(raw,),daemon=False)
            workers.append(worker)
            try:worker.start()
            except BaseException:
                overflow.append(2)
                with lock:active.discard(raw)
                try:raw.close()
                except OSError:pass
                limit.release()
    thread=threading.Thread(target=accept,daemon=False);thread.start()
    try:yield listener.getsockname()[1]
    finally:
        if overflow:print('owned-graph-tls-overflow',len(overflow),file=__import__('sys').stderr,flush=True)
        stop.set();listener.close()
        with lock:sockets=list(active)
        for sock in sockets:
            try:sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            sock.close()
        end=time.monotonic()+3
        thread.join(max(0,end-time.monotonic()))
        for worker in workers:worker.join(max(0,end-time.monotonic()))
        if thread.is_alive() or any(worker.is_alive() for worker in workers):raise RuntimeError('owned graph TLS fixture completion unknown')

def verify_graph_tls_peer(port,*,ca_file,certificate_file,key_file,expected_server_uri,diagnostics=None):
    """Preflight own immutable fixture context; SDK also verifies CA+hostname."""
    notes=[] if diagnostics is None else diagnostics
    context=ssl.create_default_context(cafile=str(ca_file));context.load_cert_chain(str(certificate_file),str(key_file))
    with socket.create_connection(('127.0.0.1',port),timeout=1) as raw:
        # Source-only diagnostic: numeric peer before wrap; DER hash only after
        # a successful handshake. No global SSL patch, no fallback, no retry.
        try:peer_address=raw.getpeername()
        except OSError:peer_address='unavailable'
        try:
            with context.wrap_socket(raw,server_hostname='localhost') as peer:
                peer_der=peer.getpeercert(binary_form=True)
                notes.append({'stage':'client_handshake_succeeded','peer_address':peer_address,
                    'peer_der_sha256':hashlib.sha256(peer_der).hexdigest() if peer_der else None,
                    'expected_server_uri':expected_server_uri})
                if [v for k,v in peer.getpeercert().get('subjectAltName',()) if k=='URI']!=[expected_server_uri]:
                    raise PermissionError('actual owned graph TLS server URI differs')
        except (OSError,ssl.SSLError,ValueError) as failure:
            notes.append({'stage':'client_handshake_failed','peer_address':peer_address,
                'peer_der_sha256':None,'error_type':type(failure).__name__})
            raise
