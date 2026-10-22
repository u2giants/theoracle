"""Actual retained pre-stop receipt selection; invented wire, no provider proof."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import time
import pytest
from test_meeting_delivery_sql import delivery,meeting_sql,original_fence,clone
from test_meeting_create_forensic_sql import begin,response
from test_meeting_stop_semantics_sql import worker,metadata
from test_meeting_create_stop_relation_sql import operation
from test_meeting_capture_sql import admin,deadline


def observed(x,tmp_path,damage=None):
    creator,end,claim=begin(x,tmp_path);bot=uuid4()
    creator.observe_v1(x['operation'],claim.claim_id,response(body={'id':str(bot)}),caller_deadline=end)
    owner=x['unattended_gets']['pre-stop-consistency']
    if damage=='foreign-relation':
        owner=clone(x,owner,dict(stop_relation_id=None,stop_mapping_sha256='f'*64,bot_id=str(bot),worker_id=str(uuid4()),worker_retrieve_operation_id=str(uuid4())))
    op=operation(x,owner);factory=worker(x,owner,tmp_path,'capture-retrieve','pre-stop-consistency',op)
    until=min(end,datetime.now(timezone.utc)+timedelta(seconds=3.3)) if damage=='stale' else end
    claimed,body=factory.claim_v1(op,caller_deadline=until);assert body==b''
    raw=metadata(uuid4() if damage=='foreign-bot' else bot,'in_call_recording')
    if damage=='incomplete':raw=raw[:-1]
    receipt=factory.observe_v1(op,claimed.claim_id,raw,caller_deadline=until)
    return owner,claimed,receipt,until


def test_exact_complete_current_pre_stop_receipt_selected_from_actual_owner(delivery,tmp_path):
    x=delivery;owner,claim,receipt,_=observed(x,tmp_path)
    due=x['unattended_stop']['factory'].due_stop_v1(caller_deadline=deadline())
    selected=due.pre_stop_observation
    assert selected is not None and selected.receipt_id==receipt.receipt_id and selected.claim_id==claim.claim_id
    assert selected.operation_id==claim.operation_id and str(selected.bot_id)==due.created_bot['bot_id']
    assert selected.metadata_sha256==receipt.observation['metadata_sha256']
    with admin(x) as c:
        assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_worker_receipts_v1 WHERE claim_id=%s',(claim.claim_id,)).fetchone()==(1,)
        assert c.execute('SELECT stop_intent_id FROM oracle2.meeting_capture_heads_v1 WHERE workspace_id=%s AND meeting_id=%s',(x['workspace'],x['meeting'])).fetchone()==(None,)


@pytest.mark.parametrize('damage',['foreign-bot','foreign-relation','incomplete','stale','revoked'])
def test_unrelated_incomplete_expired_or_revoked_receipt_cannot_fill_scheduler_input(delivery,tmp_path,damage):
    x=delivery;owner,_claim,_receipt,until=observed(x,tmp_path,damage)
    if damage=='stale':time.sleep(max(0,(until-datetime.now(timezone.utc)).total_seconds()+.02))
    if damage=='revoked':
        with admin(x) as c:c.execute('INSERT INTO oracle2.meeting_capture_revocations_v1 VALUES(%s,%s,clock_timestamp(),%s)',(uuid4(),owner['admission'],'a'*64))
    due=x['unattended_stop']['factory'].due_stop_v1(caller_deadline=deadline())
    assert due.pre_stop_observation is None and due.stop_intent_id is None
