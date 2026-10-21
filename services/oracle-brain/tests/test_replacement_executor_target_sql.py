"""GIVEN qualified-state SQL controls, not native lifecycle or graph proof."""
from dataclasses import replace
from uuid import uuid4
import psycopg
from psycopg.types.json import Jsonb
import pytest
from test_source_processing_qualification import processing
from test_processing_projection_leases import projectable,paid_attestation,sql_ack,delivery_reader
from oracle_brain.operating_model.authority_adapter import ProcessingArtifactResolver
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.processing_projection import lease_processing_projection

@pytest.fixture
def target(admin_url,processing,tmp_path):
    f=processing();ledger,m=projectable(f,tmp_path,workflow_id='invented-flow');lease=lease_processing_projection(ledger,f['workspace'])
    receipt=paid_attestation(lease);sql_ack(f,lease,receipt)
    reader,grant=delivery_reader(admin_url,processing,f)
    with psycopg.connect(admin_url) as c:
        c.execute('UPDATE oracle2.hosting_role_source_admissions SET principal_id=%s WHERE role_name=%s',(f['actor'],reader.binding.expected_session_role))
        c.execute('UPDATE oracle2.appointments SET actor_id=%s WHERE appointment_id=%s',(f['actor'],grant))
    reader=ProcessingArtifactResolver(reader.url,binding=replace(reader.binding,principal=f['actor']))
    refs=tuple(r.model_dump(mode='json') for r in reader.projection_delivery_seal(f['workspace'],m.artifact_id,1).source_refs)
    run=uuid4();pop=digest({'source_refs':refs})
    with psycopg.connect(admin_url) as c:
        c.execute("INSERT INTO oracle2.runs(run_id,workspace_id,actor_id,source_id,question,status) VALUES(%s,%s,%s,%s,'invented component','completed')",(run,f['workspace'],f['actor'],f['source']))
        c.execute("INSERT INTO oracle2.processing_journey_runs_v1(run_id,workspace_id,actor_id,journey_revision,population_sha256,original_population,current_model_id,current_model_version,current_model_content_hash,current_ack_event_id,state,answer_hold) VALUES(%s,%s,%s,1,%s,%s,%s,1,%s,%s,'delivered',false)",(run,f['workspace'],f['actor'],pop,Jsonb(refs),m.artifact_id,m.content_hash,lease.event.event_id))
        c.execute('INSERT INTO oracle2.hosting_replacement_executor_runs_v1 VALUES(%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s,%s,%s,%s)',(reader.binding.expected_session_role,run,f['workspace'],f['actor'],reader.binding.runtime_hash,reader.binding.source_registry_hash,pop,m.artifact_id,m.content_hash,lease.event.event_id,receipt['projection_digest'],digest([]),f['expiry']))
    return f,reader,run,m

def test_actual_executor_target_is_current_narrow_same_principal(admin_url,target):
    f,reader,run,m=target;r=reader.replacement_executor_target_v1(run)
    assert r.run_id==run and r.model_id==m.artifact_id and r.requester_principal_id==f['actor']
    assert not r.answer_hold and not r.cancelled and r.current_confirmation is None
    assert r.summary_targets==() and r.checked_at<r.valid_until
    assert not {'private_object_key','receipt','signature','reading','vectors'} & set(r.model_dump())
    with psycopg.connect(reader.url) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT * FROM oracle2.hosting_replacement_executor_runs_v1')

@pytest.mark.parametrize('change',['hold','cancel','population','actor','ack','expiry','revoke'])
def test_actual_executor_target_current_changes(admin_url,target,change):
    f,reader,run,m=target
    with psycopg.connect(admin_url) as c:
        if change=='hold':c.execute('UPDATE oracle2.processing_journey_runs_v1 SET answer_hold=true WHERE run_id=%s',(run,))
        elif change=='cancel':c.execute("UPDATE oracle2.processing_journey_runs_v1 SET state='cancelled',cancelled_at=clock_timestamp() WHERE run_id=%s",(run,))
        elif change=='population':c.execute("UPDATE oracle2.processing_journey_runs_v1 SET population_sha256=repeat('0',64) WHERE run_id=%s",(run,))
        elif change=='actor':c.execute('UPDATE oracle2.processing_journey_runs_v1 SET actor_id=%s WHERE run_id=%s',(uuid4(),run))
        elif change=='ack':c.execute('UPDATE oracle2.processing_journey_runs_v1 SET current_ack_event_id=NULL WHERE run_id=%s',(run,))
        elif change=='expiry':c.execute("UPDATE oracle2.hosting_replacement_executor_runs_v1 SET expires_at=clock_timestamp()-interval '1 second' WHERE run_id=%s",(run,))
        else:c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE workspace_id=%s AND actor_id=%s AND scope=%s',(f['workspace'],f['actor'],'source-read:'+str(f['source'])))
    if change in ('hold','cancel'):
        r=reader.replacement_executor_target_v1(run);assert r.answer_hold if change=='hold' else r.cancelled
    else:
        with pytest.raises((PermissionError,psycopg.errors.InsufficientPrivilege)):reader.replacement_executor_target_v1(run)

