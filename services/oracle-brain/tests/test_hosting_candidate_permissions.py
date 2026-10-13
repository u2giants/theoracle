"""Real SCRAM-login source/outbox isolation on an owned invented ledger."""
from pathlib import Path
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest

@pytest.fixture
def scoped(admin_url):
    workspace, other, source, actor, root, appointment, artifact = (uuid4() for _ in range(7))
    login='hosting_source_'+uuid4().hex[:12]
    scripts=Path(__file__).resolve().parents[1]/'sql'
    with psycopg.connect(admin_url,autocommit=True) as c:
        c.execute((scripts/'004_workflow_integrity.sql').read_text())
        c.execute((scripts/'007_hosting_candidate_permissions.sql').read_text())
        c.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD {}').format(sql.Identifier(login),sql.Literal('invented-test-only')))
        c.execute(sql.SQL('GRANT oracle2_candidate_compiler TO {}').format(sql.Identifier(login)))
        for w,s in [(workspace,source),(other,uuid4())]:
            c.execute("INSERT INTO oracle2.sources(source_id,workspace_id,uploaded_by,filename,content_type,status) VALUES(%s,%s,%s,'invented','text/plain','draft')",(s,w,actor))
            c.execute("INSERT INTO oracle2.drafts(draft_id,source_id,workspace_id,created_by,process_name,status) VALUES(%s,%s,%s,%s,'invented','confirmed')",(uuid4(),s,w,actor))
            for i,kind in enumerate(['original','original-metadata','chunk']):
                c.execute('INSERT INTO oracle2.source_blocks VALUES(%s,%s,%s,%s,%s,%s,0,1)',(uuid4(),s,w,i,kind,'invented-'+kind))
        c.execute("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by) VALUES(%s,%s,%s,'root',%s)",(root,workspace,uuid4(),uuid4()))
        c.execute("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id) VALUES(%s,%s,%s,%s,%s,%s)",(appointment,workspace,actor,'source-read:'+str(source),uuid4(),root))
        c.execute('INSERT INTO oracle2.operating_model_source_receipts VALUES(%s,%s,1,%s,%s,%s,%s)',(workspace,source,'a'*64,'b'*64,'invented',Jsonb({})))
        c.execute("INSERT INTO oracle2.hosting_role_source_admissions VALUES(%s,%s,%s,1,%s,%s,%s,'invented',%s,%s,now()+interval '1 hour')",(login,workspace,source,actor,'a'*64,'b'*64,'c'*64,'d'*64))
        c.execute("INSERT INTO oracle2.artifact_manifests VALUES(%s,%s,1,'documentary',%s,%s,%s,%s,%s,%s,'invented','ready',%s,now())",(workspace,artifact,*(['e'*64]*6),Jsonb({'invented':True})))
    url=psycopg.conninfo.make_conninfo(admin_url,user=login,password='invented-test-only')
    return url,workspace,other,source,appointment,artifact,login


def test_session_login_originals_only(scoped):
    with psycopg.connect(scoped[0]) as c:
        assert c.execute('SELECT kind FROM oracle2.source_blocks ORDER BY kind').fetchall()==[('original',),('original-metadata',)]
        assert c.execute('SELECT * FROM oracle2.source_blocks WHERE workspace_id=%s',(scoped[2],)).fetchall()==[]
        c.execute('SET ROLE oracle2_candidate_compiler')
        assert len(c.execute('SELECT text FROM oracle2.source_blocks').fetchall())==2

@pytest.mark.parametrize('mutation',[
    'UPDATE oracle2.appointments SET revoked_at=now() WHERE appointment_id=%s',
    'UPDATE oracle2.sources SET revision=2 WHERE source_id=%s',
    "UPDATE oracle2.hosting_role_source_admissions SET expires_at=now()-interval '1 second' WHERE source_id=%s",
    "UPDATE oracle2.hosting_role_source_admissions SET reading_hash=repeat('f',64) WHERE source_id=%s",
    "UPDATE oracle2.drafts SET status='withdrawn' WHERE source_id=%s",
])
def test_current_denials(admin_url,scoped,mutation):
    with psycopg.connect(admin_url) as c:
        c.execute(mutation,(scoped[4] if 'appointments' in mutation else scoped[3],))
    with psycopg.connect(scoped[0]) as c:
        assert c.execute('SELECT text FROM oracle2.source_blocks').fetchall()==[]

@pytest.mark.parametrize('query',[
 'UPDATE oracle2.sources SET status=\'confirmed\'',
 'UPDATE oracle2.appointments SET revoked_at=NULL',
 'SELECT * FROM oracle2.hosting_role_source_admissions',
 'INSERT INTO oracle2.accepted VALUES(NULL,NULL,1,\'active\',\'{}\')',
])
def test_no_authority_writes(scoped,query):
    with psycopg.connect(scoped[0]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege): c.execute(query)

@pytest.mark.parametrize('variant',['valid','namespace','manifest','extra','knowledge','withdraw','other-workspace'])
def test_candidate_outbox_only(scoped,variant):
    payload={'namespace':'oracle_operating_model_v1','manifest':{'invented':True}}
    if variant=='namespace': payload['namespace']='knowledge'
    if variant=='manifest': payload['manifest']={}
    if variant=='extra': payload['actor']='invented'
    assertion=uuid4() if variant=='knowledge' else scoped[5]
    workspace=scoped[2] if variant=='other-workspace' else scoped[1]
    with psycopg.connect(scoped[0]) as c:
        args=(uuid4(),workspace,assertion,'withdraw' if variant=='withdraw' else 'project',Jsonb(payload))
        statement='INSERT INTO oracle2.outbox(event_id,workspace_id,assertion_id,revision,operation,payload) VALUES(%s,%s,%s,1,%s,%s)'
        if variant=='valid': c.execute(statement,args)
        else:
            with pytest.raises(psycopg.errors.InsufficientPrivilege): c.execute(statement,args)


def test_unregistered_actual_login(admin_url,scoped):
    login='hosting_unregistered_'+uuid4().hex[:12]
    with psycopg.connect(admin_url,autocommit=True) as c:
        c.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(login),sql.Literal('invented-test-only')))
        c.execute(sql.SQL('GRANT oracle2_candidate_compiler TO {}').format(sql.Identifier(login)))
    url=psycopg.conninfo.make_conninfo(admin_url,user=login,password='invented-test-only')
    with psycopg.connect(url) as c:
        assert c.execute('SELECT text FROM oracle2.source_blocks').fetchall()==[]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("INSERT INTO oracle2.outbox(event_id,workspace_id,assertion_id,revision,operation,payload) VALUES(%s,%s,%s,1,'project',%s)",(uuid4(),scoped[1],scoped[5],Jsonb({'namespace':'oracle_operating_model_v1','manifest':{'invented':True}})))


def test_documentary_executor_cannot_compile_outbox(admin_url,scoped):
    login='hosting_documentary_'+uuid4().hex[:12]
    with psycopg.connect(admin_url,autocommit=True) as c:
        c.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(login),sql.Literal('invented-test-only')))
        c.execute(sql.SQL('GRANT oracle2_documentary_executor TO {}').format(sql.Identifier(login)))
    url=psycopg.conninfo.make_conninfo(admin_url,user=login,password='invented-test-only')
    with psycopg.connect(url) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("INSERT INTO oracle2.outbox(event_id,workspace_id,assertion_id,revision,operation,payload) VALUES(%s,%s,%s,1,'project',%s)",(uuid4(),scoped[1],scoped[5],Jsonb({'namespace':'oracle_operating_model_v1','manifest':{'invented':True}})))
