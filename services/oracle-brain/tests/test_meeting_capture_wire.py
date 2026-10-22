"""Raw-wire facts use invented retained bytes only, never live Recall/TLS proof."""
from datetime import datetime,timezone
from uuid import UUID
import json
import pytest
from oracle_brain.meetings.capture_wire_v1 import observe_capture_wire_v1
BOT=UUID('01000000-0000-4000-8000-000000000001')
def wire(status=200,value=None,*,body=None,headers=b''):
    body=json.dumps(value).encode() if body is None else body
    return b'HTTP/1.1 '+str(status).encode()+b' OK\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: '+str(len(body)).encode()+b'\r\n'+headers+b'\r\n'+body

def test_actual_raw_create_literal201_uuid_only_observation():
    r=observe_capture_wire_v1(wire(201,{'id':str(BOT)}),effect='capture-create',expected_bot=None)
    assert r==dict(kind='create-observed',bot_id=str(BOT),latest_status=None,complete=True)
    assert observe_capture_wire_v1(wire(200,{'id':str(BOT)}),effect='capture-create',expected_bot=None)['kind']=='UNKNOWN'

def test_empty_leave_200_is_not_terminal_stop_proof():
    r=observe_capture_wire_v1(wire(body=b''),effect='capture-leave',expected_bot=BOT)
    assert r['kind']=='leave-observed' and 'remote_stop_proven' not in r
    assert observe_capture_wire_v1(wire(body=b'{}'),effect='capture-leave',expected_bot=BOT)['kind']=='UNKNOWN'

@pytest.mark.parametrize('bad',[b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\nextra',wire(body=b'',headers=b'Content-Length: 0\r\n'),wire(body=b'',headers=b'Transfer-Encoding: chunked\r\n'),wire(body=b'')+wire(body=b''),wire(body=b'')[:-1]])
def test_partial_extra_duplicate_and_double_responses_remain_unknown(bad):
    assert observe_capture_wire_v1(bad,effect='capture-leave',expected_bot=BOT)['kind']=='UNKNOWN'

def test_metadata_exact_bot_and_latest_nonfuture_status_no_source_proof():
    now=datetime(2026,10,21,20,tzinfo=timezone.utc)
    value={'id':str(BOT),'status_changes':[{'code':'call_ended','created_at':'2026-10-21T19:59:00Z'}]}
    r=observe_capture_wire_v1(wire(value=value),effect='capture-retrieve',expected_bot=BOT,now=now)
    assert r['kind']=='metadata-observed' and r['latest_status']==value['status_changes'][0]
    for change in ({'id':str(UUID(int=3))},{'status_changes':[{'code':'done','created_at':'2026-10-22T00:00:00Z'}]},{'status_changes':value['status_changes']+[{'code':'fatal','created_at':'2026-10-21T19:59:00Z'}]}):
        assert observe_capture_wire_v1(wire(value=value|change),effect='capture-retrieve',expected_bot=BOT,now=now)['kind']=='UNKNOWN'

def test_duplicate_json_and_known_transport_failure_never_become_success():
    assert observe_capture_wire_v1(wire(201,body=b'{"id":"'+str(BOT).encode()+b'","id":"'+str(BOT).encode()+b'"}'),effect='capture-create',expected_bot=None)['kind']=='UNKNOWN'
    assert observe_capture_wire_v1(wire(201,{'id':str(BOT)}),effect='capture-create',expected_bot=None,error='timeout')['kind']=='UNKNOWN'
