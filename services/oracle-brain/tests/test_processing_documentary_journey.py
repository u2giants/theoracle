"""Actual role/queue/SDK source proof with invented outputs, never model quality."""
import hashlib
import json
from uuid import uuid4

import psycopg
import pytest

from test_source_processing_qualification import processing, resolver, RUNTIME, REGISTRY
from test_processing_compiler_capabilities import compiler, executor_for
from test_replacement_documentary_journey import InventedProvider, assemble_invented
from oracle_brain.operating_model.extraction import ExtractionPersistenceProfile
from oracle_brain.operating_model.pipeline import dispatch_source
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.source_receipts import SourceRef



def prove_owned_target(admin_url):
    parts=psycopg.conninfo.conninfo_to_dict(admin_url)
    if (parts.get('host') not in {'127.0.0.1','localhost'} or not parts.get('port','5432').isdigit()
            or not parts.get('dbname','').startswith('oracle_operating_model_test_')):
        raise PermissionError('exact isolated owned processing test database required')
    with psycopg.connect(admin_url) as conn:
        if conn.execute('SELECT current_database()').fetchone()[0]!=parts['dbname']:
            raise PermissionError('actual owned test target differs')

def current_two_originals(admin_url,f):
    """Owned fixture admission only; neither source draft is confirmed/reviewed."""
    texts=('Design sends ART to Supplier. The approval owner is unknown.',
           'Supplier receives ART from Design. Reported timing conflicts: one or two days.')
    source2=uuid4()
    with psycopg.connect(admin_url) as conn:
        owner=conn.execute('SELECT actor_id FROM oracle2.appointments WHERE appointment_id=%s',(f['root'],)).fetchone()[0]
        for source,text,new in ((f['source'],texts[0],False),(source2,texts[1],True)):
            seal=hashlib.sha256(text.encode()).hexdigest()
            provenance=dict(original_hash=seal,content_hash=seal,parser_identity='b'*64,
                content_type='text/plain',evidence_kind='native_text',page_count=1,review_receipt='c'*64)
            if new:
                conn.execute("INSERT INTO oracle2.sources(source_id,workspace_id,uploaded_by,filename,content_type,status) VALUES(%s,%s,%s,'invented-second.txt','text/plain','draft')",(source,f['workspace'],f['actor']))
                conn.execute("INSERT INTO oracle2.drafts(draft_id,source_id,workspace_id,created_by,process_name,status) VALUES(%s,%s,%s,%s,'fresh unconfirmed original','draft')",(uuid4(),source,f['workspace'],f['actor']))
                for index,(kind,body) in enumerate((('original',text),('original-metadata',json.dumps(provenance)))):
                    conn.execute('INSERT INTO oracle2.source_blocks VALUES(%s,%s,%s,%s,%s,%s,0,%s)',(uuid4(),source,f['workspace'],index,kind,body,len(body)))
                for scope in ('source-read:','source-extraction:'):
                    conn.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(uuid4(),f['workspace'],f['actor'],scope+str(source),owner,f['root'],f['expiry']))
                conn.execute('INSERT INTO oracle2.hosting_role_source_admissions VALUES(%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s)',(f['login'],f['workspace'],source,f['actor'],seal,seal,'b'*64,RUNTIME,REGISTRY,f['expiry']))
            else:
                conn.execute("UPDATE oracle2.source_blocks SET text=%s,span_end=%s WHERE source_id=%s AND kind='original'",(text,len(text),source))
                metadata=json.dumps(provenance)
                conn.execute("UPDATE oracle2.source_blocks SET text=%s,span_end=%s WHERE source_id=%s AND kind='original-metadata'",(metadata,len(metadata),source))
                conn.execute('UPDATE oracle2.hosting_role_source_admissions SET original_hash=%s,reading_hash=%s WHERE role_name=%s AND source_id=%s',(seal,seal,f['login'],source))
    reader=resolver(f)
    receipts=tuple(reader.current_for_processing(f['workspace'],s) for s in (f['source'],source2))
    assert tuple(r.reading for r in receipts)==texts
    return receipts



def compiler_extraction_guard(f):
    reader=resolver(f)
    def guard(manifest,payload,principal,now):
        if (manifest.kind!='processing_extraction_v1' or manifest.workspace_id!=f['workspace']
                or principal!=f['actor'] or manifest.content_hash!=digest(payload)):
            raise PermissionError('fixture compiler extraction context differs')
        for raw in payload['source_refs']:
            ref=SourceRef.model_validate_json(json.dumps(raw))
            if reader.identity(ref.workspace_id,ref.source_id)!=ref:
                raise PermissionError('current compiler source identity differs')
        return None
    return guard

