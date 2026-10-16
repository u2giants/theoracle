"""Real caller roles on the owned invented ledger; not semantic/live admission."""
from datetime import datetime,timedelta,timezone
from dataclasses import replace
import hashlib,json,time
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from test_source_processing_qualification import processing,resolver,RUNTIME,REGISTRY
from oracle_brain.operating_model.authority_adapter import ProcessingArtifactResolver,ProcessingSourceBinding
from oracle_brain.operating_model.artifact_storage import FileBlobStore
from oracle_brain.operating_model.processing_ledger import ProcessingCompilerLedger
from oracle_brain.operating_model.ledger import Ledger
from oracle_brain.operating_model.contracts import ArtifactManifest,canonical_bytes,digest


def compiler(f,tmp_path,guard=None,read_guard=None):
    source=ProcessingArtifactResolver(f['url'],binding=f['binding'])
    return ProcessingCompilerLedger(f['url'],FileBlobStore(tmp_path),principal=f['actor'],processing_sources=source,
        processing_compile_guard=guard,processing_read_guard=read_guard)


def bundle(f,*,kind='processing_extraction_v1',payload=None,dependencies=(),artifact=None,deadline=None):
    receipt=resolver(f).current_for_processing(f['workspace'],f['source'])
    refs=(receipt.ref,)
    body=payload or {'source_refs':[receipt.ref.model_dump(mode='json')],'findings':[]}
    deps=tuple(sorted(set(dependencies)|{('source',str(f['source']),'1')}))
    rb=canonical_bytes({'refs':[receipt.ref.model_dump(mode='json')]});db=canonical_bytes({'dependencies':deps});pb=canonical_bytes(body)
    manifest=ArtifactManifest(workspace_id=f['workspace'],artifact_id=artifact or uuid4(),version=1,kind=kind,
        input_digest=hashlib.sha256(rb).hexdigest(),source_digest=hashlib.sha256(rb).hexdigest(),permission_digest='f'*64,
        compiler_digest=RUNTIME,dependency_digest=hashlib.sha256(db).hexdigest(),content_hash=hashlib.sha256(pb).hexdigest(),
        private_object_key=f'operating-model/{f["workspace"]}/{hashlib.sha256(pb).hexdigest()}.json',
        state='failed' if kind in {'processing_failed_extraction_v1','processing_failed_assembly_v1'} else 'ready')
    return [Jsonb(manifest.model_dump(mode='json')),pb,rb,db,Jsonb([receipt.model_dump(mode='json')]),RUNTIME,REGISTRY,deadline or f['expiry']],manifest,body


def commit(f,b):
    with psycopg.connect(f['url']) as conn:
        return conn.execute('SELECT oracle2.commit_processing_candidate(%s,%s,%s,%s,%s,%s,%s,%s)',b).fetchone()[0]


def persist_extraction(f,tmp_path,**kwargs):
    receipt=resolver(f).current_for_processing(f['workspace'],f['source'])
    ledger=compiler(f,tmp_path,read_guard=lambda *a:None)
    payload={'source_refs':[receipt.ref.model_dump(mode='json')],'findings':[]}
    manifest=ledger.persist(workspace_id=f['workspace'],artifact_id=uuid4(),version=1,kind='processing_extraction_v1',payload=payload,
        refs=(receipt.ref,),permission_digest='a'*64,compiler_digest=RUNTIME,**kwargs)
    return ledger,manifest,payload


def executor_for(admin_url,f):
    login='processing_exec_'+uuid4().hex[:10]
    with psycopg.connect(admin_url) as conn:
        conn.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(login),sql.Literal('invented-test-only')))
        conn.execute(sql.SQL('GRANT oracle2_documentary_executor TO {}').format(sql.Identifier(login)))
        conn.execute('INSERT INTO oracle2.hosting_role_runtime_admissions SELECT %s,runtime_hash,registry_hash,expires_at FROM oracle2.hosting_role_runtime_admissions WHERE role_name=%s',(login,f['login']))
        conn.execute('INSERT INTO oracle2.hosting_role_source_admissions SELECT %s,workspace_id,source_id,revision,principal_id,original_hash,reading_hash,parser_id,runtime_hash,registry_hash,expires_at FROM oracle2.hosting_role_source_admissions WHERE role_name=%s',(login,f['login']))
    binding=replace(f['binding'],expected_session_role=login,profile='documentary-executor')
    return psycopg.conninfo.make_conninfo(admin_url,user=login,password='invented-test-only'),binding


def test_actual_unconfirmed_compiler_persists_new_extraction_no_graph_event(admin_url,processing,tmp_path):
    f=processing();ledger,m,p=persist_extraction(f,tmp_path)
    assert ledger.read_with_manifest(f['workspace'],m.artifact_id,1)==(m,p)
    with psycopg.connect(admin_url) as conn:
        assert conn.execute('SELECT status FROM oracle2.drafts WHERE source_id=%s',(f['source'],)).fetchone()[0]=='draft'
        assert conn.execute('SELECT count(*) FROM oracle2.operating_model_source_receipts WHERE source_id=%s',(f['source'],)).fetchone()[0]==1
        assert conn.execute('SELECT count(*) FROM oracle2.outbox WHERE assertion_id=%s',(m.artifact_id,)).fetchone()[0]==0


