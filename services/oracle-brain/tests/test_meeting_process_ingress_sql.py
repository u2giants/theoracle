"""Actual dedicated owned SQL + existing custody/intake, invented identities.

The final capture event here is explicitly installed/written through the actual
same owner fixture; these cases do not claim provider-network or queue proof.
"""
from datetime import datetime,timedelta,timezone
from uuid import uuid4,uuid5,NAMESPACE_URL
from pathlib import Path
import hashlib,json,time
import psycopg
from psycopg.types.json import Jsonb
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.meeting_capture_v1 import load_meeting_capture_settings_v1,MeetingCaptureFactoryV1
from oracle_brain.hosting.meeting_normalization_v1 import load_meeting_normalization_settings_v1,MeetingNormalizationFactoryV1
from oracle_brain.meetings.capture_contracts import InstalledFinalArtifactV1
from oracle_brain.meetings.processing_contracts import final_population_sha256_v1
from test_meeting_normalization_sql import normalized
from test_meeting_capture_sql import meeting_sql,admin,ingest,deadline,original_request_fence


def install(x,f,tmp_path,selection,*,actions=None,operation=None):
    old=f.settings.capture;ident=uuid4();seal=hashlib.sha256(ident.bytes).hexdigest();raw=canonical_bytes(selection.model_dump(mode='json'));desc=tmp_path/(ident.hex+'-selection');desc.write_bytes(raw);desc.chmod(0o600);sha=hashlib.sha256(raw).hexdigest()
    op=operation or uuid5(NAMESPACE_URL,f'oracle-meeting-final:{x["workspace"]}:{x["meeting"]}:{sha}')
    with admin(x) as c:
        row=c.execute('SELECT to_jsonb(a) FROM oracle2.meeting_capture_admissions_v1 a WHERE admission_id=%s',(old.config.admission_id,)).fetchone()[0]
        row.update(admission_id=str(ident),admission_sha256=seal,final_artifact_sha256=sha,final_artifact_descriptor=selection.model_dump(mode='json'),final_artifact_operation_id=str(op))
        if actions is not None:row['actions']=actions
        c.execute('INSERT INTO oracle2.meeting_capture_admissions_v1 SELECT (jsonb_populate_record(NULL::oracle2.meeting_capture_admissions_v1,%s)).*',(Jsonb(row),))
    config=old.config.model_copy(update=dict(admission_id=ident,admission_sha256=seal,final_artifact_file=str(desc),final_artifact_sha256=sha));p=tmp_path/(ident.hex+'-capture');data=canonical_bytes(config.model_dump(mode='json'));p.write_bytes(data);p.chmod(0o600)
    capture=load_meeting_capture_settings_v1(old.host,p,hashlib.sha256(data).hexdigest())
    nc=f.settings.config.model_copy(update=dict(capture_config_sha256=capture.config_sha256));np=tmp_path/(ident.hex+'-normalizer');data=canonical_bytes(nc.model_dump(mode='json'));np.write_bytes(data);np.chmod(0o600)
    return MeetingNormalizationFactoryV1(load_meeting_normalization_settings_v1(capture,f.settings.intake,np,hashlib.sha256(data).hexdigest(),nc.issuer_actor,nc.reviewer_actor)),op

@pytest.fixture
def processing(normalized,tmp_path):
    x,f,_old,actor=normalized
    x['fixture_original_final']=_old
    original=ingest(x,event_id='process-original',head=2)
    selection=f.capture._artifact
    installed,op=install(x,f,tmp_path,selection)
    return x,installed,original.event_id,op,selection,actor


def complete_actual_final(x,f,op,selection):
    # The original raw is actual protected retained bytes. Reopen through the
    # same owner, independently verify hash/count before publishing final event.
    h=f.settings.capture.host.config;parts=['meeting-raw',str(x['workspace']),str(x['meeting']),selection.original_sha256+'.bin']
    raw,_receipt=f.capture.reopen_raw_v1(x['fixture_original_final'],caller_deadline=deadline())
    assert hashlib.sha256(raw).hexdigest()==selection.original_sha256 and len(raw)==selection.byte_count
    head=f.capture.head_v1(caller_deadline=deadline(),processing=True)
    return f.capture.transition_v1(expected_head=head.version,operation_id=op,action='final_artifact',payload=dict(selection_sha256=f.settings.capture.config.final_artifact_sha256,provider_event_id='final:'+f.settings.capture.config.final_artifact_sha256,raw_sha256=selection.original_sha256,byte_count=selection.byte_count,raw_object_key='/'.join(parts),event_kind='recall.final'),caller_deadline=deadline()).event_id


def test_actual_once_fetch_claim_exact_final_link_then_existing_intake(processing):
    x,f,raw,op,selection,actor=processing
    claim=f.capture.process_ingress_binding_v1('claim_fetch',raw,caller_deadline=deadline())
    assert claim.fresh_fetch_claim and claim.final_event_id is None and claim.population_sha256==final_population_sha256_v1(selection)
    repeat=f.capture.process_ingress_binding_v1('claim_fetch',raw,caller_deadline=deadline())
    assert repeat.state=='UNKNOWN' and not repeat.fresh_fetch_claim and repeat.fetch_claim_id==claim.fetch_claim_id
    final=complete_actual_final(x,f,op,selection)
    assert f.capture.process_ingress_binding_v1('status',raw,caller_deadline=deadline()).state=='UNKNOWN' # status never creates link
    linked=f.capture.process_ingress_binding_v1('record_final',raw,returned_final=final,caller_deadline=deadline())
    assert linked.state=='final_linked' and linked.final_event_id==final and not linked.fresh_fetch_claim
    result=f.normalize_v1(final,caller_deadline=deadline());assert result.state=='awaiting_independently_installed_exact_reading_review' and result.source_binding.qualification is False
    f.normalize_v1(final,caller_deadline=deadline())
    with admin(x) as c:
        assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_final_fetch_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)
        assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_processing_links_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)
        assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)
        assert c.execute('SELECT count(*) FROM oracle2.accepted WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)


def test_metadata_reinstallation_cannot_reset_spent_population(processing,tmp_path):
    x,f,raw,op,selection,_actor=processing
    first=f.capture.process_ingress_binding_v1('claim_fetch',raw,caller_deadline=deadline())
    changed=selection.model_copy(update={'download_url':'https://other-cdn.example.invalid/new-signed-path'})
    assert final_population_sha256_v1(changed)==first.population_sha256
    new,_=install(x,f,tmp_path,changed)
    with pytest.raises(psycopg.errors.InsufficientPrivilege,match='globally spent'):new.capture.process_ingress_binding_v1('claim_fetch',raw,caller_deadline=deadline())
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_final_fetch_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)


