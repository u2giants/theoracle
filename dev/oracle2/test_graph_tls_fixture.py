"""Owned TEST ONLY bounded opaque TLS tunnel to one proven local graph.

No Redis parsing, credentials, endpoint selector or production startup route.
The caller owns the exact graph/ACL; closing this tunnel is not graph cleanup.
"""
from contextlib import contextmanager
import select,socket,ssl,threading,time
from dev.oracle2.test_readonly_graph_fixture import owned_target

_DIAG='/tmp/fixture-diag.log'
def _diag(msg):
    try:
        with open(_DIAG,'a') as f:f.write('[%.3f] %s\n'%(time.monotonic(),msg))
    except Exception:pass

@contextmanager
def owned_graph_tls(container,admin_url,*,server_context,expected_client_uri):
    _,target=owned_target(container,admin_url)
    if not isinstance(server_context,ssl.SSLContext) or server_context.verify_mode!=ssl.CERT_REQUIRED:
        raise PermissionError('mutually verified owned graph TLS fixture required')
    listener=socket.socket();listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    listener.bind(('127.0.0.1',0));listener.listen(8);listener.settimeout(.1)
    stop=threading.Event();lock=threading.Lock();active=set();workers=[];limit=threading.BoundedSemaphore(8)
    def track(sock):
        with lock:active.add(sock)
        return sock
    _sem_acquired=0;_sem_released=0;_sem_lock=threading.Lock()
    def _sem_acquire():
        nonlocal _sem_acquired
        ok=limit.acquire(blocking=False)
        if ok:
            with _sem_lock:_sem_acquired+=1
            _diag('sem acquire #%d (live=%d)'%(_sem_acquired,_sem_acquired-_sem_released))
        return ok
    def _sem_release():
        nonlocal _sem_released
        limit.release()
        with _sem_lock:_sem_released+=1
        _diag('sem release #%d (live=%d)'%(_sem_released,_sem_acquired-_sem_released))
    def serve(raw):
        remote=None;client=raw;conn_id=threading.get_ident()
        try:
            raw.settimeout(1)
            hs_start=time.monotonic()
            client=track(server_context.wrap_socket(raw,server_side=True))
            _diag('serve[%d] handshake ok in %.3fs'%(conn_id,time.monotonic()-hs_start))
            uris=[v for k,v in client.getpeercert().get('subjectAltName',()) if k=='URI']
            if uris!=[expected_client_uri]:raise PermissionError('actual graph tunnel client URI differs')
            remote=track(socket.create_connection(('127.0.0.1',target.port),timeout=1))
            client.settimeout(.2);remote.settimeout(.2)
            _diag('serve[%d] pump start'%conn_id)
            while not stop.is_set():
                ready,_,_=select.select([client,remote],[],[],.1)
                if client.pending() and client not in ready:ready.append(client)
                # Explicit liveness: SSLSocket may buffer FIN so select misses it.
                # Only treat b'' as EOF when the fd is readable (FIN actually arrived);
                # otherwise b'' just means no data in the SSL buffer.
                if client not in ready:
                    try:
                        r,_,_=select.select([client],[],[],0)
                        if r:
                            peek=client.recv(1,socket.MSG_PEEK)
                            if not peek:_diag('serve[%d] liveness EOF'%conn_id);return
                    except (socket.timeout,ssl.SSLWantReadError,BlockingIOError):pass
                    except (ConnectionResetError,ConnectionAbortedError,BrokenPipeError,ssl.SSLError,OSError) as exc:
                        _diag('serve[%d] liveness dead=%s'%(conn_id,type(exc).__name__));return
                for source in ready:
                    try:data=source.recv(65536)
                    except (socket.timeout,ssl.SSLWantReadError):continue
                    except (ConnectionResetError,ConnectionAbortedError,BrokenPipeError) as exc:
                        _diag('serve[%d] recv dead=%s'%(conn_id,type(exc).__name__));return
                    if not data:_diag('serve[%d] peer closed'%conn_id);return
                    dest=remote if source is client else client
                    try:dest.sendall(data)
                    except (socket.timeout,ssl.SSLWantWriteError,BlockingIOError):continue
                    except (ConnectionResetError,ConnectionAbortedError,BrokenPipeError,OSError) as exc:
                        _diag('serve[%d] send dead=%s'%(conn_id,type(exc).__name__));return
        except (OSError,ValueError,PermissionError) as exc:
            _diag('serve[%d] exc=%s:%s'%(conn_id,type(exc).__name__,exc))
        finally:
            for sock in (client,remote,raw):
                if sock is not None:
                    with lock:active.discard(sock)
                    try:sock.close()
                    except OSError:pass
            _sem_release()
            _diag('serve[%d] done active=%d'%(conn_id,len(active)))
    def accept():
        while not stop.is_set():
            try:raw,_=listener.accept()
            except socket.timeout:continue
            except OSError as exc:
                _diag('accept OSError=%s:%s stop=%s'%(type(exc).__name__,exc,stop.is_set()))
                if stop.is_set():return
                continue
            if not _sem_acquire():
                _diag('accept semaphore full, rejecting');raw.close();continue
            _diag('accept ok port=%s'%listener.getsockname()[1])
            track(raw);worker=threading.Thread(target=serve,args=(raw,),daemon=False)
            workers.append(worker);worker.start()
    thread=threading.Thread(target=accept,daemon=False);thread.start()
    _diag('fixture started port=%d'%listener.getsockname()[1])
    try:yield listener.getsockname()[1]
    finally:
        stop.set();listener.close()
        _diag('fixture stopping sem_acquired=%d sem_released=%d live=%d'%(_sem_acquired,_sem_released,_sem_acquired-_sem_released))
        with lock:sockets=list(active)
        for sock in sockets:
            try:sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            sock.close()
        end=time.monotonic()+3
        thread.join(max(0,end-time.monotonic()))
        for worker in workers:worker.join(max(0,end-time.monotonic()))
        if thread.is_alive() or any(worker.is_alive() for worker in workers):raise RuntimeError('owned graph TLS fixture completion unknown')

def verify_graph_tls_peer(port,*,ca_file,certificate_file,key_file,expected_server_uri):
    """Preflight own immutable fixture context; SDK also verifies CA+hostname."""
    context=ssl.create_default_context(cafile=str(ca_file));context.load_cert_chain(str(certificate_file),str(key_file))
    with socket.create_connection(('127.0.0.1',port),timeout=1) as raw:
        with context.wrap_socket(raw,server_hostname='localhost') as peer:
            if [v for k,v in peer.getpeercert().get('subjectAltName',()) if k=='URI']!=[expected_server_uri]:
                raise PermissionError('actual owned graph TLS server URI differs')
