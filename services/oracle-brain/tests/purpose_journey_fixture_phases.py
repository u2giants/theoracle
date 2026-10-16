"""Late, independently appointed synthetic phase input provisioning.

Uses the one existing fake provider, account ledger and TLS server collection.
Nothing here is production issuance or an authority callback accepted over HTTP.
"""
import base64,hashlib,json
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from uuid import uuid4
import psycopg
from psycopg import sql
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.authority_adapter import ProcessingSourceBinding
from oracle_brain.operating_model.purpose_context import ParentPopulationAdmissionV2
from oracle_brain.operating_model.processing_context import (
    QualifiedProcessingSources,ProcessingEnvelope,ProcessingPins,ProcessingProjection,derive_processing_descriptor)
from oracle_brain.hosting.parent_observer_v2 import ParentObserverAdmissionV2,ParentCurrentnessWitnessV2,DOMAIN
from oracle_brain.hosting.gateway import MutualTLSServer
from oracle_brain.hosting.processing_extraction_runtime_v2 import (
    ExtractionTargetV2,ExtractionOperationQualificationV2,load_extraction_runtime_settings_v2,build_extraction_broker_v2)
from oracle_brain.hosting.purpose_transport import extraction_ingress_server_v2,ExtractionProviderClientV2
from test_parent_observer_v2 import provision
from test_purpose_transport import WORKER,SERVER
from purpose_journey_fixture_models import extraction_json


