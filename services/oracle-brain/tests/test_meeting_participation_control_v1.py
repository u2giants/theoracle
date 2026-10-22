"""Closed host input contract; no SQL/provider/browser acceptance."""
from datetime import datetime,timezone,timedelta
from uuid import uuid4
import json
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.meetings.participation_control_contracts_v1 import parse_participation_control_v1


def body():
    return dict(schema_version=1,operation='control',expected_head=0,command_id=str(uuid4()),enabled=True,
        proactive_enabled=False,cooldown_seconds=120,max_proactive=3,
        caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=20)).isoformat().replace('+00:00','Z'))


def test_exact_host_controls_roundtrip():
    value=body();parsed=parse_participation_control_v1(canonical_bytes(value))
    assert parsed.enabled and not parsed.proactive_enabled and parsed.max_proactive==3


@pytest.mark.parametrize('key,value',[('actor',str(uuid4())),('workspace',str(uuid4())),('role','sender'),
    ('observation_id',str(uuid4())),('chat_available',True),('text','Oracle invented caller bytes'),
    ('body',{'to':'everyone','message':'invented'}),('provider','recall'),('bot_id',str(uuid4())),
    ('config','self-appointed'),('audience_complete',True)])
def test_authority_observation_or_body_selectors_refused(key,value):
    original=body();original[key]=value
    with pytest.raises(ValueError):parse_participation_control_v1(canonical_bytes(original))


@pytest.mark.parametrize('change',[dict(expected_head=True),dict(expected_head=-1),dict(enabled=1),
    dict(proactive_enabled='false'),dict(cooldown_seconds=119),dict(max_proactive=4),
    dict(operation='send'),dict(enabled=False,proactive_enabled=True)])
def test_noncanonical_or_widened_control_refused(change):
    original=body();original.update(change)
    with pytest.raises(ValueError):parse_participation_control_v1(canonical_bytes(original))


def test_duplicates_and_noncanonical_order_refused():
    original=body();raw=canonical_bytes(original)
    with pytest.raises(ValueError):parse_participation_control_v1(raw.replace(b'"enabled":true',b'"enabled":false,"enabled":true'))
    with pytest.raises(ValueError):parse_participation_control_v1(json.dumps(original).encode())


def test_omitted_defaults_do_not_manufacture_fresh_permissions():
    original=body();original.pop('proactive_enabled')
    with pytest.raises(ValueError):parse_participation_control_v1(canonical_bytes(original))
