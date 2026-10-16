"""Actual revision withdrawal and explicit later pending head, no auto grants."""
from uuid import uuid4
import psycopg
from psycopg.types.json import Jsonb
import pytest
from test_replacement_source_intake_sql import requester,call,reserve,custody
from test_source_intake_reconcile_sql import read_grant


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
