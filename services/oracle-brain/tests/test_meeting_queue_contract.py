"""Queue-specific bounds and closed bytes; no network or installed authority."""
from datetime import datetime,timezone
from uuid import UUID
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.original_intake_v1 import _parse
from oracle_brain.hosting.meeting_queue_service_v1 import MeetingQueueRequestV1
from oracle_brain.meetings.queue_contracts import MAX_QUEUE_WIRE_V1,observe_queue_wire_v1

def envelope():
    return dict(schema_version=1,operation='observe',ingress_event_id=str(UUID(int=1)),claim_id=str(UUID(int=2)),request_sha256='a'*64,
        raw_wire_hex='ff'*MAX_QUEUE_WIRE_V1,error='framing',caller_deadline='2026-10-22T12:00:00.123456Z')

def test_exact_maximum_private_hex_envelope_fits_existing_request_cap():
    value=envelope();raw=canonical_bytes(value)
    assert len(raw)==41278 and len(raw)<65536
    assert len(bytes.fromhex(_parse(MeetingQueueRequestV1,raw).raw_wire_hex))==20480
    with pytest.raises(ValueError):_parse(MeetingQueueRequestV1,canonical_bytes(value|dict(raw_wire_hex='ff'*20481)))

@pytest.mark.parametrize('change',[dict(operation='pending'),dict(claim_id=None),dict(request_sha256=None),dict(actor='x'),dict(raw_wire_hex='FF'),dict(error='retry'),dict(schema_version=True)])
def test_closed_queue_request_refuses_selectors_and_changed_types(change):
    with pytest.raises(ValueError):_parse(MeetingQueueRequestV1,canonical_bytes(envelope()|change))

def test_queue_bounds_preserve_private_capability_header_without_publication():
    body=b'{"id":"run_1"}';prefix=b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: '+str(len(body)).encode()+b'\r\nx-trigger-jwt: '
    wire=prefix+b'x'*(16384-len(prefix)-4)+b'\r\n\r\n'+body
    result=observe_queue_wire_v1(wire)
    assert len(wire)==16384+len(body) and result['kind']=='enqueue-observed' and 'x-trigger-jwt' not in repr(result)
    assert observe_queue_wire_v1(wire.replace(b'\r\n\r\n',b'x\r\n\r\n',1))['kind']=='UNKNOWN'
    with pytest.raises(ValueError):observe_queue_wire_v1(b'x'*20481)
    large=b' '*4097
    wire=b'HTTP/1.1 200 OK\r\nContent-Length: 4097\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n'+large
    assert observe_queue_wire_v1(wire)['kind']=='UNKNOWN'
