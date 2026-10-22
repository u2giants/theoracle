"""Invented whole-final provider bytes; no provider or employee-session proof."""
import hashlib,json
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
from oracle_brain.meetings.capture_contracts import RawMeetingArtifactV1,derive_reported_text_v1
from oracle_brain.meetings.final_transcript import InstalledSpeakerMappingV1,InstalledSpeakerLinkV1,parse_final_recall_v1

def case():
    now=datetime.now(timezone.utc)
    turns=[dict(participant=dict(id=1,name='Untrusted CEO',email='ignored@example.test'),language_code='zh',words=[dict(text='原话',start_timestamp=dict(relative=1.125),end_timestamp=dict(relative=2.0))]),dict(participant=dict(id=2,name='Oracle'),language_code='en',words=[dict(text='Suggestion',start_timestamp=dict(relative=3),end_timestamp=None)]),dict(participant=dict(id=3,name='Employee'),language_code='en',words=[dict(text='Unknown',start_timestamp=dict(relative=4),end_timestamp=None)])]
    raw=json.dumps(turns,ensure_ascii=False).encode()
    descriptor=RawMeetingArtifactV1(workspace_id=uuid4(),meeting_id=uuid4(),provider='recall',provider_account='independent-account',tenant_id='independent-tenant',provider_meeting_id='meeting',provider_artifact_id='transcript',provider_revision='r1',original_sha256=hashlib.sha256(raw).hexdigest(),byte_count=len(raw),media_type='application/json',final=True)
    mapping=InstalledSpeakerMappingV1(purpose='meeting-speaker-mapping-v1',**{key:getattr(descriptor,key) for key in ('workspace_id','meeting_id','provider','provider_account','tenant_id','provider_meeting_id')},raw_sha256=descriptor.original_sha256,links=(InstalledSpeakerLinkV1(provider_speaker_id='1',attribution='verified_external'),InstalledSpeakerLinkV1(provider_speaker_id='2',attribution='oracle')),issuer_actor=uuid4(),reviewer_actor=uuid4(),valid_from=now-timedelta(seconds=1),expires_at=now+timedelta(seconds=10),original_horizon=now+timedelta(seconds=20))
    return now,raw,descriptor,mapping

def test_actual_final_schema_exact_language_unknown_and_oracle_accounted():
    now,raw,d,m=case();revision=parse_final_recall_v1(raw,d,revision=1,mapping=m,observed_at=now)
    assert revision.turns[0].words[0].start_relative_seconds=='1.125'
    assert [t.attribution for t in revision.turns]==['verified_external','oracle','unknown']
    text,seal=derive_reported_text_v1(revision)
    assert text=='原话'.encode() and seal.included_turn_ids==('raw-turn:0',) and seal.excluded_turn_ids==('raw-turn:1','raw-turn:2')
    assert seal.qualification is False

def test_names_and_email_never_map_employee_without_installed_link():
    now,raw,d,_=case();revision=parse_final_recall_v1(raw,d,revision=1,observed_at=now)
    assert all(t.attribution=='unknown' and t.employee_id is None for t in revision.turns)
    with pytest.raises(ValueError,match='no independently'):derive_reported_text_v1(revision)

@pytest.mark.parametrize('change',[dict(meeting_id=uuid4()),dict(provider_account='other'),dict(raw_sha256='0'*64),dict(expires_at=datetime(2020,1,1,tzinfo=timezone.utc))])
def test_mapping_exact_scope_raw_and_freshness(change):
    now,raw,d,m=case()
    with pytest.raises(ValueError):parse_final_recall_v1(raw,d,revision=1,mapping=m.model_copy(update=change),observed_at=now)

@pytest.mark.parametrize('mutate',[lambda v:v[0]['participant'].update(id=True),lambda v:v[0]['words'][0]['start_timestamp'].update(relative=True),lambda v:v[0]['words'][0]['start_timestamp'].update(relative=-1),lambda v:v[0].update(words=[]),lambda v:v[0].update(language_code=None)])
def test_malformed_actual_provider_types_refuse(mutate):
    now,raw,d,_=case();value=json.loads(raw);mutate(value);raw=json.dumps(value).encode();d=d.model_copy(update=dict(byte_count=len(raw),original_sha256=hashlib.sha256(raw).hexdigest()))
    with pytest.raises(ValueError):parse_final_recall_v1(raw,d,revision=1,observed_at=now)