def test_actual_profile_dispatch_persists_both_fresh_originals_with_no_confirmation(admin_url,processing,tmp_path):
    prove_owned_target(admin_url)
    f=processing();receipts=current_two_originals(admin_url,f)
    # Actual bound SQL identity/dual-scope checks, never semantic serving approval.
    ledger=compiler(f,tmp_path,read_guard=compiler_extraction_guard(f))
    provider=InventedProvider();extractions=[]
    for receipt in receipts:
        artifact=uuid4()
        manifest=dispatch_source(ledger,provider,receipt,artifact_id=artifact,version=1,batch_id=uuid4(),
            permission_digest='f'*64,compiler_digest=RUNTIME,
            persistence_profile=ExtractionPersistenceProfile.PROCESSING_V1)
        assert manifest.kind=='processing_extraction_v1'
        assert ledger.read_with_manifest(f['workspace'],artifact,1)[0]==manifest
        extractions.append(manifest)
    assert len(provider.calls)==2
    with psycopg.connect(admin_url) as conn:
        assert conn.execute('SELECT status FROM oracle2.drafts WHERE source_id=ANY(%s)',([r.ref.source_id for r in receipts],)).fetchall()==[('draft',),('draft',)]
        assert conn.execute('SELECT count(*) FROM oracle2.reviews WHERE workspace_id=%s',(f['workspace'],)).fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM oracle2.outbox WHERE workspace_id=%s',(f['workspace'],)).fetchone()[0]==0