def admit_extraction_phase(x,*,admin_url,root,census_row):
    """Invoke ONLY after the actual worker's authorized census journal row."""
    assert census_row['state']=='awaiting-external-phase-admission'
    assert x['state']['posts']==1 and x['input_parent'] is not None
    p=x['platform'];original=x['f'];parent=x['input_parent'];end=min(x['expires_at'],*(c.job.pricing.expires_at for c in parent.contexts));now=datetime.now(timezone.utc)
    assert now<end
    root.mkdir(mode=0o700)
    def store(name,value):
        raw=canonical_bytes(value.model_dump(mode='json')) if hasattr(value,'model_dump') else value
        path=root/name;path.write_bytes(raw);path.chmod(0o600)
        return str(path),hashlib.sha256(raw).hexdigest()
    actor=x['input_actor'];runtime=x['input_runtime'];login='coherent_extractor_'+uuid4().hex[:10]
    with psycopg.connect(admin_url) as conn:
        owner=conn.execute('SELECT actor_id FROM oracle2.appointments WHERE appointment_id=%s',(original['root'],)).fetchone()[0]
        conn.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(login),sql.Literal('invented-coherent-only')))
        conn.execute(sql.SQL('GRANT oracle2_source_reader TO {}').format(sql.Identifier(login)))
        conn.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',(login,runtime,original['registry'],end))
        for ref in original['refs']:
            conn.execute('INSERT INTO oracle2.hosting_role_source_admissions VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (login,ref.workspace_id,ref.source_id,ref.revision,actor,ref.original_sha256,ref.reading_sha256,ref.parser_id,runtime,original['registry'],end))
            for purpose in ('source-read','source-extraction'):
                conn.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                    (uuid4(),ref.workspace_id,actor,purpose+':'+str(ref.source_id),owner,original['root'],end))
    url=psycopg.conninfo.make_conninfo(admin_url,user=login,password='invented-coherent-only')
    refs=original['refs'];issuer,reviewer=parent.issuer_actor,parent.reviewer_actor
    parent_hash=digest(parent.model_dump(mode='json'));allocation=p['allocation']
    population=ParentPopulationAdmissionV2(workspace_id=original['workspace'],parent_registry_sha256=parent_hash,runtime_hash=runtime,
        source_registry_hash=original['registry'],source_refs=refs,population_digest=x['population'].population_digest,
        issuer_actor=issuer,reviewer_actor=reviewer,expires_at=x['population'].expires_at)
    qualified=QualifiedProcessingSources(workspace_id=original['workspace'],actor_id=actor,runtime_hash=runtime,source_registry_hash=original['registry'],
        expected_owner_role=original['binding'].expected_owner_role,source_refs=refs,issuer_actor=issuer,reviewer_actor=reviewer,expires_at=end)
    envelope=ProcessingEnvelope(run_id=uuid4(),worker_uri=WORKER,runtime_hash=runtime,source_registry_hash=original['registry'],parent_registry_sha256=parent_hash,
        ledger_registry_hash=p['ledger_hash'],key_coverage_hash=p['coverage_hash'],budget_allocation_hash=allocation.allocation_hash,
        budget_receipt_hash=allocation.original_receipt_hash,budget_ceiling_usd=allocation.original_ceiling_usd,budget_expires_at=allocation.original_expires_at,
        dispatch_ids=tuple(c.job.dispatch_id for c in parent.contexts),source_refs=refs,issuer_actor=issuer,reviewer_actor=reviewer,expires_at=end)
    pins=ProcessingPins(runtime_hash=runtime,worker_uri=WORKER,source_registry_hash=original['registry'],expected_owner_role=qualified.expected_owner_role,
        parent_registry_sha256=parent_hash,envelope_sha256=digest(envelope.model_dump(mode='json')),qualification_sha256=digest(qualified.model_dump(mode='json')),
        descriptor_sha256='0'*64,projection_sha256='0'*64,ledger_registry_hash=p['ledger_hash'],key_coverage_hash=p['coverage_hash'])
    descriptor=derive_processing_descriptor(parent,envelope,qualified,pins=pins,now=now)
    projection=ProcessingProjection(descriptor=descriptor,descriptor_sha256=digest(descriptor.model_dump(mode='json')))
    pins=pins.model_copy(update={'descriptor_sha256':projection.descriptor_sha256,'projection_sha256':digest(projection.model_dump(mode='json'))})
    qualification=ExtractionOperationQualificationV2(workspace_id=original['workspace'],actor_id=actor,provider_login=login,worker_uri=WORKER,runtime_hash=runtime,
        source_registry_hash=original['registry'],parent_registry_sha256=parent_hash,envelope_sha256=pins.envelope_sha256,source_qualification_sha256=pins.qualification_sha256,
        descriptor_sha256=pins.descriptor_sha256,projection_sha256=pins.projection_sha256,population_admission_sha256=digest(population.model_dump(mode='json')),
        budget_allocation_projection_sha256=digest(allocation.model_dump(mode='json')),source_refs=refs,population_digest=population.population_digest,
        targets=tuple(ExtractionTargetV2(dispatch_id=c.job.dispatch_id,artifact_id=c.job.artifact_id,artifact_version=1,source_ref=c.receipt.ref,native_job_hash=c.job_hash,
            context_hash=digest(c.model_dump(mode='json'))) for c in sorted(parent.contexts,key=lambda c:c.job.dispatch_id.int)),
        issuer_actor=issuer,reviewer_actor=reviewer,expires_at=end)
    admission,observer,spool,replay=_phase_observer(x,population=population,actor=actor,end=end,root=root)
    custody=root/'private-custody';custody.mkdir(mode=0o700)
    config=x['settings'].config.model_dump(mode='json',exclude_none=True)
    for key in ('phase_registry_file','private_context_files'):config.pop(key)
    paths={}
    for name,value in [('pins',pins),('population',population),('projection',projection),('parent',parent),('envelope',envelope),('qualified',qualified),('operation',qualification),('observer',admission),('source-url',url.encode())]:
        paths[name]=store(name+'.json',value)
    config.update(phase='extraction',pins_file=paths['pins'][0],pins_sha256=paths['pins'][1],population_file=paths['population'][0],projection_file=paths['projection'][0],
        source_url_file=paths['source-url'][0],expected_session_role=login,source_expires_at=end.isoformat(),parent_registry_file=paths['parent'][0],envelope_file=paths['envelope'][0],
        source_qualification_file=paths['qualified'][0],extraction_qualification_file=paths['operation'][0],extraction_qualification_sha256=paths['operation'][1],
        parent_observer_admission_file=paths['observer'][0],parent_observer_admission_hash=paths['observer'][1],observer_port=observer.server_port,
        observer_spool=str(spool),observer_initialization_hash=replay['initialization_receipt_hash'],private_receipts=str(custody))
    config_file,config_hash=store('settings.json',canonical_bytes(config))
    settings=load_extraction_runtime_settings_v2(config_file,config_hash,expected_role='provider');ingress=build_extraction_broker_v2(settings)
    provider=extraction_ingress_server_v2(('127.0.0.1',0),tls=p['tls'],worker_uri=WORKER,ingress=ingress);p['start'](provider)
    client=ExtractionProviderClientV2(replace(p['binding'](provider.server_port),timeout=90))
    x['state'].setdefault('content_by_request_hash',{}).update({c.job.request_hash:extraction_json(c.receipt) for c in parent.contexts})
    f=dict(original,actor=actor,runtime=runtime,login=login,url=url,binding=ProcessingSourceBinding(runtime,original['registry'],qualified.expected_owner_role,login,actor,'source-reader',end))
    return dict(x,f=f,job=parent.contexts[0].job,private=parent,settings=settings,client=client,descriptor=descriptor,custody=custody,
        contexts=parent.contexts,qualification=qualification,operation_hash=paths['operation'][1],population=population,mode='extraction',context_file=paths['parent'][0])


