"""Owned loopback wire owner proof; production public-address policy UNCHANGED.

Fixture connects a separately owned synthetic TLS socket explicitly. It is not
an installed public Recall/CDN profile, provider permission, or SQL authority.
"""
import hashlib,socket,ssl,threading,time
from datetime import datetime,timedelta,timezone
import pytest
from test_hosting_boundary import certificates
from oracle_brain.research.fetch import _InstalledArtifactGET,_read_artifact_http_v1,UnsafeDestination
BODY=b'{"original":"invented"}'

def wire(certificates,mode):
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1)
    tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(certificates/'server.pem',certificates/'server.key')
    seen=[]
    def server():
        try:
            raw,_=listener.accept()
            with tls.wrap_socket(raw,server_side=True) as peer:
                data=b''
                while b'\r\n\r\n' not in data:data+=peer.recv(1024)
                seen.append(data);assert data.startswith(b'GET /invented-final HTTP/1.1\r\n') and b'Authorization:' not in data
                status='302 Found' if mode=='redirect' else '200 OK'
                headers=f'HTTP/1.1 {status}\r\nContent-Length: {len(BODY)}\r\nConnection: close\r\n'
                if mode=='duplicate':headers+=f'Content-Length: {len(BODY)}\r\n'
                if mode=='largeheader':headers+='X-Long: '+'x'*16384+'\r\n'
                if mode=='chunked':headers+='Transfer-Encoding: chunked\r\n'
                peer.sendall(headers.encode()+b'\r\n'+(BODY[:-1] if mode=='truncated' else BODY))
                if mode=='extra':time.sleep(.03);peer.sendall(b'EXTRA')
                if mode=='noeof':time.sleep(.35)
                try:peer.unwrap()
                except (OSError,ssl.SSLError):pass
        except (OSError,ssl.SSLError):pass
        finally:listener.close()
    thread=threading.Thread(target=server);thread.start()
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.load_verify_locations(cafile=certificates/'ca.pem')
    sock=context.wrap_socket(socket.create_connection(('127.0.0.1',listener.getsockname()[1]),timeout=1),server_hostname='localhost',suppress_ragged_eofs=False)
    return sock,thread,seen
@pytest.mark.parametrize('mode',['valid','extra','noeof','truncated','duplicate','largeheader','chunked','redirect','wronghash'])
def test_owned_actual_tls_original_wire_refusals(certificates,mode):
    active,thread,seen=wire(certificates,mode);end=time.monotonic()+(.12 if mode=='noeof' else 1)
    def remaining():
        result=end-time.monotonic()
        if result<=0:raise UnsafeDestination('original deadline elapsed')
        return result
    try:
        if mode=='valid':assert _read_artifact_http_v1(active,'localhost','/invented-final',hashlib.sha256(BODY).hexdigest(),len(BODY),remaining)==BODY
        else:
            with pytest.raises((ValueError,OSError,ssl.SSLError)):_read_artifact_http_v1(active,'localhost','/invented-final','0'*64 if mode=='wronghash' else hashlib.sha256(BODY).hexdigest(),len(BODY),remaining)
        assert len(seen)==1
    finally:active.close();thread.join(2);assert not thread.is_alive()
def test_production_installed_artifact_refuses_private_dns_before_connect(certificates,monkeypatch):
    ca=certificates/'ca.pem';owner=_InstalledArtifactGET(url='https://installed-final.example.test/exact',expected_sha256=hashlib.sha256(BODY).hexdigest(),byte_count=len(BODY),ca_file=str(ca),ca_sha256=hashlib.sha256(ca.read_bytes()).hexdigest(),server_der_sha256='a'*64,current=lambda:None)
    monkeypatch.setattr(owner._resolver,'resolve',lambda _:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))])
    from oracle_brain.hosting._protected_control_listener_v1 import _request_fence_v1
    with _request_fence_v1(float(time.monotonic()+1)):
        with pytest.raises(ValueError):owner.fetch(caller_deadline=datetime.now(timezone.utc)+timedelta(seconds=1))
