"""Pure installed final workspace mapping, never employee/source authority."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
from oracle_brain.meetings.final_mapping import FinalWorkspaceSpeakerMappingV1,FinalWorkspaceSpeakerLinkV1
from oracle_brain.meetings.final_transcript import parse_final_graph_v1
from test_meeting_final_transcript import graph_case

def case():
    now=datetime.now(timezone.utc)
    return FinalWorkspaceSpeakerMappingV1(purpose='meeting-final-workspace-mapping-v1',mapping_id=uuid4(),mapping_revision=1,workspace_id=uuid4(),meeting_id=uuid4(),provider='graph',provider_account='account',tenant_id='tenant',provider_meeting_id='meeting',raw_sha256='a'*64,language='zh',links=(FinalWorkspaceSpeakerLinkV1(provider_speaker_id='raw-cue:0',attribution='workspace_actor',actor_id=uuid4(),mapping_evidence_sha256='b'*64),),issuer_actor=uuid4(),reviewer_actor=uuid4(),valid_from=now-timedelta(seconds=1),expires_at=now+timedelta(seconds=10),original_horizon=now+timedelta(seconds=20))

def test_workspace_actor_projection_cannot_create_employee_or_source():
    m=case();v=m.structural_mapping_v1()
    assert v.links[0].attribution=='verified_external' and v.links[0].employee_id is None
    assert not hasattr(m,'source_id') and not hasattr(m,'employee_id')
    assert m.sha256!=m.model_copy(update=dict(mapping_revision=2)).sha256

@pytest.mark.parametrize('changes',[dict(schema_version=True),dict(mapping_revision=True),dict(provider_account=' '),dict(language=''),dict(expires_at=datetime(2040,1,1,tzinfo=timezone.utc))])
def test_actual_types_nonblank_language_and_original_horizon(changes):
    v=case().model_dump(mode='python');v.update(changes)
    with pytest.raises(ValueError):FinalWorkspaceSpeakerMappingV1.model_validate(v)

@pytest.mark.parametrize('changes',[dict(schema_version=True),dict(attribution='verified_employee'),dict(actor_id=None),dict(provider_speaker_id=' ')])
def test_no_employee_label_or_unmapped_actor_or_blank_cue(changes):
    v=case().links[0].model_dump(mode='python');v.update(changes)
    with pytest.raises(ValueError):FinalWorkspaceSpeakerLinkV1.model_validate(v)

def test_duplicate_or_unknown_mapping_cannot_masquerade_as_actor():
    m=case();v=m.model_dump(mode='python');v['links']=m.links+m.links
    with pytest.raises(ValueError):FinalWorkspaceSpeakerMappingV1.model_validate(v)
    unknown=FinalWorkspaceSpeakerLinkV1(provider_speaker_id='raw-cue:1',attribution='unknown',actor_id=None,mapping_evidence_sha256='c'*64)
    assert m.model_copy(update=dict(links=(unknown,))).structural_mapping_v1().links==()