def extraction_worker_appointments(x,*,prior_settings,initial_job,census_row,root):
    from oracle_brain.operating_model.purpose_journey import PurposeWorkerJobV2
    from oracle_brain.hosting.purpose_journey_v2 import CompilerPhaseCustodyFileV2
    from test_purpose_worker_startup import make_next_compiler_worker_v2
    root.mkdir(mode=0o700);jobs=[];files={}
    for context in x['contexts']:
        native=context.job;target=x['qualification'].target(native.dispatch_id)
        job=PurposeWorkerJobV2(job_id=uuid4(),journey_id=initial_job.journey_id,workspace_id=initial_job.workspace_id,actor_id=initial_job.actor_id,
            phase='extraction',source_refs=initial_job.source_refs,source_id=context.receipt.ref.source_id,allocation_hash=initial_job.allocation_hash,
            parent_journal_hash=census_row['journal_hash'],prior_receipt_hash=census_row['receipt_hash'],nonce=uuid4().hex,
            runtime_hash=initial_job.runtime_hash,admission_hash=x['operation_hash'],dispatch_id=native.dispatch_id,request_hash=native.request_hash,
            phase_registry_sha256=x['operation_hash'],expires_at=initial_job.expires_at,original_horizon=initial_job.original_horizon)
        path=root/(str(native.dispatch_id)+'.context.json');raw=canonical_bytes(context.model_dump(mode='json'));path.write_bytes(raw);path.chmod(0o600)
        identity=dict(dispatch_id=native.dispatch_id,native_job_hash=context.job_hash,artifact_id=target.artifact_id,artifact_version=target.artifact_version,source_ref=target.source_ref)
        outputs=[]
        for kind,suffix in [('phase_commit','.phase-commit.json'),('native_receipt','.json'),('raw_wire','.wire'),('wire_metadata','.wire.json')]:
            outputs.append(CompilerPhaseCustodyFileV2(kind=kind,path=str(x['custody']/(str(native.dispatch_id)+suffix)),
                request_hash=native.request_hash,producer_runtime_hash=x['f']['runtime'],**identity))
        qpath=root/(str(native.dispatch_id)+'.qualified-operation.json')
        qbytes=Path(x['settings'].config.extraction_qualification_file).read_bytes()
        assert hashlib.sha256(qbytes).hexdigest()==x['operation_hash']
        qpath.write_bytes(qbytes);qpath.chmod(0o600)
        poppath=root/(str(native.dispatch_id)+'.population.json')
        popbytes=Path(x['settings'].config.population_file).read_bytes()
        assert hashlib.sha256(popbytes).hexdigest()==x['qualification'].population_admission_sha256
        poppath.write_bytes(popbytes);poppath.chmod(0o600)
        outputs.extend([
            CompilerPhaseCustodyFileV2(kind='native_job',path=str(path),sha256=hashlib.sha256(raw).hexdigest(),**identity),
            CompilerPhaseCustodyFileV2(kind='extraction_qualification',path=str(qpath),sha256=x['operation_hash'],**identity),
            CompilerPhaseCustodyFileV2(kind='extraction_population',path=str(poppath),sha256=x['qualification'].population_admission_sha256,**identity)])
        jobs.append(job);files[job.job_id]=tuple(outputs)
    # Explicit compiler custody covers all three current extraction outputs,
    # enabling the retained full-population handoff after all actual commits.
    all_files=tuple(entry for entries in files.values() for entry in entries)
    assert len({entry.path for entry in all_files})==len(all_files)
    files={job.job_id:all_files for job in jobs}
    return make_next_compiler_worker_v2(x,root/'worker',prior_settings=prior_settings,jobs=tuple(jobs),custody_files=files)


