"""Actual NOINHERIT LOGIN: documentary custody and scoped finding review."""
import json
from pathlib import Path
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from test_hosting_runtime_permissions import runtime_scope
from test_hosting_candidate_permissions import scoped
from oracle_brain.hosting.job_authority import PostgresJobAuthority
from oracle_brain.operating_model.source_binding import SourceRoleBinding
from oracle_brain.operating_model.authority_adapter import PostgresSources
from oracle_brain.operating_model.artifact_storage import FileBlobStore
from oracle_brain.operating_model.ledger import Ledger
from oracle_brain.operating_model.release_manifest import ReleaseManifest
from oracle_brain.operating_model.findings import import_legacy
from oracle_brain.operating_model.action_jobs import execute_review

@pytest.fixture
def native_job(admin_url,runtime_scope,tmp_path):
    s=runtime_scope[0]; workspace=s[1]
    compiler_url=psycopg.conninfo.make_conninfo(s[0],options='-c role=oracle2_candidate_compiler')
    sources=PostgresSources(compiler_url,source_binding=SourceRoleBinding('c'*64,'d'*64,synthetic=True))
    receipt=sources.current(workspace,s[3]); blobs=FileBlobStore(tmp_path)
    with psycopg.connect(admin_url) as c:
        actor=c.execute('SELECT principal_id FROM oracle2.hosting_role_source_admissions WHERE role_name=%s',(s[6],)).fetchone()[0]
        root=c.execute('SELECT parent_id FROM oracle2.appointments WHERE appointment_id=%s',(s[4],)).fetchone()[0]
        review_appointment=uuid4()
        c.execute("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id) VALUES(%s,%s,%s,'finding-review:workflow',%s,%s)",(review_appointment,workspace,actor,uuid4(),root))
    finding=import_legacy(workspace_id=workspace,refs=(receipt.ref,),scope='workflow',texts=['invented gap'])[0]
    compiler=Ledger(compiler_url,blobs,principal=actor,can_read=sources.can_read,current_source=sources.current)
    artifact=compiler.persist(workspace_id=workspace,artifact_id=uuid4(),version=1,kind='extraction',
        payload={'source_refs':[receipt.ref.model_dump(mode='json')],'findings':[finding.model_dump(mode='json')]},
        refs=(receipt.ref,),permission_digest='a'*64,compiler_digest='c'*64)
    with psycopg.connect(admin_url) as c:
        watermark=c.execute('SELECT max(sequence) FROM oracle2.operating_model_change_log WHERE workspace_id=%s',(workspace,)).fetchone()[0]
        release=ReleaseManifest(release_id=uuid4(),workspace_id=workspace,artifact_id=artifact.artifact_id,artifact_version=1,
            artifact_content_hash=artifact.content_hash,runtime_digest='c'*64,permission_digest='a'*64,source_refs=(receipt.ref,),
            graph_generation=uuid4(),graph_name='oracle_operating_model_v1_invented',graph_record_digest='a'*64,
            acceptance_state='synthetic',independent_review_hash='a'*64,documentary_gate_hash='a'*64,source_inventory_hash='a'*64,ledger_watermark=watermark)
        c.execute('INSERT INTO oracle2.operating_release_manifests VALUES(%s,%s,%s,%s,now())',(workspace,release.release_id,release.content_hash(),Jsonb(release.model_dump(mode='json'))))
        c.execute('UPDATE oracle2.operating_release_selectors SET release_id=%s,generation=generation+1,watermark=%s WHERE workspace_id=%s',(release.release_id,watermark,workspace))
        c.execute('UPDATE oracle2.operating_view_runs SET release_id=%s,release_hash=%s,source_refs=%s WHERE run_id=%s',(release.release_id,release.content_hash(),Jsonb([receipt.ref.model_dump(mode="json")]),runtime_scope[2]))
        review=uuid4(); payload={'finding_id':finding.finding_id,'scope':'workflow','action':'annotate','note':'invented annotation'}
        c.execute("INSERT INTO oracle2.operating_action_runs(run_id,workspace_id,actor_id,operation,payload,release_id,release_hash,status) VALUES(%s,%s,%s,'finding_review',%s,%s,%s,'pending')",(review,workspace,actor,Jsonb(payload),release.release_id,release.content_hash()))
        c.execute(sql.SQL('ALTER ROLE {} NOINHERIT').format(sql.Identifier(s[6])))
    doc_url=psycopg.conninfo.make_conninfo(s[0],options='-c role=oracle2_documentary_executor')
    current=PostgresSources(doc_url,source_binding=SourceRoleBinding('c'*64,'d'*64,synthetic=True))
    ledger=Ledger(doc_url,blobs,principal=actor,can_read=current.can_read,current_source=current.current)
    authority=PostgresJobAuthority(doc_url,runtime_hash='c'*64,synthetic=True,allowed_release_hashes=frozenset({release.content_hash()}))
    return s,doc_url,runtime_scope[2],review,ledger,authority,release,review_appointment


