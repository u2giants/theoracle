"""Actual owned SQL delivery fences. Supervisor receipt inputs are invented;
this does not prove a real installed supervisor, provider or employee session.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import UUID,uuid4
import hashlib,time
import psycopg
from psycopg.types.json import Jsonb
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.hosting.meeting_capture_v1 import MeetingCaptureFactoryV1,load_meeting_capture_settings_v1
from oracle_brain.hosting._protected_control_listener_v1 import _request_fence_v1
from test_meeting_capture_sql import meeting_sql,admin,invite,deadline

@pytest.fixture(autouse=True)
def original_fence():
    with _request_fence_v1(float(time.monotonic()+25)):yield

def clone(x,base,updates):
    selected=uuid4();seal=digest({'invented_admission':str(selected)});updates=dict(updates,admission_id=str(selected),admission_sha256=seal)
    with admin(x) as c:
        c.execute('INSERT INTO oracle2.meeting_capture_admissions_v1 SELECT (jsonb_populate_record(NULL::oracle2.meeting_capture_admissions_v1,to_jsonb(m)||%s)).* FROM oracle2.meeting_capture_admissions_v1 m WHERE admission_id=%s',(Jsonb(updates),base['admission']))
    cfg=base['settings'].config.model_copy(update=dict(admission_id=selected,admission_sha256=seal,channel='worker'))
    path=base['settings'].config_path.parent/('worker-'+selected.hex);raw=canonical_bytes(cfg.model_dump(mode='json'));path.write_bytes(raw);path.chmod(0o600)
    setting=load_meeting_capture_settings_v1(base['settings'].host,path,hashlib.sha256(raw).hexdigest())
    return dict(base,admission=selected,seal=seal,settings=setting,factory=MeetingCaptureFactoryV1(setting))

@pytest.fixture
def delivery(meeting_sql):
    x=meeting_sql;worker=uuid4();op=uuid4();body=canonical_bytes({'meeting_url':'https://teams.microsoft.com/l/meetup-join/invented','bot_name':'Invented','recording_config':{'transcript':{'provider':{'elevenlabs_streaming':{}}},'realtime_endpoints':[{'type':'webhook','url':'https://ingress.example.test/recall','events':['transcript.data']}]}});sha=hashlib.sha256(body).hexdigest()
    # Independent invented installation happens BEFORE invitation. A future
    # provider bot is deliberately absent; this is not a real active supervisor.
    from oracle_brain.meetings.create_stop_relation import CreateOperationStopRelationV1
    with admin(x) as c:
        windows=c.execute('SELECT stop_valid_from,stop_until,original_horizon FROM oracle2.meeting_capture_admissions_v1 WHERE admission_id=%s',(x['worker']['admission'],)).fetchone()
    relation=CreateOperationStopRelationV1(purpose='meeting-create-operation-stop-relation-v1',mapping_id=uuid4(),workspace_id=x['workspace'],meeting_id=x['meeting'],provider='recall',provider_account=x['account'],tenant_id='tenant1',provider_meeting_id='meeting1',create_operation_id=op,create_request_sha256=sha,supervision_scope_sha256='e'*64,scheduler_id=uuid4(),stop_owner_id=x['worker']['actor'],scheduler_runtime_sha256='a'*64,scheduler_config_sha256='b'*64,stop_runtime_sha256='c'*64,stop_config_sha256='d'*64,capture_until=x['capture_until'],stop_valid_from=windows[0],stop_until=windows[1],original_horizon=windows[2],issuer_actor=uuid4(),reviewer_actor=uuid4(),valid_from=windows[0]-timedelta(seconds=1),expires_at=windows[1])
    with admin(x) as c:c.execute('INSERT INTO oracle2.meeting_create_stop_relations_v1(mapping_id,workspace_id,meeting_id,mapping_sha256,mapping_payload) VALUES(%s,%s,%s,%s,%s)',(relation.mapping_id,x['workspace'],x['meeting'],relation.sha256,Jsonb(relation.model_dump(mode='json'))))
    unattended=clone(x,x['worker'],dict(actions=['supervise','stop_intent','stop_observed','stop_unknown','status'],bot_id=None,supervision_scope_sha256='e'*64,stop_relation_id=str(relation.mapping_id),stop_mapping_sha256=relation.sha256,worker_id=str(uuid4()),worker_effect='capture-leave',worker_policy_sha256='d'*64))
    unattended_gets={}
    for stage in ('pre-stop-consistency','post-stop-terminal'):
        unattended_gets[stage]=clone(x,unattended,dict(actions=['stop_reconciled','status'],worker_id=str(uuid4()),worker_effect='capture-retrieve',worker_retrieve_stage=stage,worker_retrieve_operation_id=str(uuid4())))
    invite(x)
    observer=clone(x,x['provider-ingress'],dict(actions=['supervised','supervise','status'],supervision_scope_sha256='e'*64))
    creator=clone(x,x['employee-control'],dict(actions=['create_intent','create_observed','create_unknown','status'],stop_relation_id=str(relation.mapping_id),stop_mapping_sha256=relation.sha256,stop_valid_from=relation.stop_valid_from.isoformat(),stop_until=relation.stop_until.isoformat(),supervisor_admission_id=str(observer['admission']),supervision_scope_sha256='e'*64,worker_id=str(worker),worker_effect='capture-create',worker_policy_sha256='d'*64,worker_create_operation_id=str(op),worker_create_request_sha256=sha))
    now=datetime.now(timezone.utc);proof=uuid4();payload=dict(scope_sha256='e'*64,create_operation_id=str(op),request_sha256=sha,witness_sha256='a'*64,witness_object_key=f'meeting-supervisor/{x["workspace"]}/{x["meeting"]}/'+('a'*64)+'.bin',nonce='b'*64,observed_at=now.isoformat(),valid_until=(now+timedelta(seconds=4)).isoformat(),scheduler_observation_sha256='c'*64)
    observer['factory'].transition_v1(expected_head=1,operation_id=proof,action='supervised',payload=payload,caller_deadline=deadline())
    return x|dict(creator=creator,observer=observer,operation=op,body=body,sha=sha,worker_identity=worker,stop_relation=relation,unattended_stop=unattended,unattended_gets=unattended_gets)

def prepare(x):return x['creator']['factory']._worker_delivery_v1('prepare',caller_deadline=deadline())
def claim(x,*,caller_deadline=None,owner=None):return (owner or x['creator'])['factory']._worker_delivery_v1('claim',operation_id=x['operation'],body_sha256=x['sha'],caller_deadline=caller_deadline or deadline())

def test_actual_prepare_reuses_business_intent_and_only_one_claim(delivery):
    x=delivery;first=prepare(x);again=prepare(x);assert first.intent_event_id==again.intent_event_id and first.state=='prepared'
    original=min(deadline(),x['capture_until']);one=claim(x,caller_deadline=original);two=claim(x,caller_deadline=original)
    assert one.fresh_claim and one.state=='claimed' and not two.fresh_claim and two.state=='UNKNOWN' and one.claim_id==two.claim_id
    assert one.claim_original_deadline==original
    with admin(x) as c:
        assert c.execute("SELECT count(*) FROM oracle2.meeting_capture_events_v1 WHERE workspace_id=%s AND action='create_intent'",(x['workspace'],)).fetchone()==(1,)
        assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_worker_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)

def test_actual_concurrent_claim_and_reinstalled_admission_cannot_replay(delivery):
    x=delivery;prepare(x);original=min(deadline(),x['capture_until'])
    def attempt():
        with _request_fence_v1(float(time.monotonic()+20)):return claim(x,caller_deadline=original)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:attempt(),range(2)))
    assert sum(v.fresh_claim for v in results)==1 and {v.state for v in results}=={'claimed','UNKNOWN'}
    replacement=clone(x,x['creator'],dict(worker_id=str(uuid4())))
    replay=claim(x,caller_deadline=original,owner=replacement);assert replay.state=='UNKNOWN' and not replay.fresh_claim and replay.claim_id==results[0].claim_id
    other_role=clone(x,x['provider-ingress'],dict(actions=['create_intent','create_observed','create_unknown','status'],stop_relation_id=str(x['stop_relation'].mapping_id),stop_mapping_sha256=x['stop_relation'].sha256,stop_valid_from=x['stop_relation'].stop_valid_from.isoformat(),stop_until=x['stop_relation'].stop_until.isoformat(),supervisor_admission_id=str(x['observer']['admission']),supervision_scope_sha256='e'*64,worker_id=str(uuid4()),worker_effect='capture-create',worker_policy_sha256='d'*64,worker_create_operation_id=str(x['operation']),worker_create_request_sha256=x['sha']))
    # This different role is also the independent observer principal; it
    # cannot borrow creator authority even to reclaim a spent effect.
    with pytest.raises(psycopg.errors.InsufficientPrivilege):claim(x,caller_deadline=original,owner=other_role)
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_worker_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)

def test_actual_null_legacy_admission_grants_no_worker_and_old_status_still_works(meeting_sql):
    x=meeting_sql;invite(x);f=x['worker']['factory'];assert f.head_v1(caller_deadline=deadline()).version==1
    with pytest.raises(psycopg.errors.InsufficientPrivilege):f._worker_delivery_v1('prepare',caller_deadline=deadline())
    assert f.head_v1(caller_deadline=deadline()).version==1

def test_actual_body_collision_and_foreign_claim_refuse_without_new_rows(delivery):
    x=delivery;prepare(x);original=min(deadline(),x['capture_until'])
    with pytest.raises(psycopg.Error):x['creator']['factory']._worker_delivery_v1('claim',operation_id=x['operation'],body_sha256='f'*64,caller_deadline=original)
    one=claim(x,caller_deadline=original)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):x['creator']['factory']._worker_delivery_v1('current',operation_id=x['operation'],claim_id=uuid4(),caller_deadline=original)
    with pytest.raises(psycopg.Error):x['creator']['factory']._worker_delivery_v1('claim',operation_id=uuid4(),body_sha256=x['sha'],caller_deadline=original)
    assert x['creator']['factory']._worker_delivery_v1('current',operation_id=x['operation'],claim_id=one.claim_id,caller_deadline=original).state=='inflight'

def test_actual_receipt_is_immutable_and_partial_remains_unknown(delivery):
    x=delivery;prepare(x);original=min(deadline(),x['capture_until']);one=claim(x,caller_deadline=original);raw=b'HTTP/1.1 200';sha=hashlib.sha256(raw).hexdigest()
    packet=dict(wire_object_key=f'meeting-worker/{x["workspace"]}/{x["meeting"]}/{one.claim_id}/{sha}.wire',wire_sha256=sha,wire_byte_count=len(raw),observation=dict(kind='UNKNOWN',bot_id=None,latest_status=None,complete=False))
    f=x['creator']['factory'];receipt=f._worker_delivery_v1('observe',operation_id=x['operation'],claim_id=one.claim_id,wire=packet,caller_deadline=original)
    repeated=f._worker_delivery_v1('observe',operation_id=x['operation'],claim_id=one.claim_id,wire=packet,caller_deadline=original)
    assert receipt.state=='UNKNOWN' and receipt.receipt_id==repeated.receipt_id
    with pytest.raises(psycopg.Error):f._worker_delivery_v1('observe',operation_id=x['operation'],claim_id=one.claim_id,wire=packet|dict(wire_byte_count=len(raw)+1),caller_deadline=original)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):f._worker_delivery_v1('current',operation_id=x['operation'],claim_id=one.claim_id,caller_deadline=original)

def test_actual_worker_null_partial_installation_cannot_pass_nullable_check(delivery):
    x=delivery
    for change in (dict(worker_effect=None),dict(worker_policy_sha256=None),dict(worker_create_operation_id=None),dict(worker_retrieve_stage='pre-stop-consistency')):
        with pytest.raises(psycopg.errors.CheckViolation):clone(x,x['creator'],change)

def test_actual_claim_deadline_cannot_be_renewed_by_new_current_request(delivery):
    x=delivery;prepare(x);original=min(deadline(),x['capture_until']);one=claim(x,caller_deadline=original)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):x['creator']['factory']._worker_delivery_v1('current',operation_id=x['operation'],claim_id=one.claim_id,caller_deadline=original+timedelta(seconds=1))
    assert x['creator']['factory']._worker_delivery_v1('current',operation_id=x['operation'],claim_id=one.claim_id,caller_deadline=original).state=='inflight'

@pytest.mark.parametrize('meeting_sql',[{'capture_seconds':7}],indirect=True)
def test_actual_separate_get_stages_globally_once_across_new_admissions(delivery):
    x=delivery;prepared=prepare(x);original=min(deadline(),x['capture_until']);claim(x,caller_deadline=original);bot=uuid4();receipt_sha='9'*64
    head=x['creator']['factory'].head_v1(caller_deadline=original)
    x['creator']['factory'].transition_v1(expected_head=head.version,operation_id=uuid4(),action='create_observed',payload=dict(intent_id=str(x['operation']),receipt_sha256=receipt_sha,bot_id=str(bot)),caller_deadline=original)
    def retrieval(stage,op):return clone(x,x['worker'],dict(actions=['stop_reconciled','status'],bot_id=str(bot),worker_id=str(uuid4()),worker_effect='capture-retrieve',worker_policy_sha256='d'*64,worker_retrieve_stage=stage,worker_retrieve_operation_id=str(op)))
    preop,postop=uuid4(),uuid4();pre=retrieval('pre-stop-consistency',preop);post=retrieval('post-stop-terminal',postop)
    pf=pre['factory'];preparing=pf._worker_delivery_v1('prepare',caller_deadline=original);assert preparing.intent_event_id==prepared.intent_event_id
    first=pf._worker_delivery_v1('claim',operation_id=preop,body_sha256=hashlib.sha256(b'').hexdigest(),caller_deadline=original);assert first.fresh_claim
    replacement=retrieval('pre-stop-consistency',preop)
    repeat=replacement['factory']._worker_delivery_v1('claim',operation_id=preop,body_sha256=hashlib.sha256(b'').hexdigest(),caller_deadline=original);assert not repeat.fresh_claim and repeat.claim_id==first.claim_id
    changed=retrieval('pre-stop-consistency',uuid4())
    with pytest.raises(psycopg.Error):changed['factory']._worker_delivery_v1('prepare',caller_deadline=original)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):post['factory']._worker_delivery_v1('claim',operation_id=postop,body_sha256=hashlib.sha256(b'').hexdigest(),caller_deadline=original)
    leave=clone(x,x['worker'],dict(actions=['stop_intent','stop_observed','stop_unknown','status'],bot_id=str(bot),worker_id=str(uuid4()),worker_effect='capture-leave',worker_policy_sha256='d'*64))
    time.sleep(max(0,(x['capture_until']-datetime.now(timezone.utc)).total_seconds()-4.9))
    head=leave['factory'].head_v1(caller_deadline=original)
    leave['factory'].transition_v1(expected_head=head.version,operation_id=uuid4(),action='stop_intent',payload=dict(create_intent_id=str(x['operation']),bot_id=str(bot),create_receipt_sha256=receipt_sha,stop_mapping_sha256='f'*64,metadata_sha256='e'*64),caller_deadline=original)
    second=post['factory']._worker_delivery_v1('claim',operation_id=postop,body_sha256=hashlib.sha256(b'').hexdigest(),caller_deadline=original)
    assert second.fresh_claim and second.claim_id!=first.claim_id and second.intent_event_id==first.intent_event_id
    with admin(x) as c:assert c.execute("SELECT count(*) FROM oracle2.meeting_capture_worker_claims_v1 WHERE workspace_id=%s AND effect='capture-retrieve'",(x['workspace'],)).fetchone()==(2,)

def worker_factory(x,owner,tmp_path):
    from oracle_brain.hosting.meeting_capture_worker_v1 import CaptureWorkerConfigV1,load_capture_worker_settings_v1,CaptureWorkerFactoryV1
    body=tmp_path/('body-'+uuid4().hex);body.write_bytes(x['body']);body.chmod(0o600)
    c=CaptureWorkerConfigV1(purpose='meeting-capture-worker-consumer-v1',capture_config_sha256=owner['settings'].config_sha256,worker_id=UUID(str(x['worker_identity'])) if owner is x['creator'] else uuid4(),effect='capture-create',operation_policy_sha256='d'*64,create_operation_id=x['operation'],create_body=dict(path=str(body),sha256=x['sha']),retrieve_stage=None,retrieve_operation_id=None,stop_mapping_sha256=None,issuer_actor=uuid4(),reviewer_actor=uuid4(),valid_from=datetime.now(timezone.utc)-timedelta(seconds=1),expires_at=min(x['capture_until'],owner['settings'].config.expires_at),original_horizon=owner['settings'].config.original_horizon)
    # Independent invented installation uses the actual selected SQL worker ID.
    with admin(x) as connection:identity=connection.execute('SELECT worker_id FROM oracle2.meeting_capture_admissions_v1 WHERE admission_id=%s',(owner['admission'],)).fetchone()[0]
    c=c.model_copy(update=dict(worker_id=identity));raw=canonical_bytes(c.model_dump(mode='json'));path=tmp_path/('config-'+uuid4().hex);path.write_bytes(raw);path.chmod(0o600)
    return CaptureWorkerFactoryV1(load_capture_worker_settings_v1(owner['settings'],path,hashlib.sha256(raw).hexdigest()))

def test_actual_factory_reveals_exact_body_once_and_denies_foreign_receipt_before_private_write(delivery,tmp_path,monkeypatch):
    import oracle_brain.hosting.meeting_capture_worker_v1 as module
    x=delivery;f=worker_factory(x,x['creator'],tmp_path);original=min(deadline(),x['capture_until']);f.prepare_v1(caller_deadline=original)
    claimed,body=f.claim_v1(x['operation'],caller_deadline=original);assert body==x['body'] and claimed.fresh_claim
    repeated,no_body=f.claim_v1(x['operation'],caller_deadline=original);assert not repeated.fresh_claim and no_body is None
    replacement=clone(x,x['creator'],dict(worker_id=str(uuid4())));foreign=worker_factory(x,replacement,tmp_path)
    writes=[];monkeypatch.setattr(module,'_write_private_at',lambda *args,**kwargs:writes.append(args))
    with pytest.raises(PermissionError,match='own claim'):foreign.observe_v1(x['operation'],claimed.claim_id,b'',error='timeout',caller_deadline=original)
    assert writes==[]