def freeze_authorized_census(settings,job):
    """Freeze the actual committed census; no invented dispatch/time receipt."""
    from oracle_brain.operating_model.purpose_profiles_v2 import PurposePrivateContextV2
    from oracle_brain.operating_model.purpose_receipts_v2 import PhaseResponseCommitV2
    from oracle_brain.operating_model.acceptance_profiles import CensusPayload
    from oracle_brain.operating_model.semantic_acceptance import FrozenCensus
    selectors={'dispatch_id':job.dispatch_id}
    private_raw,_=settings.private(job,'census_context',**selectors)
    wire,_=settings.private(job,'raw_wire',**selectors)
    commit_raw,_=settings.private(job,'phase_commit',**selectors)
    private=PurposePrivateContextV2.model_validate_json(private_raw)
    commit=PhaseResponseCommitV2.model_validate_json(commit_raw)
    assert private.phase=='census' and commit.phase=='census'
    assert digest(private.model_dump(mode='json'))==commit.context_hash
    assert hashlib.sha256(wire).hexdigest()==commit.raw_response_hash
    payload=CensusPayload.model_validate_json(json.loads(wire)['choices'][0]['message']['content'])
    return FrozenCensus(workspace_id=job.workspace_id,source_refs=job.source_refs,regions=private.census.scope.regions,
        obligations=payload.obligations,source_only_context_hash=commit.context_hash,source_only_dispatch_hash=digest(commit.model_dump(mode='json')),
        frozen_at=commit.committed_at,census_model=private.job.request['model'])


