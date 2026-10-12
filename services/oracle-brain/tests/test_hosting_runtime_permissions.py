"""Real native ledger scoped compiler and documentary completion permissions."""
import hashlib,json
from pathlib import Path
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from test_hosting_candidate_permissions import scoped

@pytest.fixture
def runtime_scope(admin_url,scoped):
    scripts=Path(__file__).resolve().parents[1]/'sql'
    url,workspace,other,source,appointment,artifact,login=scoped
    release,run=uuid4(),uuid4()
    reading='invented-original'
    reading_hash=hashlib.sha256(reading.encode()).hexdigest()
    with psycopg.connect(admin_url) as c:
        c.execute((scripts/'006_hosting_gateway_authority.sql').read_text())
        c.execute((scripts/'008_hosting_runtime_permissions.sql').read_text())
        # Existing test receipt was immutable invented prequalification; use a new
        # source revision so first native receipt is exercised without deletion.
        c.execute('UPDATE oracle2.sources SET revision=2 WHERE source_id=%s',(source,))
        c.execute("UPDATE oracle2.hosting_role_source_admissions SET revision=2,reading_hash=%s,parser_id=repeat('a',64) WHERE role_name=%s",(reading_hash,login))
        c.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,now()+interval \'1 hour\')',(login,'c'*64,'d'*64))
        c.execute("UPDATE oracle2.source_blocks SET text=%s WHERE source_id=%s AND kind='original-metadata'",(json.dumps({'original_hash':'a'*64,'content_hash':reading_hash,'parser_identity':'a'*64,'content_type':'text/plain','evidence_kind':'native_text','page_count':1,'review_receipt':'a'*64}),source))
        c.execute(sql.SQL('GRANT oracle2_documentary_executor TO {}').format(sql.Identifier(login)))
        ref={'workspace_id':str(workspace),'source_id':str(source),'revision':2,'original_sha256':'a'*64,'reading_sha256':reading_hash,'parser_id':'a'*64}
        watermark=c.execute('SELECT max(sequence) FROM oracle2.operating_model_change_log WHERE workspace_id=%s',(workspace,)).fetchone()[0]
        payload={'source_refs':[ref],'runtime_digest':'c'*64,'ledger_watermark':watermark,'artifact_content_hash':'e'*64}
        c.execute('INSERT INTO oracle2.operating_release_manifests VALUES(%s,%s,%s,%s,now())',(workspace,release,'f'*64,Jsonb(payload)))
        c.execute('INSERT INTO oracle2.operating_release_selectors VALUES(%s,%s,1,%s)',(workspace,release,watermark))
        actor=c.execute('SELECT principal_id FROM oracle2.hosting_role_source_admissions WHERE role_name=%s',(login,)).fetchone()[0]
        c.execute("INSERT INTO oracle2.operating_view_runs(run_id,workspace_id,actor_id,query_plan,release_id,release_hash,status,source_refs) VALUES(%s,%s,%s,%s,%s,%s,'pending',%s)",(run,workspace,actor,Jsonb({'max_bytes':1024}),release,'f'*64,Jsonb([ref])))
    return scoped,release,run,reading_hash


def test_first_receipt_and_completion(runtime_scope):
    scoped,release,run,reading_hash=runtime_scope
    with psycopg.connect(scoped[0]) as c:
        assert len(c.execute('SELECT text FROM oracle2.source_blocks').fetchall())==2
        c.execute('INSERT INTO oracle2.operating_model_source_receipts VALUES(%s,%s,2,%s,%s,%s,%s)',(scoped[1],scoped[3],'a'*64,reading_hash,'a'*64,Jsonb({'ref':{'invented':True}})))
        c.execute("SELECT oracle2.complete_documentary_view(%s,%s)",(run,canonical_bytes({'state':'coverage_incomplete','artifact_hash':'e'*64})))
        assert c.execute('SELECT status FROM oracle2.operating_view_runs WHERE run_id=%s',(run,)).fetchone()[0]=='completed'

