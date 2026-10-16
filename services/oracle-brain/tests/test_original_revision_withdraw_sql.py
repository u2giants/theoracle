"""Actual revision withdrawal and explicit later pending head, no auto grants."""
from uuid import uuid4
import psycopg
from psycopg.types.json import Jsonb
import pytest
from test_replacement_source_intake_sql import requester,call,reserve,custody
from test_source_intake_reconcile_sql import read_grant
from test_original_population_sql import raw_reader


def ready(x):
    e=reserve(x);r=e['reservation'];call(x,'finalize_source_revision_v1',r['reservation_id'],0,Jsonb(custody(e)))
    leaf=read_grant(x,r['source_id']);payload={'reason':'Invented obsolete source','expected_context':custody(e)['expected_context'],'caller_deadline':x['until'].isoformat()}
    return e,r,leaf,payload


def test_revision_withdraw_is_atomic_immutable_idempotent_and_new_head_not_qualified(requester):
    x=requester;e,r,leaf,p=ready(x);key=uuid4()
    first=call(x,'withdraw_original_revision_v1',r['source_id'],1,Jsonb(p),key)
    again=call(x,'withdraw_original_revision_v1',r['source_id'],1,Jsonb(p),key)
    assert first['event_id']==again['event_id'] and first['withdrawn']
    with psycopg.connect(x['admin']) as c:
        assert c.execute('SELECT count(*) FROM oracle2.source_original_withdrawals_v1 WHERE source_id=%s',(r['source_id'],)).fetchone()[0]==1
        assert c.execute('SELECT status FROM oracle2.sources WHERE source_id=%s',(r['source_id'],)).fetchone()[0]=='error'
        assert c.execute('SELECT count(*) FROM oracle2.source_original_revisions WHERE source_id=%s',(r['source_id'],)).fetchone()[0]==1
    p['reason']='Changed request'
    with pytest.raises(psycopg.errors.UniqueViolation):call(x,'withdraw_original_revision_v1',r['source_id'],1,Jsonb(p),key)
    next_e=reserve(x,source=r['source_id'],head=1)
    result=call(x,'finalize_source_revision_v1',next_e['reservation']['reservation_id'],1,Jsonb(custody(next_e)))
    assert result['snapshot']['revision']==2 and result['snapshot']['qualifiedSourceRef'] is None
    with psycopg.connect(x['admin']) as c:
        assert c.execute('SELECT revision FROM oracle2.source_original_withdrawals_v1 WHERE source_id=%s',(r['source_id'],)).fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM oracle2.hosting_original_source_admissions WHERE source_id=%s AND revision=2',(r['source_id'],)).fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM oracle2.source_reading_qualifications WHERE source_id=%s',(r['source_id'],)).fetchone()[0]==0

@pytest.mark.parametrize('change',['read','intake','identity','deadline','head'])
def test_withdraw_requires_current_exact_authority_before_any_event(requester,change):
    x=requester;e,r,leaf,p=ready(x)
    if change in ('read','intake'):
        with psycopg.connect(x['admin']) as c:c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(leaf if change=='read' else x['leaf'],))
    elif change=='identity':p['expected_context']['principal_id']=str(uuid4())
    elif change=='deadline':p['caller_deadline']='2000-01-01T00:00:00+00:00'
    with pytest.raises((psycopg.errors.InsufficientPrivilege,psycopg.errors.SerializationFailure)):
        call(x,'withdraw_original_revision_v1',r['source_id'],2 if change=='head' else 1,Jsonb(p),uuid4())
    with psycopg.connect(x['admin']) as c:
        assert c.execute('SELECT count(*) FROM oracle2.source_original_withdrawals_v1 WHERE source_id=%s',(r['source_id'],)).fetchone()[0]==0
        assert c.execute('SELECT status FROM oracle2.sources WHERE source_id=%s',(r['source_id'],)).fetchone()[0]=='processing'