def test_duplicate_json_and_raw_mismatch_and_live_utterance_refuse():
    now,raw,d,_=case()
    for data,desc in [(raw+b' ',d),(raw,d.model_copy(update=dict(final=False)))]:
        with pytest.raises(ValueError):parse_final_recall_v1(data,desc,revision=1,observed_at=now)
    raw=b'[{"participant":{},"participant":{},"words":[]}]';d=d.model_copy(update=dict(byte_count=len(raw),original_sha256=hashlib.sha256(raw).hexdigest()))
    with pytest.raises(ValueError):parse_final_recall_v1(raw,d,revision=1,observed_at=now)

def test_dangling_and_duplicate_installed_speakers_refuse():
    now,raw,d,m=case();links=m.links+(InstalledSpeakerLinkV1(provider_speaker_id='9',attribution='verified_external'),)
    with pytest.raises(ValueError,match='dangling'):parse_final_recall_v1(raw,d,revision=1,mapping=m.model_copy(update=dict(links=links)),observed_at=now)
    with pytest.raises(ValueError):InstalledSpeakerMappingV1.model_validate(m.model_copy(update=dict(links=m.links+m.links)).model_dump(mode='python'))

# Graph's documented voice labels contain display names, not directory IDs.
# This exact-raw positional cue mapping is independently installed.
def graph_case(raw=None):
    from oracle_brain.meetings.final_transcript import parse_final_graph_v1
    now,_raw,d,m=case()
    raw=raw or 'WEBVTT\n\n1\n00:00:01.125 --> 00:00:02.000\n<v CEO>原话 &amp; text</v>\n\n2\n00:00:03.000 --> 00:00:04.000\n<v Oracle>Suggestion</v>\n\n3\n00:00:04.000 --> 00:00:05.000\n<v Employee>Unknown</v>\n'.encode()
    d=d.model_copy(update=dict(provider='graph',media_type='text/vtt',original_sha256=hashlib.sha256(raw).hexdigest(),byte_count=len(raw)))
    m=m.model_copy(update=dict(provider='graph',raw_sha256=d.original_sha256,links=(InstalledSpeakerLinkV1(provider_speaker_id='raw-cue:0',attribution='verified_external'),InstalledSpeakerLinkV1(provider_speaker_id='raw-cue:1',attribution='oracle'))))
    return parse_final_graph_v1,now,raw,d,m

def test_graph_exact_original_cues_language_and_display_only_names():
    parse,now,raw,d,m=graph_case();v=parse(raw,d,revision=1,language='zh',mapping=m,observed_at=now)
    assert [t.display_name for t in v.turns]==['CEO','Oracle','Employee']
    assert [t.attribution for t in v.turns]==['verified_external','oracle','unknown']
    text,seal=derive_reported_text_v1(v)
    assert text=='原话 & text'.encode() and seal.excluded_turn_ids==('raw-cue:1','raw-cue:2')
    assert v.turns[0].words[0].start_relative_seconds=='1.125'
    assert all(t.employee_id is None for t in parse(raw,d,revision=1,language='zh',observed_at=now).turns)

@pytest.mark.parametrize('mutate',[
 lambda raw:raw.replace(b'WEBVTT',b'NOTVTT'),
 lambda raw:raw.replace(b'00:00:01.125',b'00:60:01.125'),
 lambda raw:raw.replace(b'00:00:02.000',b'00:00:00.000'),
 lambda raw:raw.replace(b'\n2\n',b'\n1\n'),
 lambda raw:raw.replace(b'&amp; text',b'<script>text</script>'),
 lambda raw:raw.replace(b'&amp; text',b'\x00'),
 lambda raw:raw.replace(b' --> ',b'-->'),
])
def test_graph_malformed_or_unsupported_original_never_silently_drops_content(mutate):
    parse,now,raw,_d,_m=graph_case();raw=mutate(raw);parse,now,raw,d,m=graph_case(raw)
    with pytest.raises(ValueError):parse(raw,d,revision=1,language='zh',mapping=m,observed_at=now)

def test_graph_missing_language_foreign_or_dangling_mapping_refuses():
    parse,now,raw,d,m=graph_case()
    with pytest.raises(ValueError):parse(raw,d,revision=1,language='',mapping=m,observed_at=now)
    with pytest.raises(ValueError):parse(raw,d,revision=1,language='zh',mapping=m.model_copy(update=dict(raw_sha256='0'*64)),observed_at=now)
    with pytest.raises(ValueError):parse(raw,d,revision=1,language='zh',mapping=m.model_copy(update=dict(links=m.links+(InstalledSpeakerLinkV1(provider_speaker_id='raw-cue:9',attribution='oracle'),))),observed_at=now)
