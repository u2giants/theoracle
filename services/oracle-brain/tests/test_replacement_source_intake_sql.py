"""Actual own-session intake capabilities; bytes are not authenticated by SQL."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest


@pytest.fixture
def requester(admin_url):
    workspace,actor,owner=uuid4(),uuid4(),uuid4()
    login='replacement_request_'+uuid4().hex[:12]
    runtime,registry='a'*64,'b'*64
    until=datetime.now(timezone.utc)+timedelta(seconds=90)
    root,leaf=uuid4(),uuid4()
    with psycopg.connect(admin_url) as c:
        for migration in ('012_processing_compiler_capabilities.sql','013_processing_purpose_permissions.sql','014_replacement_source_custody.sql'):
            c.execute((Path(__file__).parents[1]/'sql'/migration).read_text())
        c.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(
            sql.Identifier(login),sql.Literal('synthetic-requester-only')))
        c.execute(sql.SQL('GRANT oracle2_replacement_requester TO {}').format(sql.Identifier(login)))
        c.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',(login,runtime,registry,until))
        c.execute('INSERT INTO oracle2.hosting_request_principal_admissions VALUES(%s,%s,%s,%s,%s,%s)',
            (login,actor,workspace,runtime,registry,until))
        c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,expires_at) VALUES(%s,%s,%s,%s,%s,%s)',
            (root,workspace,owner,'root',uuid4(),until))
        c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',
            (leaf,workspace,actor,'intake',owner,root,until))
    url=psycopg.conninfo.make_conninfo(admin_url,user=login,password='synthetic-requester-only')
    try:
        yield dict(url=url,login=login,workspace=workspace,actor=actor,owner=owner,root=root,runtime=runtime,registry=registry,until=until,leaf=leaf,admin=admin_url)
    finally:
        with psycopg.connect(admin_url) as c:
            c.execute('DELETE FROM oracle2.hosting_request_principal_admissions WHERE role_name=%s',(login,))
            c.execute('DELETE FROM oracle2.hosting_role_runtime_admissions WHERE role_name=%s',(login,))
            c.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(login)))


def call(x,function,*arguments,connection=None):
    def run(c):
        c.execute("SET LOCAL statement_timeout='5s'")
        return c.execute(sql.SQL('SELECT oracle2.{}({})').format(sql.Identifier(function),
            sql.SQL(',').join(sql.Placeholder() for _ in arguments)),arguments).fetchone()[0]
    if connection is not None:return run(connection)
    with psycopg.connect(x['url']) as c:return run(c)


def reserve(x,*,deadline=None,key=None,head=0,source=None):
    intake={'source_id':str(source) if source else None,'filename':'invented.pdf','media_type':'application/pdf',
        'byte_count':7,'caller_deadline':(deadline or x['until']).isoformat()}
    return call(x,'reserve_source_revision_v1',head,Jsonb(intake),key or uuid4())


def custody(envelope,**changes):
    context=envelope['context']
    value={'original_sha256':'c'*64,'byte_count':7,'custody_seal_sha256':'d'*64,
        'caller_deadline':context['valid_until'],
        'expected_context':{k:context[k] for k in ('principal_id','workspace_id','session_role','runtime_hash','source_registry_hash')}}
    value.update(changes);return value


def test_actual_requester_reserve_finalize_has_no_fake_reading_or_source_grant(requester):
    x=requester;e=reserve(x);r=e['reservation']
    assert set(e)=={'schema_version','context','reservation'}
    assert e['context']['principal_id']==str(x['actor']) and e['context']['session_role']==x['login']
    assert r['private_object_key']==f"source-originals/{x['workspace']}/{r['source_id']}/1/{r['reservation_id']}"
    result=call(x,'finalize_source_revision_v1',r['reservation_id'],0,Jsonb(custody(e)))
    assert result['snapshot']['state']=='awaiting_original_reading' and result['snapshot']['qualifiedSourceRef'] is None
    with psycopg.connect(x['admin']) as c:
        assert c.execute('SELECT count(*) FROM oracle2.operating_model_source_receipts WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)
        assert c.execute("SELECT count(*) FROM oracle2.appointments WHERE workspace_id=%s AND scope LIKE 'source-read:%%'",(x['workspace'],)).fetchone()==(0,)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):call(x,'original_revision_view_v1',r['source_id'],1)


def test_actual_finalizer_rejects_drifted_external_identity_before_head_mutation(requester):
    x=requester;e=reserve(x);r=e['reservation'];bad=custody(e);bad['expected_context']['principal_id']=str(uuid4())
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        call(x,'finalize_source_revision_v1',r['reservation_id'],0,Jsonb(bad))
    with psycopg.connect(x['admin']) as c:
        assert c.execute('SELECT count(*) FROM oracle2.sources WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)
        assert c.execute('SELECT finalized_at FROM oracle2.source_intake_reservations_v1 WHERE reservation_id=%s',(r['reservation_id'],)).fetchone()==(None,)


def test_actual_finalizer_rechecks_current_intake_revocation(requester):
    x=requester;e=reserve(x)
    with psycopg.connect(x['admin']) as c:c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(x['leaf'],))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        call(x,'finalize_source_revision_v1',e['reservation']['reservation_id'],0,Jsonb(custody(e)))
    with psycopg.connect(x['admin']) as c:assert c.execute('SELECT count(*) FROM oracle2.sources WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)


def test_actual_reservation_idempotency_never_renews_original_deadline(requester):
    x=requester;key=uuid4();deadline=datetime.now(timezone.utc)+timedelta(seconds=10)
    first=reserve(x,key=key,deadline=deadline);again=reserve(x,key=key,deadline=deadline)
    assert first['reservation']==again['reservation']
    with pytest.raises(psycopg.errors.UniqueViolation,match='replacement idempotency conflict'):
        reserve(x,key=key,deadline=deadline+timedelta(seconds=1))


def test_actual_existing_revision_compare_and_swap_and_historical_custody(requester):
    x=requester;first=reserve(x);r=first['reservation'];source=r['source_id']
    call(x,'finalize_source_revision_v1',r['reservation_id'],0,Jsonb(custody(first)))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):reserve(x,head=1,source=source)
    with psycopg.connect(x['admin']) as c:
        c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',
            (uuid4(),x['workspace'],x['actor'],'source-read:'+source,x['owner'],x['root'],x['until']))
    second=reserve(x,head=1,source=source);stale=reserve(x,head=1,source=source)
    call(x,'finalize_source_revision_v1',second['reservation']['reservation_id'],1,Jsonb(custody(second,original_sha256='e'*64)))
    with pytest.raises(psycopg.errors.SerializationFailure,match='replacement revision conflict'):
        call(x,'finalize_source_revision_v1',stale['reservation']['reservation_id'],1,Jsonb(custody(stale)))
    with psycopg.connect(x['admin']) as c:
        assert c.execute('SELECT revision FROM oracle2.sources WHERE source_id=%s',(source,)).fetchone()==(2,)
        assert c.execute('SELECT revision,original_sha256 FROM oracle2.source_original_revisions WHERE source_id=%s ORDER BY revision',(source,)).fetchall()==[(1,'c'*64),(2,'e'*64)]
        assert c.execute('SELECT finalized_at FROM oracle2.source_intake_reservations_v1 WHERE reservation_id=%s',(stale['reservation']['reservation_id'],)).fetchone()==(None,)


def test_actual_finalizer_expiry_while_waiting_lineage_lock_rolls_back_everything(requester):
    import concurrent.futures,queue,time
    x=requester;e=reserve(x);r=e['reservation'];pid=queue.Queue()
    value=custody(e,caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=.4)).isoformat())
    def finalize():
        with psycopg.connect(x['url']) as c:
            pid.put(c.info.backend_pid)
            return call(x,'finalize_source_revision_v1',r['reservation_id'],0,Jsonb(value),connection=c)
    with psycopg.connect(x['admin']) as blocker:
        blocker.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('operating-lineage:'+str(x['workspace']),))
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(finalize);backend=pid.get(timeout=2);observed=False;limit=time.monotonic()+1
            with psycopg.connect(x['admin'],autocommit=True) as observer:
                while time.monotonic()<limit:
                    if observer.execute("SELECT wait_event_type='Lock' FROM pg_stat_activity WHERE pid=%s",(backend,)).fetchone()==(True,):
                        observed=True;break
                    time.sleep(.005)
                assert observed,'actual finalizer never reached retained lineage lock'
                # Deliberately wait past the genuine caller horizon; no timer claim.
                observer.execute('SELECT pg_sleep(.45)')
            blocker.commit()
            with pytest.raises(psycopg.errors.InsufficientPrivilege,match='expired before mutation'):
                pending.result(timeout=2)
    with psycopg.connect(x['admin']) as c:
        assert c.execute('SELECT count(*) FROM oracle2.sources WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)
        assert c.execute('SELECT count(*) FROM oracle2.source_original_revisions WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)
        assert c.execute('SELECT finalized_at FROM oracle2.source_intake_reservations_v1 WHERE reservation_id=%s',(r['reservation_id'],)).fetchone()==(None,)


def test_actual_requester_has_no_direct_custody_or_authority_table_access(requester):
    x=requester
    for table in ('source_original_revisions','hosting_request_principal_admissions','source_intake_reservations_v1'):
        with psycopg.connect(x['url']) as c,pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute(sql.SQL('SELECT * FROM oracle2.{}').format(sql.Identifier(table)))


def test_actual_seal_metadata_encoding_matches_python_and_stays_private(requester):
    from oracle_brain.operating_model.contracts import canonical_bytes
    x=requester;value={'z':[{'é':'quoted " and \\','schema_version':1},True,None], 'a':{'revision':12}}
    with psycopg.connect(x['admin']) as c:
        encoded=c.execute('SELECT oracle2._replacement_metadata_json(%s)',(Jsonb(value),)).fetchone()[0]
        assert encoded.encode()==canonical_bytes(value)
    with psycopg.connect(x['admin']) as c,pytest.raises(psycopg.errors.InvalidParameterValue):
        c.execute('SELECT oracle2._replacement_metadata_json(%s)',(Jsonb({'number':1.0}),))
    with psycopg.connect(x['url']) as c,pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute('SELECT oracle2._replacement_metadata_json(%s)',(Jsonb(value),))


@pytest.mark.parametrize('deadline',['infinity','2026-10-16T10:00:00','NaN'])
def test_actual_finalizer_rejects_nonfinite_or_naive_deadline(requester,deadline):
    x=requester;e=reserve(x)
    with pytest.raises((psycopg.errors.InvalidParameterValue,psycopg.errors.InsufficientPrivilege)):
        call(x,'finalize_source_revision_v1',e['reservation']['reservation_id'],0,Jsonb(custody(e,caller_deadline=deadline)))