def test_wrong_independent_operation_pin_refuses_before_claim(processing,tmp_path):
    x,f,raw,_op,selection,_actor=processing
    wrong,_=install(x,f,tmp_path,selection,operation=uuid4())
    with pytest.raises(PermissionError,match='population/operation'):wrong.capture.process_ingress_binding_v1('claim_fetch',raw,caller_deadline=deadline())
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_final_fetch_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)


def test_foreign_or_hash_only_final_event_never_links(processing):
    x,f,raw,_op,_selection,_actor=processing
    f.capture.process_ingress_binding_v1('claim_fetch',raw,caller_deadline=deadline())
    with admin(x) as c:old=c.execute("SELECT event_id FROM oracle2.meeting_capture_events_v1 WHERE workspace_id=%s AND action='final_artifact'",(x['workspace'],)).fetchone()[0]
    for candidate in (old,uuid4()):
        with pytest.raises(psycopg.errors.InsufficientPrivilege,match='originating'):f.capture.process_ingress_binding_v1('record_final',raw,returned_final=candidate,caller_deadline=deadline())
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_processing_links_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)


def test_expired_original_fetch_requires_separate_observation_only_and_never_new_effect(processing,tmp_path):
    x,f,raw,op,selection,_actor=processing
    observer,_=install(x,f,tmp_path,selection,actions=['status','process_observe']) # independently installed BEFORE effect
    claim=f.capture.process_ingress_binding_v1('claim_fetch',raw,caller_deadline=datetime.now(timezone.utc)+timedelta(seconds=3))
    final=complete_actual_final(x,f,op,selection)
    time.sleep(max(0,(claim.original_effect_deadline-datetime.now(timezone.utc)).total_seconds())+.03)
    with pytest.raises(psycopg.errors.InsufficientPrivilege,match='observation-only'):f.capture.process_ingress_binding_v1('record_final',raw,returned_final=final,caller_deadline=deadline())
    with pytest.raises(psycopg.errors.InsufficientPrivilege):observer.capture.process_ingress_binding_v1('claim_fetch',raw,caller_deadline=deadline())
    linked=observer.capture.process_ingress_binding_v1('record_final',raw,returned_final=final,caller_deadline=deadline())
    assert linked.state=='final_linked' and linked.observation_only and linked.original_effect_deadline==claim.original_effect_deadline
    with pytest.raises(psycopg.errors.InsufficientPrivilege):observer.capture.fetch_final_artifact_v1(caller_deadline=deadline())
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)


def test_same_factory_processes_actual_raw_to_final_and_intake_once(processing,monkeypatch):
    x,f,raw,op,selection,_actor=processing;calls=[]
    def owned_final(*,caller_deadline):
        calls.append(caller_deadline)
        return complete_actual_final(x,f,op,selection)
    # Deliberately a fixture-only network seam: the real same SQL/custody owner
    # creates the final event. Actual public-network/TLS is NOT claimed here.
    monkeypatch.setattr(f.capture,'fetch_final_artifact_v1',owned_final)
    end=deadline();first=f.process_ingress_v1(raw,caller_deadline=end)
    assert first.ingress_event_id==raw and first.state=='awaiting_independently_installed_exact_reading_review'
    assert first.source_binding is not None and first.source_binding.qualification is False
    again=f.process_ingress_v1(raw,caller_deadline=end)
    assert again.source_binding==first.source_binding and len(calls)==1 and calls[0]<=end
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)


def test_fetch_lost_ack_reconciles_only_real_final_event_never_second_fetch(processing,monkeypatch):
    x,f,raw,op,selection,_actor=processing;calls=[]
    def lost(*,caller_deadline):
        calls.append(caller_deadline);complete_actual_final(x,f,op,selection)
        raise ConnectionError('invented lost final ACK')
    monkeypatch.setattr(f.capture,'fetch_final_artifact_v1',lost)
    end=deadline()
    with pytest.raises(ConnectionError):f.process_ingress_v1(raw,caller_deadline=end)
    recovered=f.process_ingress_v1(raw,caller_deadline=end)
    assert recovered.state=='awaiting_independently_installed_exact_reading_review' and len(calls)==1
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)


def test_missing_independent_SQL_descriptor_is_pending_without_claim_fetch_or_intake(normalized,monkeypatch):
    x,f,_old,_actor=normalized;raw=ingest(x,event_id='missing-descriptor',head=2).event_id;calls=[]
    monkeypatch.setattr(f.capture,'fetch_final_artifact_v1',lambda **kw:calls.append(kw))
    result=f.process_ingress_v1(raw,caller_deadline=deadline())
    assert result.state=='final_artifact_pending' and result.ingress_event_id==raw and result.source_binding is None and calls==[]
    with admin(x) as c:
        assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_final_fetch_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)
        assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)
