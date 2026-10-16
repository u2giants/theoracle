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
        return PurposeTLSBindingV2('localhost',port,uri,WORKER if client=='worker' else 'spiffe://oracle/unrelated',certificates/'ca.pem',certificates/(client+'.pem'),certificates/(client+'.key'))
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


def test_fixed_phase_entrypoints_reuse_boundary_without_future_inputs():
    from pathlib import Path
    import yaml
    root=Path(__file__).resolve().parents[3]/'dev/oracle2/hosting'
    base=yaml.safe_load((root/'purpose-v2-boundary.yaml').read_text())['services']['purpose-boundary']
    assert base['profiles']==['definition-only-never-run']
    assert base['user']=='10001:10001' and base['read_only'] is True
    assert base['cap_drop']==['ALL'] and not base.get('ports')
    for phase in ('extraction','census','assembly','assessment','embedding'):
        value=yaml.safe_load((root/('purpose-v2-'+phase+'.yaml')).read_text())
        roles=('provider',) if phase=='embedding' else ('provider','metadata')
        assert set(value['services'])=={phase+'-'+r for r in roles}
        for name,service in value['services'].items():
            role=name.split('-')[1]
            assert service['extends']=={'file':'purpose-v2-boundary.yaml','service':'purpose-boundary'}
            assert service['command'][:4]==['--phase',phase,'--role',role]
            assert service['profiles']==['purpose-'+phase+'-admitted']
            assert service['networks']==[phase,'ledger']+([phase+'-outbound'] if role=='provider' else [])
            assert service['volumes']==[name+'-auth:/run/purpose-auth:ro',name+'-state:/run/purpose-state']+([phase+'-input:/run/purpose-input:ro'] if role=='provider' else [])
        assert value['networks']['ledger']['external'] is True
    assert not (root/'purpose-v2-isolated.yaml').exists()


def test_actual_installed_compose_each_phase_needs_only_own_hashes():
    import os,subprocess
    from pathlib import Path
    root=Path(__file__).resolve().parents[3]/'dev/oracle2/hosting'
    for phase in ('extraction','census','assembly','assessment','embedding'):
        roles=('provider',) if phase=='embedding' else ('provider','metadata')
        env={'PATH':os.defpath,'ORACLE_PURPOSE_IMAGE':'node@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20','ORACLE_PURPOSE_LEDGER_NETWORK':'invented-existing-ledger'}
        for role in roles:env['ORACLE_'+phase.upper()+'_'+role.upper()+'_SETTINGS_SHA256']='a'*64
        result=subprocess.run(['docker','compose','-f',str(root/('purpose-v2-'+phase+'.yaml')),'--profile','purpose-'+phase+'-admitted','config','--format','json'],env=env,capture_output=True,text=True,check=True,timeout=10)
        value=json.loads(result.stdout)
        assert set(value['services'])=={phase+'-'+r for r in roles}
        for service in value['services'].values():
            assert service['user']=='10001:10001' and service['read_only'] is True
            assert not service.get('ports') and not service.get('privileged')


def test_cli_requires_fixed_phase_role_and_seal_before_authority_load():
    from oracle_brain.hosting.purpose_transport import main
    with pytest.raises(SystemExit) as result:main([])
    assert result.value.code==2


def test_client_certificate_must_match_own_external_uri_pin(bound_tls):
    import dataclasses
    _,binding=bound_tls
    with pytest.raises(GatewayDenied):
        dataclasses.replace(binding(443),client_uri='spiffe://oracle/wrong-caller')


