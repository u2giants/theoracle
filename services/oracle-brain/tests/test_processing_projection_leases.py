"""SQL fencing on invented attestations; NOT proof of actual graph delivery."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import time
from uuid import UUID,uuid4
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from test_source_processing_qualification import processing,RUNTIME,REGISTRY
from test_purpose_source_authority import purpose_population
from test_processing_compiler_capabilities import persist_extraction,bundle,commit
from test_assembly_context import context
from test_assembly_qualification import qualified
from oracle_brain.operating_model.processing_projection import lease_processing_projection


def projectable(f,tmp_path,*,workflow_id=None):
    ledger,parent,_=persist_extraction(f,tmp_path)
    payload=None
    if workflow_id is not None:
        from test_source_processing_qualification import resolver
        ref=resolver(f).current_for_processing(f['workspace'],f['source']).ref
        payload={'source_refs':[ref.model_dump(mode='json')],'findings':[],
            'workflows':[{'workflow_id':workflow_id,'status':'reported'}]}
    args,m,_=bundle(f,kind='processing_qualified_model_v1',payload=payload,dependencies=(('artifact',str(parent.artifact_id),'1'),))
    commit(f,args)
    return ledger,m


def attestation(lease):
    e=lease.event;m=e.payload['manifest']
    return dict(schema_version=1,event_id=str(e.event_id),workspace_id=str(e.workspace_id),artifact_id=str(e.assertion_id),version=e.revision,
        content_hash=m['content_hash'],source_digest=m['source_digest'],permission_digest=m['permission_digest'],
        graph_name=f'oracle_processing_v1_{e.workspace_id.hex}_{e.assertion_id.hex}_{e.revision}_'+('a'*32),
        record_digest='b'*64,projection_schema='qualified-evidence-projection-v1',projection_digest='d'*64,sdk_version='1.4.0',projector_id='invented-sql-boundary-control',lease_role=lease.lease_role,
        lease_token=str(lease.lease_token),lease_attempt=e.attempts,lease_until=lease.lease_until.isoformat())


def sql_ack(f,lease,receipt=None,deadline=None):
    e=lease.event
    with psycopg.connect(f['url']) as conn:
        return conn.execute('SELECT oracle2.ack_processing_projection(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
          (e.event_id,e.workspace_id,lease.lease_token,e.attempts,Jsonb(receipt or attestation(lease)),'c'*64,f['binding'].runtime_hash,f['binding'].source_registry_hash,deadline or lease.lease_until)).fetchone()[0]


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


def test_actual_ack_deadline_expiring_during_workspace_lock_rolls_back(admin_url,processing,tmp_path):
    f=processing();ledger,_=projectable(f,tmp_path);lease=lease_processing_projection(ledger,f['workspace'])
    name='owned_ack_wait_'+uuid4().hex
    waiting=dict(f,url=psycopg.conninfo.make_conninfo(f['url'],application_name=name))
    with ThreadPoolExecutor(max_workers=1) as pool:
        with psycopg.connect(admin_url) as blocker:
            blocker.execute("SELECT pg_advisory_xact_lock(hashtext('oracle2-authz:'||%s))",(str(f['workspace']),))
            deadline=blocker.execute("SELECT clock_timestamp()+interval '500 milliseconds'").fetchone()[0]
            future=pool.submit(sql_ack,waiting,lease,paid_attestation(lease),deadline)
            observed=False;limit=time.monotonic()+.4
            while time.monotonic()<limit:
                blocker.execute('SELECT pg_stat_clear_snapshot()')
                observed=blocker.execute("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name=%s AND wait_event_type='Lock' AND wait_event='advisory')",(name,)).fetchone()[0]
                if observed:break
                time.sleep(.01)
            assert observed,'actual ACK must be waiting on the held workspace lock'
            # Actual DB clock, not an elapsed-time claim, proves expiry BEFORE
            # releasing the lock and permitting the transaction to continue.
            while blocker.execute('SELECT clock_timestamp()<%s',(deadline,)).fetchone()[0]:time.sleep(.01)
            blocker.commit()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):future.result(timeout=3)
    with psycopg.connect(admin_url) as conn:
        assert conn.execute('SELECT delivered_at FROM oracle2.outbox WHERE event_id=%s',(lease.event.event_id,)).fetchone()==(None,)
        assert conn.execute('SELECT count(*) FROM oracle2.operating_projection_receipts WHERE event_id=%s',(lease.event.event_id,)).fetchone()==(0,)


def test_competing_workspaces_writer_lock_is_bounded_without_upgrade_deadlock(processing,tmp_path):
    fs=[processing(),processing()];started=time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda pair:persist_extraction(pair[1],tmp_path/str(pair[0]),before_commit=lambda:time.sleep(.15)),enumerate(fs)))
    assert len(results)==2 and time.monotonic()-started<4


@pytest.mark.parametrize('field,value',[('graph_name',None),('record_digest',None),('lease_role','wrong'),('sdk_version','0'),('version','1')])
def test_malformed_receipt_denied_without_delivery(admin_url,processing,tmp_path,field,value):
    f=processing();ledger,_=projectable(f,tmp_path);lease=lease_processing_projection(ledger,f['workspace']);r=attestation(lease);r[field]=value
    with pytest.raises(psycopg.errors.InsufficientPrivilege):sql_ack(f,lease,r)
    with psycopg.connect(admin_url) as conn:assert conn.execute('SELECT delivered_at FROM oracle2.outbox WHERE event_id=%s',(lease.event.event_id,)).fetchone()[0] is None


def test_more_than64_denied_prefix_does_not_hide_eligible_event(admin_url,processing,tmp_path):
    f=processing();ledger,m=projectable(f,tmp_path)
    # Deliberately invalid append-only rows precede the real event. No authority
    # is issued to these controls; exact dependency sealing must reject them.
    with psycopg.connect(admin_url) as conn:
        valid_event=conn.execute('SELECT event_id FROM oracle2.outbox WHERE assertion_id=%s',(m.artifact_id,)).fetchone()[0]
        for index in range(65):
            bad=m.model_copy(update={'artifact_id':uuid4(),'dependency_digest':'0'*64})
            conn.execute('INSERT INTO oracle2.artifact_manifests(workspace_id,artifact_id,version,kind,input_digest,source_digest,permission_digest,compiler_digest,dependency_digest,content_hash,private_object_key,state,manifest) VALUES(%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (bad.workspace_id,bad.artifact_id,bad.kind,bad.input_digest,bad.source_digest,bad.permission_digest,bad.compiler_digest,bad.dependency_digest,bad.content_hash,bad.private_object_key,bad.state,Jsonb(bad.model_dump(mode='json'))))
            conn.execute('INSERT INTO oracle2.artifact_dependencies VALUES(%s,%s,1,%s,%s,%s)',(f['workspace'],bad.artifact_id,'source',str(f['source']),'1'))
            conn.execute('INSERT INTO oracle2.outbox(event_id,workspace_id,assertion_id,revision,operation,payload) VALUES(%s,%s,%s,1,%s,%s)',
                (UUID(int=valid_event.int-1000-index),f['workspace'],bad.artifact_id,'project',Jsonb({'namespace':'oracle_processing_v1','manifest':bad.model_dump(mode='json')})))
    lease=lease_processing_projection(ledger,f['workspace'])
    assert lease and lease.event.assertion_id==m.artifact_id
    sql_ack(f,lease)
    with psycopg.connect(admin_url) as conn:
        assert conn.execute('SELECT count(*) FROM oracle2.outbox WHERE workspace_id=%s AND attempts>0',(f['workspace'],)).fetchone()[0]==1


@pytest.mark.parametrize('mode',['unexpected','timeout'])
def test_eligibility_unexpected_fault_or_timeout_propagates_without_claim(admin_url,processing,tmp_path,mode):
    f=processing();ledger,_=projectable(f,tmp_path)
    signature='oracle2._processing_projection_eligible(uuid,uuid,integer,jsonb,text,text)'
    with psycopg.connect(admin_url) as conn:
        original=conn.execute('SELECT pg_get_functiondef(to_regprocedure(%s))',(signature,)).fetchone()[0]
        body="RAISE EXCEPTION 'owned unexpected eligibility fault' USING ERRCODE='XX000';" if mode=='unexpected' else 'PERFORM pg_sleep(6); RETURN true;'
        conn.execute('CREATE OR REPLACE FUNCTION oracle2._processing_projection_eligible(workspace uuid,artifact uuid,ver integer,event_payload jsonb,runtime text,registry text) RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $owned$ BEGIN '+body+' END $owned$')
    try:
        start=time.monotonic()
        with pytest.raises(psycopg.errors.InternalError_ if mode=='unexpected' else psycopg.errors.QueryCanceled):
            if mode=='unexpected':
                lease_processing_projection(ledger,f['workspace'])
            else:
                # Actual compiler SQL honors a tighter caller deadline. This is
                # rollback proof, not an elapsed reliability claim. Adapter's
                # production 5s/2s settings are unchanged.
                with psycopg.connect(f['url']) as conn:
                    conn.execute("SET LOCAL statement_timeout='300ms'")
                    conn.execute('SELECT oracle2.lease_processing_projection(%s,%s,%s,60)',
                        (f['workspace'],RUNTIME,REGISTRY))
        assert time.monotonic()-start<7
        with psycopg.connect(admin_url) as conn:
            assert conn.execute('SELECT sum(attempts),count(delivered_at) FROM oracle2.outbox WHERE workspace_id=%s',(f['workspace'],)).fetchone()==(0,0)
    finally:
        with psycopg.connect(admin_url) as conn:conn.execute(original)


def test_adapter_applies_actual_fixed_command_and_lock_deadlines(processing,tmp_path,monkeypatch):
    from contextlib import contextmanager
    import oracle_brain.operating_model.processing_projection as delivery
    f=processing();ledger,_=projectable(f,tmp_path)
    connect=psycopg.connect; settings=[]
    @contextmanager
    def observed_connect(*args,**kwargs):
        with connect(*args,**kwargs) as conn:
            yield conn
            settings.append(conn.execute("SELECT current_setting('statement_timeout'),current_setting('lock_timeout')").fetchone())
    monkeypatch.setattr(delivery.psycopg,'connect',observed_connect)
    assert lease_processing_projection(ledger,f['workspace']) is not None
    assert settings==[('5s','2s')]


def test_legacy_delivery_refuses_paid_v3_before_any_ledger_or_ack(monkeypatch):
    import asyncio
    from oracle_brain.operating_model.sdk_projection import PaidProcessingSDKProjectionV3
    import oracle_brain.operating_model.processing_projection as delivery
    calls=[]
    def forbidden(*args,**kwargs):
        calls.append('authority-or-ack')
        raise AssertionError('legacy entry must refuse paid V3 before access')
    monkeypatch.setattr(delivery,'_compiler',forbidden)
    monkeypatch.setattr(delivery,'acknowledge_processing_projection',forbidden)
    # Deliberately incomplete adversarial instance: no constructor/configuration
    # can turn this subclass into a legacy projection or schema-1 ACK.
    projection=object.__new__(PaidProcessingSDKProjectionV3)
    with pytest.raises(PermissionError,match='explicit strict V3'):
        asyncio.run(delivery.project_processing_event(object(),None,projection,secret=b'invented',projector_id='test'))
    assert calls==[]


def paid_attestation(lease):
    """Invented SQL control only: NOT an actual paid graph proof."""
    body=attestation(lease);body.update(schema_version=3,embedding_protocol='paid-sdk-embedding-v3')
    for key in ('inventory','context','native_receipt','wire','commit','vectors','coverage'):
        body['embedding_'+key+'_hash']='e'*64
    return body


def delivery_reader(admin_url,processing,f):
    from oracle_brain.operating_model.authority_adapter import ProcessingArtifactResolver
    reader=processing('documentary-executor')
    with psycopg.connect(admin_url) as conn:
        owner=conn.execute('SELECT actor_id FROM oracle2.appointments WHERE appointment_id=%s',(f['root'],)).fetchone()[0]
        conn.execute('INSERT INTO oracle2.hosting_role_source_admissions SELECT %s,workspace_id,source_id,revision,%s,original_hash,reading_hash,parser_id,runtime_hash,registry_hash,expires_at FROM oracle2.hosting_role_source_admissions WHERE role_name=%s',
            (reader['login'],reader['actor'],f['login']))
        grant=uuid4()
        conn.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',
            (grant,f['workspace'],reader['actor'],'source-read:'+str(f['source']),owner,f['root'],f['expiry']))
        conn.execute('UPDATE oracle2.hosting_role_runtime_admissions SET runtime_hash=%s,registry_hash=%s WHERE role_name=%s',
            (f['binding'].runtime_hash,f['binding'].source_registry_hash,reader['login']))
    binding=replace(reader['binding'],runtime_hash=f['binding'].runtime_hash,source_registry_hash=f['binding'].source_registry_hash)
    return ProcessingArtifactResolver(reader['url'],binding=binding),grant


def test_actual_v3_ack_and_separate_executor_compiler_readbacks(admin_url,processing,tmp_path):
    from oracle_brain.operating_model.contracts import digest
    f=processing();ledger,m=projectable(f,tmp_path);lease=lease_processing_projection(ledger,f['workspace'])
    receipt=paid_attestation(lease)
    # Non-ASCII/control scalar encoding must match Python's actual signing bytes.
    receipt['projector_id']='invented-É-"\\\n\b\u001f'
    sql_ack(f,lease,receipt)
    compiler=ledger.processing_sources
    actual=compiler.projection_receipt_v3(f['workspace'],m.artifact_id,m.version)
    assert actual.receipt.model_dump(mode='json')==receipt and actual.signature=='c'*64
    reader,grant=delivery_reader(admin_url,processing,f)
    seal=reader.projection_delivery_seal(f['workspace'],m.artifact_id,m.version)
    assert seal.receipt_body_hash==digest(receipt) and seal.graph_name==receipt['graph_name']
    assert seal.permission_digest==m.permission_digest and seal.checked_at<seal.valid_until
    assert not {'private_object_key','receipt','lease_token','lease_role','projector_id','vectors'} & set(seal.model_dump())
    with pytest.raises(PermissionError):reader.projection_receipt_v3(f['workspace'],m.artifact_id,m.version)
    with pytest.raises(PermissionError):compiler.projection_delivery_seal(f['workspace'],m.artifact_id,m.version)
    with psycopg.connect(reader.url) as conn:
        conn.execute("SET LOCAL statement_timeout='5s'")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute('SELECT oracle2.hosting_processing_projection_receipt_v3(%s,%s,%s,%s,%s,%s)',
                (f['workspace'],m.artifact_id,m.version,reader.binding.principal,RUNTIME,REGISTRY))
    with psycopg.connect(admin_url) as conn:conn.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(grant,))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):reader.projection_delivery_seal(f['workspace'],m.artifact_id,m.version)


@pytest.mark.parametrize('change',['missing','extra','bad-hash','old-protocol','unknown-schema','numeric-schema','string-schema'])
def test_actual_v3_ack_rejects_malformed_paid_receipts(processing,tmp_path,change):
    f=processing();ledger,m=projectable(f,tmp_path);lease=lease_processing_projection(ledger,f['workspace']);r=paid_attestation(lease)
    if change=='missing':r.pop('embedding_coverage_hash')
    elif change=='extra':r['private_wire']='never permitted'
    elif change=='bad-hash':r['embedding_wire_hash']='wrong'
    elif change=='old-protocol':r['embedding_protocol']='legacy'
    elif change=='unknown-schema':r['schema_version']=4
    elif change=='numeric-schema':r['schema_version']=3.0
    else:r['schema_version']='3'
    with pytest.raises(psycopg.errors.InsufficientPrivilege):sql_ack(f,lease,r)


@pytest.mark.parametrize('ack',['none','legacy'])
def test_new_delivery_getters_refuse_missing_or_legacy_ack(admin_url,processing,tmp_path,ack):
    f=processing();ledger,m=projectable(f,tmp_path);lease=lease_processing_projection(ledger,f['workspace'])
    if ack=='legacy':sql_ack(f,lease)
    reader,_=delivery_reader(admin_url,processing,f)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):reader.projection_delivery_seal(f['workspace'],m.artifact_id,m.version)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):ledger.processing_sources.projection_receipt_v3(f['workspace'],m.artifact_id,m.version)


def test_delivery_preserves_historical_unsorted_source_digest(admin_url,processing,purpose_population,tmp_path):
    from oracle_brain.operating_model.authority_adapter import ProcessingArtifactResolver
    from oracle_brain.operating_model.processing_ledger import ProcessingCompilerLedger
    from oracle_brain.operating_model.artifact_storage import FileBlobStore
    from oracle_brain.operating_model.contracts import digest
    f=purpose_population('embedding','candidate-compiler')
    sources=ProcessingArtifactResolver(f['url'],binding=f['binding'])
    receipts=tuple(sorted((sources.current_for_processing(f['workspace'],r.source_id) for r in f['refs']),key=lambda r:r.ref.source_id.int,reverse=True))
    refs=tuple(r.ref for r in receipts)
    class SQLControl:
        def __call__(self,*args):return None
        def valid_until(self,*args):return f['expiry']
    control=SQLControl()
    ledger=ProcessingCompilerLedger(f['url'],FileBlobStore(tmp_path),principal=f['actor'],processing_sources=sources,
        processing_compile_guard=control,processing_read_guard=control)
    parents=[]
    for receipt in receipts:
        parents.append(ledger.persist(workspace_id=f['workspace'],artifact_id=uuid4(),version=1,kind='processing_extraction_v1',
            payload={'source_refs':[receipt.ref.model_dump(mode='json')],'findings':[]},refs=(receipt.ref,),permission_digest='f'*64,compiler_digest=f['runtime']))
    manifest=ledger.persist(workspace_id=f['workspace'],artifact_id=uuid4(),version=1,kind='processing_qualified_model_v1',
        payload={'source_refs':[r.model_dump(mode='json') for r in refs],'findings':[]},refs=refs,
        permission_digest='f'*64,compiler_digest=f['runtime'],dependencies=tuple(('artifact',str(p.artifact_id),'1') for p in parents))
    lease=lease_processing_projection(ledger,f['workspace'],lease_seconds=60)
    sql_ack(f,lease,paid_attestation(lease))
    readback=sources.projection_receipt_v3(f['workspace'],manifest.artifact_id,1)
    assert readback.receipt.source_digest==manifest.source_digest==digest({'refs':[r.model_dump(mode='json') for r in refs]})
    assert tuple(reversed(readback.source_refs))==refs
    assert digest({'refs':[r.model_dump(mode='json') for r in readback.source_refs]})!=manifest.source_digest
    reader,_=delivery_reader(admin_url,processing,f)
    with psycopg.connect(admin_url) as conn:
        owner=conn.execute('SELECT actor_id FROM oracle2.appointments WHERE appointment_id=%s',(f['root'],)).fetchone()[0]
        for ref in refs:
            if ref.source_id==f['source']:continue
            conn.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                (uuid4(),f['workspace'],reader.binding.principal,'source-read:'+str(ref.source_id),owner,f['root'],f['expiry']))
    seal=reader.projection_delivery_seal(f['workspace'],manifest.artifact_id,1)
    assert seal.source_digest==manifest.source_digest and set(seal.source_refs)==set(refs)


@pytest.mark.parametrize('authority',[None,False,lambda:None])
def test_paid_delivery_has_no_optional_authority_fallback(authority,monkeypatch):
    import asyncio
    import oracle_brain.operating_model.processing_projection as delivery
    from oracle_brain.operating_model.sdk_projection import PaidProcessingSDKProjectionV3
    def forbidden(*args):raise AssertionError('authority-less request reached compiler')
    monkeypatch.setattr(delivery,'_compiler',forbidden)
    with pytest.raises(PermissionError,match='strict paid V3'):
        asyncio.run(delivery.project_paid_processing_event_v3(object(),None,object.__new__(PaidProcessingSDKProjectionV3),
            secret=b'invented',projector_id='test',authority=authority))


@pytest.mark.parametrize('suppress_cancel',[False,True])
def test_paid_delivery_total_deadline_never_acks_late_or_partial_graph(monkeypatch,suppress_cancel):
    """Coroutine boundary control only, not an actual admitted graph delivery."""
    import asyncio
    from types import SimpleNamespace
    import oracle_brain.operating_model.processing_projection as delivery
    from oracle_brain.operating_model.sdk_projection import PaidProcessingSDKProjectionV3
    from oracle_brain.operating_model.paid_sdk_embeddings_v3 import PaidSDKProjectionProofV3
    from oracle_brain.operating_model.contracts import ArtifactManifest
    workspace,artifact,event_id=uuid4(),uuid4(),uuid4();now=datetime.now(timezone.utc)
    body={'source_refs':[]};manifest=ArtifactManifest(workspace_id=workspace,artifact_id=artifact,version=1,
        kind='processing_qualified_model_v1',input_digest='a'*64,source_digest='b'*64,permission_digest='c'*64,
        compiler_digest='d'*64,dependency_digest='e'*64,content_hash=delivery.digest(body),private_object_key='never-opened',state='ready')
    event=delivery.ProjectionEvent(event_id,workspace,artifact,1,'project',{'namespace':'oracle_processing_v1','manifest':manifest.model_dump(mode='json')},1)
    lease=delivery.ProcessingProjectionLease(event,'synthetic-compiler',uuid4(),now+timedelta(seconds=2))
    class Guard:
        def valid_until(self,*args):return now+timedelta(seconds=2)
    ledger=SimpleNamespace(read_with_manifest=lambda *a:(manifest,body),processing_read_guard=Guard(),principal=uuid4(),clock=lambda:datetime.now(timezone.utc))
    monkeypatch.setattr(delivery,'_compiler',lambda *a:SimpleNamespace(expected_session_role='synthetic-compiler',expires_at=now+timedelta(seconds=2)))
    calls=[]
    monkeypatch.setattr(delivery,'acknowledge_processing_projection',lambda *a,**k:calls.append('ACK'))
    class Connection:
        async def query(self,*args):
            try:await asyncio.sleep(1)
            except asyncio.CancelledError:
                if not suppress_cancel:raise
                calls.append('late-remote-write')
                return SimpleNamespace(result_set=[[0]])
    projection=object.__new__(PaidProcessingSDKProjectionV3);projection.graph_name=f'oracle_processing_v1_{workspace.hex}_{artifact.hex}_1_'+('a'*32);projection.connection=Connection()
    async def noop(*args):pass
    async def proof(*args):
        return PaidSDKProjectionProofV3(**{'embedding_'+k+'_hash':'a'*64 for k in ('inventory','context','native_receipt','wire','commit','vectors','coverage')})
    projection.build=noop;projection.verify=noop;projection.paid_projection_proof=proof
    class Authority:
        deadline=None
        def authorize_current(self):
            if self.deadline is None:self.deadline=datetime.now(timezone.utc)+timedelta(seconds=.1)
            return delivery.ProcessingProjectionAuthorityWindowV3(self.deadline,self.deadline)
    unknown=[]
    async def attempt():
        try:
            await delivery.project_paid_processing_event_v3(ledger,lease,projection,secret=b'invented',projector_id='test',authority=Authority())
        except delivery.ProcessingProjectionIncomplete as error:
            unknown.append(error)
            assert isinstance(error.task,asyncio.Task) and not error.task.done()
            await asyncio.gather(error.task,return_exceptions=True)
            raise
    with pytest.raises(delivery.ProcessingProjectionIncomplete):asyncio.run(attempt())
    assert len(unknown)==1 and unknown[0].task.done() and unknown[0].reason=='deadline'
    assert 'ACK' not in calls
    assert calls==(['late-remote-write'] if suppress_cancel else [])


@pytest.mark.parametrize('value',[None,False,datetime.now(timezone.utc)])
def test_paid_window_refuses_ambiguous_single_deadline(value):
    from types import SimpleNamespace
    import oracle_brain.operating_model.processing_projection as delivery
    with pytest.raises(PermissionError,match='explicit currentness'):
        delivery._current_window(SimpleNamespace(authorize_current=lambda:value))


def test_paid_window_separates_current_freshness_from_operation_duration():
    from types import SimpleNamespace
    import oracle_brain.operating_model.processing_projection as delivery
    now=datetime.now(timezone.utc)
    window=delivery.ProcessingProjectionAuthorityWindowV3(now+timedelta(seconds=1),now+timedelta(seconds=30))
    assert delivery._current_window(SimpleNamespace(authorize_current=lambda:window)) is window
    assert window.operation_horizon-window.current_until==timedelta(seconds=29)
    stale=delivery.ProcessingProjectionAuthorityWindowV3(now-timedelta(seconds=1),now+timedelta(seconds=30))
    with pytest.raises(PermissionError):delivery._current_window(SimpleNamespace(authorize_current=lambda:stale))
    with pytest.raises(ValueError):delivery.ProcessingProjectionAuthorityWindowV3(now+timedelta(seconds=30),now)
    with pytest.raises(ValueError):delivery.ProcessingProjectionAuthorityWindowV3(now.replace(tzinfo=None),now)


def paid_final_context(qualified):
    """Pure boundary control, NOT a real native/vector delivery attestation."""
    import oracle_brain.operating_model.processing_projection as delivery
    from oracle_brain.operating_model.sdk_projection import ProcessingSDKProjection
    from oracle_brain.operating_model.paid_sdk_embeddings_v3 import processing_embedding_inventory_v3
    manifest,payload=qualified['manifest'],qualified['payload']
    event=delivery.ProjectionEvent(uuid4(),manifest.workspace_id,manifest.artifact_id,manifest.version,
        'project',{'namespace':'oracle_processing_v1','manifest':manifest.model_dump(mode='json')},1)
    lease=delivery.ProcessingProjectionLease(event,'invented-compiler',uuid4(),datetime.now(timezone.utc)+timedelta(seconds=30))
    receipt=paid_attestation(lease)
    receipt.update(record_digest=delivery.digest({'records':ProcessingSDKProjection.records(payload)}),
        projection_digest=ProcessingSDKProjection.processing_projection_digest(payload),
        embedding_inventory_hash=delivery.digest(processing_embedding_inventory_v3(payload).model_dump(mode='json')))
    return lease,receipt,manifest,payload


@pytest.mark.parametrize('changed',['none','model','dependency','compiler','source','receipt-source','projection','inventory','lease','event','float-schema','bool-schema'])
def test_paid_final_read_binds_current_body_manifest_projection_and_lease(qualified,changed):
    import copy
    import oracle_brain.operating_model.processing_projection as delivery
    lease,receipt,manifest,payload=paid_final_context(qualified)
    if changed=='model':payload=copy.deepcopy(payload);payload['findings'].append({'changed':'after graph'})
    elif changed=='dependency':manifest=manifest.model_copy(update={'dependency_digest':'f'*64})
    elif changed=='compiler':manifest=manifest.model_copy(update={'compiler_digest':'f'*64})
    elif changed=='source':manifest=manifest.model_copy(update={'source_digest':'f'*64})
    elif changed=='receipt-source':receipt['source_digest']='f'*64
    elif changed=='projection':receipt['projection_digest']='f'*64
    elif changed=='inventory':receipt['embedding_inventory_hash']='f'*64
    elif changed=='lease':receipt['lease_token']=str(uuid4())
    elif changed=='event':receipt['event_id']=str(uuid4())
    elif changed=='float-schema':receipt['schema_version']=3.0
    elif changed=='bool-schema':receipt['schema_version']=True
    if changed=='none':delivery._validate_paid_ack_context(lease,receipt,manifest,payload)
    else:
        with pytest.raises(PermissionError):
            delivery._validate_paid_ack_context(lease,receipt,manifest,payload)


@pytest.mark.parametrize('changed',['source','registry','projector-appointment'])
def test_paid_final_authority_change_denies_before_any_sql_ack(qualified,monkeypatch,changed):
    """Final-boundary sequencing control; actual role denials have SQL tests."""
    from types import SimpleNamespace
    import oracle_brain.operating_model.processing_projection as delivery
    lease,receipt,manifest,payload=paid_final_context(qualified);events=[];secret=b'invented-boundary-control-only-0000'
    class Guard:
        def valid_until(self,*args):
            events.append('semantic-current')
            if changed=='registry':raise PermissionError('registry changed after graph')
            return lease.lease_until
    class Authority:
        def authorize_current(self):
            events.append('authority-current')
            raise PermissionError(changed+' changed after graph')
    def current_read(*args):
        events.append('actual-final-read')
        if changed=='source':raise PermissionError('source revoked after graph')
        return manifest,payload
    ledger=SimpleNamespace(read_with_manifest=current_read,processing_read_guard=Guard(),principal=uuid4(),
        clock=lambda:datetime.now(timezone.utc))
    monkeypatch.setattr(delivery,'_compiler',lambda *_:SimpleNamespace(expected_session_role=lease.lease_role,expires_at=lease.lease_until))
    def sql_forbidden(*args,**kwargs):raise AssertionError('changed authority reached SQL ACK')
    monkeypatch.setattr(delivery.psycopg,'connect',sql_forbidden)
    with pytest.raises(PermissionError,match='after graph'):
        delivery.acknowledge_processing_projection(ledger,lease,receipt,delivery.signature(secret,receipt),secret=secret,
            caller_deadline=lease.lease_until,authority=Authority())
    assert events.count('actual-final-read')==1
    if changed=='projector-appointment':assert events[-1]=='authority-current'
