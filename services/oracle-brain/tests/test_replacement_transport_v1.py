"""Actual local mTLS/framing only; no source or runtime admission is manufactured."""
import hashlib,http.client,ssl,threading,time,io
from http.server import BaseHTTPRequestHandler
from types import SimpleNamespace
from email.message import Message
import pytest
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from test_hosting_boundary import certificates,WORKER
from test_purpose_transport import bound_tls
from oracle_brain.hosting.gateway import MutualTLSServer
from oracle_brain.hosting.replacement_transport_v1 import fixed_request_length_v1,read_request_body_v1,peer_der_v1

@pytest.mark.parametrize('lengths,types,te,path',[(['1','1'],['application/json'],[], '/fixed'),
    (['1'],['application/json','application/json'],[], '/fixed'),(['1'],['application/json'],['chunked'],'/fixed'),
    (['0'],['application/json'],[],'/fixed'),(['4097'],['application/json'],[],'/fixed'),
    (['1'],['application/json'],[],'/other')])
def test_strict_private_framing_denies_ambiguous_or_unbounded_body(lengths,types,te,path):
    headers=Message()
    for value in lengths:headers['Content-Length']=value
    for value in types:headers['Content-Type']=value
    for value in te:headers['Transfer-Encoding']=value
    with pytest.raises(PermissionError):fixed_request_length_v1(SimpleNamespace(headers=headers,path=path,command='POST'),
        path='/fixed',content_type='application/json',maximum_bytes=4096)

def test_absolute_body_deadline_is_not_reset_between_chunks(monkeypatch):
    from oracle_brain.hosting import replacement_transport_v1 as m
    ticks=iter([1.,1.4,2.1]);seen=[]
    handler=SimpleNamespace(connection=SimpleNamespace(settimeout=seen.append),rfile=SimpleNamespace(read1=lambda n:b'x'))
    monkeypatch.setattr(m.time,'monotonic',lambda:next(ticks))
    with pytest.raises(PermissionError,match='original replacement body deadline'):
        read_request_body_v1(handler,3,absolute_monotonic_deadline=2.)
    assert seen==[1.,pytest.approx(.6)]
    for value in (float('inf'),float('nan'),True):
        with pytest.raises(PermissionError):read_request_body_v1(handler,1,absolute_monotonic_deadline=value)

def test_actual_mutual_tls_peer_fingerprint_uri_and_fixed_complete_body(bound_tls,certificates):
    tls,_=bound_tls
    worker=x509.load_pem_x509_certificate((certificates/'worker.pem').read_bytes()).public_bytes(Encoding.DER)
    expected=hashlib.sha256(worker).hexdigest();calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            try:
                peer_der_v1(self.connection,expected_uri=WORKER,expected_der_sha256=expected)
                size=fixed_request_length_v1(self,path='/fixed',content_type='application/json',maximum_bytes=4096)
                body=read_request_body_v1(self,size,absolute_monotonic_deadline=time.monotonic()+2)
                calls.append(body);status=200
            except Exception:status=403
            self.send_response(status);self.send_header('Content-Length','0');self.end_headers()
    server=MutualTLSServer(('127.0.0.1',0),Handler,tls=tls)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01});thread.start()
    def request(client):
        context=ssl.create_default_context(cafile=str(certificates/'ca.pem'))
        context.load_cert_chain(str(certificates/(client+'.pem')),str(certificates/(client+'.key')))
        connection=http.client.HTTPSConnection('localhost',server.server_port,context=context,timeout=2)
        try:
            connection.request('POST','/fixed',body=b'{}',headers={'Content-Type':'application/json'})
            response=connection.getresponse();response.read();return response.status
        finally:connection.close()
    try:
        assert request('worker')==200
        assert request('other')==403
        assert calls==[b'{}']
    finally:server.shutdown();server.server_close();thread.join(2)