def test_actual_role_resolves_documentary_job(native_job):
    s,url,run,_,_,authority,*_=native_job
    with psycopg.connect(url) as c:
        assert c.execute('SELECT current_user,SESSION_USER').fetchone()==('oracle2_documentary_executor',s[6])
        assert c.execute('SELECT rolinherit FROM pg_roles WHERE rolname=SESSION_USER').fetchone()==(False,)
    assert authority.resolve(str(run),'c'*64,'a'*64)['scope']=='documentary-view'


def test_native_finding_review_preserves_append_only_capability(native_job):
    s,url,_,run,ledger,authority,release,_=native_job
    assert authority.resolve(str(run),'c'*64,'a'*64)['scope']=='finding-review'
    outcome=execute_review(url,run,s[1],ledger,True)
    assert outcome=={'state':'completed','run_id':str(run),'review_recorded':True,'policy_promoted':False}
    assert execute_review(url,run,s[1],ledger,True)==outcome
    assert len(ledger.review_events(s[1],release.artifact_id,1))==1


@pytest.mark.parametrize('foreign',[False,True])
def test_global_duplicate_identity_denied(admin_url,native_job,foreign):
    s,url,run,_,_,authority,release,_=native_job
    with psycopg.connect(admin_url) as c:
        c.execute("INSERT INTO oracle2.operating_action_runs(run_id,workspace_id,actor_id,operation,payload,release_id,release_hash,status) VALUES(%s,%s,%s,'event_import','{}',%s,%s,'pending')",(run,s[2] if foreign else s[1],uuid4(),release.release_id,release.content_hash()))
    with pytest.raises(PermissionError):authority.resolve(str(run),'c'*64,'a'*64)