@pytest.mark.parametrize('profile',['source-reader','documentary-executor','gateway-metadata'])
def test_noncompiler_cannot_call_atomic_writer(processing,profile):
    f=processing(profile)
    with psycopg.connect(f['url']) as conn,pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("SELECT oracle2.commit_processing_candidate('{}',NULL,NULL,NULL,'[]',%s,%s,clock_timestamp()+interval '1 minute')",(RUNTIME,REGISTRY))


def test_only_qualified_model_emits_new_namespace_and_unqualified_default_denies(admin_url,processing,tmp_path):
    f=processing();_,parent,_=persist_extraction(f,tmp_path/'parent')
    args,m,p=bundle(f,kind='processing_qualified_model_v1',dependencies=(('artifact',str(parent.artifact_id),'1'),))
    assert commit(f,args)==m.model_dump(mode='json')
    with psycopg.connect(admin_url) as conn:
        assert conn.execute('SELECT operation,payload->>\'namespace\' FROM oracle2.outbox WHERE assertion_id=%s',(m.artifact_id,)).fetchall()==[('project','oracle_processing_v1')]
    class NoBlob:
        def read(self,*args):raise AssertionError('unqualified body opened')
    src=ProcessingArtifactResolver(f['url'],binding=f['binding'])
    ledger=Ledger(f['url'],NoBlob(),principal=f['actor'],can_read=lambda *a:False,current_source=lambda *a:None,processing_sources=src)
    with pytest.raises(PermissionError,match='qualification'):ledger.read(f['workspace'],m.artifact_id,1)


@pytest.mark.parametrize('kind',['processing_failed_extraction_v1','processing_failed_assembly_v1'])
def test_failed_processing_artifact_has_no_outbox(admin_url,processing,kind):
    f=processing();args,m,_=bundle(f,kind=kind)
    commit(f,args)
    with psycopg.connect(admin_url) as conn:
        assert conn.execute('SELECT state FROM oracle2.artifact_manifests WHERE artifact_id=%s',(m.artifact_id,)).fetchone()[0]=='failed'
        assert conn.execute('SELECT count(*) FROM oracle2.outbox WHERE assertion_id=%s',(m.artifact_id,)).fetchone()[0]==0


@pytest.mark.parametrize('scope',['root','read','extract'])
def test_revoked_current_grant_rejects_entire_bundle(admin_url,processing,scope):
    f=processing();args,m,_=bundle(f)
    with psycopg.connect(admin_url) as conn:conn.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(f[scope],))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):commit(f,args)
    with psycopg.connect(admin_url) as conn:
        assert conn.execute('SELECT count(*) FROM oracle2.artifact_manifests WHERE artifact_id=%s',(m.artifact_id,)).fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM oracle2.operating_model_source_receipts WHERE source_id=%s',(f['source'],)).fetchone()[0]==0


def test_idempotency_conflict_and_source_population_integrity(admin_url,processing):
    f=processing();args,m,_=bundle(f);commit(f,args);assert commit(f,args)==m.model_dump(mode='json')
    altered,_,_=bundle(f,artifact=m.artifact_id,payload={'source_refs':json.loads(args[2])['refs'],'different':True})
    with pytest.raises(psycopg.errors.InsufficientPrivilege):commit(f,altered)
    bad=list(args);bad[2]=canonical_bytes({'refs':[]})
    with pytest.raises(psycopg.errors.InsufficientPrivilege):commit(f,bad)


@pytest.mark.parametrize('mutation',['extra_dependency','invalidation'])
def test_metadata_and_both_read_apis_deny_before_blob_after_relational_change(admin_url,processing,tmp_path,mutation):
    f=processing();ledger,m,_=persist_extraction(f,tmp_path)
    with psycopg.connect(admin_url) as conn:
        # This models the old legacy INSERT surface after a source is confirmed.
        conn.execute("UPDATE oracle2.sources SET status='confirmed' WHERE source_id=%s",(f['source'],))
        conn.execute("UPDATE oracle2.drafts SET status='confirmed' WHERE source_id=%s",(f['source'],))
    if mutation=='extra_dependency':
        with psycopg.connect(f['url']) as conn:
            conn.execute('INSERT INTO oracle2.artifact_dependencies VALUES(%s,%s,1,%s,%s,%s)',(f['workspace'],m.artifact_id,'identity','unexpected','1'))
    else:
        with psycopg.connect(admin_url) as conn:
            conn.execute('INSERT INTO oracle2.artifact_invalidations(workspace_id,artifact_id,version,reason,event_id) VALUES(%s,%s,1,%s,%s)',(f['workspace'],m.artifact_id,'invented current invalidation',uuid4()))
    class NoBlob:
        def read(self,*args):raise AssertionError('invalidated/extended body opened')
    ledger.blobs=NoBlob()
    for method in (ledger.read,ledger.read_with_manifest):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):method(f['workspace'],m.artifact_id,1)


