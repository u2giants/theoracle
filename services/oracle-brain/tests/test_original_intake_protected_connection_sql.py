"""Actual own-role protected intake/reconcile; independent fixture grants only."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import hashlib,time,os
import psycopg
import pytest
from oracle_brain.hosting.original_intake_v1 import OriginalIntakeFactoryV1,load_original_intake_settings_v1
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
from test_replacement_source_intake_sql import requester
from test_replacement_requester_sql import configured_settings,owned_admin



def factory(x,tmp_path):
    s=configured_settings(tmp_path,x);a=s.appointment.model_copy(update=dict(media_types=('application/pdf','text/plain')));raw=canonical_bytes(a.model_dump(mode='json'));s.appointment_path.write_bytes(raw)
    return OriginalIntakeFactoryV1(load_original_intake_settings_v1(s.config_path,s.config_sha256,s.appointment_path,hashlib.sha256(raw).hexdigest(),s.expected_issuer_actor,s.expected_reviewer_actor))


def test_actual_shared_protected_intake_then_own_current_reconcile_never_reserves_again(requester,tmp_path):
    x=requester;f=factory(x,tmp_path);key=uuid4();data='Invented original, awaiting independent reading.'.encode();end=datetime.now(timezone.utc)+timedelta(seconds=15)
    with _request_fence_v1(float(time.monotonic()+15)):
        result=f.intake_text_v1(source_id=None,expected_head=0,idempotency_key=key,filename='meeting.txt',original_sha256=hashlib.sha256(data).hexdigest(),data=data,caller_deadline=end)
        assert result.state=='awaiting_original_reading' and result.qualifiedSourceRef is None
        # Intake permission is not source-read. No caller DTO can grant it.
        with pytest.raises(psycopg.errors.InsufficientPrivilege):f.reconcile_intake_v1(key,caller_deadline=end)
        with owned_admin(x) as c:
            c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(uuid4(),x['workspace'],x['actor'],'source-read:'+str(result.sourceId),x['owner'],x['root'],x['until']))
        observed=f.reconcile_intake_v1(key,caller_deadline=end)
        assert observed.status=='finalized' and observed.snapshot==result
        with owned_admin(x) as c:
            assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)
            assert c.execute('SELECT count(*) FROM oracle2.sources WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)
            c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE workspace_id=%s AND actor_id=%s AND scope=%s',(x['workspace'],x['actor'],'source-read:'+str(result.sourceId)))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):f.reconcile_intake_v1(key,caller_deadline=end)


def test_protected_original_intake_refuses_PG_defaults_and_sub2s_before_socket(requester,tmp_path,monkeypatch):
    x=requester;f=factory(x,tmp_path);calls=[];original=psycopg.connect
    monkeypatch.setattr(psycopg,'connect',lambda *a,**k:(calls.append((a,k)),original(*a,**k))[1])
    with _request_fence_v1(float(time.monotonic()+10)):
        monkeypatch.setenv('PGAPPNAME','invented-ambient')
        with pytest.raises(PermissionError,match='PG environment'):f.reconcile_intake_v1(uuid4(),caller_deadline=datetime.now(timezone.utc)+timedelta(seconds=5))
        monkeypatch.delenv('PGAPPNAME')
        with pytest.raises(PermissionError,match='two-second'):f.reconcile_intake_v1(uuid4(),caller_deadline=datetime.now(timezone.utc)+timedelta(seconds=1))
    assert calls==[]
