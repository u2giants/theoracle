"""Real SQL idle status is descriptive readiness, not an executable claim."""
import hashlib
import pytest
from test_meeting_stop_semantics_sql import setup_stop,delivery,meeting_sql,original_fence,admin

@pytest.mark.parametrize('meeting_sql',[{'capture_seconds':7}],indirect=True)
def test_actual_idle_STOP_status_then_real_prepare_and_global_once_claim(delivery,tmp_path):
    x=delivery;original,bot,owner,leave,unused,operation=setup_stop(x,tmp_path,claim_first=False)
    status=leave.status_v1(caller_deadline=original)
    assert status.state=='idle' and status.operation_id==operation and status.bot_id==bot
    assert status.request_sha256==hashlib.sha256(b'').hexdigest() and status.claim_id is None and not status.fresh_claim
    with admin(x) as c:assert c.execute("SELECT count(*) FROM oracle2.meeting_capture_worker_claims_v1 WHERE workspace_id=%s AND effect='capture-leave'",(x['workspace'],)).fetchone()==(0,)
    prepared=leave.prepare_v1(caller_deadline=original)
    assert prepared.state=='prepared' and prepared.operation_id==operation and prepared.claim_id is None
    claim,body=leave.claim_v1(operation,caller_deadline=original)
    assert claim.fresh_claim and claim.state=='claimed' and body==b''
    # Already claimed status must not look ready or yield another body.
    spent=leave.status_v1(caller_deadline=original)
    assert spent.state=='UNKNOWN' and spent.claim_id==claim.claim_id and not spent.fresh_claim
    repeated,again=leave.claim_v1(operation,caller_deadline=original)
    assert repeated.state=='UNKNOWN' and not repeated.fresh_claim and again is None
    with admin(x) as c:assert c.execute("SELECT count(*) FROM oracle2.meeting_capture_worker_claims_v1 WHERE workspace_id=%s AND effect='capture-leave'",(x['workspace'],)).fetchone()==(1,)
