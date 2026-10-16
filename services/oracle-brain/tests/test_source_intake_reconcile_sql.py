"""Current own-principal reconciliation, never retry or renewed write authority."""
from uuid import uuid4
import psycopg
from psycopg.types.json import Jsonb
import pytest
from test_replacement_source_intake_sql import requester,call,reserve,custody


def read_grant(x,source):
    leaf=uuid4()
    with psycopg.connect(x['admin']) as c:c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(leaf,x['workspace'],x['actor'],'source-read:'+source,x['owner'],x['root'],x['until']))
    return leaf


def test_pending_and_expired_reconcile_never_renew_or_return_private_key(requester):
    x=requester;key=uuid4();e=reserve(x,key=key);r=e['reservation']
    before=call(x,'reconcile_source_intake_v1',key)
    assert before['status']=='pending' and before['snapshot'] is None
    assert 'private_object_key' not in str(before)
    with psycopg.connect(x['admin']) as c:c.execute("UPDATE oracle2.source_intake_reservations_v1 SET expires_at=clock_timestamp()-interval '1 second' WHERE reservation_id=%s",(r['reservation_id'],))
    expired=call(x,'reconcile_source_intake_v1',key)
    assert expired['status']=='expired' and expired['snapshot'] is None
    assert expired['reservation_expires_at']<expired['context']['checked_at']
    with pytest.raises(psycopg.errors.InsufficientPrivilege):call(x,'finalize_source_revision_v1',r['reservation_id'],0,Jsonb(custody(e)))


@pytest.mark.parametrize('change',['none','revoke-read','revoke-intake','head','seal','foreign'])
def test_finalized_reconcile_after_old_expiry_requires_current_authority(requester,change):
    x=requester;key=uuid4();e=reserve(x,key=key);r=e['reservation']
    actual=call(x,'finalize_source_revision_v1',r['reservation_id'],0,Jsonb(custody(e)))['snapshot']
    with pytest.raises(psycopg.errors.InsufficientPrivilege):call(x,'reconcile_source_intake_v1',key)
    leaf=read_grant(x,r['source_id'])
    with psycopg.connect(x['admin']) as c:
        c.execute("UPDATE oracle2.source_intake_reservations_v1 SET expires_at=clock_timestamp()-interval '1 second' WHERE reservation_id=%s",(r['reservation_id'],))
        if change=='revoke-read':c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(leaf,))
        elif change=='revoke-intake':c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(x['leaf'],))
        elif change=='head':c.execute('UPDATE oracle2.sources SET revision=2 WHERE source_id=%s',(r['source_id'],))
        elif change=='seal':c.execute("UPDATE oracle2.source_intake_reservations_v1 SET custody_seal_sha256=repeat('0',64) WHERE reservation_id=%s",(r['reservation_id'],))
    if change=='none':
        result=call(x,'reconcile_source_intake_v1',key)
        assert result['status']=='finalized' and result['snapshot']==actual
        assert result['reservation_expires_at']<result['context']['checked_at']<result['context']['valid_until']
        assert set(result)=={'schema_version','context','status','reservation_expires_at','snapshot'}
    else:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):call(x,'reconcile_source_intake_v1',uuid4() if change=='foreign' else key)
