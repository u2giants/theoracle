"""Synthetic issuer/observer contracts only; no actual grants or provider calls."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from uuid import uuid4

import pytest

from oracle_brain.hosting.provider_runtime import CurrentJobs, JobRegistry
from oracle_brain.hosting.processing_profile import ProcessingCurrentJobs, ProcessingMetadataJobs, ProcessingCustody
from oracle_brain.operating_model.processing_context import (
    QualifiedProcessingSources, ProcessingEnvelope, ProcessingPins, ProcessingProjection,
    derive_processing_descriptor, ProcessingAuthorityProof,
)
from oracle_brain.operating_model.contracts import canonical_bytes, digest
from oracle_brain.hosting.gateway import OpaqueJob, parse_job
from test_provider_runtime import registry_fixture
from oracle_brain.operating_model.pipeline import extraction_messages

WORKER = 'spiffe://oracle/dedicated-trigger'


def write(path, value):
    path.write_bytes(value if isinstance(value, bytes) else canonical_bytes(value.model_dump(mode='json')))
    path.chmod(0o600)
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def processing(tmp_path):
    parent, ctx, parent_path, registry = registry_fixture(tmp_path)
    now = datetime.now(timezone.utc)
    ctx = ctx.model_copy(update={'receipt':ctx.receipt.model_copy(update={'ref':ctx.receipt.ref.model_copy(update={'parser_id':'4'*64})})})
    # Two distinct source contexts, same immutable actor/workspace, no generated
    # artifact lookup. Parent artifact IDs name intended outputs, not old claims.
    ref2 = ctx.receipt.ref.model_copy(update={'source_id': uuid4()})
    second_job = ctx.job.model_copy(update={'dispatch_id': uuid4(), 'artifact_id': uuid4()})
    second = ctx.model_copy(update={'job': second_job, 'job_hash': digest(second_job.model_dump(mode='json')),
        'receipt': ctx.receipt.model_copy(update={'ref': ref2})})
    bound_contexts=[]
    for item in (ctx,second):
        request={**item.job.request,'messages':extraction_messages(item.receipt)}
        job=item.job.model_copy(update={'request':request,'request_hash':digest(request),
            'input_tokens_upper_bound':len(canonical_bytes(request))+2048})
        bound_contexts.append(item.model_copy(update={'job':job,'job_hash':digest(job.model_dump(mode='json'))}))
    ctx,second=bound_contexts
    registry = registry.model_copy(update={'contexts': (ctx, second)})
    parent.config['job_registry_hash'] = write(parent_path, registry)
    refs = tuple(c.receipt.ref for c in registry.contexts)
    envelope = ProcessingEnvelope(
        run_id=uuid4(), worker_uri=WORKER, runtime_hash=registry.runtime_hash,
        source_registry_hash='e'*64, parent_registry_sha256=parent.config['job_registry_hash'],
        ledger_registry_hash='f'*64, key_coverage_hash='1'*64,
        budget_allocation_hash='2'*64, budget_receipt_hash='3'*64,
        budget_ceiling_usd=Decimal('0.20'), budget_expires_at=now+timedelta(minutes=3),
        dispatch_ids=tuple(c.job.dispatch_id for c in registry.contexts), source_refs=refs,
        issuer_actor=registry.issuer_actor, reviewer_actor=registry.reviewer_actor,
        expires_at=now+timedelta(seconds=90))
    qualification = QualifiedProcessingSources(workspace_id=ctx.job.workspace_id, actor_id=ctx.actor_id,
        runtime_hash=registry.runtime_hash, source_registry_hash='e'*64, expected_owner_role='oracle2_admin',
        source_refs=refs, issuer_actor=registry.issuer_actor, reviewer_actor=registry.reviewer_actor,
        expires_at=now+timedelta(minutes=3))
    ep, qp, pp = (tmp_path/name for name in ('envelope', 'qualification', 'projection'))
    pins = ProcessingPins(runtime_hash=registry.runtime_hash, worker_uri=WORKER,
        source_registry_hash='e'*64, expected_owner_role='oracle2_admin',
        parent_registry_sha256=parent.config['job_registry_hash'], envelope_sha256=write(ep,envelope),
        qualification_sha256=write(qp,qualification), descriptor_sha256='0'*64,projection_sha256='0'*64,
        ledger_registry_hash='f'*64,key_coverage_hash='1'*64)
    descriptor = derive_processing_descriptor(registry,envelope,qualification,pins=pins,now=now)
    projection = ProcessingProjection(descriptor=descriptor,descriptor_sha256=digest(descriptor.model_dump(mode='json')))
    pins = pins.model_copy(update={'descriptor_sha256':projection.descriptor_sha256,'projection_sha256':write(pp,projection)})
    jobs = ProcessingCurrentJobs(parent,envelope_path=ep,qualification_path=qp,pins=pins)
    return dict(parent=parent,registry=registry,envelope=envelope,qualification=qualification,pins=pins,
                ep=ep,qp=qp,pp=pp,parent_path=parent_path,jobs=jobs,now=now,ctx=ctx)


def reseal_parent(state, registry):
    seal = write(state['parent_path'],registry)
    state['parent'].config['job_registry_hash'] = seal
    state['envelope'] = state['envelope'].model_copy(update={'parent_registry_sha256':seal})
    state['pins'] = state['pins'].model_copy(update={'parent_registry_sha256':seal,
        'envelope_sha256':write(state['ep'],state['envelope'])})
    state['jobs'].pins = state['pins']


def test_processing_descriptor_exact_registry_projection(processing):
    s=processing; parent, projection=s['jobs'].snapshot(); d=projection.descriptor
    assert d.actor_id==s['ctx'].actor_id and d.workspace_id==s['ctx'].job.workspace_id
    assert d.run_id==s['envelope'].run_id and len(d.source_refs)==len(d.dispatches)==2
    assert d.purpose=='source-extraction'
    assert {x.source_ref for x in d.dispatches}==set(s['envelope'].source_refs)
    for ctx in parent.contexts:
        assert s['jobs'].resolve(ctx.job.dispatch_id)==ctx.job
        assert s['jobs'].context(ctx.job)==ctx
    assert s['jobs'].projection_bytes()==s['pp'].read_bytes()


@pytest.mark.parametrize('field',('dispatch_ids','source_refs'))
def test_processing_descriptor_omitted_source_or_dispatch_denied(processing,field):
    s=processing;env=s['envelope'].model_copy(update={field:getattr(s['envelope'],field)[:1]})
    s['jobs'].pins=s['pins'].model_copy(update={'envelope_sha256':write(s['ep'],env)})
    with pytest.raises(PermissionError):s['jobs'].snapshot()


@pytest.mark.parametrize('field',('model','account','terms','budget','actor','workspace','source','alias','purpose'))
def test_processing_descriptor_model_account_terms_budget_mismatch_denied(processing,field):
    s=processing;ctx=s['registry'].contexts[0];job=ctx.job
    if field=='budget':
        env=s['envelope'].model_copy(update={'budget_ceiling_usd':Decimal('999')})
        s['jobs'].pins=s['pins'].model_copy(update={'envelope_sha256':write(s['ep'],env)})
    else:
        if field=='model':job=job.model_copy(update={'request':{**job.request,'model':'openai/gpt-6-astra'}})
        elif field in {'account','terms'}:
            key='account' if field=='account' else 'terms_hash'
            job=job.model_copy(update={'processing_request':job.processing_request.model_copy(update={key:'f'*64})})
        elif field=='purpose':job=job.model_copy(update={'purpose':'operating-audit'})
        elif field=='actor':ctx=ctx.model_copy(update={'actor_id':uuid4()})
        elif field=='workspace':job=job.model_copy(update={'workspace_id':uuid4()})
        elif field=='source':ctx=ctx.model_copy(update={'receipt':ctx.receipt.model_copy(update={'ref':ctx.receipt.ref.model_copy(update={'revision':2})})})
        else:ctx=ctx.model_copy(update={'receipt':ctx.receipt.model_copy(update={'aliases':(str(uuid4()),)})})
        ctx=ctx.model_copy(update={'job':job,'job_hash':digest(job.model_dump(mode='json'))})
        reseal_parent(s,s['registry'].model_copy(update={'contexts':(ctx,s['registry'].contexts[1])}))
    with pytest.raises((PermissionError,ValueError)):s['jobs'].snapshot()


def test_processing_projection_never_contains_originals(processing):
    s=processing;raw=s['jobs'].projection_bytes();metadata=json.loads(raw)
    assert b'synthetic source' not in raw and b'invented fixture only' not in raw
    forbidden={'reading','request','inventories','receipt','job_registry_file','endpoint','account','source_path','hmac','credentials'}
    def walk(value):
        if isinstance(value,dict):
            assert not forbidden.intersection(value)
            for item in value.values():walk(item)
        elif isinstance(value,list):
            for item in value:walk(item)
    walk(metadata)
    metadata['raw_registry']={}
    with pytest.raises(ValueError):ProcessingProjection.model_validate_json(json.dumps(metadata))


def test_processing_no_generated_artifact_bootstrap_dependency(processing,monkeypatch):
    import psycopg
    def denied(*_args,**_kwargs):raise AssertionError('descriptor must not invent generated DB artifact')
    monkeypatch.setattr(psycopg,'connect',denied)
    assert processing['jobs'].snapshot()[1].descriptor.dispatches
    with pytest.raises(PermissionError,match='not installed'):processing['jobs'].authorize(processing['ctx'].job)


@pytest.mark.parametrize('change',('expired','issuer','owner','unsealed','missing_pin','unknown_field'))
def test_processing_external_qualification_and_startup_required(processing,change):
    s=processing;q=s['qualification']
    if change=='expired':q=q.model_copy(update={'expires_at':s['now']-timedelta(seconds=1)})
    elif change=='issuer':q=q.model_copy(update={'issuer_actor':q.reviewer_actor})
    elif change=='owner':q=q.model_copy(update={'expected_owner_role':'foreign_owner'})
    elif change=='unsealed':s['ep'].write_bytes(s['ep'].read_bytes()+b' ')
    elif change=='missing_pin':
        raw=s['pins'].model_dump(mode='json');del raw['qualification_sha256']
        with pytest.raises(ValueError):ProcessingPins.model_validate_json(json.dumps(raw))
        return
    else:
        raw=q.model_dump(mode='json');raw['actor_from_http']=str(uuid4())
        s['qp'].write_bytes(canonical_bytes(raw));s['qp'].chmod(0o600)
        s['jobs'].pins=s['pins'].model_copy(update={'qualification_sha256':hashlib.sha256(s['qp'].read_bytes()).hexdigest()})
    if change not in {'unsealed','unknown_field'}:
        s['jobs'].pins=s['pins'].model_copy(update={'qualification_sha256':write(s['qp'],q)})
    with pytest.raises((PermissionError,ValueError)):s['jobs'].snapshot()


class SyntheticAuthority:
    def __init__(self):self.active=True;self.calls=[]
    @contextmanager
    def hold(self,descriptor,dispatch):
        if not self.active:raise PermissionError('synthetic live authority revoked')
        assert dispatch.source_ref in descriptor.source_refs
        self.calls.append((descriptor.actor_id,dispatch.source_ref))
        yield ProcessingAuthorityProof(workspace_id=descriptor.workspace_id,actor_id=descriptor.actor_id,
            source_ref=dispatch.source_ref,runtime_hash=descriptor.runtime_hash,
            source_registry_hash=descriptor.source_registry_hash,descriptor_sha256=digest(descriptor.model_dump(mode='json')),
            parent_registry_sha256=descriptor.parent_registry_sha256,envelope_sha256=descriptor.envelope_sha256,
            session_role='invented_metadata',profile='gateway-metadata',
            checked_at=datetime.now(timezone.utc),expires_at=descriptor.expires_at)


def metadata_profile(s,tmp_path):
    authority=SyntheticAuthority();current=[s['pins'].parent_registry_sha256]
    metadata=ProcessingMetadataJobs(projection_path=s['pp'],pins=s['pins'],current_parent_seal=lambda:current[0],live_authority=authority)
    spool=tmp_path/'spool';spool.mkdir()
    custody=ProcessingCustody(metadata=metadata,spool=spool)
    opaque=OpaqueJob(str(s['ctx'].job.dispatch_id),s['pins'].runtime_hash,s['pins'].projection_sha256,str(uuid4()),int(datetime.now(timezone.utc).timestamp())+60)
    return custody,authority,current,opaque


def test_processing_profile_preserves_documentary_defaults(processing,tmp_path):
    custody,authority,current,opaque=metadata_profile(processing,tmp_path)
    custody.admit(opaque,WORKER)
    assert len(authority.calls)==1
    # Same disk spool after object restart: changing nonce cannot rerun same dispatch.
    restarted=ProcessingCustody(metadata=custody.metadata,spool=custody.spool)
    with pytest.raises(PermissionError):restarted.admit(opaque,WORKER)
    changed=OpaqueJob(opaque.job_id,opaque.runtime_hash,opaque.admission_hash,str(uuid4()),opaque.expires_at)
    with pytest.raises(PermissionError):restarted.admit(changed,WORKER)
    assert restarted.claim()[0]==opaque
    assert restarted.claim() is None
    from oracle_brain.hosting.custody import FileCustody
    assert FileCustody.resolve is not ProcessingCustody.resolve
    with pytest.raises(PermissionError):custody.resolve(opaque,WORKER,result=True)


@pytest.mark.parametrize('failure',('parent','authority','worker','runtime','seal','foreign_dispatch'))
def test_processing_metadata_drift_denied_before_spool(processing,tmp_path,failure):
    custody,authority,current,opaque=metadata_profile(processing,tmp_path)
    worker=WORKER
    if failure=='parent':current[0]='0'*64
    elif failure=='authority':authority.active=False
    elif failure=='worker':worker='spiffe://oracle/foreign'
    else:
        changes={'runtime':'runtime_hash','seal':'admission_hash','foreign_dispatch':'job_id'}
        from dataclasses import replace
        opaque=replace(opaque,**{changes[failure]:str(uuid4()) if failure=='foreign_dispatch' else '0'*64})
    with pytest.raises((PermissionError,ValueError)):custody.admit(opaque,worker)
    assert list(custody.spool.glob('*.pending'))==[]


def test_processing_caller_cannot_supply_actor(processing):
    s=processing;now=int(datetime.now(timezone.utc).timestamp())
    raw={'job_id':str(s['ctx'].job.dispatch_id),'runtime_hash':s['pins'].runtime_hash,'admission_hash':s['pins'].projection_sha256,
         'nonce':str(uuid4()),'expires_at':now+90,'actor_id':str(uuid4())}
    with pytest.raises(ValueError):parse_job(json.dumps(raw).encode(),now=now)


@pytest.mark.parametrize('untrusted', (False, None))
def test_processing_false_or_empty_live_authority_denied(processing,tmp_path,untrusted):
    custody,_,_,opaque=metadata_profile(processing,tmp_path)
    class Denied:
        @contextmanager
        def hold(self,*_args):yield untrusted
    custody.metadata.live_authority=Denied()
    with pytest.raises(PermissionError):custody.admit(opaque,WORKER)
    assert not list(custody.spool.glob('*.pending'))


@pytest.mark.parametrize('field',('actor','workspace','source','runtime','registry','descriptor','parent','envelope','profile','future','stale','expired'))
def test_processing_live_proof_exact_and_fresh_before_queue(processing,tmp_path,field):
    custody,_,_,opaque=metadata_profile(processing,tmp_path)
    class Wrong(SyntheticAuthority):
        @contextmanager
        def hold(self,descriptor,dispatch):
            with super().hold(descriptor,dispatch) as proof:
                changes={'actor':{'actor_id':uuid4()},'workspace':{'workspace_id':uuid4()},
                    'source':{'source_ref':proof.source_ref.model_copy(update={'revision':2})},
                    'runtime':{'runtime_hash':'0'*64},'registry':{'source_registry_hash':'0'*64},
                    'descriptor':{'descriptor_sha256':'0'*64},'parent':{'parent_registry_sha256':'0'*64},
                    'envelope':{'envelope_sha256':'0'*64},'profile':{'profile':'source-reader'},
                    'future':{'checked_at':datetime.now(timezone.utc)+timedelta(seconds=1)},
                    'stale':{'checked_at':datetime.now(timezone.utc)-timedelta(seconds=6)},
                    'expired':{'expires_at':datetime.now(timezone.utc)-timedelta(seconds=1)}}
                yield proof.model_copy(update=changes[field])
    custody.metadata.live_authority=Wrong()
    with pytest.raises(PermissionError):custody.admit(opaque,WORKER)
    assert not list(custody.spool.glob('*.pending'))


def test_processing_projection_parser_identity_cannot_carry_raw_text(processing):
    value=json.loads(processing['pp'].read_bytes())
    value['descriptor']['source_refs'][0]['parser_id']='Raw original words must never be metadata'
    with pytest.raises(ValueError):ProcessingProjection.model_validate_json(json.dumps(value))


def test_processing_parent_observer_never_runs_under_sql_hold(processing,tmp_path):
    custody,_,_,opaque=metadata_profile(processing,tmp_path)
    held=[False]
    def observer():
        assert not held[0], 'parent observer must remain outside SQL lock'
        return processing['pins'].parent_registry_sha256
    class Held(SyntheticAuthority):
        @contextmanager
        def hold(self,*args):
            held[0]=True
            try:
                with super().hold(*args) as proof:yield proof
            finally:held[0]=False
    custody.metadata.current_parent_seal=observer
    custody.metadata.live_authority=Held()
    custody.admit(opaque,WORKER)


def test_processing_missing_or_error_observer_and_authority_denied(processing,tmp_path):
    s=processing
    with pytest.raises(PermissionError):ProcessingMetadataJobs(projection_path=s['pp'],pins=s['pins'],current_parent_seal=None,live_authority=None)
    custody,_,_,opaque=metadata_profile(s,tmp_path)
    def error():raise RuntimeError('observer unavailable')
    custody.metadata.current_parent_seal=error
    with pytest.raises(RuntimeError):custody.admit(opaque,WORKER)
    assert not list(custody.spool.glob('*.pending'))


def test_processing_dispatch_cannot_borrow_other_source_in_same_population(processing):
    s=processing;first,second=s['registry'].contexts
    wrong=first.model_copy(update={'receipt':second.receipt})
    # Even an issuer-side proposed new descriptor must reject mismatched source
    # messages: neither a union of permitted sources nor a fresh seal fixes it.
    registry=s['registry'].model_copy(update={'contexts':(wrong,second)})
    with pytest.raises(PermissionError):derive_processing_descriptor(registry,s['envelope'],s['qualification'],pins=s['pins'],now=s['now'])
    request={**first.job.request,'messages':extraction_messages(second.receipt)}
    job=first.job.model_copy(update={'request':request,'request_hash':digest(request)})
    wrong=first.model_copy(update={'job':job,'job_hash':digest(job.model_dump(mode='json'))})
    registry=s['registry'].model_copy(update={'contexts':(wrong,second)})
    with pytest.raises(PermissionError,match='exact source-only'):derive_processing_descriptor(registry,s['envelope'],s['qualification'],pins=s['pins'],now=s['now'])