@pytest.mark.parametrize('query',[
 'UPDATE oracle2.operating_action_runs SET status=\'completed\'',
 'DELETE FROM oracle2.finding_events',
 "INSERT INTO oracle2.finding_events VALUES(gen_random_uuid(),'x',gen_random_uuid(),gen_random_uuid(),'x','annotate','{}',now())",
 'SELECT * FROM oracle2.hosting_role_runtime_admissions',
])
def test_executor_direct_mutations_and_authority_denied(native_job,query):
    with psycopg.connect(native_job[1]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute(query)


@pytest.mark.parametrize('mutation',['review-revoked','runtime-expired','source-expired','selector-drift','wrong-actor','lease-expired','event-import'])
def test_current_job_denials(admin_url,native_job,mutation):
    s,url,_,run,ledger,authority,release,appointment=native_job
    with psycopg.connect(admin_url) as c:
        if mutation=='review-revoked':c.execute('UPDATE oracle2.appointments SET revoked_at=now() WHERE appointment_id=%s',(appointment,))
        elif mutation=='runtime-expired':c.execute("UPDATE oracle2.hosting_role_runtime_admissions SET expires_at=now()-interval '1 second' WHERE role_name=%s",(s[6],))
        elif mutation=='source-expired':c.execute("UPDATE oracle2.hosting_role_source_admissions SET expires_at=now()-interval '1 second' WHERE role_name=%s",(s[6],))
        elif mutation=='selector-drift':c.execute('UPDATE oracle2.operating_release_selectors SET watermark=watermark+1 WHERE workspace_id=%s',(s[1],))
        elif mutation in {'wrong-actor','lease-expired','event-import'}:
            original=run; run=uuid4()
            c.execute("""INSERT INTO oracle2.operating_action_runs(run_id,workspace_id,actor_id,operation,payload,release_id,release_hash,status,expires_at)
                SELECT %s,workspace_id,%s,%s,payload,release_id,release_hash,'pending',
                CASE WHEN %s THEN clock_timestamp()-interval '1 second' ELSE expires_at END
                FROM oracle2.operating_action_runs WHERE run_id=%s""",
                (run,uuid4() if mutation=='wrong-actor' else ledger.principal,
                 'event_import' if mutation=='event-import' else 'finding_review',mutation=='lease-expired',original))
    with pytest.raises(PermissionError):authority.resolve(str(run),'c'*64,'a'*64)
    with psycopg.connect(url) as c:
        assert c.execute('SELECT * FROM oracle2.operating_action_runs WHERE run_id=%s',(run,)).fetchall()==[]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT oracle2.complete_hosted_finding_review(%s)',(run,))


def test_completion_without_recorded_event_denied(native_job):
    with psycopg.connect(native_job[1]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT oracle2.complete_hosted_finding_review(%s)',(native_job[3],))


@pytest.mark.parametrize('field,value',[('note','changed'),('artifact_id',str(uuid4())),('version',2),('finding_hash','bad')])
def test_review_append_exact_binding_denied(native_job,field,value):
    *_,release,_=native_job
    event={'artifact_id':str(release.artifact_id),'version':1,'finding_hash':'a'*64,'note':'invented annotation'};event[field]=value
    with psycopg.connect(native_job[1]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT oracle2.append_hosted_finding_review(%s,%s)',(native_job[3],Jsonb(event)))


def test_real_executor_claims_existing_admitted_job(native_job,tmp_path):
    import time
    from oracle_brain.hosting.custody import FileCustody
    from oracle_brain.hosting.gateway import OpaqueJob
    from oracle_brain.operating_model.contracts import digest
    _,_,run,_,_,authority,release,_=native_job
    worker='spiffe://oracle/synthetic-worker'
    record={'worker_uri':worker,'runtime_hash':'c'*64,'active':True,'expires_at':int(time.time())+120,'allowed_release_hashes':[release.content_hash()]}
    registry=tmp_path/'registry';registry.write_text(json.dumps(record));spool=tmp_path/'spool';spool.mkdir()
    custody=FileCustody(registry=registry,spool=spool,trusted_registry_hash=digest(record),runtime_hash='c'*64,worker_uri=worker,job_authority=authority)
    job=OpaqueJob(str(run),'c'*64,'a'*64,str(uuid4()),int(time.time())+60)
    custody.admit(job,worker)
    claimed,row=custody.claim()
    assert claimed==job and row['scope']=='documentary-view'
    assert len(list(spool.glob('*.claimed')))==1 and not list(spool.glob('*.pending'))
    assert custody.claim() is None


def test_collision_after_resolve_is_denied_at_hold(admin_url,native_job):
    s,_,run,_,_,authority,release,_=native_job
    row=authority.resolve(str(run),'c'*64,'a'*64)
    with psycopg.connect(admin_url) as c:
        c.execute("INSERT INTO oracle2.operating_action_runs(run_id,workspace_id,actor_id,operation,payload,release_id,release_hash,status) VALUES(%s,%s,%s,'event_import','{}',%s,%s,'pending')",(run,s[2],uuid4(),release.release_id,release.content_hash()))
    with pytest.raises(PermissionError):
        with authority.hold(row):pass
