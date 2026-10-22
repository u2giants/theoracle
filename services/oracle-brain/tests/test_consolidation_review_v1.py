"""Closed request contract; no DTO is actual authority or browser acceptance."""
import json
from datetime import datetime,timezone,timedelta
from uuid import uuid4
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.consolidation_review_v1 import parse_review_request

def request():return dict(schema_version=1,operation='inspect',model_id=str(uuid4()),base_version=1,caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=10)).isoformat().replace('+00:00','Z'))
@pytest.mark.parametrize('damage',('actor','role','url','config','advance','missing','boolean','replay','duplicate','noncanonical'))
def test_closed_review_request_refuses_before_consumer(damage):
    value=request()
    if damage in ('actor','role','url','config','advance'):value[damage]='untrusted'
    elif damage=='missing':del value['base_version']
    elif damage=='boolean':value['base_version']=True
    elif damage=='replay':value['operation']='retry'
    raw=canonical_bytes(value)
    if damage=='duplicate':raw=raw.replace(b'"base_version":1',b'"base_version":1,"base_version":1')
    elif damage=='noncanonical':raw=json.dumps(value).encode()
    with pytest.raises((ValueError,PermissionError)):parse_review_request(raw)

def test_closed_inspect_request_preserves_original_absolute_deadline():
    raw=canonical_bytes(request());parsed=parse_review_request(raw)
    assert canonical_bytes(parsed.model_dump(mode='json'))==raw



def test_decision_assertion_tuple_is_exact_existing_sql_selector():
    value=request();value.pop('base_version');value.update(operation='decide',version=1,expected_hash='a'*64,decision='accept',decision_kind='employee-account',
        scope={'schema_version':1,**{k:{'schema_version':1,'mode':'unknown','identities':[]} for k in ('process','customer','product','region')}},
        assertions=[{'assertion_id':str(uuid4()),'revision':1}],command_id=str(uuid4()))
    parsed=parse_review_request(canonical_bytes(value))
    assert set(parsed.assertions[0].model_dump())=={'assertion_id','revision'}


@pytest.mark.parametrize('damage',('mutable-semantic-pins','mutable-capability-pins'))
def test_installed_consumer_cannot_retain_mutable_authority_pins(damage):
    from oracle_brain.operating_model.consolidation_authority_v1 import ConsolidationBindingV1,_FUNCTIONS
    values=dict(appointment_id=uuid4(),principal_id=uuid4(),workspace_id=uuid4(),model_id=uuid4(),session_login='invented_history',expected_owner='invented_owner',operation='history-read',
        runtime_hash='a'*64,registry_hash='b'*64,config_hash='c'*64,ca_path='/not-an-installed-ca',ca_sha256='d'*64,original_horizon=datetime.now(timezone.utc)+timedelta(seconds=20),
        retained_semantic_admissions=frozenset({'e'*64}),capability_body_hashes=tuple((signature.split('(')[0],'f'*64) for signature in _FUNCTIONS)+(('_commit_processing_candidate_canonical_v1','f'*64),))
    if damage=='mutable-semantic-pins':values['retained_semantic_admissions']=set(values['retained_semantic_admissions'])
    else:values['capability_body_hashes']=list(values['capability_body_hashes'])
    with pytest.raises(PermissionError):ConsolidationBindingV1(**values)
