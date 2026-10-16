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



def assert_no_uncited_originals(value):
    serialized=json.dumps(value,sort_keys=True,default=str)
    assert 'UNPROJECTED_ORIGINAL_ALPHA' not in serialized
    assert 'UNPROJECTED_ORIGINAL_BETA' not in serialized


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
    texts=('Design sends ART to Supplier. The approval owner is unknown. UNPROJECTED_ORIGINAL_ALPHA',
           'Supplier receives ART from Design. Reported timing conflicts: one or two days. UNPROJECTED_ORIGINAL_BETA')
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



class SelectiveInventedProvider(InventedProvider):
    """Injected observations deliberately leave distinctive nonbusiness text uncited."""
    def extract(self,**kwargs):
        from oracle_brain.operating_model.source_receipts import EvidenceRef,SourceRef
        from oracle_brain.operating_model.findings import Finding
        original=json.loads(kwargs['messages'][1]['content']);ref=SourceRef.model_validate_json(json.dumps(original['source_ref']))
        text=original['reading'];end=text.index('.')+1;last=text.index(' UNPROJECTED_')
        self.calls.append((ref.source_id,text));first=EvidenceRef(ref=ref,start=0,end=end,quote=text[:end])
        second=EvidenceRef(ref=ref,start=end+1,end=last,quote=text[end+1:last])
        missing='unknown' in second.quote
        finding=Finding(finding_id='missing-owner' if missing else 'reported-timing-conflict',
            kind='missing_information' if missing else 'source_conflict',workspace_id=ref.workspace_id,
            source_refs=(ref,),scope='invented-handoff',text='Approval owner remains unknown.' if missing else 'Reported timing conflict remains unresolved.',
            origin='source_reported' if missing else 'reported_conflict_unverified',evidence_refs=(second,))
        raw=json.dumps({'schema_version':1,'source_id':str(ref.source_id),'source_revision':ref.revision,'complete':True,'unresolved_items':[],
            'observations':[{'occurrence_key':'literal-handoff','kind':'handoff','scope':'invented-handoff','value':first.quote,'evidence':[first.model_dump(mode='json')]}],
            'findings':[finding.model_dump(mode='json')]})
        kwargs['response_validator'](raw);return raw

