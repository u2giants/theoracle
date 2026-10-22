"""Pure refusal boundaries for pending normalization custody metadata."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
from oracle_brain.hosting.meeting_normalization_v1 import (MeetingNormalizationConfigV1,
    NormalizationSourceBindingV1,normalization_idempotency_key_v1)


def config():
    now=datetime.now(timezone.utc)
    return dict(schema_version=1,purpose='meeting-normalization-consumer-v1',capture_config_sha256='a'*64,
        intake_config_sha256='b'*64,intake_appointment_sha256='c'*64,intake_issuer_actor=uuid4(),
        intake_reviewer_actor=uuid4(),issuer_actor=uuid4(),reviewer_actor=uuid4(),valid_from=now,
        expires_at=now+timedelta(seconds=20),original_processing_horizon=now+timedelta(seconds=30))


@pytest.mark.parametrize('field,value',[('schema_version',True),('schema_version',1.0),
    ('purpose','meeting-capture-worker-consumer-v1'),('intake_config_sha256',''),
    ('future_source_id',uuid4()),('future_reading_commit_sha256','f'*64)])
def test_no_schema_coercion_wider_purpose_or_future_phase_appointment(field,value):
    c=config();c[field]=value
    with pytest.raises(ValueError):MeetingNormalizationConfigV1.model_validate(c)


def test_no_self_issuer_or_renewed_processing_window():
    c=config();c['reviewer_actor']=c['issuer_actor']
    with pytest.raises(ValueError):MeetingNormalizationConfigV1.model_validate(c)
    c=config();c['expires_at']=c['original_processing_horizon']+timedelta(microseconds=1)
    with pytest.raises(ValueError):MeetingNormalizationConfigV1.model_validate(c)


@pytest.mark.parametrize('field,value',[('qualification',0),('qualification',True),
    ('source_read_permission',0),('source_read_permission',True),('byte_count',True)])
def test_source_link_cannot_be_coerced_to_grant(field,value):
    c=dict(workspace_id=uuid4(),source_id=uuid4(),revision=1,original_sha256='a'*64,
        byte_count=10,custody_seal_sha256='b'*64,qualification=False,source_read_permission=False)
    c[field]=value
    with pytest.raises(ValueError):NormalizationSourceBindingV1.model_validate(c)


def test_global_idempotency_is_scope_bound_never_profile_selected():
    workspace,meeting,event=uuid4(),uuid4(),uuid4()
    key=normalization_idempotency_key_v1(workspace,meeting,event)
    assert key==normalization_idempotency_key_v1(workspace,meeting,event)
    assert len({key,normalization_idempotency_key_v1(uuid4(),meeting,event),
        normalization_idempotency_key_v1(workspace,uuid4(),event),
        normalization_idempotency_key_v1(workspace,meeting,uuid4())})==4
    with pytest.raises(TypeError):normalization_idempotency_key_v1(str(workspace),meeting,event)
