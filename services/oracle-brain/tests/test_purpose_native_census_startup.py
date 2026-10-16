"""Owned three-original native census startup. Fake key/wire; no public calls."""
import base64
from copy import deepcopy
import hashlib
import json
import threading
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4
import psycopg
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_native_factory import actual_ledger,KEY,FP,MODELS
from test_purpose_source_authority import purpose_population,context
from test_source_processing_qualification import processing
from test_purpose_transport import bound_tls,certificates,WORKER,SERVER
from test_parent_observer_v2 import provision
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.acceptance_profiles import OriginalScope,CensusContext,CensusPayload,request_for
from oracle_brain.operating_model.semantic_acceptance import SourceRegion
from oracle_brain.operating_model.coverage import Obligation
from oracle_brain.operating_model.source_receipts import EvidenceRef
from oracle_brain.operating_model.purpose_profiles_v2 import PurposePrivateContextV2
from oracle_brain.operating_model.purpose_context import (ParentPopulationAdmissionV2,PurposePhaseRegistryV2,PurposeRunDescriptorV2,
    PurposeDispatchV2,PurposeMetadataProjectionV2,PurposePinsV2,BudgetAllocationPinsV2,source_population_digest)
from oracle_brain.operating_model.native_factory import NativeDispatchJob
from oracle_brain.operating_model.native_provider import current_pricing
from oracle_brain.operating_model.key_coverage import KeyCoverageAdmission,KeyConsumer
from oracle_brain.provider_policy import ProcessingRequest,ProcessingApproval
from oracle_brain.hosting.parent_observer_v2 import ParentObserverAdmissionV2,ParentCurrentnessWitnessV2,DOMAIN
from oracle_brain.hosting.provider_runtime import CoverageWitness
from oracle_brain.hosting.gateway import MutualTLSServer,GatewayDenied
from oracle_brain.hosting.purpose_runtime import load_purpose_runtime_settings_v2,build_purpose_broker_v2
from oracle_brain.hosting.purpose_transport import purpose_ingress_server_v2,PurposeProviderClientV2

