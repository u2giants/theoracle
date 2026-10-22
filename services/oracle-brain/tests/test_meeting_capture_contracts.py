"""Pure lineage bounds; no DTO grants capture or qualification."""
from uuid import uuid4
import hashlib
import pytest
from oracle_brain.meetings.capture_contracts import RawMeetingArtifactV1,MeetingWordV1,MeetingTurnV1,MeetingRevisionV1,MeetingTextDerivationV1,derive_reported_text_v1,reconcile_revision_v1

def revision(**updates):
    raw=RawMeetingArtifactV1(workspace_id=uuid4(),meeting_id=uuid4(),provider='recall',provider_account='account',tenant_id='tenant',provider_meeting_id='exact-provider-meeting',provider_artifact_id='artifact',provider_revision='etag1',original_sha256='a'*64,byte_count=10,media_type='application/json',final=True)
    turns=tuple(MeetingTurnV1(turn_id=str(i),provider_speaker_id=str(i),display_name='Same Name',employee_id=uuid4() if kind=='verified_employee' else None,attribution=kind,language='zh-CN',words=(MeetingWordV1(text=text,start_relative_seconds='1.25',end_relative_seconds='2.000'),)) for i,(kind,text) in enumerate((('verified_employee','原文'),('unknown','unknown speaker'),('oracle','assistant words'))))
    return MeetingRevisionV1(raw=raw,revision=1,turns=turns,**updates)
def test_final_original_language_and_exact_raw_lineage_excludes_oracle_and_unknown():
    r=revision();text,binding=derive_reported_text_v1(r)
    assert text=='原文'.encode() and binding.raw==r.raw and binding.normalized_sha256==hashlib.sha256(text).hexdigest()
    assert binding.included_turn_ids==('0',) and binding.excluded_turn_ids==('1','2') and binding.qualification is False
    assert r.turns[0].words[0].start_relative_seconds=='1.25'
def test_live_never_normalized_and_revision_original_swaps_conflict():
    r=revision();live=r.model_copy(update={'raw':r.raw.model_copy(update={'final':False})})
    with pytest.raises(ValueError,match='whole-final'):derive_reported_text_v1(live)
    assert reconcile_revision_v1(r,r)==r
    for change in ({'original_sha256':'b'*64},{'provider_artifact_id':'other'},{'provider_revision':'etag2'}):
        with pytest.raises(ValueError,match='conflict'):reconcile_revision_v1(r,r.model_copy(update={'raw':r.raw.model_copy(update=change)}))
    with pytest.raises(ValueError,match='final'):reconcile_revision_v1(r,live.model_copy(update={'revision':2}))
def test_cross_tenant_provider_account_and_unknown_identity_refuse():
    r=revision()
    for change in ({'tenant_id':'other'},{'provider_account':'other'},{'meeting_id':uuid4()},{'workspace_id':uuid4()},{'provider':'graph'}):
        with pytest.raises(ValueError,match='cross-meeting'):reconcile_revision_v1(r,r.model_copy(update={'raw':r.raw.model_copy(update=change),'revision':2}))
    with pytest.raises(ValueError,match='employee link'):MeetingTurnV1.model_validate(r.turns[0].model_copy(update={'employee_id':None}).model_dump(mode='python'))
def test_bools_text_time_population_and_observation_flags_strict():
    r=revision()
    for change in ({'revision':True},{'revision':0},{'turns':(r.turns[0],r.turns[0])}):
        with pytest.raises(ValueError):MeetingRevisionV1.model_validate(r.model_copy(update=change).model_dump(mode='python'))
    for t in ('NaN','Infinity','-1','01','1e3'):
        with pytest.raises(ValueError):MeetingWordV1(text='original',start_relative_seconds=t)
    with pytest.raises(ValueError):MeetingWordV1(text='original',start_relative_seconds='2',end_relative_seconds='1')
    _,binding=derive_reported_text_v1(r)
    for field,value in (('qualification',0),('reported_only',1),('excluded_turn_ids',('0',))):
        with pytest.raises(ValueError):MeetingTextDerivationV1.model_validate(binding.model_copy(update={field:value}).model_dump(mode='python'))