@pytest.mark.parametrize('change',['none','hash','parent','extra','duplicate','projection'])
def test_registered_summary_and_projection_are_actual_sql_bindings(admin_url,target,change):
    from test_processing_compiler_capabilities import bundle,commit
    f,reader,run,m=target
    args,summary,_=bundle(f,kind='processing_summary_v1',dependencies=(('artifact',str(m.artifact_id),'1'),));commit(f,args)
    item=dict(schema_version=1,summary_artifact_id=str(summary.artifact_id),summary_version=1,summary_content_hash=summary.content_hash,
        qualified_parent_id=str(m.artifact_id),qualified_parent_version=1,qualified_parent_content_hash=m.content_hash)
    if change=='hash':item['summary_content_hash']='0'*64
    elif change=='parent':item['qualified_parent_id']=str(uuid4())
    elif change=='extra':item['private_path']='forbidden'
    items=[item,item] if change=='duplicate' else [item]
    with psycopg.connect(admin_url) as c:
        c.execute('UPDATE oracle2.processing_journey_runs_v1 SET summary_targets=%s WHERE run_id=%s',(Jsonb(items),run))
        c.execute('UPDATE oracle2.hosting_replacement_executor_runs_v1 SET summary_targets_sha256=%s WHERE run_id=%s',(digest(items),run))
        if change=='projection':c.execute("UPDATE oracle2.hosting_replacement_executor_runs_v1 SET projection_digest=repeat('0',64) WHERE run_id=%s",(run,))
    if change=='none':assert reader.replacement_executor_target_v1(run).summary_targets[0].summary_artifact_id==summary.artifact_id
    else:
        with pytest.raises((PermissionError,psycopg.errors.InsufficientPrivilege)):reader.replacement_executor_target_v1(run)

@pytest.mark.parametrize('change',['none','revoke','withdraw','held'])
def test_current_confirmation_requires_exact_current_leaf(admin_url,target,change):
    f,reader,run,m=target;event,leaf=uuid4(),uuid4()
    with psycopg.connect(admin_url) as c:
        owner=c.execute('SELECT actor_id FROM oracle2.appointments WHERE appointment_id=%s',(f['root'],)).fetchone()[0]
        c.execute("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,'process-confirm',%s,%s,%s)",(leaf,f['workspace'],f['actor'],owner,f['root'],f['expiry']))
        payload={'workflow_id':'invented-flow','model_id':str(m.artifact_id),'ack_event_id':str(c.execute('SELECT current_ack_event_id FROM oracle2.processing_journey_runs_v1 WHERE run_id=%s',(run,)).fetchone()[0]),'version':1,'content_hash':m.content_hash}
        c.execute("INSERT INTO oracle2.replacement_journey_events(event_id,run_id,workspace_id,journey_revision,actor_id,action,payload_sha256,payload,idempotency_key) VALUES(%s,%s,%s,2,%s,'confirm',%s,%s,%s)",(event,run,f['workspace'],f['actor'],digest(payload),Jsonb(payload),uuid4()))
        if change=='revoke':c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(leaf,))
        elif change=='held':c.execute('UPDATE oracle2.processing_journey_runs_v1 SET answer_hold=true WHERE run_id=%s',(run,))
        elif change=='withdraw':
            p={'confirmation_id':str(event)}
            c.execute("INSERT INTO oracle2.replacement_journey_events(event_id,run_id,workspace_id,journey_revision,actor_id,action,payload_sha256,payload,idempotency_key) VALUES(%s,%s,%s,3,%s,'withdraw',%s,%s,%s)",(uuid4(),run,f['workspace'],f['actor'],digest(p),Jsonb(p),uuid4()))
    r=reader.replacement_executor_target_v1(run)
    if change=='none':assert r.current_confirmation.eligible and r.current_confirmation.workflow_id=='invented-flow'
    else:assert r.current_confirmation is None


def test_actual_target_lock_wait_cannot_extend_registered_horizon(admin_url,target):
    from concurrent.futures import ThreadPoolExecutor
    import time
    f,reader,run,m=target
    with psycopg.connect(admin_url) as blocker:
        blocker.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('oracle2-authz:'+str(f['workspace']),))
        with psycopg.connect(admin_url) as c:
            c.execute("UPDATE oracle2.hosting_replacement_executor_runs_v1 SET expires_at=clock_timestamp()+interval '350 milliseconds' WHERE run_id=%s",(run,))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(reader.replacement_executor_target_v1,run)
            time.sleep(.45);blocker.commit()
            with pytest.raises((PermissionError,psycopg.errors.InsufficientPrivilege)):future.result(timeout=5)
    with psycopg.connect(admin_url) as c:
        assert c.execute('SELECT journey_revision,state,answer_hold FROM oracle2.processing_journey_runs_v1 WHERE run_id=%s',(run,)).fetchone()==(1,'delivered',False)
        assert c.execute('SELECT count(*) FROM oracle2.replacement_journey_events WHERE run_id=%s',(run,)).fetchone()[0]==0
