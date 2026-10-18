"""Protected metadata refusal and controlled boundary order; no native proof."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import hashlib,os

import pytest
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.original_source_authority_v1 import OriginalPopulationSnapshotV1
from oracle_brain.hosting import raw_original_settings_v1 as m
from test_raw_original_context_v1 import context


def config():
    x=context();now=datetime.now(timezone.utc)
    def f(name):return {'path':'/private/invented/'+name,'sha256':'a'*64}
    return m.RawOriginalProviderConfigV1(population=x.population,actor_id=x.actor_id,
        phase_purpose=x.job.purpose,expected_owner_role='invented_owner',expected_session_role=x.expected_session_role,
        original_allocation_hash=x.original_allocation_hash,original_horizon=x.original_horizon,
        database_url=f('sql'),database_ca=f('ca'),database_hostname='invented.invalid',database_port=5432,
        database_name='invented',context=f('context'),observer_admission=f('observer'),
        observer_tls={'hostname':'invented.invalid','port':8443,'server_uri':'spiffe://oracle/invented-observer',
            'client_uri':'spiffe://oracle/invented-reader','ca':f('observer-ca'),'certificate':f('cert'),'key':f('key')},
        observer_spool='/private/invented/spool',observer_namespace='raw-reader',observer_initialization_hash='a'*64,
        original_root='/private/invented/originals',original_root_identity=(1,2,os.getuid()),storage_profile_hash='b'*64,
        vision_policy=f('vision'),issuer_actor=uuid4(),reviewer_actor=uuid4(),valid_from=now-timedelta(seconds=1),
        expires_at=x.phase_expires_at)


def appointment(c,seal):
    return m.RawOriginalProviderAppointmentV1(config_sha256=seal,context_sha256=c.context.sha256,
        population=c.population,actor_id=c.actor_id,expected_session_role=c.expected_session_role,
        original_allocation_hash=c.original_allocation_hash,original_horizon=c.original_horizon,
        issuer_actor=c.issuer_actor,reviewer_actor=c.reviewer_actor,valid_from=c.valid_from,expires_at=c.expires_at)


def write(path,value):
    raw=canonical_bytes(value.model_dump(mode='json'));path.write_bytes(raw);path.chmod(0o600)
    return hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize('field',['config_sha256','context_sha256','actor_id','population','expected_session_role','issuer_actor','expires_at'])
def test_foreign_appointment_refuses_before_any_sql_or_other_private_file(tmp_path,monkeypatch,field):
    c=config();cp=tmp_path/'config';ch=write(cp,c);a=appointment(c,ch);body=a.model_dump(mode='python')
    if field in {'config_sha256','context_sha256'}:body[field]='0'*64
    elif field in {'actor_id','issuer_actor'}:body[field]=uuid4()
    elif field=='population':body[field]['population_id']=uuid4()
    elif field=='expected_session_role':body[field]='foreign_login'
    else:body[field]=datetime.now(timezone.utc)-timedelta(seconds=1)
    a=m.RawOriginalProviderAppointmentV1.model_validate(body);ap=tmp_path/'appointment';ah=write(ap,a)
    seen=[];read=m._worker_file
    def only_metadata(path,*args,**kwargs):
        seen.append(Path(path));assert Path(path) in {cp,ap},'private credential read before appointment'
        return read(path,*args,**kwargs)
    monkeypatch.setattr(m,'_worker_file',only_metadata)
    from oracle_brain.hosting import purpose_journey_v2
    monkeypatch.setattr(purpose_journey_v2,'_worker_file',only_metadata)
    with pytest.raises(PermissionError):m.load_raw_original_provider_settings_v1(cp,ch,appointment_path=ap,
        expected_appointment_sha256=ah,issuer_actor=c.issuer_actor,reviewer_actor=c.reviewer_actor)
    assert seen==[cp,ap]


@pytest.mark.parametrize('bad',[True,1.0,'1',2])
def test_closed_config_and_appointment_versions(bad):
    c=config();a=appointment(c,digest(c.model_dump(mode='json')))
    for value,cls in ((c,m.RawOriginalProviderConfigV1),(a,m.RawOriginalProviderAppointmentV1)):
        body=value.model_dump(mode='python');body['schema_version']=bad
        with pytest.raises(ValueError):cls.model_validate(body)


def test_current_window_separates_fresh_witness_from_true_original_horizon():
    c=config();now=datetime.now(timezone.utc);events=[]
    snapshot=OriginalPopulationSnapshotV1(population=c.population,original_allocation_hash=c.original_allocation_hash,
        original_horizon=c.original_horizon,actual_principal_id=c.actor_id,session_role=c.expected_session_role,
        checked_at=now,valid_until=c.expires_at)
    class SQL:
        def original_population_current_v1(self,p):events.append('sql');assert p==c.population.population_id;return snapshot
    class Observer:
        admission=SimpleNamespace(expires_at=c.expires_at)
        def current(self,p):
            events.append('observer');assert p==c.population
            return SimpleNamespace(expires_at=now+timedelta(seconds=4),model_dump=lambda **_: {'invented':'witness'})
    window=m._current_window(c,SQL(),Observer(),c.expires_at)
    assert events==['sql','observer','sql']
    assert window.current_until==now+timedelta(seconds=4)
    assert window.operation_horizon==c.expires_at


def test_current_window_revocation_after_observer_denies():
    c=config();now=datetime.now(timezone.utc);events=[]
    snapshot=OriginalPopulationSnapshotV1(population=c.population,original_allocation_hash=c.original_allocation_hash,
        original_horizon=c.original_horizon,actual_principal_id=c.actor_id,session_role=c.expected_session_role,
        checked_at=now,valid_until=c.expires_at)
    class SQL:
        def original_population_current_v1(self,p):
            events.append('sql')
            if len(events)>1:raise PermissionError('invented third source revoked')
            return snapshot
    class Observer:
        def current(self,p):events.append('observer');return None
    with pytest.raises(PermissionError,match='third source revoked'):
        m._current_window(c,SQL(),Observer(),c.expires_at)
    assert events==['sql','observer','sql']