def _phase_observer(x,*,population,actor,end,root):
    p=x['platform']
    signing=Ed25519PrivateKey.generate();public=signing.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    admission=ParentObserverAdmissionV2(purpose='complete-parent-currentness-v2',population=population,principal_id=actor,observer_uri=SERVER,client_uri=WORKER,
        signing_public_key=public.hex(),signing_key_fingerprint=hashlib.sha256(public).hexdigest(),issuer_actor=uuid4(),reviewer_actor=uuid4(),minimum_sequence=1,max_age_seconds=5,expires_at=end)
    sequence=[1]
    class Observer(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            assert self.path=='/v2/parent/current';incoming=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            sequence[0]+=1;clock=datetime.now(timezone.utc)
            witness=ParentCurrentnessWitnessV2(purpose='complete-parent-currentness-v2',admission_hash=digest(admission.model_dump(mode='json')),challenge=incoming['challenge'],
                sequence=sequence[0],population=population,principal_id=actor,observer_uri=SERVER,client_uri=WORKER,checked_at=clock,expires_at=min(end,clock+timedelta(seconds=4)),revoked=False)
            value=witness.model_dump(mode='json');raw=canonical_bytes({'witness':value,'signature':base64.b64encode(signing.sign(DOMAIN+canonical_bytes(value))).decode()})
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    observer=MutualTLSServer(('127.0.0.1',0),Observer,tls=p['tls']);p['start'](observer)
    spool=root/'observer-state';spool.mkdir(mode=0o700);_,replay=provision(spool,admission)
    return admission,observer,spool,replay


def admit_assembly_phase(x,*,admin_url,root,handoff,census,receipts):
    """Late assembly admission consumes only this journey's durable handoff."""
    from oracle_brain.operating_model.purpose_context import (PurposeDispatchV2,PurposePhaseRegistryV2,PurposeRunDescriptorV2,PurposeMetadataProjectionV2,PurposePinsV2)
    from oracle_brain.operating_model.native_factory import NativeDispatchJob
    from oracle_brain.operating_model.native_provider import current_pricing
    from oracle_brain.operating_model.assembly_context import assembly_messages
    from oracle_brain.operating_model.purpose_assembly_v2 import AssemblyJobContextV2
    from oracle_brain.operating_model.purpose_profiles_v2 import PurposePrivateContextV2
    from oracle_brain.operating_model.purpose_capture_v2 import AssemblyObserverContextV2,ObservedAssemblyProtocolV2
    from oracle_brain.provider_policy import ProcessingRequest,ProcessingApproval
    from oracle_brain.hosting.purpose_runtime import load_purpose_runtime_settings_v2,build_purpose_broker_v2
    from oracle_brain.hosting.purpose_transport import purpose_ingress_server_v2,PurposeProviderClientV2
    from purpose_journey_fixture_models import model_json
    p=x['platform'];original=x['f'];now=datetime.now(timezone.utc);end=min(x['expires_at'],now+timedelta(seconds=100));assert now<end
    root.mkdir(mode=0o700)
    def store(name,value):
        raw=canonical_bytes(value.model_dump(mode='json')) if hasattr(value,'model_dump') else value
        path=root/name;path.write_bytes(raw);path.chmod(0o600)
        return str(path),hashlib.sha256(raw).hexdigest()
    actor=x['phase_actors']['assembly'];runtime=x['phase_runtimes']['assembly'];login='coherent_assembly_'+uuid4().hex[:10]
    with psycopg.connect(admin_url) as conn:
        owner=conn.execute('SELECT actor_id FROM oracle2.appointments WHERE appointment_id=%s',(original['root'],)).fetchone()[0]
        conn.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(login),sql.Literal('invented-coherent-only')))
        conn.execute(sql.SQL('GRANT oracle2_source_reader TO {}').format(sql.Identifier(login)))
        conn.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',(login,runtime,original['registry'],end))
        for ref in original['refs']:
            conn.execute('INSERT INTO oracle2.hosting_role_source_admissions VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(login,ref.workspace_id,ref.source_id,ref.revision,actor,ref.original_sha256,ref.reading_sha256,ref.parser_id,runtime,original['registry'],end))
            for scope in ('source-read:','operating-audit:'):
                conn.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(uuid4(),original['workspace'],actor,scope+str(ref.source_id),owner,original['root'],end))
    url=psycopg.conninfo.make_conninfo(admin_url,user=login,password='invented-coherent-only')
    processing=ProcessingRequest(provider='openrouter',account=x['job'].processing_request.account,endpoint='https://openrouter.ai/api/v1',data_classes=frozenset({'synthetic'}),purpose='operating-audit',terms_hash='b'*64)
    approval=ProcessingApproval(**processing.model_dump(),expires_at=end,register_ref='invented-coherent-late-assembly')
    model_id=uuid4();request={**x['job'].request,'model':'openai/gpt-6.1-sol','messages':assembly_messages(receipts=receipts,extractions=handoff.extractions,census=census,model_id=model_id,version=1),'max_tokens':4096}
    job=NativeDispatchJob(dispatch_id=uuid4(),workspace_id=original['workspace'],artifact_id=model_id,batch_id=x['job'].batch_id,purpose='operating-audit',attempt=1,request=request,request_hash=digest(request),permission_hash='a'*64,processing_request=processing,approvals=(approval,),pricing=current_pricing(p['catalog'],model=request['model'],max_output_tokens=request['max_tokens'],register_hash='d'*64,now=now),register_hash='d'*64,input_tokens_upper_bound=2*len(canonical_bytes(request))+4096)
    assembly=AssemblyJobContextV2(actor_id=actor,provider_login=login,runtime_hash=runtime,source_registry_hash=original['registry'],compiler_digest=handoff.compiler_runtime_hash,parent_registry_hash=x['population'].parent_registry_sha256,expected_handoff_hash=digest(handoff.model_dump(mode='json')),job=job,receipts=receipts,handoff=handoff,census=census,reviewed_inventories={},model_id=model_id,model_version=1,expires_at=end)
    private=PurposePrivateContextV2(phase='assembly',job=job,assembly=assembly)
    allocation=p['allocation'];policy=processing.model_dump(mode='json');refs=original['refs'];issuer,reviewer=uuid4(),uuid4()
    population=x['population'].model_copy(update={'runtime_hash':runtime,'issuer_actor':issuer,'reviewer_actor':reviewer})
    dispatch=PurposeDispatchV2(dispatch_id=job.dispatch_id,source_refs=refs,job_hash=digest(job.model_dump(mode='json')),request_hash=job.request_hash,permission_hash=job.permission_hash,context_hash=digest(private.model_dump(mode='json')),model=request['model'],processing_request_hash=digest(policy),account_policy_hash=digest({k:v for k,v in policy.items() if k!='terms_hash'}),account_identity_hash=allocation.account_identity_hash,terms_hash=policy['terms_hash'],pricing_hash=digest(job.pricing.model_dump(mode='json')),register_hash=job.register_hash,approvals_hash=digest({'approvals':[approval.model_dump(mode='json')]}),budget_identity_hash=digest(allocation.model_dump(mode='json')),ledger_registry_hash=p['ledger_hash'],key_coverage_hash=p['coverage_hash'])
    phase=PurposePhaseRegistryV2(qualification_purpose='phase-operation-qualification-v2',run_id=uuid4(),workspace_id=original['workspace'],actor_id=actor,provider_login=login,worker_uri=WORKER,phase='assembly',purpose='operating-audit',operation='chat',runtime_hash=runtime,source_registry_hash=original['registry'],parent_registry_sha256=population.parent_registry_sha256,population_admission_sha256=digest(population.model_dump(mode='json')),source_refs=refs,population_digest=population.population_digest,dispatches=(dispatch,),issuer_actor=issuer,reviewer_actor=reviewer,expires_at=end)
    values=phase.model_dump(mode='python');values.pop('qualification_purpose');values['phase_registry_sha256']=digest(phase.model_dump(mode='json'));descriptor=PurposeRunDescriptorV2.model_validate(values)
    projection=PurposeMetadataProjectionV2(descriptor=descriptor,descriptor_sha256=digest(descriptor.model_dump(mode='json')))
    pins=PurposePinsV2(qualification_purpose='phase-operation-qualification-v2',phase='assembly',operation='chat',runtime_hash=runtime,source_registry_hash=original['registry'],parent_registry_sha256=population.parent_registry_sha256,population_admission_sha256=descriptor.population_admission_sha256,phase_registry_sha256=descriptor.phase_registry_sha256,budget_allocation_projection_sha256=dispatch.budget_identity_hash,descriptor_sha256=projection.descriptor_sha256,projection_sha256=digest(projection.model_dump(mode='json')),provider_login=login,worker_uri=WORKER,issuer_actor=issuer,reviewer_actor=reviewer,expires_at=end)
    admission,observer,spool,replay=_phase_observer(x,population=population,actor=actor,end=end,root=root)
    protocol=ObservedAssemblyProtocolV2();custodian_id=uuid4();custodian_config=digest({'owned-phase':'assembly','run':str(phase.run_id)});custodian_session=digest({'owned-session':str(uuid4())})
    capture=AssemblyObserverContextV2(custodian_id=custodian_id,custodian_config_hash=custodian_config,custodian_session_hash=custodian_session,runtime_hash=runtime,census_hash=digest(census.model_dump(mode='json')),protocol_hash=digest(protocol.model_dump(mode='json')),dispatch_id=job.dispatch_id,job_hash=digest(job.model_dump(mode='json')),request_hash=job.request_hash,key_fingerprint=p['coverage'].key_fingerprint,ledger_identity_hash=p['ledger_hash'],expires_at=end,assembly_context_hash=digest(assembly.model_dump(mode='json')),handoff_hash=digest(handoff.model_dump(mode='json')))
    paths={name:store(name+'.json',value) for name,value in [('pins',pins),('population',population),('projection',projection),('phase',phase),('context',private),('observer',admission),('source-url',url.encode()),('capture',capture),('protocol',protocol)]}
    custody=root/'private-custody';custody.mkdir(mode=0o700)
    config=x['settings'].config.model_dump(mode='json',exclude_none=True)
    config.update(phase='assembly',pins_file=paths['pins'][0],pins_sha256=paths['pins'][1],population_file=paths['population'][0],projection_file=paths['projection'][0],source_url_file=paths['source-url'][0],expected_session_role=login,source_expires_at=end.isoformat(),phase_registry_file=paths['phase'][0],private_context_files={str(job.dispatch_id):paths['context'][0]},parent_observer_admission_file=paths['observer'][0],parent_observer_admission_hash=paths['observer'][1],observer_port=observer.server_port,observer_spool=str(spool),observer_initialization_hash=replay['initialization_receipt_hash'],private_receipts=str(custody),assembly_observer_file=paths['capture'][0],assembly_observer_hash=paths['capture'][1],assembly_protocol_file=paths['protocol'][0],assembly_protocol_hash=paths['protocol'][1],actual_custodian_id=str(custodian_id),actual_custodian_config_hash=custodian_config,actual_custodian_session_hash=custodian_session)
    config_file,config_hash=store('settings.json',canonical_bytes(config));settings=load_purpose_runtime_settings_v2(config_file,config_hash,expected_phase='assembly',expected_role='provider')
    ingress=build_purpose_broker_v2(settings);server=purpose_ingress_server_v2(('127.0.0.1',0),tls=p['tls'],worker_uri=WORKER,ingress=ingress);p['start'](server)
    client=PurposeProviderClientV2(replace(p['binding'](server.server_port),timeout=90))
    x['state'].setdefault('content_by_request_hash',{})[job.request_hash]=model_json(handoff.extractions,source_refs=refs,model_id=model_id,version=1)
    return dict(x,job=job,private=private,settings=settings,client=client,descriptor=descriptor,custody=custody,population=population,operation_hash=descriptor.phase_registry_sha256,mode='assembly',context_file=paths['context'][0],assembly=assembly,assembly_observer=capture,assembly_protocol=protocol)


