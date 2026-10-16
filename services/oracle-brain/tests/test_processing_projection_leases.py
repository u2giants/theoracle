"""SQL fencing on invented attestations; NOT proof of actual graph delivery."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import time
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from test_source_processing_qualification import processing,RUNTIME,REGISTRY
from test_processing_compiler_capabilities import persist_extraction,bundle,commit
from oracle_brain.operating_model.processing_projection import lease_processing_projection


def projectable(f,tmp_path):
    ledger,parent,_=persist_extraction(f,tmp_path)
    args,m,_=bundle(f,kind='processing_qualified_model_v1',dependencies=(('artifact',str(parent.artifact_id),'1'),))
    commit(f,args)
    return ledger,m


def attestation(lease):
    e=lease.event;m=e.payload['manifest']
    return dict(schema_version=1,event_id=str(e.event_id),workspace_id=str(e.workspace_id),artifact_id=str(e.assertion_id),version=e.revision,
        content_hash=m['content_hash'],source_digest=m['source_digest'],permission_digest=m['permission_digest'],
        graph_name=f'oracle_processing_v1_{e.workspace_id.hex}_{e.assertion_id.hex}_{e.revision}_'+('a'*32),
        record_digest='b'*64,sdk_version='1.4.0',projector_id='invented-sql-boundary-control',lease_role=lease.lease_role,
        lease_token=str(lease.lease_token),lease_attempt=e.attempts,lease_until=lease.lease_until.isoformat())


def sql_ack(f,lease,receipt=None,deadline=None):
    e=lease.event
    with psycopg.connect(f['url']) as conn:
        return conn.execute('SELECT oracle2.ack_processing_projection(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
          (e.event_id,e.workspace_id,lease.lease_token,e.attempts,Jsonb(receipt or attestation(lease)),'c'*64,RUNTIME,REGISTRY,deadline or lease.lease_until)).fetchone()[0]


def test_current_lease_fences_ack_and_exact_idempotency(admin_url,processing,tmp_path):
    f=processing();ledger,m=projectable(f,tmp_path);lease=lease_processing_projection(ledger,f['workspace'])
    assert lease and lease.event.assertion_id==m.artifact_id and lease.event.attempts==1
    assert lease_processing_projection(ledger,f['workspace']) is None
    result=sql_ack(f,lease);assert sql_ack(f,lease)==result
    forged=attestation(lease);forged['record_digest']='d'*64
    with pytest.raises(psycopg.errors.InsufficientPrivilege):sql_ack(f,lease,forged)
    with psycopg.connect(admin_url) as conn:
        assert conn.execute('SELECT delivered_at IS NOT NULL,lease_until IS NULL,processing_lease_role::text,processing_lease_token FROM oracle2.outbox WHERE event_id=%s',(lease.event.event_id,)).fetchone()==(True,True,f['login'],lease.lease_token)
        assert conn.execute('SELECT count(*) FROM oracle2.operating_projection_receipts WHERE event_id=%s',(lease.event.event_id,)).fetchone()[0]==1


def test_expired_claim_reclaim_changes_token_and_denies_stale_ack(processing,tmp_path):
    f=processing();ledger,_=projectable(f,tmp_path)
    old=lease_processing_projection(ledger,f['workspace'],lease_seconds=1);time.sleep(1.05)
    new=lease_processing_projection(ledger,f['workspace'])
    assert new.lease_token!=old.lease_token and new.event.attempts==old.event.attempts+1
    with pytest.raises(psycopg.errors.InsufficientPrivilege):sql_ack(f,old)
    assert sql_ack(f,new)['receipt']['lease_token']==str(new.lease_token)


@pytest.mark.parametrize('scope',['root','read','extract'])
def test_revocation_after_claim_keeps_event_undelivered(admin_url,processing,tmp_path,scope):
    f=processing();ledger,_=projectable(f,tmp_path);lease=lease_processing_projection(ledger,f['workspace'])
    with psycopg.connect(admin_url) as conn:conn.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(f[scope],))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):sql_ack(f,lease)
    with psycopg.connect(admin_url) as conn:
        assert conn.execute('SELECT delivered_at FROM oracle2.outbox WHERE event_id=%s',(lease.event.event_id,)).fetchone()[0] is None
        assert conn.execute('SELECT count(*) FROM oracle2.operating_projection_receipts WHERE event_id=%s',(lease.event.event_id,)).fetchone()[0]==0


def test_sibling_role_and_wrong_token_cannot_ack_current_claim(admin_url,processing,tmp_path):
    f=processing();ledger,_=projectable(f,tmp_path);lease=lease_processing_projection(ledger,f['workspace'])
    with pytest.raises(psycopg.errors.InsufficientPrivilege):sql_ack(f,replace(lease,lease_token=uuid4()))
    login='processing_sibling_'+uuid4().hex[:10]
    with psycopg.connect(admin_url) as conn:
        conn.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(login),sql.Literal('invented-test-only')))
        conn.execute(sql.SQL('GRANT oracle2_candidate_compiler TO {}').format(sql.Identifier(login)))
        conn.execute('INSERT INTO oracle2.hosting_role_runtime_admissions SELECT %s,runtime_hash,registry_hash,expires_at FROM oracle2.hosting_role_runtime_admissions WHERE role_name=%s',(login,f['login']))
        conn.execute('INSERT INTO oracle2.hosting_role_source_admissions SELECT %s,workspace_id,source_id,revision,principal_id,original_hash,reading_hash,parser_id,runtime_hash,registry_hash,expires_at FROM oracle2.hosting_role_source_admissions WHERE role_name=%s',(login,f['login']))
    sibling={**f,'url':psycopg.conninfo.make_conninfo(f['url'],user=login,password='invented-test-only')}
    with pytest.raises(psycopg.errors.InsufficientPrivilege):sql_ack(sibling,lease)


def test_concurrent_leases_have_one_current_owner(processing,tmp_path):
    f=processing();ledger,_=projectable(f,tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:lease_processing_projection(ledger,f['workspace']),range(2)))
    assert sum(x is not None for x in results)==1


def test_denied_workspace_does_not_starve_another(processing,tmp_path):
    denied=processing();allowed=processing();projectable(denied,tmp_path/'bad');goodledger,_=projectable(allowed,tmp_path/'good')
    assert lease_processing_projection(goodledger,denied['workspace']) is None
    assert lease_processing_projection(goodledger,allowed['workspace']) is not None


def test_actual_semantic_deadline_and_expired_lease_reject_ack(admin_url,processing,tmp_path):
    f=processing();ledger,_=projectable(f,tmp_path);lease=lease_processing_projection(ledger,f['workspace'],lease_seconds=1)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):sql_ack(f,lease,deadline=datetime.now(timezone.utc)-timedelta(seconds=1))
    time.sleep(1.05)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):sql_ack(f,lease,deadline=f['expiry'])
    with psycopg.connect(admin_url) as conn:assert conn.execute('SELECT delivered_at FROM oracle2.outbox WHERE event_id=%s',(lease.event.event_id,)).fetchone()[0] is None


def test_competing_workspaces_writer_lock_is_bounded_without_upgrade_deadlock(processing,tmp_path):
    fs=[processing(),processing()];started=time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda pair:persist_extraction(pair[1],tmp_path/str(pair[0]),before_commit=lambda:time.sleep(.15)),enumerate(fs)))
    assert len(results)==2 and time.monotonic()-started<4


@pytest.mark.parametrize('field,value',[('graph_name',None),('record_digest',None),('lease_role','wrong'),('sdk_version','0'),('version','1')])
def test_malformed_receipt_denied_without_delivery(admin_url,processing,tmp_path,field,value):
    f=processing();ledger,_=projectable(f,tmp_path);lease=lease_processing_projection(ledger,f['workspace']);r=attestation(lease);r[field]=value
    with pytest.raises(psycopg.errors.InsufficientPrivilege):sql_ack(f,lease,r)
    with psycopg.connect(admin_url) as conn:assert conn.execute('SELECT delivered_at FROM oracle2.outbox WHERE event_id=%s',(lease.event.event_id,)).fetchone()[0] is None