@pytest.fixture
def native_census_startup(admin_url,purpose_population,actual_ledger,bound_tls,tmp_path,monkeypatch):
    f=purpose_population('census','source-reader');source,_,_=context(f)
    receipts=source.read_population();now=datetime.now(timezone.utc);expiry=now+timedelta(seconds=90)
    ledger_url,registry,billing_admin=actual_ledger
    registry=registry.model_copy(update={'transport':'verify-full-tls'})
    ledger_hash=digest(registry.model_dump(mode='json'))
    catalog=deepcopy(MODELS)
    catalog['data'][0]['context_length']=131072
    catalog['data'][0]['top_provider']['context_length']=131072
    state={'posts':0,'after_post':None,'revoked':False,'sequence':1,'wire':None,'requests':[],'failure':None}
    regions=tuple(SourceRegion(region_id=f'original-{i}',kind='section',evidence=EvidenceRef(ref=r.ref,start=0,end=len(r.reading),quote=r.reading)) for i,r in enumerate(receipts))
    scope=OriginalScope(workspace_id=f['workspace'],receipts=receipts,regions=regions,
        source_region_register_hash=digest({'regions':[r.model_dump(mode='json') for r in regions]}))
    census=CensusContext(scope=scope,actor_id=f['actor'],runtime_hash=f['runtime'],permission_hash='c'*64,protocol_hash='d'*64,request_hash='e'*64)
    request=request_for(census);census=census.model_copy(update={'request_hash':digest(request)})
    processing_request=ProcessingRequest(provider='openrouter',account='key-sha256:'+FP,endpoint='https://openrouter.ai/api/v1',
        data_classes=frozenset({'synthetic'}),purpose='source-census',terms_hash='b'*64)
    approval=ProcessingApproval(**processing_request.model_dump(),expires_at=expiry,register_ref='invented-native-census-only')
    job=NativeDispatchJob(dispatch_id=uuid4(),workspace_id=f['workspace'],artifact_id=uuid4(),batch_id=uuid4(),purpose='source-census',attempt=1,
        request=request,request_hash=digest(request),permission_hash=census.permission_hash,processing_request=processing_request,approvals=(approval,),
        pricing=current_pricing(catalog,model=request['model'],max_output_tokens=request['max_tokens'],register_hash='d'*64,now=now),
        register_hash='d'*64,input_tokens_upper_bound=2*len(canonical_bytes(request))+4096)
    private=PurposePrivateContextV2(phase='census',job=job,census=census)
    coverage=KeyCoverageAdmission(domain='existing-owner-authorized-oracle-key',key_fingerprint=FP,provider_key_record_hash='4'*64,
        consumers=(KeyConsumer(consumer_id='invented-census',runtime_revision_hash=f['runtime'],mode='central-reservation',proof_hash='5'*64),),
        census_hash='6'*64,ledger_identity_hash=ledger_hash,external_liability_receipt_hash='7'*64,issuer_actor=uuid4(),reviewer_actor=uuid4(),
        observed_at=now,expires_at=expiry,census_complete=True,unreserved_paid_callers=0,unreserved_outstanding_liabilities=0)
    coverage_hash=digest(coverage.model_dump(mode='json'));policy=processing_request.model_dump(mode='json')
    allocation=BudgetAllocationPinsV2(original_batch_id=job.batch_id,allocation_hash='8'*64,original_receipt_hash='9'*64,original_ceiling_usd=Decimal('.25'),
        original_expires_at=expiry,ledger_registry_hash=ledger_hash,key_coverage_hash=coverage_hash,
        account_identity_hash=digest({k:policy[k] for k in ('provider','account','endpoint')}))
    dispatch=PurposeDispatchV2(dispatch_id=job.dispatch_id,source_refs=f['refs'],job_hash=digest(job.model_dump(mode='json')),request_hash=job.request_hash,
        permission_hash=job.permission_hash,context_hash=digest(private.model_dump(mode='json')),model=request['model'],processing_request_hash=digest(policy),
        account_policy_hash=digest({k:v for k,v in policy.items() if k!='terms_hash'}),account_identity_hash=allocation.account_identity_hash,terms_hash=policy['terms_hash'],
        pricing_hash=digest(job.pricing.model_dump(mode='json')),register_hash=job.register_hash,approvals_hash=digest({'approvals':[approval.model_dump(mode='json')]}),
        budget_identity_hash=digest(allocation.model_dump(mode='json')),ledger_registry_hash=ledger_hash,key_coverage_hash=coverage_hash)
    issuer,reviewer=uuid4(),uuid4()
    population=ParentPopulationAdmissionV2(workspace_id=f['workspace'],parent_registry_sha256='1'*64,runtime_hash=f['runtime'],source_registry_hash=f['registry'],
        source_refs=f['refs'],population_digest=source_population_digest(f['refs']),issuer_actor=issuer,reviewer_actor=reviewer,expires_at=expiry)
    phase=PurposePhaseRegistryV2(qualification_purpose='phase-operation-qualification-v2',run_id=uuid4(),workspace_id=f['workspace'],actor_id=f['actor'],provider_login=f['login'],worker_uri=WORKER,
        phase='census',purpose='source-census',operation='chat',runtime_hash=f['runtime'],source_registry_hash=f['registry'],parent_registry_sha256=population.parent_registry_sha256,
        population_admission_sha256=digest(population.model_dump(mode='json')),source_refs=f['refs'],population_digest=population.population_digest,
        dispatches=(dispatch,),issuer_actor=issuer,reviewer_actor=reviewer,expires_at=expiry)
    values=phase.model_dump(mode='python');values.pop('qualification_purpose');values['phase_registry_sha256']=digest(phase.model_dump(mode='json'))
    descriptor=PurposeRunDescriptorV2.model_validate(values)
    projection=PurposeMetadataProjectionV2(descriptor=descriptor,descriptor_sha256=digest(descriptor.model_dump(mode='json')))
    pins=PurposePinsV2(qualification_purpose='phase-operation-qualification-v2',phase='census',operation='chat',runtime_hash=f['runtime'],source_registry_hash=f['registry'],
        parent_registry_sha256=population.parent_registry_sha256,population_admission_sha256=descriptor.population_admission_sha256,phase_registry_sha256=descriptor.phase_registry_sha256,
        budget_allocation_projection_sha256=dispatch.budget_identity_hash,descriptor_sha256=projection.descriptor_sha256,projection_sha256=digest(projection.model_dump(mode='json')),
        provider_login=f['login'],worker_uri=WORKER,issuer_actor=issuer,reviewer_actor=reviewer,expires_at=expiry)
    payload=CensusPayload(obligations=tuple(Obligation(obligation_id=f'original-{i}',priority='essential',expected='represented',
        evidence=r.evidence,reason='Explicit invented role approval') for i,r in enumerate(regions))).model_dump_json()
    def store(name,value):
        path=tmp_path/name;raw=canonical_bytes(value.model_dump(mode='json')) if hasattr(value,'model_dump') else value
        path.write_bytes(raw);path.chmod(0o600);return str(path),hashlib.sha256(raw).hexdigest()
    tls,binding=bound_tls;servers=[];threads=[]
    def start(server):
        servers.append(server);thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);threads.append(thread);thread.start()
    class FakeOpenRouter(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,value):
            raw=canonical_bytes(value);self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            assert self.headers['Authorization']=='Bearer '+KEY
            if self.path=='/models':self.reply(catalog)
            elif self.path=='/key':self.reply({'data':{'usage_daily':0,'byok_usage_daily':0,'usage_monthly':0,'byok_usage_monthly':0,'limit':25,'limit_remaining':25,'is_free_tier':False}})
            else:raise AssertionError('unadmitted fake-provider operation')
        def do_POST(self):
            assert self.path=='/chat/completions' and self.headers['Authorization']=='Bearer '+KEY
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));state['requests'].append(body);state['posts']+=1
            packet=json.loads(body['messages'][1]['content']);assert set(packet)=={'purpose','originals','regions'}
            assert tuple(r['ref']['source_id'] for r in packet['originals'])==tuple(str(r.source_id) for r in f['refs'])
            if state['after_post']:state['after_post']()
            wire={'id':'invented-native-census','model':request['model'],'created':1,'private_wire_canary':'PRIVATE_NATIVE_WIRE',
                'choices':[{'finish_reason':'stop','message':{'content':payload}}],'usage':{'cost':'.00001','prompt_tokens':100,'completion_tokens':100}}
            state['wire']=canonical_bytes(wire);self.reply(wire)
    fake=ThreadingHTTPServer(('127.0.0.1',0),FakeOpenRouter);start(fake)
    import oracle_brain.operating_model.native_provider as native_module
    monkeypatch.setattr(native_module,'ENDPOINT','http://127.0.0.1:'+str(fake.server_port))
    signing=Ed25519PrivateKey.generate();public=signing.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    admission=ParentObserverAdmissionV2(purpose='complete-parent-currentness-v2',population=population,principal_id=f['actor'],observer_uri=SERVER,client_uri=WORKER,
        signing_public_key=public.hex(),signing_key_fingerprint=hashlib.sha256(public).hexdigest(),issuer_actor=uuid4(),reviewer_actor=uuid4(),minimum_sequence=1,max_age_seconds=5,expires_at=expiry)
    class Observer(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            assert self.path=='/v2/parent/current';incoming=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            state['sequence']+=1;clock=datetime.now(timezone.utc)
            witness=ParentCurrentnessWitnessV2(purpose='complete-parent-currentness-v2',admission_hash=digest(admission.model_dump(mode='json')),challenge=incoming['challenge'],
                sequence=state['sequence'],population=population,principal_id=f['actor'],observer_uri=SERVER,client_uri=WORKER,checked_at=clock,expires_at=clock+timedelta(seconds=4),revoked=state['revoked'])
            value=witness.model_dump(mode='json');raw=canonical_bytes({'witness':value,'signature':base64.b64encode(signing.sign(DOMAIN+canonical_bytes(value))).decode()})
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    observer=MutualTLSServer(('127.0.0.1',0),Observer,tls=tls);start(observer)
    try:
        spool=tmp_path/'observer-state';spool.mkdir();_,replay=provision(spool,admission)
        private_dir=tmp_path/'private-custody';private_dir.mkdir(mode=0o700)
        pins_file,pins_hash=store('pins.json',pins);population_file,_=store('population.json',population);projection_file,_=store('projection.json',projection)
        allocation_file,_=store('allocation.json',allocation);phase_file,_=store('phase.json',phase);context_file,_=store('private-census.json',private)
        source_url_file,_=store('source-url',f['url'].encode());ledger_url_file,_=store('ledger-url',ledger_url.encode());ledger_file,_=store('ledger.json',registry)
        key_file,_=store('provider-key',KEY.encode());coverage_file,_=store('coverage.json',coverage);observer_file,observer_hash=store('observer.json',admission)
        coverage_signing=Ed25519PrivateKey.generate();coverage_public=coverage_signing.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw).hex()
        witness=CoverageWitness(census_hash=coverage.census_hash,provider_key_record_hash=coverage.provider_key_record_hash,ledger_identity_hash=ledger_hash,
            external_liability_receipt_hash=coverage.external_liability_receipt_hash,observed_at=datetime.now(timezone.utc)).model_dump(mode='json')
        coverage_witness_file,_=store('coverage-witness.json',canonical_bytes({'witness':witness,'signature':base64.b64encode(coverage_signing.sign(canonical_bytes(witness))).decode()}))
        b=binding(443)
        config=dict(schema_version=2,phase='census',role='provider',worker_uri=WORKER,pins_file=pins_file,pins_sha256=pins_hash,population_file=population_file,
            projection_file=projection_file,budget_allocation_projection_file=allocation_file,source_url_file=source_url_file,expected_owner_role=f['binding'].expected_owner_role,
            expected_session_role=f['login'],source_expires_at=expiry.isoformat(),parent_observer_admission_file=observer_file,parent_observer_admission_hash=observer_hash,
            observer_timeout_seconds=5,observer_hostname='localhost',observer_port=observer.server_port,observer_server_uri=SERVER,observer_client_uri=WORKER,observer_ca=str(b.ca_file),
            observer_certificate=str(b.certificate_file),observer_key=str(b.key_file),observer_spool=str(spool),observer_namespace='parent-v2',observer_initialization_hash=replay['initialization_receipt_hash'],
            server_certificate=str(tmp_path/'server.pem'),server_key=str(tmp_path/'server.key'),client_ca=str(b.ca_file),bind_host='127.0.0.1',bind_port=9444,
            phase_registry_file=phase_file,private_context_files={str(job.dispatch_id):context_file},provider_key_file=key_file,ledger_url_file=ledger_url_file,
            ledger_registry_file=ledger_file,ledger_registry_hash=ledger_hash,coverage_admission_file=coverage_file,coverage_admission_hash=coverage_hash,
            coverage_witness_file=coverage_witness_file,coverage_observer_public_key=coverage_public,private_receipts=str(private_dir))
        config_file,config_hash=store('settings.json',canonical_bytes(config))
        settings=load_purpose_runtime_settings_v2(config_file,config_hash,expected_phase='census',expected_role='provider')
        ingress=build_purpose_broker_v2(settings)
        actual_dispatch=ingress.dispatch
        def observed_dispatch(*args):
            try:return actual_dispatch(*args)
            except Exception as error:
                state['failure']=type(error).__name__+': '+str(error)
                raise
        ingress.dispatch=observed_dispatch
        provider=purpose_ingress_server_v2(('127.0.0.1',0),tls=tls,worker_uri=WORKER,ingress=ingress);start(provider)
        yield dict(f=f,job=job,private=private,settings=settings,client=PurposeProviderClientV2(binding(provider.server_port)),dispatch=dispatch,
            descriptor=descriptor,state=state,custody=private_dir,billing_admin=billing_admin,context_file=context_file,pins_file=Path(pins_file),pins=pins)
    finally:
        for server,thread in zip(servers,threads):server.shutdown();server.server_close();thread.join(2)