def phase_worker_appointment(x,*,prior_settings,prior_job,prior_row,root):
    from oracle_brain.operating_model.purpose_journey import PurposeWorkerJobV2
    from oracle_brain.hosting.purpose_journey_v2 import CompilerPhaseCustodyFileV2
    from test_purpose_worker_startup import make_next_compiler_worker_v2
    native=x['job'];phase=x['mode']
    job=PurposeWorkerJobV2(job_id=uuid4(),journey_id=prior_job.journey_id,workspace_id=prior_job.workspace_id,actor_id=prior_job.actor_id,
        phase=phase,source_refs=prior_job.source_refs,allocation_hash=prior_job.allocation_hash,parent_journal_hash=prior_row['journal_hash'],
        prior_receipt_hash=prior_row['receipt_hash'],nonce=uuid4().hex,runtime_hash=prior_job.runtime_hash,admission_hash=x['operation_hash'],
        dispatch_id=native.dispatch_id,request_hash=native.request_hash,phase_registry_sha256=x['operation_hash'],
        expires_at=x['descriptor'].expires_at,original_horizon=prior_job.original_horizon)
    files=tuple(CompilerPhaseCustodyFileV2(kind=kind,path=str(x['custody']/(str(native.dispatch_id)+suffix)),dispatch_id=native.dispatch_id,
        request_hash=native.request_hash,producer_runtime_hash=x['descriptor'].runtime_hash,native_job_hash=digest(native.model_dump(mode='json')))
        for kind,suffix in [('phase_commit','.phase-commit.json'),('native_receipt','.json'),('raw_wire','.wire'),('wire_metadata','.wire.json')])
    settings,jobs=make_next_compiler_worker_v2(x,root,prior_settings=prior_settings,jobs=(job,),custody_files={job.job_id:files})
    return settings,jobs[0]
