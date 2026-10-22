"""Explicit owned TLS adapter proof; production public-DNS guard is unchanged.

No real publisher is contacted. Factory composition uses this separately owned
adapter only in tests, never an installed research transport qualification.
"""
import hashlib,socket,ssl,threading,time
from datetime import datetime,timedelta,timezone
import pytest
from test_hosting_boundary import certificates
from oracle_brain.research.fetch import _read_verified_public_http_v1,_InstalledResearchGET,ResearchTransportUnknown,UnsafeDestination

BODY=b'Invented industry reference; applicability remains unreviewed.'

def owned_wire(certificates,mode='valid'):
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1)
    port=listener.getsockname()[1];seen=[]
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(certificates/'server.pem',certificates/'server.key')
    def serve():
        try:
            raw,_=listener.accept()
            with context.wrap_socket(raw,server_side=True) as peer:
                request=b''
                while b'\r\n\r\n' not in request:request+=peer.recv(1024)
                assert len(request)<4096 and request.startswith(b'GET /reference HTTP/1.1\r\n')
                assert b'Authorization:' not in request and b'Cookie:' not in request
                seen.append(request)
                status=b'302 Found' if mode=='redirect' else b'404 Not Found' if mode=='missing' else b'200 OK'
                if mode in ('chunked','trailer','hugechunk'):
                    payload=BODY if mode!='hugechunk' else b'x'*1025
                    body=f'{len(payload):x}\r\n'.encode()+payload+b'\r\n0\r\n'+(b'Unwanted: trailer\r\n' if mode=='trailer' else b'')+b'\r\n'
                    header=b'Transfer-Encoding: chunked\r\n'
                else:
                    header=f'Content-Length: {len(BODY)}\r\n'.encode();body=BODY[:-1] if mode=='truncated' else BODY
                if mode=='redirect':header+=b'Location: https://industry.example.test/next\r\n'
                if mode=='duplicate':header+=f'content-length: {len(BODY)}\r\n'.encode()
                if mode=='largeheader':header+=b'X-Long: '+b'x'*16384+b'\r\n'
                response=b'HTTP/1.1 '+status+b'\r\n'+header+b'Connection: close\r\n\r\n'+body
                peer.sendall(response)
                if mode=='extra':time.sleep(.02);peer.sendall(b'EXTRA')
                if mode=='noeof':time.sleep(.3)
                try:peer.unwrap()
                except (OSError,ssl.SSLError):pass
        except (OSError,ssl.SSLError):pass
        finally:listener.close()
    thread=threading.Thread(target=serve);thread.start()
    client=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);client.load_verify_locations(cafile=certificates/'ca.pem')
    peer=client.wrap_socket(socket.create_connection(('127.0.0.1',port),timeout=1),server_hostname='localhost',suppress_ragged_eofs=False)
    return peer,thread,seen

def read_owned(certificates,mode='valid'):
    peer,thread,seen=owned_wire(certificates,mode);end=time.monotonic()+(.1 if mode=='noeof' else 1)
    def remaining():
        value=end-time.monotonic()
        if value<=0:raise UnsafeDestination('original wire budget elapsed')
        return value
    try:return _read_verified_public_http_v1(peer,'localhost','/reference',1024,remaining,allow_chunked=True)
    finally:
        peer.close();thread.join(2);assert not thread.is_alive() and len(seen)==1

@pytest.mark.parametrize('mode',['valid','chunked','missing'])
def test_actual_owned_tls_research_body_and_original_wire_retained(certificates,mode):
    response=read_owned(certificates,mode)
    assert response.body==BODY and response.wire.startswith(b'HTTP/1.1 ') and response.wire.endswith(BODY if mode!='chunked' else b'0\r\n\r\n')
    assert response.status==(404 if mode=='missing' else 200)
    assert ('transfer-encoding','chunked') in response.headers if mode=='chunked' else ('content-length',str(len(BODY))) in response.headers

@pytest.mark.parametrize('mode',['extra','noeof','truncated','duplicate','largeheader','trailer','hugechunk'])
def test_actual_wire_failures_keep_bounded_observed_prefix_and_refuse_success(certificates,mode):
    with pytest.raises(ResearchTransportUnknown) as error:read_owned(certificates,mode)
    assert error.value.wire.startswith(b'HTTP/1.1 ') and len(error.value.wire)<=1064960
    assert b'Authorization:' not in error.value.wire

def test_registered_research_all_dns_answers_must_be_public_before_connect(certificates,monkeypatch):
    from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
    from oracle_brain.hosting.purpose_transport import _BoundedDNSResolver
    ca=certificates/'ca.pem';owner=_InstalledResearchGET(url='https://industry.example.test/reference',ca_file=str(ca),ca_sha256=hashlib.sha256(ca.read_bytes()).hexdigest(),current=lambda:None)
    monkeypatch.setattr(_BoundedDNSResolver,'resolve',lambda *_:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))])
    def forbidden(*args,**kwargs):raise AssertionError('private resolved destination cannot open a socket')
    monkeypatch.setattr(socket,'socket',forbidden)
    with _request_fence_v1(float(time.monotonic()+2)):
        with pytest.raises(ResearchTransportUnknown):owner.fetch(caller_deadline=datetime.now(timezone.utc)+timedelta(seconds=2))


def test_research_fixed_destination_length_refused_before_any_dns_or_connect(certificates):
    ca=certificates/'ca.pem'
    with pytest.raises(UnsafeDestination):
        _InstalledResearchGET(url='https://industry.example.test/'+('x'*2048),ca_file=str(ca),ca_sha256=hashlib.sha256(ca.read_bytes()).hexdigest(),current=lambda:None)
