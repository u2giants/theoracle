"""Live workspace actor epochs are not employee or shared-source grants."""
import hashlib,json
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
from oracle_brain.operating_model.contracts import digest
from oracle_brain.meetings.participant_epoch import LiveParticipantEpochV1,LiveParticipantLinkV1
from oracle_brain.meetings.capture_contracts import RawMeetingArtifactV1
from oracle_brain.meetings.final_transcript import parse_live_recall_utterance_v1

def fixture():
    now=datetime.now(timezone.utc);workspace,meeting,actor=uuid4(),uuid4(),uuid4()
    epoch=LiveParticipantEpochV1(purpose='meeting-live-participant-epoch-v1',epoch_id=uuid4(),epoch_revision=1,workspace_id=workspace,meeting_id=meeting,provider='recall',provider_account='account',tenant_id='tenant',provider_meeting_id='meeting',bot_id='bot',provider_participant_ids=('1','2','3'),participant_set_sha256=digest({'provider_participant_ids':['1','2','3']}),links=(LiveParticipantLinkV1(provider_participant_id='1',attribution='workspace_actor',actor_id=actor,employee_uuid_metadata=uuid4(),mapping_evidence_sha256='a'*64),LiveParticipantLinkV1(provider_participant_id='2',attribution='oracle',actor_id=None,mapping_evidence_sha256='b'*64),LiveParticipantLinkV1(provider_participant_id='3',attribution='unknown',actor_id=None,mapping_evidence_sha256='c'*64)),issuer_actor=uuid4(),reviewer_actor=uuid4(),capture_until=now+timedelta(seconds=20),valid_from=now-timedelta(seconds=1),expires_at=now+timedelta(seconds=10),original_horizon=now+timedelta(seconds=30))
    return now,epoch

def parse(epoch,now,*,speaker=1,event='transcript.data',bot='bot',text='原话'):
    raw=json.dumps(dict(event=event,data=dict(bot=dict(id=bot),data=dict(participant=dict(id=speaker,name='Not authority',email='ignored@example.test'),words=[dict(text=text,start_timestamp=dict(relative=1.125),end_timestamp=None)],language_code='zh'))),ensure_ascii=False).encode()
    d=RawMeetingArtifactV1(workspace_id=epoch.workspace_id,meeting_id=epoch.meeting_id,provider='recall',provider_account=epoch.provider_account,tenant_id=epoch.tenant_id,provider_meeting_id=epoch.provider_meeting_id,provider_artifact_id='message',provider_revision='1',original_sha256=hashlib.sha256(raw).hexdigest(),byte_count=len(raw),media_type='application/json',final=False)
    return parse_live_recall_utterance_v1(raw,d,revision=1,epoch=epoch,observed_at=now,expected_bot_id='bot')

def test_one_epoch_supports_distinct_raw_words_with_exact_original_language():
    now,e=fixture();a=parse(e,now);b=parse(e,now,text='另一句')
    assert a.turns[0].words[0].text=='原话' and b.turns[0].words[0].text=='另一句' and a.raw.original_sha256!=b.raw.original_sha256
    assert a.turns[0].employee_id is None and a.raw.final is False

@pytest.mark.parametrize('change',[dict(provider_participant_ids=('1','1')),dict(provider_participant_ids=('3','2','1')),dict(participant_set_sha256='0'*64),dict(links=()),dict(epoch_revision=True)])
def test_malformed_or_incomplete_epoch_population_refuses(change):
    _now,e=fixture()
    with pytest.raises(ValueError):LiveParticipantEpochV1.model_validate(e.model_copy(update=change).model_dump(mode='python'))

@pytest.mark.parametrize('change',[dict(speaker=4),dict(speaker=True),dict(event='transcript.partial_data'),dict(bot='other')])
def test_unknown_stable_identity_partial_or_wrong_bot_cannot_enter_current_turn(change):
    now,e=fixture()
    with pytest.raises(ValueError):parse(e,now,**change)

def test_oracle_and_unknown_stay_visible_and_never_become_employee():
    now,e=fixture()
    assert parse(e,now,speaker=2).turns[0].attribution=='oracle'
    assert parse(e,now,speaker=3).turns[0].attribution=='unknown'
    assert all(parse(e,now,speaker=i).turns[0].employee_id is None for i in (1,2,3))

def test_expired_epoch_and_wrong_full_scope_refuse():
    now,e=fixture()
    with pytest.raises(ValueError):parse(e,now+timedelta(seconds=11))
    with pytest.raises(ValueError):parse(e.model_copy(update=dict(bot_id='foreign')),now)
