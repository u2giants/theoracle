"""Owned TEST ONLY bounded opaque TLS tunnel to one proven local graph.

No Redis parsing, credentials, endpoint selector or production startup route.
The caller owns the exact graph/ACL; closing this tunnel is not graph cleanup.
"""
from contextlib import contextmanager
import select,socket,ssl,threading,time
from dev.oracle2.test_readonly_graph_fixture import owned_target

@contextmanager
def owned_graph_tls(container,admin_url,*,server_context,expected_client_uri):
    _,target=owned_target(container,admin_url)
    if not isinstance(server_context,ssl.SSLContext) or server_context.verify_mode!=ssl.CERT_REQUIRED:
        raise PermissionError('mutually verified owned graph TLS fixture required')
    listener=socket.socket();listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    listener.bind(('127.0.0.1',0));listener.listen(32);listener.settimeout(.1)
    stop=threading.Event();lock=threading.Lock();active=set();workers=[];overflow=[];limit=threading.BoundedSemaphore(32)
    def track(sock):
        with lock:active.add(sock)
        return sock
    def serve(raw):
        remote=None;client=raw
        try:
            raw.settimeout(1)
            client=track(server_context.wrap_socket(raw,server_side=True))
            uris=[v for k,v in client.getpeercert().get('subjectAltName',()) if k=='URI']
            if uris!=[expected_client_uri]:raise PermissionError('actual graph tunnel client URI differs')
            remote=track(socket.create_connection(('127.0.0.1',target.port),timeout=1))
            client.settimeout(.2);remote.settimeout(.2)
            while not stop.is_set():
                ready,_,_=select.select([client,remote],[],[],.1)
                if client.pending() and client not in ready:ready.append(client)
                for source in ready:
                    try:data=source.recv(65536)
                    except (socket.timeout,ssl.SSLWantReadError):continue
                    if not data:return
                    (remote if source is client else client).sendall(data)
        except (OSError,ValueError,PermissionError):pass
        finally:
            for sock in (client,remote,raw):
                if sock is not None:
                    with lock:active.discard(sock)
                    try:sock.close()
                    except OSError:pass
            limit.release()
    def accept():
        while not stop.is_set():
            try:raw,_=listener.accept()
            except socket.timeout:continue
            except OSError:return
            if not limit.acquire(blocking=False):
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

def verify_graph_tls_peer(port,*,ca_file,certificate_file,key_file,expected_server_uri):
    """Preflight own immutable fixture context; SDK also verifies CA+hostname."""
    context=ssl.create_default_context(cafile=str(ca_file));context.load_cert_chain(str(certificate_file),str(key_file))
    with socket.create_connection(('127.0.0.1',port),timeout=1) as raw:
        with context.wrap_socket(raw,server_hostname='localhost') as peer:
            if [v for k,v in peer.getpeercert().get('subjectAltName',()) if k=='URI']!=[expected_server_uri]:
                raise PermissionError('actual owned graph TLS server URI differs')