def test_executor_metadata_and_payload_read_without_raw_original_or_write(admin_url,processing,tmp_path):
    f=processing();_,m,p=persist_extraction(f,tmp_path)
    url,binding=executor_for(admin_url,f);src=ProcessingArtifactResolver(url,binding=binding)
    with pytest.raises((PermissionError,psycopg.errors.InsufficientPrivilege)):
        src.artifact_metadata(f['workspace'],m.artifact_id,1)
    seal=src.extraction_seal(f['workspace'],m.artifact_id,1)
    assert seal.manifest_hash==digest(m.model_dump(mode='json')) and seal.source_refs[0].source_id==f['source']
    assert 'private_object_key' not in seal.model_dump() and f['reading'] not in json.dumps(seal.model_dump(mode='json'))
    with pytest.raises(PermissionError):src.current_for_processing(f['workspace'],f['source'])
    with pytest.raises(PermissionError):ProcessingCompilerLedger(url,FileBlobStore(tmp_path/'executor'),principal=f['actor'],processing_sources=src)


def test_actual_clock_expiry_rolls_back_after_local_callback(admin_url,processing,tmp_path):
    f=processing();f['binding']=replace(f['binding'],expires_at=datetime.now(timezone.utc)+timedelta(seconds=.3))
    with pytest.raises(PermissionError):persist_extraction(f,tmp_path,before_commit=lambda:time.sleep(.35))
    with psycopg.connect(admin_url) as conn:
        assert conn.execute('SELECT count(*) FROM oracle2.artifact_manifests WHERE workspace_id=%s',(f['workspace'],)).fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM oracle2.operating_model_source_receipts WHERE source_id=%s',(f['source'],)).fetchone()[0]==0


@pytest.mark.parametrize('read_api',['read','read_with_manifest'])
@pytest.mark.parametrize('kind',['processing_extraction_v1','processing_failed_extraction_v1','processing_failed_assembly_v1'])
def test_executor_processing_kind_denied_before_blob(admin_url,processing,tmp_path,read_api,kind):
    f=processing(); args,m,_=bundle(f,kind=kind); commit(f,args)
    url,binding=executor_for(admin_url,f);src=ProcessingArtifactResolver(url,binding=binding)
    class NoBlob:
        def read(self,*args):raise AssertionError('executor opened restricted candidate blob')
    ledger=Ledger(url,NoBlob(),principal=f['actor'],can_read=lambda *args:False,current_source=lambda *args:None,processing_sources=src,processing_read_guard=lambda *args:None)
    with pytest.raises((PermissionError,psycopg.errors.InsufficientPrivilege)):
        getattr(ledger,read_api)(f['workspace'],m.artifact_id,1,include_failed=True)


@pytest.mark.parametrize('profile',['source-reader','gateway-metadata'])
@pytest.mark.parametrize('read_api',['read','read_with_manifest'])
def test_original_or_gateway_role_never_opens_generated_blob(admin_url,processing,tmp_path,profile,read_api):
    f=processing(profile);src=ProcessingArtifactResolver(f['url'],binding=f['binding'])
    class NoBlob:
        def read(self,*args):raise AssertionError('metadata/original role opened generated blob')
    ledger=Ledger(f['url'],NoBlob(),principal=f['actor'],can_read=lambda *args:False,current_source=lambda *args:None,
        processing_sources=src,processing_read_guard=lambda *args:None)
    with pytest.raises(PermissionError):getattr(ledger,read_api)(f['workspace'],uuid4(),1)
    with psycopg.connect(f['url']) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute('SELECT * FROM oracle2.hosting_processing_artifact(%s,%s,1,%s,%s,%s)',
                (f['workspace'],uuid4(),f['actor'],RUNTIME,REGISTRY))


@pytest.mark.parametrize('value',[True,False,object(),lambda *args:None])
def test_opt_in_extraction_boundary_rejects_untyped_guards_before_blob(processing,tmp_path,value):
    f=processing();source=ProcessingArtifactResolver(f['url'],binding=f['binding'])
    class NoBlob:
        def put(self,*args):raise AssertionError('untyped extraction authority reached blob')
        def read(self,*args):raise AssertionError('untyped extraction authority reached blob')
    with pytest.raises(PermissionError,match='exact protected'):
        ProcessingCompilerLedger(f['url'],NoBlob(),principal=f['actor'],processing_sources=source,
            processing_read_guard=lambda *args:None,processing_extraction_guard=value)


def test_opt_in_extraction_boundary_rejects_subclasses(processing,tmp_path):
    from oracle_brain.operating_model.purpose_journey import ProcessingCompilerExtractionGuardV2
    class BorrowedGuard(ProcessingCompilerExtractionGuardV2):pass
    f=processing();source=ProcessingArtifactResolver(f['url'],binding=f['binding'])
    with pytest.raises(PermissionError,match='exact protected'):
        ProcessingCompilerLedger(f['url'],FileBlobStore(tmp_path),principal=f['actor'],processing_sources=source,
            processing_read_guard=lambda *args:None,processing_extraction_guard=object.__new__(BorrowedGuard))
