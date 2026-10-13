"""Actual dedicated PostgreSQL column grants and current job authority."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb
import pytest

from oracle_brain.hosting.job_authority import PostgresJobAuthority
from oracle_brain.operating_model.release_manifest import ReleaseManifest
from oracle_brain.operating_model.source_receipts import SourceRef
from oracle_brain.operating_model.contracts import digest

RUNTIME = "a" * 64


@pytest.fixture(scope="module")
def gateway_database(admin_url):
    sql = Path(__file__).resolve().parents[1] / "sql"
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute((sql / "004_workflow_integrity.sql").read_text())
        conn.execute((sql / "006_hosting_gateway_authority.sql").read_text())
        for migration in ("007_hosting_candidate_permissions.sql", "008_hosting_runtime_permissions.sql", "010_hosting_job_permissions.sql"):
            conn.execute((sql / migration).read_text())
        login='oracle2_gateway_test_'+uuid4().hex[:12]
        conn.execute(psycopg.sql.SQL("CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS PASSWORD {}").format(
            psycopg.sql.Identifier(login),psycopg.sql.Literal('invented-public-gateway-test-only')))
        conn.execute(psycopg.sql.SQL('GRANT oracle2_gateway_metadata TO {}').format(psycopg.sql.Identifier(login)))
    # Actual unprivileged LOGIN, not merely SET ROLE from a superuser session.
    return psycopg.conninfo.make_conninfo(admin_url,user=login,password='invented-public-gateway-test-only',
                                         options="-c role=oracle2_gateway_metadata")


@pytest.fixture
def fixture_job(admin_url, gateway_database):
    workspace, source, artifact, actor, root_actor, run, release = (uuid4() for _ in range(7))
    root_appointment, source_appointment = uuid4(), uuid4()
    ref = SourceRef(workspace_id=workspace, source_id=source, revision=1,
                    original_sha256="b" * 64, reading_sha256="c" * 64, parser_id="invented-parser")
    with psycopg.connect(admin_url) as conn:
        conn.execute("INSERT INTO oracle2.sources(source_id,workspace_id,uploaded_by,filename,content_type,status) VALUES(%s,%s,%s,'invented','text/plain','draft')", (source,workspace,actor))
        conn.execute("INSERT INTO oracle2.drafts(draft_id,source_id,workspace_id,created_by,process_name,status) VALUES(%s,%s,%s,%s,'invented','confirmed')", (uuid4(),source,workspace,actor))
        conn.execute("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by) VALUES(%s,%s,%s,'root',%s)", (root_appointment,workspace,root_actor,uuid4()))
        conn.execute("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id) VALUES(%s,%s,%s,%s,%s,%s)", (source_appointment,workspace,actor,'source-read:'+str(source),root_actor,root_appointment))
        conn.execute("INSERT INTO oracle2.operating_model_source_receipts VALUES(%s,%s,1,%s,%s,%s,%s)", (workspace,source,ref.original_sha256,ref.reading_sha256,ref.parser_id,Jsonb({'reading':'invented private original','ref':ref.model_dump(mode='json')})))
        content_hash, permission = "d" * 64, "e" * 64
        conn.execute("""INSERT INTO oracle2.artifact_manifests(workspace_id,artifact_id,version,kind,input_digest,source_digest,permission_digest,compiler_digest,dependency_digest,content_hash,private_object_key,state,manifest)
            VALUES(%s,%s,1,'documentary',%s,%s,%s,%s,%s,%s,'private-secret-location','ready','{}')""", (workspace,artifact,digest({}),digest({'refs':[ref.model_dump(mode='json')]}),permission,RUNTIME,digest({}),content_hash))
        conn.execute("INSERT INTO oracle2.artifact_dependencies VALUES(%s,%s,1,'source',%s,'1')",(workspace,artifact,str(source)))
        watermark=conn.execute("SELECT max(sequence) FROM oracle2.operating_model_change_log WHERE workspace_id=%s",(workspace,)).fetchone()[0]
        manifest=ReleaseManifest(release_id=release,workspace_id=workspace,artifact_id=artifact,artifact_version=1,
            artifact_content_hash=content_hash,runtime_digest=RUNTIME,permission_digest=permission,source_refs=(ref,),
            graph_generation=uuid4(),graph_name='oracle_operating_model_v1_invented',graph_record_digest='f'*64,
            acceptance_state='synthetic',independent_review_hash='1'*64,documentary_gate_hash='2'*64,
            source_inventory_hash='3'*64,ledger_watermark=watermark)
        conn.execute("INSERT INTO oracle2.operating_release_manifests(workspace_id,release_id,content_hash,payload) VALUES(%s,%s,%s,%s)",(workspace,release,manifest.content_hash(),Jsonb(manifest.model_dump(mode='json'))))
        conn.execute("INSERT INTO oracle2.operating_release_selectors VALUES(%s,%s,1,%s)",(workspace,release,watermark))
        conn.execute("INSERT INTO oracle2.operating_view_runs(run_id,workspace_id,actor_id,query_plan,release_id,release_hash,status,source_refs,pack) VALUES(%s,%s,%s,%s,%s,%s,'pending',%s,%s)", (run,workspace,actor,Jsonb({'private_query':'invented'}),release,manifest.content_hash(),Jsonb([ref.model_dump(mode='json')]),Jsonb({'original':'invented private output'})))
    row={'job_id':str(uuid4()),'workspace_id':str(workspace),'run_id':str(run),'scope':'documentary-view','admission_hash':'2'*64,'active':True,'expires_at':9999999999}
    return row,workspace,source,artifact,actor,run,release,source_appointment,root_appointment,manifest.content_hash()


def authority(url, fixture):
    return PostgresJobAuthority(url,runtime_hash=RUNTIME,synthetic=True,allowed_release_hashes=frozenset({fixture[9]}))


def test_actual_gateway_role_validates_metadata_only(gateway_database,fixture_job):
    authority(gateway_database,fixture_job)(fixture_job[0])
    with psycopg.connect(gateway_database) as conn:
        assert conn.execute('SELECT current_user').fetchone()[0]=='oracle2_gateway_metadata'
        conn.execute('RESET ROLE')
        assert conn.execute('SELECT rolsuper FROM pg_roles WHERE rolname=session_user').fetchone()[0] is False
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute('SELECT text FROM oracle2.source_blocks')


@pytest.mark.parametrize('query',[
    'SELECT pack FROM oracle2.operating_view_runs',
    'SELECT query_plan FROM oracle2.operating_view_runs',
    'SELECT receipt FROM oracle2.operating_model_source_receipts',
    'SELECT text FROM oracle2.source_blocks',
    'SELECT payload FROM oracle2.operating_action_runs',
    'SELECT private_object_key FROM oracle2.artifact_manifests',
    "UPDATE oracle2.sources SET status='error'",
])
def test_real_postgres_denies_private_columns_and_writes(gateway_database,query):
    with psycopg.connect(gateway_database) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(query)


@pytest.mark.parametrize('mutation',[
    "UPDATE oracle2.appointments SET revoked_at=now() WHERE appointment_id=%s",
    "UPDATE oracle2.appointments SET expires_at=now()-interval '1 second' WHERE appointment_id=%s",
])
def test_appointment_revocation_or_expiry_denies_before_enqueue(admin_url,gateway_database,fixture_job,mutation):
    row,*_=fixture_job
    authority(gateway_database,fixture_job)(row)
    with psycopg.connect(admin_url) as conn:
        conn.execute(mutation,(fixture_job[7],))
    queue=[]
    with pytest.raises(PermissionError):
        with authority(gateway_database,fixture_job).hold(row):
            queue.append(row['job_id'])
    assert not queue


def test_parent_revocation_denies(admin_url,gateway_database,fixture_job):
    with psycopg.connect(admin_url) as conn:
        conn.execute('UPDATE oracle2.appointments SET revoked_at=now() WHERE appointment_id=%s',(fixture_job[8],))
    with pytest.raises(PermissionError):authority(gateway_database,fixture_job)(fixture_job[0])


@pytest.mark.parametrize('change',[
    "UPDATE oracle2.sources SET status='error' WHERE source_id=%s",
    "UPDATE oracle2.sources SET revision=revision+1 WHERE source_id=%s",
    "UPDATE oracle2.drafts SET status='withdrawn' WHERE source_id=%s",
])
def test_source_withdrawal_and_watermark_drift_denied(admin_url,gateway_database,fixture_job,change):
    with psycopg.connect(admin_url) as conn:conn.execute(change,(fixture_job[2],))
    with pytest.raises(PermissionError):authority(gateway_database,fixture_job)(fixture_job[0])


@pytest.mark.parametrize('field',['workspace_id','run_id'])
def test_foreign_run_and_workspace_denied(gateway_database,fixture_job,field):
    row={**fixture_job[0],field:str(uuid4())}
    with pytest.raises(PermissionError):authority(gateway_database,fixture_job)(row)


def test_finding_helper_never_exposes_note_and_requires_scope(admin_url,gateway_database,fixture_job):
    row,workspace,_,_,actor,_,release,*_=fixture_job
    run=uuid4()
    with psycopg.connect(admin_url) as conn:
        release_hash=conn.execute('SELECT content_hash FROM oracle2.operating_release_manifests WHERE workspace_id=%s AND release_id=%s',(workspace,release)).fetchone()[0]
        conn.execute("INSERT INTO oracle2.operating_action_runs(run_id,workspace_id,actor_id,operation,payload,release_id,release_hash,status) VALUES(%s,%s,%s,'finding_review',%s,%s,%s,'pending')",(run,workspace,actor,Jsonb({'scope':'invented-scope','note':'invented private note'}),release,release_hash))
    scoped={**row,'scope':'finding-review','run_id':str(run)}
    with psycopg.connect(gateway_database) as conn:
        data=conn.execute('SELECT * FROM oracle2.gateway_action_metadata(%s,%s)',(workspace,run)).fetchone()
        assert data[4:] == ('finding_review','invented-scope')
        assert 'invented private note' not in str(data)
    with pytest.raises(PermissionError):authority(gateway_database,fixture_job)(scoped)


def test_unknown_semantic_scope_fails_closed(gateway_database,fixture_job):
    with pytest.raises(PermissionError):
        authority(gateway_database,fixture_job)({**fixture_job[0],'scope':'semantic-verification'})


def test_dynamic_resolver_uses_actual_run_identity(gateway_database,fixture_job):
    row=fixture_job[0]
    actual=authority(gateway_database,fixture_job).resolve(row['run_id'],'a'*64,row['admission_hash'])
    assert actual['job_id']==row['run_id']
    assert actual['workspace_id']==row['workspace_id']
    assert actual['scope']=='documentary-view'


@pytest.mark.parametrize('runtime,admission',[('b'*64,'2'*64),('a'*64,'3'*64)])
def test_dynamic_resolver_denies_unsealed_admission(gateway_database,fixture_job,runtime,admission):
    with pytest.raises(PermissionError):
        authority(gateway_database,fixture_job).resolve(fixture_job[0]['run_id'],runtime,admission)


def test_dynamic_resolver_denies_unreviewed_release(gateway_database,fixture_job):
    resolver=PostgresJobAuthority(gateway_database,runtime_hash='a'*64,synthetic=True,allowed_release_hashes=frozenset({'f'*64}))
    with pytest.raises(PermissionError):resolver.resolve(fixture_job[0]['run_id'],'a'*64,'2'*64)


@pytest.mark.parametrize('mutation',[
    "UPDATE oracle2.operating_view_runs SET status='completed' WHERE run_id=%s",
    "UPDATE oracle2.operating_view_runs SET expires_at=now()-interval '1 second' WHERE run_id=%s",
])
def test_dynamic_resolver_denies_stale_run(admin_url,gateway_database,fixture_job,mutation):
    with psycopg.connect(admin_url) as conn:conn.execute(mutation,(fixture_job[5],))
    with pytest.raises(PermissionError):authority(gateway_database,fixture_job).resolve(str(fixture_job[5]),'a'*64,'2'*64)
