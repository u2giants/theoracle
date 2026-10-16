"""Actual protected metadata startup + owned SQL/mTLS, not native paid dispatch."""
import base64
import hashlib
import json
import threading
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from test_purpose_source_authority import purpose_population,context
from test_source_processing_qualification import processing
from test_purpose_transport import bound_tls,certificates,WORKER,SERVER
from test_parent_observer_v2 import provision
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.purpose_context import ParentPopulationAdmissionV2,PurposeMetadataProjectionV2,PurposePinsV2
from oracle_brain.hosting.parent_observer_v2 import ParentObserverAdmissionV2,ParentCurrentnessWitnessV2,DOMAIN
from oracle_brain.hosting.purpose_runtime import load_purpose_runtime_settings_v2,build_purpose_metadata_v2
from oracle_brain.hosting.purpose_transport import purpose_ingress_server_v2,PurposeProviderClientV2
from oracle_brain.hosting.gateway import MutualTLSServer
from http.server import BaseHTTPRequestHandler

@pytest.fixture
def actual_metadata_startup(admin_url,purpose_population,bound_tls,tmp_path):
    f=purpose_population('census','gateway-metadata');_,descriptor,dispatch=context(f,caller_kind='gateway')
    descriptor=descriptor.model_copy(update={'worker_uri':WORKER})
    now=datetime.now(timezone.utc)
    population=ParentPopulationAdmissionV2(workspace_id=f['workspace'],parent_registry_sha256=descriptor.parent_registry_sha256,
        runtime_hash=f['runtime'],source_registry_hash=f['registry'],source_refs=f['refs'],population_digest=descriptor.population_digest,
        issuer_actor=uuid4(),reviewer_actor=uuid4(),expires_at=f['expiry'])
    descriptor=descriptor.model_copy(update={'population_admission_sha256':digest(population.model_dump(mode='json'))})
    projection=PurposeMetadataProjectionV2(descriptor=descriptor,descriptor_sha256=digest(descriptor.model_dump(mode='json')))
    pins=PurposePinsV2(qualification_purpose='phase-operation-qualification-v2',phase='census',operation='chat',
        runtime_hash=f['runtime'],source_registry_hash=f['registry'],parent_registry_sha256=descriptor.parent_registry_sha256,
        population_admission_sha256=digest(population.model_dump(mode='json')),phase_registry_sha256=descriptor.phase_registry_sha256,
        budget_allocation_projection_sha256=dispatch.budget_identity_hash,descriptor_sha256=projection.descriptor_sha256,
        projection_sha256=digest(projection.model_dump(mode='json')),provider_login=descriptor.provider_login,worker_uri=WORKER,
        issuer_actor=descriptor.issuer_actor,reviewer_actor=descriptor.reviewer_actor,expires_at=f['expiry'])
    def store(name,value):
        path=tmp_path/name;raw=canonical_bytes(value.model_dump(mode='json')) if hasattr(value,'model_dump') else value
        path.write_bytes(raw);path.chmod(0o600);return str(path),hashlib.sha256(raw).hexdigest()
    key=Ed25519PrivateKey.generate();public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    admission=ParentObserverAdmissionV2(purpose='complete-parent-currentness-v2',population=population,principal_id=f['actor'],
        observer_uri=SERVER,client_uri=WORKER,signing_public_key=public.hex(),signing_key_fingerprint=hashlib.sha256(public).hexdigest(),
        issuer_actor=uuid4(),reviewer_actor=uuid4(),minimum_sequence=1,max_age_seconds=5,expires_at=f['expiry'])
    tls,binding=bound_tls;servers=[];threads=[];state={'sequence':1,'revoked':False,'provider_calls':0,'after_provider':None}
    class Observer(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            assert self.path=='/v2/parent/current'
            request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert set(request)=={'schema_version','purpose','challenge'}
            state['sequence']+=1;clock=datetime.now(timezone.utc)
            witness=ParentCurrentnessWitnessV2(purpose='complete-parent-currentness-v2',admission_hash=digest(admission.model_dump(mode='json')),
                challenge=request['challenge'],sequence=state['sequence'],population=population,principal_id=f['actor'],observer_uri=SERVER,
                client_uri=WORKER,checked_at=clock,expires_at=clock+timedelta(seconds=4),revoked=state['revoked'])
            value=witness.model_dump(mode='json');raw=canonical_bytes({'witness':value,'signature':base64.b64encode(key.sign(DOMAIN+canonical_bytes(value))).decode()})
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    class ProviderFixture:
        def dispatch(self,peer,request):
            assert peer==WORKER;state['provider_calls']+=1
            if state['after_provider']:state['after_provider']()
            return {**request,'raw_response_hash':'c'*64,'receipt_hash':'d'*64}
    observer=MutualTLSServer(('127.0.0.1',0),Observer,tls=tls)
    provider=purpose_ingress_server_v2(('127.0.0.1',0),tls=tls,worker_uri=WORKER,ingress=ProviderFixture())
    def start(server):
        servers.append(server);thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);threads.append(thread);thread.start()
    start(observer);start(provider)
    try:
        spool=tmp_path/'observer-state';spool.mkdir();_,replay=provision(spool,admission)
        pins_file,pins_hash=store('pins.json',pins);pop_file,_=store('population.json',population);projection_file,_=store('projection.json',projection)
        observer_file,observer_hash=store('observer.json',admission);url_file,_=store('source-url',f['url'].encode())
        b=binding(provider.server_port)
        import socket
        with socket.socket() as reserved:
            reserved.bind(('127.0.0.1',0));metadata_port=reserved.getsockname()[1]
        config=dict(schema_version=2,phase='census',role='metadata',worker_uri=WORKER,pins_file=pins_file,pins_sha256=pins_hash,
            population_file=pop_file,projection_file=projection_file,source_url_file=url_file,expected_owner_role=f['binding'].expected_owner_role,
            expected_session_role=f['login'],source_expires_at=f['expiry'].isoformat(),parent_observer_admission_file=observer_file,parent_observer_admission_hash=observer_hash,
            observer_hostname='localhost',observer_port=observer.server_port,observer_server_uri=SERVER,observer_client_uri=WORKER,
            observer_ca=str(b.ca_file),observer_certificate=str(b.certificate_file),observer_key=str(b.key_file),observer_spool=str(spool),
            observer_namespace='parent-v2',observer_initialization_hash=replay['initialization_receipt_hash'],server_certificate=str(tmp_path/'server.pem'),
            server_key=str(tmp_path/'server.key'),client_ca=str(b.ca_file),bind_host='127.0.0.1',bind_port=metadata_port,
            provider_hostname='localhost',provider_port=provider.server_port,provider_server_uri=SERVER,provider_client_uri=WORKER,
            provider_ca=str(b.ca_file),provider_certificate=str(b.certificate_file),provider_key=str(b.key_file))
        config_file,config_hash=store('settings.json',canonical_bytes(config))
        settings=load_purpose_runtime_settings_v2(config_file,config_hash,expected_phase='census',expected_role='metadata')
        ingress=build_purpose_metadata_v2(settings)
        yield dict(f=f,settings=settings,ingress=ingress,state=state,pins=pins,pins_file=Path(pins_file),config_file=config_file,config_hash=config_hash,binding=binding,request={
            'dispatch_id':str(dispatch.dispatch_id),'request_hash':dispatch.request_hash,'phase_registry_sha256':descriptor.phase_registry_sha256})
    finally:
        for server,thread in zip(servers,threads):server.shutdown();server.server_close();thread.join(2)