def test_withdraw_holds_affected_journey_and_invalidates_complete_artifact_closure(requester):
    from oracle_brain.operating_model.contracts import digest
    x=requester;e,r,leaf,p=ready(x);parent,child,run=uuid4(),uuid4(),uuid4()
    with psycopg.connect(x['admin']) as c:
        for artifact in (parent,child):
            c.execute("INSERT INTO oracle2.artifact_manifests(workspace_id,artifact_id,version,kind,input_digest,source_digest,permission_digest,compiler_digest,dependency_digest,content_hash,private_object_key,state,manifest) VALUES(%s,%s,1,'invented-component',%s,%s,%s,%s,%s,%s,'invented-not-read','ready','{}')",(x['workspace'],artifact,*(['a'*64]*6)))
        c.execute("INSERT INTO oracle2.artifact_dependencies VALUES(%s,%s,1,'source',%s,'1'),(%s,%s,1,'artifact',%s,'1')",(x['workspace'],parent,r['source_id'],x['workspace'],child,str(parent)))
        c.execute("INSERT INTO oracle2.runs(run_id,workspace_id,actor_id,source_id,question,status) VALUES(%s,%s,%s,%s,'given-state component','completed')",(run,x['workspace'],x['actor'],r['source_id']))
        refs=[{'source_id':r['source_id']}]
        c.execute("INSERT INTO oracle2.processing_journey_runs_v1(run_id,workspace_id,actor_id,journey_revision,population_sha256,original_population,state,answer_hold) VALUES(%s,%s,%s,1,%s,%s,'delivered',false)",(run,x['workspace'],x['actor'],digest(refs),Jsonb(refs)))
    call(x,'withdraw_original_revision_v1',r['source_id'],1,Jsonb(p),uuid4())
    with psycopg.connect(x['admin']) as c:
        assert set(v[0] for v in c.execute('SELECT artifact_id FROM oracle2.artifact_invalidations WHERE workspace_id=%s',(x['workspace'],)))=={parent,child}
        assert c.execute('SELECT answer_hold,state,journey_revision FROM oracle2.processing_journey_runs_v1 WHERE run_id=%s',(run,)).fetchone()==(True,'error',2)
        assert c.execute('SELECT count(*) FROM oracle2.artifact_manifests WHERE workspace_id=%s',(x['workspace'],)).fetchone()[0]==2


def test_new_raw_roles_ignore_old_unversioned_draft_but_exact_revision_and_root_deny(raw_reader,requester):
    x=raw_reader;ref=x['refs'][0]
    with psycopg.connect(x['admin']) as c:
        c.execute("INSERT INTO oracle2.drafts(draft_id,source_id,workspace_id,created_by,process_name,status) VALUES(%s,%s,%s,%s,'old unversioned history','withdrawn')",(uuid4(),ref.source_id,x['workspace'],x['actor']))
    assert call(x,'original_revision_read_v1',ref.source_id,1)['private_object_key']
    with psycopg.connect(x['admin']) as c:c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(x['root'],))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):call(x,'original_population_current_v1',x['population'].population_id)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):call(x,'original_revision_read_v1',ref.source_id,1)


def test_explicit_new_head_cannot_reuse_old_raw_admission(raw_reader,requester):
    x=raw_reader;u=requester;ref=x['refs'][0];read_grant(u,str(ref.source_id))
    context={k:v for k,v in [('principal_id',str(u['actor'])),('workspace_id',str(u['workspace'])),('session_role',u['login']),('runtime_hash',u['runtime']),('source_registry_hash',u['registry'])]}
    p={'reason':'invented superseded original','expected_context':context,'caller_deadline':u['until'].isoformat()}
    call(u,'withdraw_original_revision_v1',ref.source_id,1,Jsonb(p),uuid4())
    with pytest.raises(psycopg.errors.InsufficientPrivilege):call(x,'original_revision_read_v1',ref.source_id,1)
    e=reserve(u,source=ref.source_id,head=1);call(u,'finalize_source_revision_v1',e['reservation']['reservation_id'],1,Jsonb(custody(e)))
    for revision in (1,2):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):call(x,'original_revision_read_v1',ref.source_id,revision)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):call(x,'original_population_current_v1',x['population'].population_id)