def dispatch(x):return x['client'].dispatch(x['job'].dispatch_id,x['job'].request_hash,x['descriptor'].phase_registry_sha256)


def test_actual_native_census_full_private_wire_one_budget_and_metadata_reply(native_census_startup):
    x=native_census_startup
    try:reply=dispatch(x)
    except GatewayDenied:pytest.fail('actual native startup refused: '+str(x['state']['failure']))
    assert set(reply)=={'dispatch_id','request_hash','phase_registry_sha256','raw_response_hash','receipt_hash'}
    assert 'PRIVATE_NATIVE_WIRE' not in json.dumps(reply) and KEY not in json.dumps(reply)
    assert x['state']['posts']==1
    path=x['custody']/str(x['job'].dispatch_id)
    assert path.with_suffix('.wire').read_bytes()==x['state']['wire']
    committed=json.loads((x['custody']/(str(x['job'].dispatch_id)+'.phase-commit.json')).read_bytes())
    assert digest(committed)==reply['receipt_hash'] and committed['actual_caller_login']==x['f']['login']
    with psycopg.connect(x['billing_admin']) as conn:
        assert conn.execute('SELECT r.purpose,s.status,s.actual_usd FROM oracle2.operating_dispatch_reservations r JOIN oracle2.operating_dispatch_receipts s USING(reservation_id)').fetchall()==[('source-census','completed',Decimal('.00001'))]
    with pytest.raises(GatewayDenied):dispatch(x)
    assert x['state']['posts']==1