def test_actual_protected_metadata_factory_sql_and_mtls_receipt_only(actual_metadata_startup):
    x=actual_metadata_startup
    result=x['ingress'].dispatch(WORKER,x['request'])
    assert set(result)==set(x['request'])|{'raw_response_hash','receipt_hash'}
    assert x['state']['provider_calls']==1 and x['state']['sequence']==3
    with pytest.raises(PermissionError):x['ingress'].jobs.context(uuid4())


def test_actual_startup_current_third_source_revocation_blocks_before_forward(admin_url,actual_metadata_startup):
    x=actual_metadata_startup;f=x['f']
    with psycopg.connect(admin_url) as conn:conn.execute('UPDATE oracle2.appointments SET revoked_at=now() WHERE appointment_id=%s',(f['grants'][2],))
    with pytest.raises((PermissionError,psycopg.errors.InsufficientPrivilege)):x['ingress'].dispatch(WORKER,x['request'])
    assert x['state']['provider_calls']==0


def test_actual_startup_current_parent_witness_revocation_blocks_before_forward(actual_metadata_startup):
    x=actual_metadata_startup;x['state']['revoked']=True
    with pytest.raises(PermissionError):x['ingress'].dispatch(WORKER,x['request'])
    assert x['state']['provider_calls']==0


def test_actual_startup_after_post_revocation_discards_metadata_result(admin_url,actual_metadata_startup):
    x=actual_metadata_startup;f=x['f']
    def revoke():
        with psycopg.connect(admin_url) as conn:conn.execute('UPDATE oracle2.appointments SET revoked_at=now() WHERE appointment_id=%s',(f['grants'][2],))
    x['state']['after_provider']=revoke
    with pytest.raises((PermissionError,psycopg.errors.InsufficientPrivilege)):x['ingress'].dispatch(WORKER,x['request'])
    assert x['state']['provider_calls']==1


def test_actual_fixed_metadata_cli_process_uses_protected_files_and_mtls(actual_metadata_startup,tmp_path):
    import os,socket,subprocess,sys,time
    x=actual_metadata_startup;settings=x['settings']
    output=tmp_path/'metadata-cli.log';output.touch(mode=0o600)
    with output.open('wb') as stream:
        child=subprocess.Popen([sys.executable,'-m','oracle_brain.hosting.purpose_transport',
            '--phase','census','--role','metadata','--config',x['config_file'],
            '--config-sha256',x['config_hash']],stdout=stream,stderr=subprocess.STDOUT,
            env={'PATH':os.defpath,'LANG':'C.UTF-8','PYTHONNOUSERSITE':'1'})
        try:
            deadline=time.monotonic()+5
            while True:
                if child.poll() is not None:pytest.fail('owned metadata CLI exited before readiness')
                try:
                    with socket.create_connection((settings.bind_host,settings.bind_port),timeout=.1):break
                except OSError:
                    if time.monotonic()>=deadline:pytest.fail('owned metadata CLI readiness deadline')
                    time.sleep(.01)
            client=PurposeProviderClientV2(x['binding'](settings.bind_port))
            result=client.dispatch(__import__('uuid').UUID(x['request']['dispatch_id']),x['request']['request_hash'],x['request']['phase_registry_sha256'])
            assert set(result)==set(x['request'])|{'raw_response_hash','receipt_hash'}
            assert x['state']['provider_calls']==1
        finally:
            child.terminate()
            try:child.wait(timeout=3)
            except subprocess.TimeoutExpired:child.kill();child.wait(timeout=3)
    assert 'PRIVATE' not in output.read_text()