def test_actual_extraction_endpoint_cross_route_domain_and_retained_parser(bound_tls):
    import http.client
    from oracle_brain.hosting.purpose_transport import (ExtractionProviderClientV2,
        extraction_ingress_server_v2,purpose_ingress_server_v2)
    tls,binding=bound_tls
    class Ingress:
        calls=0
        def dispatch(self,peer,request):
            assert peer==WORKER
            self.calls+=1
            return {**request,'raw_response_hash':'c'*64,'receipt_hash':'d'*64}
    extraction,purpose=Ingress(),Ingress()
    servers=[extraction_ingress_server_v2(('127.0.0.1',0),tls=tls,worker_uri=WORKER,ingress=extraction),
             purpose_ingress_server_v2(('127.0.0.1',0),tls=tls,worker_uri=WORKER,ingress=purpose)]
    threads=[]
    for server in servers:
        thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start();threads.append(thread)
    client=ExtractionProviderClientV2(binding(servers[0].server_port))
    request={'dispatch_id':str(uuid4()),'request_hash':'a'*64,'extraction_qualification_sha256':'b'*64}
    raw=json.dumps(request).encode()
    def post(server,path,*,lengths=None,transfer=False,body=raw):
        conn=http.client.HTTPSConnection('localhost',server.server_port,context=client._tls,timeout=2)
        try:
            conn.putrequest('POST',path)
            conn.putheader('Content-Type','application/json')
            for length in lengths or [str(len(body))]:conn.putheader('Content-Length',length)
            if transfer:conn.putheader('Transfer-Encoding','chunked')
            conn.endheaders(body)
            response=conn.getresponse();response.read();return response.status
        finally:conn.close()
    try:
        assert client.dispatch(uuid4(),'a'*64,'b'*64)['extraction_qualification_sha256']=='b'*64
        assert extraction.calls==1
        # Identical authenticated bytes cannot cross the old/purpose domain.
        assert post(servers[1],'/v1/provider/chat')==403 and purpose.calls==0
        for path in ('/v1/provider/chat','/v2/extraction/chat/','/v2/extraction/chat?phase=census','/v2/extraction%2fchat'):
            assert post(servers[0],path)==404
        assert post(servers[0],'/v2/extraction/chat',lengths=['1','2'])==400
        assert post(servers[0],'/v2/extraction/chat',transfer=True)==400
        assert post(servers[0],'/v2/extraction/chat',lengths=['2000001'])==413
        assert post(servers[0],'/v2/extraction/chat',body=raw[:-1]+b',"request_hash":"'+b'a'*64+b'"}')==403
        assert extraction.calls==1
    finally:
        for server,thread in zip(servers,threads):server.shutdown();server.server_close();thread.join(2)


def test_actual_provider_response_can_exceed_observer_five_second_limit(bound_tls):
    import dataclasses,time
    from datetime import datetime,timedelta,timezone
    tls,binding=bound_tls
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            # Deliberately exceed the observer's fixed five-second TOTAL bound.
            threading.Event().wait(5.05)
            raw=json.dumps({**request,'raw_response_hash':'c'*64,'receipt_hash':'d'*64}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    server=MutualTLSServer(('127.0.0.1',0),Handler,tls=tls)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    try:
        pinned=dataclasses.replace(binding(server.server_port),timeout=90)
        with pytest.raises(GatewayDenied):ParentObserverClientV2(pinned)
        client=PurposeProviderClientV2(pinned)
        result=client.dispatch(uuid4(),'a'*64,'b'*64,deadline=datetime.now(timezone.utc)+timedelta(seconds=10))
        assert result['receipt_hash']=='d'*64
        with pytest.raises(GatewayDenied):client.dispatch(uuid4(),'a'*64,'b'*64,deadline=datetime.now(timezone.utc)-timedelta(seconds=1))
        with pytest.raises(GatewayDenied):dataclasses.replace(pinned,timeout=91)
    finally:server.shutdown();server.server_close();thread.join(2)


def test_unknown_phase_refuses_before_config_or_authority_load():
    from oracle_brain.hosting.purpose_transport import main
    with pytest.raises(SystemExit) as result:
        main(['--phase','unknown','--role','provider','--config','/never/open','--config-sha256','a'*64])
    assert result.value.code==2