@pytest.mark.parametrize('pack',[{'artifact_hash':'0'*64},{'artifact_hash':'e'*64,'text':'x'*2048},None])
def test_completion_bad_pack(runtime_scope,pack):
    with psycopg.connect(runtime_scope[0][0]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT oracle2.complete_documentary_view(%s,%s)",(runtime_scope[2],canonical_bytes(pack)))

@pytest.mark.parametrize('query',["UPDATE oracle2.operating_view_runs SET actor_id=gen_random_uuid()", "UPDATE oracle2.operating_view_runs SET query_plan='{}'",'UPDATE oracle2.artifact_manifests SET state=\'ready\'','UPDATE oracle2.hosting_role_runtime_admissions SET expires_at=now()',"INSERT INTO oracle2.operating_action_runs VALUES(NULL,NULL,NULL,'event_import','{}',NULL,'','pending',NULL,NULL,now(),now())"])
def test_immutable_columns_and_authority_denied(runtime_scope,query):
    with psycopg.connect(runtime_scope[0][0]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute(query)

@pytest.mark.parametrize('mutation',[
 'UPDATE oracle2.appointments SET revoked_at=now() WHERE appointment_id=%s',
 "UPDATE oracle2.hosting_role_runtime_admissions SET registry_hash=repeat('0',64) WHERE role_name=%s",
 "UPDATE oracle2.hosting_role_runtime_admissions SET expires_at=now()-interval '1 second' WHERE role_name=%s",
 'UPDATE oracle2.operating_release_selectors SET generation=generation+1,watermark=watermark+1 WHERE workspace_id=%s',
])
def test_revocation_registry_and_release_drift(admin_url,runtime_scope,mutation):
    scoped=runtime_scope[0]
    value=scoped[4] if 'appointments' in mutation else scoped[1] if 'selectors' in mutation else scoped[6]
    with psycopg.connect(admin_url) as c:c.execute(mutation,(value,))
    with psycopg.connect(scoped[0]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT oracle2.complete_documentary_view(%s,%s)",(runtime_scope[2],canonical_bytes({'artifact_hash':'e'*64})))


def test_native_first_source_ledger_persist(admin_url,runtime_scope,tmp_path):
    from oracle_brain.operating_model.authority_adapter import PostgresSources
    from oracle_brain.operating_model.artifact_storage import FileBlobStore
    from oracle_brain.operating_model.ledger import Ledger
    scoped=runtime_scope[0]
    # Restrict effective privileges to the compiler; SESSION_USER stays real LOGIN.
    url=psycopg.conninfo.make_conninfo(scoped[0],options='-c role=oracle2_candidate_compiler')
    with psycopg.connect(url) as c:
        actor=c.execute('SELECT actor_id FROM oracle2.appointments WHERE appointment_id=%s',(scoped[4],)).fetchone()[0]
    sources=PostgresSources(url)
    receipt=sources.current(scoped[1],scoped[3])
    ledger=Ledger(url,FileBlobStore(tmp_path),principal=actor,can_read=sources.can_read,current_source=sources.current)
    manifest=ledger.persist(workspace_id=scoped[1],artifact_id=uuid4(),version=1,kind='extraction',payload={'source_refs':[receipt.ref.model_dump(mode='json')]},refs=(receipt.ref,),permission_digest='a'*64,compiler_digest='c'*64)
    assert manifest.state=='ready'
    with psycopg.connect(admin_url) as c:
        assert c.execute('SELECT count(*) FROM oracle2.outbox WHERE assertion_id=%s',(manifest.artifact_id,)).fetchone()[0]==1

@pytest.mark.parametrize('text',['not-json','{}',json.dumps({'original_hash':'a'*64,'content_hash':'0'*64,'parser_identity':'a'*64})])
def test_unqualified_metadata_denied(admin_url,runtime_scope,text):
    scoped=runtime_scope[0]
    with psycopg.connect(admin_url) as c:c.execute("UPDATE oracle2.source_blocks SET text=%s WHERE source_id=%s AND kind='original-metadata'",(text,scoped[3]))
    with psycopg.connect(scoped[0]) as c:assert c.execute('SELECT text FROM oracle2.source_blocks').fetchall()==[]

@pytest.mark.parametrize('kind',['original','original-metadata'])
def test_duplicate_provenance_denied(admin_url,runtime_scope,kind):
    scoped=runtime_scope[0]
    with psycopg.connect(admin_url) as c:
        c.execute('INSERT INTO oracle2.source_blocks SELECT %s,source_id,workspace_id,99,kind,text,span_start,span_end FROM oracle2.source_blocks WHERE source_id=%s AND kind=%s',(uuid4(),scoped[3],kind))
    with psycopg.connect(scoped[0]) as c:assert c.execute('SELECT text FROM oracle2.source_blocks').fetchall()==[]


def test_wrong_receipt_and_other_workspace_insert_denied(runtime_scope):
    scoped=runtime_scope[0]
    with psycopg.connect(scoped[0]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute('INSERT INTO oracle2.operating_model_source_receipts VALUES(%s,%s,2,%s,%s,%s,%s)',(scoped[1],scoped[3],'0'*64,runtime_scope[3],'a'*64,Jsonb({})))
    with psycopg.connect(scoped[0]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("INSERT INTO oracle2.artifact_manifests VALUES(%s,%s,1,'extraction',%s,%s,%s,%s,%s,%s,'invented','ready',%s,now())",(scoped[2],uuid4(),*(['c'*64]*6),Jsonb({})))

@pytest.mark.parametrize('extra',[{'numbers':[1e20,1e-7,1.0,-0.0]}, {'unicode':'é中🙂','escapes':'"\\\n\b\t','nested':[{'a':True,'b':None}]}])
def test_exact_canonical_pack_receipt(runtime_scope,extra):
    scoped=runtime_scope[0]
    pack={'artifact_hash':'e'*64,**extra}
    data=canonical_bytes(pack)
    with psycopg.connect(scoped[0]) as c:
        c.execute('SELECT oracle2.complete_documentary_view(%s,%s)',(runtime_scope[2],data))
        raw,seal=c.execute('SELECT canonical_pack,pack_hash FROM oracle2.operating_view_pack_receipts WHERE run_id=%s',(runtime_scope[2],)).fetchone()
        assert bytes(raw)==data and seal==hashlib.sha256(data).hexdigest()
        with pytest.raises(psycopg.errors.InsufficientPrivilege): c.execute('SELECT oracle2.complete_documentary_view(%s,%s)',(runtime_scope[2],data))


def test_exact_budget_boundary(runtime_scope):
    pack={'artifact_hash':'e'*64,'numbers':[1e20,1e-7],'unicode':'中','padding':''}
    pack['padding']='x'*(1024-len(canonical_bytes(pack)))
    data=canonical_bytes(pack)
    assert len(data)==1024
    with psycopg.connect(runtime_scope[0][0]) as c:c.execute('SELECT oracle2.complete_documentary_view(%s,%s)',(runtime_scope[2],data))


def test_native_execute_view_registered_completion(admin_url,runtime_scope,tmp_path):
    import asyncio
    from types import SimpleNamespace
    from oracle_brain.operating_model.authority_adapter import PostgresSources
    from oracle_brain.operating_model.artifact_storage import FileBlobStore
    from oracle_brain.operating_model.ledger import Ledger
    from oracle_brain.operating_model.release_manifest import ReleaseManifest
    from oracle_brain.operating_model.view_jobs import execute_view
    scoped=runtime_scope[0]; workspace=scoped[1]
    compiler_url=psycopg.conninfo.make_conninfo(scoped[0],options='-c role=oracle2_candidate_compiler')
    sources=PostgresSources(compiler_url); receipt=sources.current(workspace,scoped[3]); blobs=FileBlobStore(tmp_path)
    with psycopg.connect(admin_url) as c:
        actor=c.execute('SELECT principal_id FROM oracle2.hosting_role_source_admissions WHERE role_name=%s',(scoped[6],)).fetchone()[0]
    compiler=Ledger(compiler_url,blobs,principal=actor,can_read=sources.can_read,current_source=sources.current)
    artifact=compiler.persist(workspace_id=workspace,artifact_id=uuid4(),version=1,kind='extraction',payload={'source_refs':[receipt.ref.model_dump(mode='json')]},refs=(receipt.ref,),permission_digest='a'*64,compiler_digest='c'*64)
    with psycopg.connect(admin_url) as c:
        watermark=c.execute('SELECT max(sequence) FROM oracle2.operating_model_change_log WHERE workspace_id=%s',(workspace,)).fetchone()[0]
        release=ReleaseManifest(release_id=uuid4(),workspace_id=workspace,artifact_id=artifact.artifact_id,artifact_version=1,artifact_content_hash=artifact.content_hash,
            runtime_digest='c'*64,permission_digest='a'*64,source_refs=(receipt.ref,),graph_generation=uuid4(),graph_name='oracle_operating_model_v1_invented',graph_record_digest='a'*64,
            acceptance_state='synthetic',independent_review_hash='a'*64,documentary_gate_hash='a'*64,source_inventory_hash='a'*64,ledger_watermark=watermark)
        c.execute('INSERT INTO oracle2.operating_release_manifests VALUES(%s,%s,%s,%s,now())',(workspace,release.release_id,release.content_hash(),Jsonb(release.model_dump(mode='json'))))
        c.execute('UPDATE oracle2.operating_release_selectors SET release_id=%s,generation=generation+1,watermark=%s WHERE workspace_id=%s',(release.release_id,watermark,workspace))
        c.execute('UPDATE oracle2.operating_view_runs SET release_id=%s,release_hash=%s,query_plan=%s,source_refs=%s WHERE run_id=%s',(release.release_id,release.content_hash(),Jsonb({'view':'company_overview','question':'invented','max_bytes':4096,'page':0,'page_size':25}),Jsonb([receipt.ref.model_dump(mode='json')]),runtime_scope[2]))
    doc_url=psycopg.conninfo.make_conninfo(scoped[0],options='-c role=oracle2_documentary_executor')
    current=PostgresSources(doc_url); ledger=Ledger(doc_url,blobs,principal=actor,can_read=current.can_read,current_source=current.current)
    # Only SDK network candidate retrieval is mocked. Native source authority,
    # ledger, query execution, release validation and completion are real.
    class Projection:
        graph_name=release.graph_name
        async def load(self,ledger,w,a,v):return ledger.read(w,a,v)
        async def retrieve(self,question):return SimpleNamespace(items=[])
        @property
        def rag(self):return self
    result=asyncio.run(execute_view(doc_url,runtime_scope[2],ledger=ledger,projection=Projection(),synthetic=True))
    assert result['state']=='completed'
    with psycopg.connect(doc_url) as c:
        data=c.execute('SELECT canonical_pack FROM oracle2.operating_view_pack_receipts WHERE run_id=%s',(runtime_scope[2],)).fetchone()[0]
        pack=json.loads(bytes(data)); assert pack['artifact_hash']==artifact.content_hash
        assert bytes(data)==canonical_bytes(pack)


def test_direct_completion_and_receipt_mutation_denied(runtime_scope):
    with psycopg.connect(runtime_scope[0][0]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute("UPDATE oracle2.operating_view_runs SET status='completed',pack='{}'")
    with psycopg.connect(runtime_scope[0][0]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute("DELETE FROM oracle2.operating_view_pack_receipts")

@pytest.mark.parametrize('mutation',[
 'UPDATE oracle2.operating_view_runs SET actor_id=gen_random_uuid() WHERE run_id=%s',
 "UPDATE oracle2.operating_view_runs SET release_hash=repeat('0',64) WHERE run_id=%s",
 "UPDATE oracle2.operating_view_runs SET expires_at=now()-interval '1 second' WHERE run_id=%s",
])
def test_current_canonical_job_denials(admin_url,runtime_scope,mutation):
    with psycopg.connect(admin_url) as c:c.execute(mutation,(runtime_scope[2],))
    with psycopg.connect(runtime_scope[0][0]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT oracle2.complete_documentary_view(%s,%s)',(runtime_scope[2],canonical_bytes({'artifact_hash':'e'*64})))


def test_self_only_source_runtime_binding(admin_url,runtime_scope):
    scoped=runtime_scope[0]
    with psycopg.connect(scoped[0]) as c:
        runtime,registry,expiry=c.execute('SELECT * FROM oracle2.hosting_source_runtime_binding()').fetchone()
        assert runtime=='c'*64 and registry=='d'*64
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT * FROM oracle2.hosting_role_runtime_admissions')
    with psycopg.connect(admin_url) as c:
        c.execute("UPDATE oracle2.hosting_role_runtime_admissions SET expires_at=now()-interval '1 second' WHERE role_name=%s",(scoped[6],))
    with psycopg.connect(scoped[0]) as c:assert c.execute('SELECT * FROM oracle2.hosting_source_runtime_binding()').fetchall()==[]
