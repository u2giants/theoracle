"""Actual global operation relation installed before Create, invented authority."""
from datetime import datetime,timedelta,timezone
from uuid import UUID,uuid4
import hashlib,time
import psycopg
from psycopg.types.json import Jsonb
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from test_meeting_delivery_sql import delivery,meeting_sql,original_fence,clone,prepare
from test_meeting_create_forensic_sql import begin,cancel,response,head_state
from test_meeting_stop_semantics_sql import worker,metadata,stop_state
from test_meeting_capture_sql import admin


def operation(x,owner):
    with admin(x) as c:return c.execute('SELECT worker_retrieve_operation_id FROM oracle2.meeting_capture_admissions_v1 WHERE admission_id=%s',(owner['admission'],)).fetchone()[0]


@pytest.mark.parametrize('meeting_sql',[{'capture_seconds':7}],indirect=True)
def test_actual_preinstalled_relation_derives_unseen_bot_and_stops_without_post_create_installation(delivery,tmp_path):
    x=delivery
    with admin(x) as c:
        before=c.execute('SELECT count(*) FROM oracle2.meeting_capture_admissions_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()[0]
        assert c.execute('SELECT r.installed_at<e.created_at FROM oracle2.meeting_create_stop_relations_v1 r JOIN oracle2.meeting_capture_events_v1 e ON e.workspace_id=r.workspace_id AND e.meeting_id=r.meeting_id WHERE r.mapping_id=%s AND e.action=%s',(x['stop_relation'].mapping_id,'invite')).fetchone()==(True,)
    creator,end,claimed=begin(x,tmp_path);cancel(x,end);bot=uuid4()
    creator.observe_v1(x['operation'],claimed.claim_id,response(body={'id':str(bot)}),caller_deadline=end)
    pre_owner=x['unattended_gets']['pre-stop-consistency'];pre_op=operation(x,pre_owner)
    pre=worker(x,pre_owner,tmp_path,'capture-retrieve','pre-stop-consistency',pre_op);pc,body=pre.claim_v1(pre_op,caller_deadline=end)
    assert body==b'' and pc.bot_id==bot
    consistency=pre.observe_v1(pre_op,pc.claim_id,metadata(bot,'in_call_recording'),caller_deadline=end)
    stop=x['unattended_stop'];due=stop['factory'].due_stop_v1(caller_deadline=end);assert due.created_bot['bot_id']==str(bot)
    time.sleep(max(0,(due.due_at-datetime.now(timezone.utc)).total_seconds()+.02))
    head=stop['factory'].head_v1(caller_deadline=end);stop_id=uuid4()
    stop['factory'].transition_v1(expected_head=head.version,operation_id=stop_id,action='stop_intent',payload=dict(create_intent_id=str(x['operation']),bot_id=str(bot),create_receipt_sha256=due.created_bot['receipt_sha256'],stop_mapping_sha256=x['stop_relation'].sha256,metadata_sha256=consistency.observation['metadata_sha256']),caller_deadline=end)
    leave=worker(x,stop,tmp_path,'capture-leave');lc,body=leave.claim_v1(stop_id,caller_deadline=end);assert lc.bot_id==bot and body==b''
    leave.observe_v1(stop_id,lc.claim_id,b'HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: 0\r\n\r\n',caller_deadline=end)
    assert stop_state(x)==('cancelled',False,'observed')
    post_owner=x['unattended_gets']['post-stop-terminal'];post_op=operation(x,post_owner)
    post=worker(x,post_owner,tmp_path,'capture-retrieve','post-stop-terminal',post_op);pc,_=post.claim_v1(post_op,caller_deadline=end)
    post.observe_v1(post_op,pc.claim_id,metadata(bot),caller_deadline=end)
    assert stop_state(x)==('cancelled',False,'terminal_observed')
    with admin(x) as c:
        assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_admissions_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(before,)
        assert c.execute('SELECT bot_id FROM oracle2.meeting_capture_admissions_v1 WHERE admission_id=ANY(%s)',([stop['admission'],pre_owner['admission'],post_owner['admission']],)).fetchall()==[(None,),(None,),(None,)]
        assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_worker_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(4,)


@pytest.mark.parametrize('damage',['missing','revoked','stop-revoked','short-stop-leaf','late','account','request'])
def test_actual_missing_revoked_late_or_foreign_relation_denies_before_create_claim(delivery,tmp_path,damage):
    x=delivery;owner=x['creator'];relation=x['stop_relation']
    if damage=='missing':owner=clone(x,owner,dict(stop_relation_id=None))
    elif damage=='short-stop-leaf':
        with admin(x) as c:c.execute('UPDATE oracle2.appointments SET expires_at=%s WHERE appointment_id=%s',(x['capture_until'],x['unattended_stop']['leaf']))
    elif damage in ('revoked','stop-revoked'):
        with admin(x) as c:
            if damage=='revoked':c.execute('INSERT INTO oracle2.meeting_create_stop_relation_revocations_v1 VALUES(%s,%s,clock_timestamp(),%s)',(uuid4(),relation.mapping_id,'a'*64))
            else:c.execute('INSERT INTO oracle2.meeting_capture_revocations_v1 VALUES(%s,%s,clock_timestamp(),%s)',(uuid4(),x['unattended_stop']['admission'],'a'*64))
    else:
        updates={'mapping_id':uuid4()}
        if damage=='account':updates['provider_account']='foreign'
        if damage=='request':updates['create_request_sha256']='f'*64
        changed=relation.model_copy(update=updates)
        with admin(x) as c:c.execute('INSERT INTO oracle2.meeting_create_stop_relations_v1(mapping_id,workspace_id,meeting_id,mapping_sha256,mapping_payload) VALUES(%s,%s,%s,%s,%s)',(changed.mapping_id,x['workspace'],x['meeting'],changed.sha256,Jsonb(changed.model_dump(mode='json'))))
        owner=clone(x,owner,dict(stop_relation_id=str(changed.mapping_id),stop_mapping_sha256=changed.sha256))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):owner['factory']._worker_delivery_v1('prepare',caller_deadline=min(datetime.now(timezone.utc).replace(microsecond=0)+timedelta(seconds=10),x['capture_until']))
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_worker_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)


def test_actual_dynamic_relation_refuses_manual_create_label_without_complete_retained_receipt(delivery,tmp_path):
    x=delivery;creator,end,claimed=begin(x,tmp_path);bot=uuid4();h=x['creator']['factory'].head_v1(caller_deadline=end)
    x['creator']['factory'].transition_v1(expected_head=h.version,operation_id=uuid4(),action='create_observed',payload=dict(intent_id=str(x['operation']),receipt_sha256='f'*64,bot_id=str(bot)),caller_deadline=end)
    assert x['unattended_stop']['factory'].due_stop_v1(caller_deadline=end).created_bot is None
    assert head_state(x)[1] is False
