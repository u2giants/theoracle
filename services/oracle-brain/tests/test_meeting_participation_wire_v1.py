"""Raw response framing, not provider identity/visible-delivery acceptance."""
from hashlib import sha256
import pytest
from oracle_brain.meetings.participation_wire_v1 import observed_participation_wire_v1,MAX_RESPONSE_WIRE_V1


def response(status=200,body=b'{}',extra=b''):
    return b'HTTP/1.1 '+str(status).encode()+b' OK\r\nContent-Length: '+str(len(body)).encode()+b'\r\nConnection: close\r\n'+extra+b'\r\n'+body


@pytest.mark.parametrize('status',[200,202,204,400,429,500])
def test_actual_full_wire_facts_do_not_invent_visibility_or_success(status):
    raw=response(status);v=observed_participation_wire_v1(raw)
    assert v==dict(complete=True,http_status=status,response_sha256=sha256(raw).hexdigest(),response_byte_count=len(raw),error=None)
    assert 'visible_message_proven' not in v and 'remote_stop_proven' not in v


@pytest.mark.parametrize('raw',[b'',b'partial',response()[:-1],response()+b'extra',response()+response(),
    response(extra=b'Content-Length: 2\r\n'),response(extra=b'Content-Encoding: gzip\r\n'),
    response(extra=b'Transfer-Encoding: chunked\r\n'),response(extra=b' folded: value\r\n'),
    response(extra=b'X-Test: a\r\nX-Test: b\r\n'),response(extra=b'X-Test: '+b'x'*16384+b'\r\n')])
def test_missing_or_ambiguous_wire_remains_unknown(raw):
    v=observed_participation_wire_v1(raw)
    assert v['complete'] is False and v['http_status'] is None and v['error']=='framing'
    assert v['response_sha256']==sha256(raw).hexdigest() and v['response_byte_count']==len(raw)


@pytest.mark.parametrize('error',['network','timeout','framing','expired','unknown'])
def test_even_complete_late_wire_is_unknown_when_transport_refused(error):
    raw=response();v=observed_participation_wire_v1(raw,error=error)
    assert not v['complete'] and v['http_status'] is None and v['error']==error
    assert v['response_sha256']==sha256(raw).hexdigest()


@pytest.mark.parametrize('raw,error',[(b'x'*(MAX_RESPONSE_WIRE_V1+1),None),('caller text',None),(b'','retry'),(b'',True)])
def test_bound_and_closed_error_before_any_custody(raw,error):
    with pytest.raises(ValueError):observed_participation_wire_v1(raw,error=error)