def qualified_journey(admin_url,processing,tmp_path):
    """Real SQL roles and durable chain, with explicitly injected model/admission."""
    from datetime import datetime,timedelta,timezone
    from oracle_brain.hosting.provider_runtime import JobContext,JobRegistry
    from oracle_brain.operating_model.assembly_context import AssemblyJobContext,SealedAssemblyExtraction,assembly_messages
    from oracle_brain.operating_model.assembly_qualification import QualifiedAssemblyReadGuard,persist_qualified_assembly,CapturedAssemblySemanticAdmission,qualified_content_core
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
    ledger=compiler(f,tmp_path/'blobs',read_guard=compiler_extraction_guard(f));provider=SelectiveInventedProvider()
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
        obligations=tuple(Obligation(obligation_id='source-'+str(i),priority='essential',expected='represented',
            evidence=EvidenceRef(ref=r.ref,start=0,end=r.reading.index('.')+1,quote=r.reading[:r.reading.index('.')+1]),
            reason='Injected essential documentary handoff') for i,r in enumerate(receipts)),
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
    admission=CapturedAssemblySemanticAdmission(final_envelope_hash=digest(qualified_content_core(captured,census=census,assessment=assessment)),protocol_hash=sealed(protocol),runtime_hash=RUNTIME,
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
        current_source_identity=identity,current_extraction_seal=lambda w,p,a,v:source.extraction_seal(w,a,v),
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


async def deliver_and_scan_graph(q,admin_url,tmp_path):
    import os,secrets
    from oracle_brain.operating_model.sdk_projection import ProcessingSDKProjection
    from oracle_brain.operating_model.processing_projection import lease_processing_projection,project_processing_event
    from test_operating_model_sdk import NoCallLLM,FixedEmbedder
    graph_url=os.environ.get('ORACLE2_OPERATING_TEST_GRAPH_URL')
    if not graph_url:pytest.fail('owned processing graph proof is required')
    f=q['f'];m=q['manifest'];generation=uuid4();secret=secrets.token_bytes(32)
    projection=ProcessingSDKProjection(graph_url,workspace_id=f['workspace'],artifact_id=m.artifact_id,
        artifact_version=1,generation=generation,llm=NoCallLLM(),embedder=FixedEmbedder(),dimensions=8,
        qualification_guard=q['guard'])
    try:
        lease=lease_processing_projection(q['ledger'],f['workspace'])
        assert lease and lease.event.assertion_id==m.artifact_id
        receipt=await project_processing_event(q['ledger'],lease,projection,secret=secret,projector_id='invented-processing-fixture')
        # Every property on every actual stored node AND relationship is scanned.
        nodes=(await projection.connection.query('MATCH (n) RETURN n')).result_set
        edges=(await projection.connection.query('MATCH ()-[r]->() RETURN r')).result_set
        assert nodes and edges
        for row in nodes+edges:
            for entity in row:assert_no_uncited_originals(entity.properties)
        documents=(await projection.connection.query('MATCH (d:Document) RETURN d.id,d.content_hash,d.original_source_ref')).result_set
        assert len(documents)==2 and all(row[0].startswith('qualified_doc_') for row in documents)
        assert {json.loads(row[2])['source_id'] for row in documents}=={str(r.ref.source_id) for r in q['receipts']}
        return dict(receipt=receipt,secret=secret,generation=generation)
    finally:await projection.close()


def current_delivery(admin_url,q,event):
    # Real current semantic/source checks precede the actual SQL ACK lookup.
    m=q['manifest'];q['ledger'].read_with_manifest(q['f']['workspace'],m.artifact_id,m.version)
    with psycopg.connect(admin_url) as conn:
        row=conn.execute('SELECT r.payload,r.signature FROM oracle2.operating_projection_receipts r JOIN oracle2.outbox o ON o.event_id=r.event_id WHERE r.event_id=%s AND o.delivered_at IS NOT NULL',(event,)).fetchone()
    return None if row is None else {**row[0],'signature':row[1]}


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
    import asyncio
    delivery=asyncio.run(deliver_and_scan_graph(q,admin_url,tmp_path))
    minimized=ledger.read_with_manifest(f['workspace'],m.artifact_id,1)[1]
    assert_no_uncited_originals(minimized)
    summary=summarize_from_ledger(ledger,f['workspace'],m.artifact_id,1,
        QueryPlan(view='company_overview',question='Invented whole source',max_bytes=128*1024,page=0,page_size=25),qualification_guard=q['guard'])
    sid=uuid4();sm=persist_summary(ledger,summary,summary_id=sid,summary_version=1,
        permission_digest=m.permission_digest,compiler_digest=RUNTIME,qualification_guard=q['guard'])
    assert sm.kind=='processing_summary_v1'
    assert_no_uncited_originals(ledger.read_with_manifest(f['workspace'],sid,1)[1])
    url,binding=executor_for(admin_url,f);source=ProcessingArtifactResolver(url,binding=binding);holder={}
    def identity(w,p,s):
        if p!=f['actor']:raise PermissionError('actual executor actor differs')
        return source.identity(w,s)
    current_trust=q['trust']
    guard=QualifiedAssemblyReadGuard(trusted_admissions=lambda:frozenset(current_trust),runtime_hash=RUNTIME,
        current_source_identity=identity,current_extraction_seal=lambda w,p,a,v:source.extraction_seal(w,a,v),
        qualified_parent_reader=lambda w,p,a,v:holder['ledger'].read_with_manifest(w,a,v))
    with psycopg.connect(admin_url) as conn:
        ids=conn.execute("SELECT artifact_id,version FROM oracle2.artifact_manifests WHERE workspace_id=%s AND manifest->>'kind'='processing_extraction_v1'",(f['workspace'],)).fetchall()
    for artifact,version in ids:
        seal=source.extraction_seal(f['workspace'],artifact,version)
        assert_no_uncited_originals(seal.model_dump(mode='json'))
        assert 'private_object_key' not in type(seal).model_fields
    def no_original(*args):raise AssertionError('executor attempted raw original read')
    executor=Ledger(url,FileBlobStore(tmp_path/'blobs'),principal=f['actor'],processing_sources=source,
        processing_read_guard=guard,can_read=lambda *_:False,current_source=no_original);holder['ledger']=executor
    with pytest.raises(PermissionError):source.current_for_processing(f['workspace'],f['source'])
    import os
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('processing_readonly_fixture',Path(__file__).parents[3]/'dev/oracle2/test_readonly_graph_fixture.py')
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    processing_reader=fixture.processing_reader
    graph_url=os.environ['ORACLE2_OPERATING_TEST_GRAPH_URL'];project=os.environ.get('COMPOSE_PROJECT_NAME','')
    readonly=processing_reader(project+'-falkor-candidate-1',graph_url,tmp_path/'processing-reader',
        receipt=delivery['receipt'],secret=delivery['secret'],current_delivery=lambda event:current_delivery(admin_url,q,event))
    async def reload_executor_graph():
        from oracle_brain.operating_model.sdk_projection import ProcessingSDKProjection
        from test_operating_model_sdk import NoCallLLM,FixedEmbedder
        projection=ProcessingSDKProjection(readonly['ORACLE2_TEST_PROCESSING_READONLY_GRAPH_URL'],
            workspace_id=f['workspace'],artifact_id=m.artifact_id,artifact_version=1,generation=delivery['generation'],
            llm=NoCallLLM(),embedder=FixedEmbedder(),dimensions=8,read_only=True,qualification_guard=guard)
        try:
            loaded=await projection.load(executor,f['workspace'],m.artifact_id,1)
            assert_no_uncited_originals(loaded)
            for statement in ('MATCH (n) RETURN n','MATCH ()-[r]->() RETURN r'):
                for row in (await projection.connection.query(statement)).result_set:
                    for entity in row:assert_no_uncited_originals(entity.properties)
        finally:await projection.close()
    asyncio.run(reload_executor_graph())
    # An ACKed event is not leased again and cannot create another graph generation.
    from oracle_brain.operating_model.processing_projection import lease_processing_projection
    assert lease_processing_projection(ledger,f['workspace']) is None
    served=serve_summary(executor,f['workspace'],sid,1,qualification_guard=guard)
    answer=answer_from_summary(executor,served,intent='overview',qualification_guard=guard)
    assert_no_uncited_originals(answer.model_dump(mode='json'))
    assert answer.state=='answered' and len(answer.records)==2 and answer.citations
    assert {x['kind'] for x in answer.findings}=={'missing_information','source_conflict'}
    # A genuine current source withdrawal denies metadata replay and answer.
    with psycopg.connect(admin_url) as conn:conn.execute("UPDATE oracle2.drafts SET status='withdrawn' WHERE source_id=%s",(f['source'],))
    with pytest.raises((PermissionError,psycopg.errors.InsufficientPrivilege)):
        asyncio.run(reload_executor_graph())
    with pytest.raises((PermissionError,psycopg.errors.InsufficientPrivilege)):
        current_delivery(admin_url,q,__import__('uuid').UUID(delivery['receipt']['event_id']))
    with pytest.raises((PermissionError,psycopg.errors.InsufficientPrivilege)):
        answer_from_summary(executor,served,intent='overview',qualification_guard=guard)


def test_actual_completed_graph_cannot_ack_after_current_lease_expires(admin_url,processing,tmp_path):
    import os,asyncio
    from datetime import datetime,timezone
    from oracle_brain.operating_model.sdk_projection import ProcessingSDKProjection
    from oracle_brain.operating_model.processing_projection import lease_processing_projection,project_processing_event
    from test_operating_model_sdk import NoCallLLM,FixedEmbedder
    q=qualified_journey(admin_url,processing,tmp_path);f=q['f'];m=q['manifest'];built=[]
    lease=lease_processing_projection(q['ledger'],f['workspace'],lease_seconds=1)
    class ExpiringProjection(ProcessingSDKProjection):
        async def build(self,*args):
            result=await super().build(*args);built.append(result)
            # Real elapsed expiry after actual SDK completion; no fake clock.
            await asyncio.sleep(max(0,(lease.lease_until-datetime.now(timezone.utc)).total_seconds())+0.02)
            return result
    async def exercise():
        projection=ExpiringProjection(os.environ['ORACLE2_OPERATING_TEST_GRAPH_URL'],workspace_id=f['workspace'],
            artifact_id=m.artifact_id,artifact_version=1,generation=uuid4(),llm=NoCallLLM(),embedder=FixedEmbedder(),
            dimensions=8,qualification_guard=q['guard'])
        try:
            with pytest.raises((PermissionError,psycopg.errors.InsufficientPrivilege)):
                await project_processing_event(q['ledger'],lease,projection,secret=b'x'*32,projector_id='invented-expiry-fixture')
            assert built
            assert (await projection.connection.query('MATCH (s:OperatingModelSnapshot) RETURN count(s)')).result_set==[[1]]
        finally:await projection.close()
    asyncio.run(exercise())
    with psycopg.connect(admin_url) as conn:
        assert conn.execute('SELECT delivered_at FROM oracle2.outbox WHERE event_id=%s',(lease.event.event_id,)).fetchone()==(None,)
        assert conn.execute('SELECT count(*) FROM oracle2.operating_projection_receipts WHERE event_id=%s',(lease.event.event_id,)).fetchone()==(0,)
