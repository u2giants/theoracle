"""Actual original intake once and current mapping/source fences; invented identities."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4
import hashlib,json
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.meeting_capture_v1 import load_meeting_capture_settings_v1
from oracle_brain.hosting.original_intake_v1 import load_original_intake_settings_v1
from oracle_brain.hosting.meeting_normalization_v1 import (MeetingNormalizationConfigV1,
    MeetingNormalizationFactoryV1,load_meeting_normalization_settings_v1,normalization_idempotency_key_v1)
from test_meeting_capture_sql import meeting_sql,admin,invite,deadline,original_request_fence
from test_replacement_requester_sql import configured_settings

@pytest.fixture
def normalized(meeting_sql,tmp_path):

    from oracle_brain.meetings.final_mapping import FinalWorkspaceSpeakerMappingV1,FinalWorkspaceSpeakerLinkV1
    from oracle_brain.meetings.capture_contracts import InstalledFinalArtifactV1
    from oracle_brain.operating_model.artifact_storage import _write_private_at
    from oracle_brain.hosting.meeting_capture_v1 import MeetingCaptureFactoryV1
    x=meeting_sql;invite(x);s=x['worker'];old=s['settings'];h=old.host.config;c=old.config;now=datetime.now(timezone.utc)
    raw=b'[{"participant":{"id":1,"name":"Untrusted CEO"},"language_code":"en","words":[{"text":"Exact original","start_timestamp":{"relative":0},"end_timestamp":null}]}]'
    rawsha=hashlib.sha256(raw).hexdigest()
    mapping=FinalWorkspaceSpeakerMappingV1(purpose='meeting-final-workspace-mapping-v1',mapping_id=uuid4(),mapping_revision=1,workspace_id=x['workspace'],meeting_id=x['meeting'],provider='recall',provider_account=x['account'],tenant_id='tenant1',provider_meeting_id='meeting1',raw_sha256=rawsha,language='en',links=(FinalWorkspaceSpeakerLinkV1(provider_speaker_id='1',attribution='workspace_actor',actor_id=x['owner'],mapping_evidence_sha256='a'*64),),issuer_actor=uuid4(),reviewer_actor=uuid4(),valid_from=now-timedelta(seconds=1),expires_at=min(x['until'],c.original_horizon),original_horizon=min(x['until'],c.original_horizon))
    selection=InstalledFinalArtifactV1(purpose='meeting-final-artifact-selection-v1',workspace_id=x['workspace'],meeting_id=x['meeting'],provider='recall',provider_account=x['account'],tenant_id='tenant1',provider_meeting_id='meeting1',bot_id='bot1',recording_id='recording1',transcript_id='transcript1',provider_revision='r1',provider_finality_receipt_sha256='9'*64,original_sha256=rawsha,byte_count=len(raw),media_type='application/json',download_url='https://cdn.example.invalid/final.json',ca_file=h.database_ca.path,ca_sha256=h.database_ca.sha256,server_der_sha256='8'*64,issuer_actor=uuid4(),reviewer_actor=uuid4(),valid_from=now-timedelta(seconds=1),expires_at=min(x['until'],c.original_horizon),original_horizon=min(x['until'],c.original_horizon))
    files={}
    for name,record in [('mapping',mapping),('selection',selection)]:
        data=canonical_bytes(record.model_dump(mode='json'));path=tmp_path/(name+'.json');path.write_bytes(data);path.chmod(0o600);files[name]=(str(path),hashlib.sha256(data).hexdigest())
    admission=uuid4();seal=hashlib.sha256(str(admission).encode()).hexdigest()
    with admin(x) as conn:
        conn.execute('INSERT INTO oracle2.meeting_final_mappings_v1 VALUES(%s,%s,%s,%s,%s,%s,%s)',(mapping.mapping_id,x['workspace'],x['meeting'],1,rawsha,mapping.sha256,Jsonb(mapping.model_dump(mode='json'))))
        row=conn.execute('SELECT to_jsonb(a) FROM oracle2.meeting_capture_admissions_v1 a WHERE admission_id=%s',(s['admission'],)).fetchone()[0]
        row.update(admission_id=str(admission),admission_sha256=seal,final_mapping_id=str(mapping.mapping_id),final_mapping_sha256=mapping.sha256,final_artifact_sha256=files['selection'][1],actions=row['actions']+['final_artifact'])
        conn.execute('INSERT INTO oracle2.meeting_capture_admissions_v1 SELECT (jsonb_populate_record(NULL::oracle2.meeting_capture_admissions_v1,%s)).*',(Jsonb(row),))
    cfg=c.model_copy(update=dict(admission_id=admission,admission_sha256=seal,final_mapping_id=mapping.mapping_id,speaker_mapping_file=files['mapping'][0],speaker_mapping_sha256=files['mapping'][1],final_artifact_file=files['selection'][0],final_artifact_sha256=files['selection'][1]))
    data=canonical_bytes(cfg.model_dump(mode='json'));path=tmp_path/'final-consumer.json';path.write_bytes(data);path.chmod(0o600)
    settings=load_meeting_capture_settings_v1(old.host,path,hashlib.sha256(data).hexdigest());f=MeetingCaptureFactoryV1(settings)
    parts=['meeting-raw',str(x['workspace']),str(x['meeting']),rawsha+'.bin'];_write_private_at(Path(h.storage_root),parts,raw,expected_root=(h.storage_device,h.storage_inode,h.storage_uid))
    event=uuid4();f.transition_v1(expected_head=1,operation_id=event,action='final_artifact',payload=dict(selection_sha256=files['selection'][1],provider_event_id='final-fixture',raw_sha256=rawsha,byte_count=len(raw),raw_object_key='/'.join(parts),event_kind='recall.final'),caller_deadline=deadline())

    # Separately installed actual intake role in the SAME workspace. This fixture
    # creates authority explicitly; production consumers never do so.
    actor=uuid4();role='norm_intake_'+uuid4().hex[:12];leaf=uuid4()
    with admin(x) as conn:
        conn.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role),sql.Literal('invented-normalization-only')))
        conn.execute(sql.SQL('GRANT oracle2_replacement_requester TO {}').format(sql.Identifier(role)))
        conn.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',(role,x['runtime'],x['registry'],x['until']))
        conn.execute('INSERT INTO oracle2.hosting_request_principal_admissions VALUES(%s,%s,%s,%s,%s,%s)',(role,actor,x['workspace'],x['runtime'],x['registry'],x['until']))
        conn.execute("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,'intake',%s,%s,%s)",(leaf,x['workspace'],actor,x['owner'],x['root'],x['until']))
    d=tmp_path/'intake';d.mkdir(mode=0o700)
    ix=x|dict(login=role,actor=actor,url=psycopg.conninfo.make_conninfo(x['admin'],user=role,password='invented-normalization-only'))
    intake=configured_settings(d,ix)
    apt=intake.appointment.model_copy(update=dict(media_types=('text/plain',)))
    data=canonical_bytes(apt.model_dump(mode='json'));intake.appointment_path.write_bytes(data)
    intake=load_original_intake_settings_v1(intake.config_path,intake.config_sha256,intake.appointment_path,hashlib.sha256(data).hexdigest(),intake.expected_issuer_actor,intake.expected_reviewer_actor)
    # Append a new admission with exact independent intake pins; never mutate one.
    new_admission=uuid4();new_seal=hashlib.sha256(str(new_admission).encode()).hexdigest()
    with admin(x) as conn:
        row=conn.execute('SELECT to_jsonb(a) FROM oracle2.meeting_capture_admissions_v1 a WHERE admission_id=%s',(admission,)).fetchone()[0]
        row.update(admission_id=str(new_admission),admission_sha256=new_seal,normalization_intake_principal_id=str(actor),normalization_intake_config_sha256=intake.config_sha256,normalization_intake_appointment_sha256=intake.appointment_sha256)
        conn.execute('INSERT INTO oracle2.meeting_capture_admissions_v1 SELECT (jsonb_populate_record(NULL::oracle2.meeting_capture_admissions_v1,%s)).*',(Jsonb(row),))
    cfg=cfg.model_copy(update=dict(admission_id=new_admission,admission_sha256=new_seal))
    data=canonical_bytes(cfg.model_dump(mode='json'));path=tmp_path/'normalization-capture';path.write_bytes(data);path.chmod(0o600)
    capture=load_meeting_capture_settings_v1(old.host,path,hashlib.sha256(data).hexdigest())
    config=MeetingNormalizationConfigV1(schema_version=1,purpose='meeting-normalization-consumer-v1',capture_config_sha256=capture.config_sha256,intake_config_sha256=intake.config_sha256,intake_appointment_sha256=intake.appointment_sha256,intake_issuer_actor=intake.expected_issuer_actor,intake_reviewer_actor=intake.expected_reviewer_actor,issuer_actor=uuid4(),reviewer_actor=uuid4(),valid_from=now-timedelta(seconds=1),expires_at=x['until'],original_processing_horizon=x['until'])
    data=canonical_bytes(config.model_dump(mode='json'));path=tmp_path/'normalizer';path.write_bytes(data);path.chmod(0o600)
    normalizer=MeetingNormalizationFactoryV1(load_meeting_normalization_settings_v1(capture,intake,path,hashlib.sha256(data).hexdigest(),config.issuer_actor,config.reviewer_actor))
    return x,normalizer,event,actor


def test_actual_text_source_created_once_and_duplicate_cannot_qualify(normalized):
    x,f,event,actor=normalized;end=deadline()
    first=f.normalize_v1(event,caller_deadline=end)
    assert first.state=='awaiting_independently_installed_exact_reading_review'
    assert first.source_binding.qualification is False and first.source_binding.source_read_permission is False
    again=f.normalize_v1(event,caller_deadline=end)
    assert not again.fresh_intake_claim and again.source_binding==first.source_binding
    with admin(x) as c:
        assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)
        assert c.execute('SELECT count(*) FROM oracle2.meeting_normalization_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)
        assert c.execute("SELECT count(*) FROM oracle2.meeting_capture_events_v1 WHERE workspace_id=%s AND action='normalized'",(x['workspace'],)).fetchone()==(1,)
        assert c.execute('SELECT count(*) FROM oracle2.accepted WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)


def test_lost_intake_receipt_stays_UNKNOWN_until_own_readonly_reconciliation(normalized,monkeypatch):
    x,f,event,actor=normalized;end=deadline();original=f._record
    monkeypatch.setattr(f,'_record',lambda *a:(_ for _ in ()).throw(ConnectionError('invented lost acknowledgement')))
    with pytest.raises(ConnectionError):f.normalize_v1(event,caller_deadline=end)
    assert f.status_v1(event,caller_deadline=end).state=='UNKNOWN'
    monkeypatch.setattr(f,'_record',original)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):f.reconcile_v1(event,caller_deadline=end)
    # Duplicate normal delivery cannot reserve or finalize again.
    assert f.normalize_v1(event,caller_deadline=end).state=='UNKNOWN'
    with admin(x) as c:
        source=c.execute('SELECT source_id FROM oracle2.sources WHERE workspace_id=%s',(x['workspace'],)).fetchone()[0]
        c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(uuid4(),x['workspace'],actor,'source-read:'+str(source),x['owner'],x['root'],x['until']))
    recovered=f.reconcile_v1(event,caller_deadline=end)
    assert recovered.source_binding.source_id==source
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)


def test_original_mapping_revocation_denies_before_intake(normalized):
    x,f,event,_=normalized
    with admin(x) as c:c.execute('INSERT INTO oracle2.meeting_final_mapping_revocations_v1 VALUES(%s,%s,clock_timestamp(),%s)',(uuid4(),f.settings.capture.config.final_mapping_id,'f'*64))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):f.normalize_v1(event,caller_deadline=deadline())
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)


@pytest.mark.parametrize('field',['original_sha256','derivation_sha256','mapping_sha256','intake_config_sha256','intake_appointment_sha256','idempotency_key'])
def test_global_claim_rejects_altered_payload_without_new_intake(normalized,field):
    x,f,event,_=normalized;end=deadline();first=f.normalize_v1(event,caller_deadline=end)
    changed=dict(first.binding);changed[field]=str(uuid4()) if field=='idempotency_key' else 'f'*64
    with pytest.raises(psycopg.Error):f._call('claim',event,end,binding=changed)
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)


def test_simultaneous_delivery_has_one_global_intake_effect(normalized):
    from concurrent.futures import ThreadPoolExecutor
    from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
    import time
    x,f,event,_=normalized;end=deadline()
    def run():
        with _request_fence_v1(float(time.monotonic()+20)):
            return f.normalize_v1(event,caller_deadline=end)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:run(),range(2)))
    assert sum(r.fresh_intake_claim for r in results)==0  # returned records follow actual finalized receipt
    assert all(r.state in ('UNKNOWN','awaiting_independently_installed_exact_reading_review') for r in results)
    with admin(x) as c:
        assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)
        assert c.execute('SELECT count(*) FROM oracle2.meeting_normalization_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)


def test_new_installed_admission_cannot_reset_spent_claim(normalized,tmp_path):
    x,f,event,_=normalized;end=deadline();first=f.normalize_v1(event,caller_deadline=end)
    old=f.settings.capture;admission=uuid4();seal=hashlib.sha256(str(admission).encode()).hexdigest()
    with admin(x) as c:
        row=c.execute('SELECT to_jsonb(a) FROM oracle2.meeting_capture_admissions_v1 a WHERE admission_id=%s',(old.config.admission_id,)).fetchone()[0]
        row.update(admission_id=str(admission),admission_sha256=seal)
        c.execute('INSERT INTO oracle2.meeting_capture_admissions_v1 SELECT (jsonb_populate_record(NULL::oracle2.meeting_capture_admissions_v1,%s)).*',(Jsonb(row),))
    cfg=old.config.model_copy(update=dict(admission_id=admission,admission_sha256=seal));path=tmp_path/'reinstalled-capture';raw=canonical_bytes(cfg.model_dump(mode='json'));path.write_bytes(raw);path.chmod(0o600)
    capture=load_meeting_capture_settings_v1(old.host,path,hashlib.sha256(raw).hexdigest())
    cfg=f.settings.config.model_copy(update=dict(capture_config_sha256=capture.config_sha256));path=tmp_path/'reinstalled-normalizer';raw=canonical_bytes(cfg.model_dump(mode='json'));path.write_bytes(raw);path.chmod(0o600)
    fresh=MeetingNormalizationFactoryV1(load_meeting_normalization_settings_v1(capture,f.settings.intake,path,hashlib.sha256(raw).hexdigest(),cfg.issuer_actor,cfg.reviewer_actor))
    again=fresh.normalize_v1(event,caller_deadline=end)
    assert not again.fresh_intake_claim and again.source_binding==first.source_binding
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)


def test_original_withdrawal_withholds_previously_linked_source(normalized):
    x,f,event,_=normalized;end=deadline();linked=f.normalize_v1(event,caller_deadline=end);ref=linked.source_binding
    with admin(x) as c:
        c.execute('INSERT INTO oracle2.source_original_withdrawals_v1(event_id,workspace_id,source_id,revision,original_sha256,principal_id,session_role,runtime_hash,reason,idempotency_key,request_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(uuid4(),x['workspace'],ref.source_id,ref.revision,ref.original_sha256,f.settings.intake.config.principal_id,f.settings.intake.config.expected_session_role,x['runtime'],'invented current withdrawal',uuid4(),'a'*64))
    status=f.status_v1(event,caller_deadline=end)
    assert status.state=='source_unavailable' and status.source_binding is None
    assert f.reconcile_v1(event,caller_deadline=end).source_binding is None
