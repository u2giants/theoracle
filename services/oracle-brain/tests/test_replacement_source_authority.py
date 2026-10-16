"""Strict replacement metadata mechanics; actual SQL roles are tested separately."""
import json
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
from oracle_brain.operating_model.contracts import ReplacementExecutorTargetV1


def target_metadata():
    now=datetime.now(timezone.utc);workspace,source,model,run,actor,ack=(uuid4() for _ in range(6))
    return dict(schema_version=1,run_id=str(run),journey_revision=1,state='delivered',answer_hold=False,cancelled=False,
        population_sha256='a'*64,requester_principal_id=str(actor),workspace_id=str(workspace),model_id=str(model),
        model_version=1,model_content_hash='b'*64,ack_event_id=str(ack),projection_digest='c'*64,
        source_refs=[dict(schema_version=1,workspace_id=str(workspace),source_id=str(source),revision=1,
            original_sha256='d'*64,reading_sha256='e'*64,parser_id='f'*64)],current_confirmation=None,
        summary_targets=[],checked_at=now.isoformat(),valid_until=(now+timedelta(seconds=5)).isoformat())


def test_strict_executor_run_metadata_is_metadata_only():
    value=target_metadata();parsed=ReplacementExecutorTargetV1.model_validate_json(json.dumps(value))
    assert parsed.run_id and parsed.summary_targets==() and parsed.valid_until>parsed.checked_at
    for private in ('private_object_key','signature','receipt_secret','raw_wire','reading'):
        with pytest.raises(ValueError):ReplacementExecutorTargetV1.model_validate_json(json.dumps(value|{private:'forbidden'}))


@pytest.mark.parametrize('damage',['bool_revision','duplicate_source','foreign_workspace','expired','held_badge','changed_summary_parent'])
def test_executor_run_metadata_refuses_inconsistent_or_noncurrent_identity(damage):
    value=target_metadata()
    if damage=='bool_revision':value['journey_revision']=True
    elif damage=='duplicate_source':value['source_refs']*=2
    elif damage=='foreign_workspace':value['source_refs'][0]['workspace_id']=str(uuid4())
    elif damage=='expired':value['valid_until']=value['checked_at']
    elif damage=='held_badge':
        value['answer_hold']=True
        value['current_confirmation']=dict(workflow_id='workflow',version=1,content_hash=value['model_content_hash'],eligible=True)
    else:
        value['summary_targets']=[dict(summary_artifact_id=str(uuid4()),summary_version=1,summary_content_hash='a'*64,
            qualified_parent_id=str(uuid4()),qualified_parent_version=1,qualified_parent_content_hash=value['model_content_hash'])]
    with pytest.raises(ValueError):ReplacementExecutorTargetV1.model_validate_json(json.dumps(value))


@pytest.mark.parametrize('version',[True,False,1.0,'1'])
def test_replacement_metadata_version_cannot_coerce_noninteger(version):
    value=target_metadata();value['schema_version']=version
    with pytest.raises(ValueError):ReplacementExecutorTargetV1.model_validate_json(json.dumps(value))
