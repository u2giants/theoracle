from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.replacement_result_v1 import parse_result_request_v1

def request(now):
    return dict(schema_version=1,protocol='replacement-protected-result-v1',journey_id=str(uuid4()),
        expected_journey_revision=1,model_id=str(uuid4()),model_version=1,content_hash='a'*64,
        projection_digest='b'*64,ack_event_id=str(uuid4()),summary_artifact_id=str(uuid4()),
        summary_version=1,summary_content_hash='c'*64,nonce='d'*64,expires_at=(now+timedelta(seconds=20)).isoformat())

def test_fixed_result_wire_accepts_selectors_not_identity_authority():
    now=datetime.now(timezone.utc);body=request(now)
    parsed=parse_result_request_v1(canonical_bytes(body),now=now)
    assert str(parsed.journey_id)==body['journey_id'] and parsed.expires_at==now+timedelta(seconds=20)

@pytest.mark.parametrize('key,value', [('schema_version',True),('schema_version',1.0),('model_version',True),
    ('expected_journey_revision','1'),('protocol','replacement-protected-result-v2'),('nonce','A'*64),
    ('actor',str(uuid4())),('workspace_id',str(uuid4())),('profile','executor'),('config_path','/private'),
    ('intent','arbitrary-query'),('expires_at','2026-01-01T00:00:00')])
def test_result_wire_rejects_foreign_selectors_types_and_authority_fields(key,value):
    now=datetime.now(timezone.utc);body=request(now);body[key]=value
    with pytest.raises(PermissionError):parse_result_request_v1(canonical_bytes(body),now=now)

@pytest.mark.parametrize('delta',[0,-1,31])
def test_result_wire_cannot_extend_or_replay_expired_window(delta):
    now=datetime.now(timezone.utc);body=request(now);body['expires_at']=(now+timedelta(seconds=delta)).isoformat()
    with pytest.raises(PermissionError):parse_result_request_v1(canonical_bytes(body),now=now)

@pytest.mark.parametrize('raw',[b'null',b'[]',b'{"schema_version":1,"schema_version":1}',b' '*4097,b'{"x":NaN}',b'\xff'])
def test_result_wire_malformed_bytes_fixed_refusal(raw):
    with pytest.raises(PermissionError,match='result request'):parse_result_request_v1(raw,now=datetime.now(timezone.utc))
