"""Closed read selection; request data cannot install or change research rights."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import json
import pytest
from oracle_brain.hosting.industry_answer_v1 import parse_industry_question_v1
from oracle_brain.hosting.connected_answer_service_v1 import parse_answer_request_v1
from oracle_brain.operating_model.contracts import canonical_bytes


def request(**changes):
    return dict(schema_version=1,protocol='qualified-industry-question-v1',operation='contexts',
        decision_id=None,caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=20)).isoformat())|changes


def test_same_closed_answer_owner_selects_industry_reader_without_another_transport():
    value=request();raw=canonical_bytes(value)
    assert parse_answer_request_v1(raw)==parse_industry_question_v1(raw)
    decision=uuid4();parsed=parse_industry_question_v1(canonical_bytes(request(operation='brief',decision_id=str(decision))))
    assert parsed.decision_id==decision


@pytest.mark.parametrize('changes',[
    {'schema_version':True},{'schema_version':2},{'operation':'fetch'},
    {'operation':'schedule'},{'operation':'force'},{'operation':'contexts','decision_id':str(uuid4())},
    {'operation':'brief'},{'principal_id':str(uuid4())},{'workspace_id':str(uuid4())},
    {'model_id':str(uuid4())},{'permission':True},{'source_id':str(uuid4())},
    {'operation':'brief','decision_id':uuid4().hex},
    {'operation':'brief','decision_id':str(uuid4()).upper()},
])
def test_industry_read_refuses_effects_foreign_authority_or_noncanonical_selection(changes):
    with pytest.raises((ValueError,PermissionError)):parse_industry_question_v1(canonical_bytes(request(**changes)))


def test_industry_question_does_not_accept_duplicate_or_noncanonical_or_oversized_json():
    raw=canonical_bytes(request())
    for malformed in (b' '+raw,raw.replace(b'"schema_version":1',b'"schema_version":1,"schema_version":1'),
                      json.dumps(request(),indent=2).encode(),b' '*4097):
        with pytest.raises((ValueError,PermissionError)):parse_industry_question_v1(malformed)


def test_industry_owned_loop_uses_exact_original_deadline_without_new_wire_field():
    from datetime import datetime,timezone,timedelta
    from oracle_brain.hosting.connected_answer_service_v1 import parse_answer_request_v1
    from oracle_brain.operating_model.contracts import canonical_bytes
    deadline=(datetime.now(timezone.utc)+timedelta(seconds=10)).isoformat()
    request=parse_answer_request_v1(canonical_bytes(dict(schema_version=1,
        protocol='qualified-industry-question-v1',operation='contexts',decision_id=None,
        caller_deadline=deadline)))
    assert request.expires_at==request.caller_deadline
    assert request.expires_at.isoformat()==deadline
    assert 'expires_at' not in request.model_dump(mode='json')
