"""Actual invented mTLS transport, without external provider/admission."""
import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler
from uuid import uuid4
import pytest
from test_hosting_boundary import certificates, WORKER
from oracle_brain.hosting.gateway import GatewayDenied, MutualTLSServer, server_tls
from oracle_brain.hosting.egress import EgressServer
from oracle_brain.hosting.purpose_transport import ParentObserverClientV2, PurposeProviderClientV2, PurposeTLSBindingV2, PurposeIngressBridgeV2
SERVER='spiffe://oracle/purpose/invented-provider'
@pytest.fixture
def bound_tls(certificates,tmp_path):
    def run(*args): subprocess.run(['openssl',*args],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    key,csr,cert=[tmp_path/x for x in ('server.key','server.csr','server.pem')]
    run('req','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(csr),'-subj','/CN=localhost')
    ext=tmp_path/'server.ext';ext.write_text('subjectAltName=DNS:localhost,URI:'+SERVER+'\nextendedKeyUsage=serverAuth\nbasicConstraints=critical,CA:FALSE\n')
    run('x509','-req','-in',str(csr),'-CA',str(certificates/'ca.pem'),'-CAkey',str(certificates/'ca.key'),'-CAcreateserial','-out',str(cert),'-days','1','-extfile',str(ext))
    for p in tmp_path.iterdir():p.chmod(0o600)
    tls=server_tls(certfile=str(cert),keyfile=str(key),cafile=str(certificates/'ca.pem'))
    def binding(port,client='worker',uri=SERVER):
        return PurposeTLSBindingV2('localhost',port,uri,certificates/'ca.pem',certificates/(client+'.pem'),certificates/(client+'.key'))
    return tls,binding

def test_actual_provider_tls_and_private_response_denial(bound_tls,monkeypatch):
    tls,binding=bound_tls
    class Ingress:
        calls=0;leak=False
        def dispatch(self,peer,request):
            assert peer==WORKER
            self.calls+=1
            return {**request,'raw_response_hash':'c'*64,'receipt_hash':'d'*64,**({'reading':'PRIVATE'} if self.leak else {})}
    ingress=Ingress();server=EgressServer(('127.0.0.1',0),tls=tls,executor_uri=WORKER,egress=PurposeIngressBridgeV2(ingress,WORKER))
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    try:
        monkeypatch.setenv('HTTPS_PROXY','http://127.0.0.1:1')
        client=PurposeProviderClientV2(binding(server.server_port))
        assert set(client.dispatch(uuid4(),'a'*64,'b'*64))=={'dispatch_id','request_hash','phase_registry_sha256','raw_response_hash','receipt_hash'}
        with pytest.raises(GatewayDenied):PurposeProviderClientV2(binding(server.server_port,client='other')).dispatch(uuid4(),'a'*64,'b'*64)
        with pytest.raises(GatewayDenied):PurposeProviderClientV2(binding(server.server_port,uri='spiffe://oracle/wrong')).dispatch(uuid4(),'a'*64,'b'*64)
        assert ingress.calls==1
        ingress.leak=True
        with pytest.raises(GatewayDenied):client.dispatch(uuid4(),'a'*64,'b'*64)
    finally:server.shutdown();server.server_close();thread.join(2)

def test_actual_observer_tls_fixed_envelope(bound_tls):
    tls,binding=bound_tls;seen=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            seen.append((self.path,json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            raw=b'{"witness":{},"signature":"invented"}'
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    server=MutualTLSServer(('127.0.0.1',0),Handler,tls=tls)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    try:
        client=ParentObserverClientV2(binding(server.server_port))
        assert json.loads(client.fetch_current('a'*64))=={'witness':{},'signature':'invented'}
        assert seen==[('/v2/parent/current',{'schema_version':2,'purpose':'complete-parent-currentness-v2','challenge':'a'*64})]
        with pytest.raises(GatewayDenied):client.current('A'*64)
        assert len(seen)==1
    finally:server.shutdown();server.server_close();thread.join(2)

@pytest.mark.parametrize('raw',[b'{}',b'{"phase":"census"}',b'{"dispatch_id":"x","request_hash":"a","phase_registry_sha256":"b"}'])
def test_invalid_request_never_reaches_ingress(raw):
    class Ingress:
        def dispatch(self,*args):pytest.fail('unauthorized ingress called')
    with pytest.raises(GatewayDenied):PurposeIngressBridgeV2(Ingress(),WORKER).dispatch(raw)

@pytest.mark.parametrize('case',['redirect','chunked','oversized','private','mismatched','duplicate'])
def test_actual_tls_response_refusals(bound_tls,case):
    tls,binding=bound_tls
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            value={**request,'raw_response_hash':'c'*64,'receipt_hash':'d'*64}
            if case=='private':value['raw_response']='PRIVATE'
            if case=='mismatched':value['request_hash']='f'*64
            raw=json.dumps(value).encode()
            if case=='duplicate':raw=raw[:-1]+b',"receipt_hash":"'+b'd'*64+b'"}'
            self.send_response(302 if case=='redirect' else 200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length','4097' if case=='oversized' else str(len(raw)))
            if case=='chunked':self.send_header('Transfer-Encoding','chunked')
            if case=='redirect':self.send_header('Location','http://127.0.0.1:1')
            self.end_headers()
            try:self.wfile.write(raw)
            except (BrokenPipeError,ConnectionResetError):pass
    server=MutualTLSServer(('127.0.0.1',0),Handler,tls=tls)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    try:
        with pytest.raises(GatewayDenied):PurposeProviderClientV2(binding(server.server_port)).dispatch(uuid4(),'a'*64,'b'*64)
    finally:server.shutdown();server.server_close();thread.join(2)

def test_actual_total_deadline_aborts_trickled_header(bound_tls):
    import dataclasses
    import http.client
    import time
    tls,binding=bound_tls
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            try:
                self.wfile.write(b'HTTP/1.0 200 OK\r\nX-Trickle: ');self.wfile.flush()
                for _ in range(20):
                    self.wfile.write(b'a');self.wfile.flush();time.sleep(.02)
            except (OSError,ValueError):pass
    server=MutualTLSServer(('127.0.0.1',0),Handler,tls=tls)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    try:
        client=PurposeProviderClientV2(dataclasses.replace(binding(server.server_port),timeout=.1))
        started=time.monotonic()
        with pytest.raises((GatewayDenied,OSError,http.client.HTTPException)):
            client.dispatch(uuid4(),'a'*64,'b'*64)
        assert time.monotonic()-started<.35
    finally:server.shutdown();server.server_close();thread.join(2)