def independent_assessor(admin_url,f,receipts):
    from dataclasses import replace
    from psycopg import sql
    from oracle_brain.operating_model.authority_adapter import ProcessingSourceResolver
    actor=uuid4();login='journey_assessor_'+uuid4().hex[:12]
    with psycopg.connect(admin_url) as conn:
        owner=conn.execute('SELECT actor_id FROM oracle2.appointments WHERE appointment_id=%s',(f['root'],)).fetchone()[0]
        conn.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(login),sql.Literal('invented-journey-only')))
        conn.execute(sql.SQL('GRANT oracle2_source_reader TO {}').format(sql.Identifier(login)))
        conn.execute('INSERT INTO oracle2.hosting_role_runtime_admissions SELECT %s,runtime_hash,registry_hash,expires_at FROM oracle2.hosting_role_runtime_admissions WHERE role_name=%s',(login,f['login']))
        for receipt in receipts:
            ref=receipt.ref
            for scope in ('source-read:','source-extraction:'):
                conn.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(uuid4(),f['workspace'],actor,scope+str(ref.source_id),owner,f['root'],f['expiry']))
            conn.execute('INSERT INTO oracle2.hosting_role_source_admissions VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(login,f['workspace'],ref.source_id,ref.revision,actor,ref.original_sha256,ref.reading_sha256,ref.parser_id,RUNTIME,REGISTRY,f['expiry']))
    binding=replace(f['binding'],expected_session_role=login,principal=actor,profile='source-reader')
    url=psycopg.conninfo.make_conninfo(admin_url,user=login,password='invented-journey-only')
    return actor,ProcessingSourceResolver(url,binding=binding)


def qualified_journey(admin_url,processing,tmp_path):
    """Real SQL roles and durable chain, with explicitly injected model/admission."""
    from datetime import datetime,timedelta,timezone
    from oracle_brain.hosting.provider_runtime import JobContext,JobRegistry
    from oracle_brain.operating_model.assembly_context import AssemblyJobContext,SealedAssemblyExtraction,assembly_messages
    from oracle_brain.operating_model.assembly_qualification import QualifiedAssemblyReadGuard,persist_qualified_assembly
    from oracle_brain.operating_model.authority_adapter import ProcessingArtifactResolver
    from oracle_brain.operating_model.processing_ledger import ProcessingCompilerLedger
    from oracle_brain.operating_model.captured_assembly import (AssemblyObserverContext,ObservedAssemblyProtocol,
        ObservedAssemblyCustodian,ObservedAssemblyWire,captured_assembly_candidate)
    from oracle_brain.operating_model.native_factory import ObservedAssemblyBrokerEgress
    from oracle_brain.operating_model.native_provider import NativeOpenRouter
    from oracle_brain.operating_model.pipeline import extraction_messages
    from oracle_brain.operating_model.model import BusinessOperatingModel
    from oracle_brain.operating_model.coverage import Obligation,CoverageRecord
    from oracle_brain.operating_model.semantic_acceptance import (SourceRegion,FrozenCensus,IndependentAssessment,
        CriterionReview,SemanticAdmission,CRITERIA,sealed)
    from oracle_brain.operating_model.artifact_storage import FileBlobStore
    from oracle_brain.operating_model.source_receipts import EvidenceRef
    from test_native_factory import job
    import urllib.request
    prove_owned_target(admin_url)
    f=processing();receipts=current_two_originals(admin_url,f);assessor,assessor_reader=independent_assessor(admin_url,f,receipts)
    ledger=compiler(f,tmp_path/'blobs',read_guard=compiler_extraction_guard(f));provider=InventedProvider()
    source_jobs=[];extractions=[]
    for receipt in receipts:
        j=job();request={**j.request,'messages':extraction_messages(receipt)}
        j=j.model_copy(update={'workspace_id':f['workspace'],'request':request,'request_hash':digest(request),'permission_hash':'f'*64,
            'input_tokens_upper_bound':len(json.dumps(request).encode())+2048})
        source_jobs.append(JobContext(job=j,actor_id=f['actor'],job_hash=sealed(j),permission_hash=j.permission_hash,receipt=receipt,inventories={}))
        m=dispatch_source(ledger,provider,receipt,artifact_id=j.artifact_id,version=1,batch_id=j.batch_id,
            permission_digest=j.permission_hash,compiler_digest=RUNTIME,persistence_profile=ExtractionPersistenceProfile.PROCESSING_V1)
        actual,body=ledger.read_with_manifest(f['workspace'],m.artifact_id,1)
        extractions.append(SealedAssemblyExtraction(manifest=actual,payload=body))
    parent=JobRegistry(issuer_actor=uuid4(),reviewer_actor=uuid4(),runtime_hash=RUNTIME,
        expires_at=datetime.now(timezone.utc)+timedelta(minutes=1),contexts=tuple(source_jobs))
    parent_bytes=parent.model_dump_json().encode();parent_path=tmp_path/'source-jobs.json';parent_path.write_bytes(parent_bytes);parent_path.chmod(0o600)
    from oracle_brain.hosting.provider_runtime import CurrentJobs
    parent_hash=hashlib.sha256(parent_bytes).hexdigest()
    assert CurrentJobs({'job_registry_file':str(parent_path),'job_registry_hash':parent_hash,'runtime_hash':RUNTIME}).registry()==parent
    # Independent source-only census is frozen before assembly response capture.
    evidence=tuple(EvidenceRef(ref=r.ref,start=0,end=len(r.reading),quote=r.reading) for r in receipts)
    census=FrozenCensus(workspace_id=f['workspace'],source_refs=tuple(r.ref for r in receipts),
        regions=tuple(SourceRegion(region_id=str(i),kind='section',evidence=e) for i,e in enumerate(evidence)),
        obligations=tuple(Obligation(obligation_id='source-'+str(i),priority='essential',expected='represented',evidence=e,reason='Injected full-source census obligation') for i,e in enumerate(evidence)),
        source_only_context_hash='1'*64,source_only_dispatch_hash='2'*64,
        frozen_at=datetime.now(timezone.utc),census_model='openai/gpt-6.1-sol')
    model=BusinessOperatingModel.model_validate_json(assemble_invented(tuple(e.payload for e in extractions)))
    j=job();processing_request=j.processing_request.model_copy(update={'purpose':'operating-audit'})
    approval=j.approvals[0].model_copy(update={'purpose':'operating-audit'})
    request={**j.request,'messages':assembly_messages(receipts=receipts,extractions=tuple(extractions),census=census,model_id=model.model_id,version=1)}
    j=j.model_copy(update={'workspace_id':f['workspace'],'artifact_id':model.model_id,'purpose':'operating-audit',
        'request':request,'request_hash':digest(request),'permission_hash':'f'*64,
        'processing_request':processing_request,'approvals':(approval,),
        'input_tokens_upper_bound':len(json.dumps(request).encode())+2048})
    ctx=AssemblyJobContext(actor_id=f['actor'],runtime_hash=RUNTIME,source_registry_hash=REGISTRY,
        compiler_digest=RUNTIME,parent_registry_hash=parent_hash,envelope_hash='3'*64,job=j,
        receipts=receipts,extractions=tuple(extractions),census=census,reviewed_inventories={},
        model_id=model.model_id,model_version=1,issuer_actor=parent.issuer_actor,reviewer_actor=parent.reviewer_actor,
        expires_at=parent.expires_at)
    protocol=ObservedAssemblyProtocol()
    observer=AssemblyObserverContext(custodian_id=uuid4(),custodian_config_hash='4'*64,custodian_session_hash='5'*64,
        runtime_hash=RUNTIME,census_hash=sealed(census),protocol_hash=sealed(protocol),dispatch_id=j.dispatch_id,
        job_hash=sealed(j),request_hash=j.request_hash,key_fingerprint='6'*64,ledger_identity_hash='7'*64,expires_at=ctx.expires_at)
    custodian=ObservedAssemblyCustodian(context=observer,expected_context_hash=sealed(observer),protocol=protocol,
        expected_protocol_hash=sealed(protocol),actual_custodian_id=observer.custodian_id,actual_config_hash=observer.custodian_config_hash,
        actual_session_hash=observer.custodian_session_hash,actual_runtime_hash=RUNTIME)
    capture=ObservedAssemblyBrokerEgress.__new__(ObservedAssemblyBrokerEgress)
    capture._assembly_observer=custodian;capture._key_fingerprint=observer.key_fingerprint;capture._registry_hash=observer.ledger_identity_hash
    capture._receipts=tmp_path/'private-wire';capture._receipts.mkdir(mode=0o700)
    wire=json.dumps({'model':j.request['model'],'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':model.model_dump_json()}}]}).encode()
    # Exact existing NativeOpenRouter preparse callback, with invented local HTTP.
    class Response:
        def read(self,limit):return wire
        def __enter__(self):return self
        def __exit__(self,*args):pass
    class Opener:
        def open(self,*args,**kwargs):return Response()
    original_opener=urllib.request.build_opener
    urllib.request.build_opener=lambda *_:Opener()
    try:
        native=NativeOpenRouter('invented-source-proof-only',coverage_receipt=lambda:None,
            trusted_coverage_hash='8'*64,ledger_identity_hash=observer.ledger_identity_hash,
            paid_wire_receiver=lambda raw,**kw:capture._capture_wire(j,raw,uuid4(),**kw))
        assert native._request('/chat/completions',j.request)['model']==j.request['model']
    finally:urllib.request.build_opener=original_opener
    observed=ObservedAssemblyWire.model_validate_json((capture._receipts/(str(j.dispatch_id)+'.observed-wire.json')).read_bytes())
    captured,_=captured_assembly_candidate(context=ctx,observer=observer,expected_observer_context_hash=sealed(observer),
        protocol=protocol,expected_protocol_hash=sealed(protocol),observed=observed,raw=wire,now=datetime.now(timezone.utc))
    assessment=IndependentAssessment(workspace_id=f['workspace'],census_hash=sealed(census),candidate_hash=captured.candidate_hash,
        permission_hash=j.permission_hash,protocol_hash=sealed(protocol),assessor_actor=assessor,assessor_model='openai/gpt-6-astra',
        assessed_at=datetime.now(timezone.utc),dispatch_receipt_hash='9'*64,raw_response_hash='a'*64,
        coverage=tuple(CoverageRecord(obligation_id=o.obligation_id,disposition='represented',object_ids=(pid,),reason='Injected independent source assessment') for o,pid in zip(census.obligations,('design','supplier'))),
        criteria=tuple(CriterionReview(criterion=k,verdict='pass',explanation='Injected fixture, not model quality',evidence=evidence,object_ids=('design','supplier')) for k in sorted(CRITERIA)))
    admission=SemanticAdmission(protocol_hash=sealed(protocol),runtime_hash=RUNTIME,
        source_region_register_hash=digest({'regions':[r.model_dump(mode='json') for r in census.regions]}),
        census_hash=sealed(census),assessment_hash=sealed(assessment),candidate_hash=captured.candidate_hash,
        permission_hash=j.permission_hash,reviewer_report_hash='b'*64,object_evidence_hash=captured.object_evidence_hash,
        candidate_created_at=observed.observed_at,implementer_actor=f['actor'],assessor_actor=assessor,
        candidate_model='openai/gpt-6.1-sol',purpose='independent-source-semantic-acceptance',expires_at=ctx.expires_at)
    trust={sealed(admission)};source=ProcessingArtifactResolver(f['url'],binding=f['binding']);holder={}
    def identity(w,p,s):
        if p!=f['actor']:raise PermissionError('wrong actual actor')
        return source.identity(w,s)
    qguard=QualifiedAssemblyReadGuard(trusted_admissions=lambda:frozenset(trust),runtime_hash=RUNTIME,
        current_source_identity=identity,current_extraction_manifest=lambda w,p,a,v:source.artifact_metadata(w,a,v)[0],
        qualified_parent_reader=lambda w,p,a,v:holder['ledger'].read_with_manifest(w,a,v))
    class CompilerGuard:
        def __call__(self,m,p,a,n):
            return compiler_extraction_guard(f)(m,p,a,n) if m.kind=='processing_extraction_v1' else qguard(m,p,a,n)
        def valid_until(self,*args):return qguard.valid_until(*args)
    combined=CompilerGuard()
    ledger=ProcessingCompilerLedger(f['url'],FileBlobStore(tmp_path/'blobs'),principal=f['actor'],processing_sources=source,
        processing_compile_guard=combined,processing_read_guard=combined);holder['ledger']=ledger
    def can_assess(w,p,s):
        return p==assessor and assessor_reader.identity(w,s).source_id==s
    manifest=persist_qualified_assembly(ledger,context=ctx,observer=observer,expected_observer_context_hash=sealed(observer),
        protocol=protocol,expected_protocol_hash=sealed(protocol),observed=observed,raw=wire,assessment=assessment,admission=admission,
        trusted_admission_hashes=frozenset(trust),source_regions=census.regions,
        current_source=assessor_reader.current_for_processing,can_read=can_assess,compiler_digest=RUNTIME)
    return dict(f=f,ledger=ledger,source=source,manifest=manifest,guard=qguard,trust=trust,receipts=receipts,provider=provider)