def test_actual_native_census_third_scope_revoked_before_private_context_or_post(admin_url,native_census_startup,monkeypatch):
    x=native_census_startup;seen=[]
    import oracle_brain.hosting.purpose_runtime as runtime
    original=runtime.protected_file
    def observed(path,**kwargs):
        if str(path)==x['context_file']:seen.append(path)
        return original(path,**kwargs)
    monkeypatch.setattr(runtime,'protected_file',observed)
    with psycopg.connect(admin_url) as conn:conn.execute('UPDATE oracle2.appointments SET revoked_at=now() WHERE appointment_id=%s',(x['f']['grants'][2],))
    with pytest.raises(GatewayDenied):dispatch(x)
    assert x['state']['posts']==0 and seen==[]
    with psycopg.connect(x['billing_admin']) as conn:assert conn.execute('SELECT count(*) FROM oracle2.operating_dispatch_reservations').fetchone()[0]==0


def test_actual_native_census_revoked_after_post_keeps_charge_and_raw_wire_no_commit(admin_url,native_census_startup):
    x=native_census_startup
    def revoke():
        with psycopg.connect(admin_url) as conn:conn.execute('UPDATE oracle2.appointments SET revoked_at=now() WHERE appointment_id=%s',(x['f']['grants'][2],))
    x['state']['after_post']=revoke
    with pytest.raises(GatewayDenied):dispatch(x)
    assert x['state']['posts']==1 and (x['custody']/(str(x['job'].dispatch_id)+'.wire')).read_bytes()==x['state']['wire']
    assert not (x['custody']/(str(x['job'].dispatch_id)+'.phase-commit.json')).exists()
    with psycopg.connect(x['billing_admin']) as conn:
        assert conn.execute('SELECT status,actual_usd FROM oracle2.operating_dispatch_receipts').fetchall()==[('failed',Decimal('.00001'))]