def test_actual_qualified_compile_then_metadata_only_summary_and_answer(admin_url,processing,tmp_path):
    from oracle_brain.operating_model.authority_adapter import ProcessingArtifactResolver
    from oracle_brain.operating_model.assembly_qualification import QualifiedAssemblyReadGuard
    from oracle_brain.operating_model.ledger import Ledger
    from oracle_brain.operating_model.artifact_storage import FileBlobStore
    from oracle_brain.operating_model.retrieval import QueryPlan
    from oracle_brain.operating_model.summaries import summarize_from_ledger,persist_summary,serve_summary
    from oracle_brain.operating_model.answer import answer_from_summary
    q=qualified_journey(admin_url,processing,tmp_path);f=q['f'];ledger=q['ledger'];m=q['manifest']
    assert m.kind=='processing_qualified_model_v1' and len(q['provider'].calls)==2
    with psycopg.connect(admin_url) as conn:
        assert conn.execute('SELECT operation,payload->>\'namespace\' FROM oracle2.outbox WHERE assertion_id=%s',(m.artifact_id,)).fetchall()==[('project','oracle_processing_v1')]
    summary=summarize_from_ledger(ledger,f['workspace'],m.artifact_id,1,
        QueryPlan(view='company_overview',question='Invented whole source',max_bytes=128*1024,page=0,page_size=25),qualification_guard=q['guard'])
    sid=uuid4();sm=persist_summary(ledger,summary,summary_id=sid,summary_version=1,
        permission_digest=m.permission_digest,compiler_digest=RUNTIME,qualification_guard=q['guard'])
    assert sm.kind=='processing_summary_v1'
    url,binding=executor_for(admin_url,f);source=ProcessingArtifactResolver(url,binding=binding);holder={}
    def identity(w,p,s):
        if p!=f['actor']:raise PermissionError('actual executor actor differs')
        return source.identity(w,s)
    guard=QualifiedAssemblyReadGuard(trusted_admissions=lambda:frozenset(q['trust']),runtime_hash=RUNTIME,
        current_source_identity=identity,current_extraction_manifest=lambda w,p,a,v:source.artifact_metadata(w,a,v)[0],
        qualified_parent_reader=lambda w,p,a,v:holder['ledger'].read_with_manifest(w,a,v))
    def no_original(*args):raise AssertionError('executor attempted raw original read')
    executor=Ledger(url,FileBlobStore(tmp_path/'blobs'),principal=f['actor'],processing_sources=source,
        processing_read_guard=guard,can_read=lambda *_:False,current_source=no_original);holder['ledger']=executor
    with pytest.raises(PermissionError):source.current_for_processing(f['workspace'],f['source'])
    served=serve_summary(executor,f['workspace'],sid,1,qualification_guard=guard)
    answer=answer_from_summary(executor,served,intent='overview',qualification_guard=guard)
    assert answer.state=='answered' and len(answer.records)==2 and answer.citations
    assert {x['kind'] for x in answer.findings}=={'missing_information','source_conflict'}
    # A genuine current source withdrawal denies metadata replay and answer.
    with psycopg.connect(admin_url) as conn:conn.execute("UPDATE oracle2.drafts SET status='withdrawn' WHERE source_id=%s",(f['source'],))
    with pytest.raises((PermissionError,psycopg.errors.InsufficientPrivilege)):
        answer_from_summary(executor,served,intent='overview',qualification_guard=guard)
