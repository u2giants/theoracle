"""Separate protected confirmation operation consumes existing identity only."""
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
import psycopg
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.original_intake_v1 import load_original_intake_settings_v1
from oracle_brain.hosting.replacement_confirmation_settings_v1 import (
    ConfirmationAppointmentV1, ConfirmationPeerProfileV1, load_confirmation_settings_v1,
)
from test_original_intake_v1 import settings as base_intake
from test_hosting_boundary import certificates, WORKER


def pin(path, raw):
    path.write_bytes(raw);path.chmod(0o600)
    return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest())


def intake_target(tmp_path, *, url=None, ca=None, updates=None):
    s=base_intake(tmp_path)
    c=s.config
    ca_input=pin(tmp_path/'db-ca',ca or b'invented recording SQL CA')
    target=psycopg.conninfo.conninfo_to_dict(url) if url else dict(host='127.0.0.1',port='5432',dbname='invented',user=c.expected_session_role,password='invented-only',sslmode='verify-full')
    target['sslrootcert']=ca_input['path']
    db_input=pin(tmp_path/'db-url',psycopg.conninfo.make_conninfo(**target).encode())
    c=c.model_copy(update=dict(database_url=type(c.database_url)(**db_input),database_ca=type(c.database_ca)(**ca_input))|(updates or {}))
    ci=pin(s.config_path,canonical_bytes(c.model_dump(mode='json')))
    keys=('principal_id','workspace_id','expected_session_role','runtime_hash','registry_hash')
    a=s.appointment.model_copy(update={**{k:getattr(c,k) for k in keys},'config_sha256':ci['sha256']})
    ai=pin(s.appointment_path,canonical_bytes(a.model_dump(mode='json')))
    return load_original_intake_settings_v1(ci['path'],ci['sha256'],ai['path'],ai['sha256'],s.expected_issuer_actor,s.expected_reviewer_actor)


def configured_confirmation(tmp_path,certificates,*,intake=None,appointment_changes=None,peer_changes=None):
    if intake is None:
        folder=tmp_path/'intake';folder.mkdir(mode=0o700);intake=intake_target(folder)
    c=intake.config;now=datetime.now(timezone.utc);end=intake.current()
    der=x509.load_pem_x509_certificate((certificates/'worker.pem').read_bytes()).public_bytes(Encoding.DER)
    peer=dict(schema_version=1,purpose='replacement-confirmation-peer-v1',intake_config_sha256=intake.config_sha256,
        intake_appointment_sha256=intake.appointment_sha256,principal_id=str(c.principal_id),workspace_id=str(c.workspace_id),
        client_uri=WORKER,client_certificate_sha256=hashlib.sha256(der).hexdigest(),listen_host='127.0.0.1',listen_port=0,server_hostname='localhost',
        server_certificate=pin(tmp_path/'server-cert',(certificates/'server.pem').read_bytes()),
        server_key=pin(tmp_path/'server-key',(certificates/'server.key').read_bytes()),client_ca=pin(tmp_path/'client-ca',(certificates/'ca.pem').read_bytes()),
        valid_from=(now-timedelta(seconds=1)).isoformat(),expires_at=end.isoformat(),original_horizon=c.original_horizon.isoformat())
    peer.update(peer_changes or {});p=ConfirmationPeerProfileV1.model_validate_json(json.dumps(peer));pi=pin(tmp_path/'confirm-peer',canonical_bytes(p.model_dump(mode='json')))
    a=dict(schema_version=1,purpose='replacement-exact-map-confirm-v1',operation='exact-map-confirm',
        intake_config_sha256=intake.config_sha256,intake_appointment_sha256=intake.appointment_sha256,peer_profile_sha256=pi['sha256'],
        principal_id=str(c.principal_id),workspace_id=str(c.workspace_id),expected_session_role=c.expected_session_role,
        runtime_hash=c.runtime_hash,registry_hash=c.registry_hash,issuer_actor=str(intake.expected_issuer_actor),reviewer_actor=str(intake.expected_reviewer_actor),
        valid_from=(now-timedelta(seconds=1)).isoformat(),expires_at=end.isoformat(),original_horizon=c.original_horizon.isoformat())
    a.update(appointment_changes or {});a=ConfirmationAppointmentV1.model_validate_json(json.dumps(a));ai=pin(tmp_path/'confirm-appointment',canonical_bytes(a.model_dump(mode='json')))
    args=(intake,ai['path'],ai['sha256'],pi['path'],pi['sha256'])
    settings=load_confirmation_settings_v1(*args,issuer_actor=intake.expected_issuer_actor,reviewer_actor=intake.expected_reviewer_actor)
    return SimpleNamespace(settings=settings,intake=intake,args=args,target=psycopg.conninfo.conninfo_to_dict(Path(c.database_url.path).read_text()))


def test_separate_confirm_appointment_consumes_existing_identity(tmp_path,certificates):
    f=configured_confirmation(tmp_path,certificates)
    assert f.settings.current()>datetime.now(timezone.utc)
    assert f.settings.appointment.operation=='exact-map-confirm'
    with pytest.raises(TypeError):load_confirmation_settings_v1(object(),*f.args[1:],issuer_actor=f.intake.expected_issuer_actor,reviewer_actor=f.intake.expected_reviewer_actor)


@pytest.mark.parametrize('change',[dict(operation='advance'),dict(intake_config_sha256='0'*64),dict(peer_profile_sha256='0'*64),
    dict(runtime_hash='0'*64),dict(expected_session_role='foreign'),dict(unknown=True),dict(expires_at='2000-01-01T00:00:00Z')])
def test_unappointed_scope_or_identity_denied(tmp_path,certificates,change):
    with pytest.raises((ValueError,PermissionError)):configured_confirmation(tmp_path,certificates,appointment_changes=change)


@pytest.mark.parametrize('which',['appointment_input','peer_input'])
def test_changed_confirmation_pins_denied(tmp_path,certificates,which):
    f=configured_confirmation(tmp_path,certificates);path=Path(getattr(f.settings,which).path);path.write_bytes(b'{}')
    with pytest.raises(PermissionError):f.settings.current()


@pytest.mark.parametrize('change',[dict(server_hostname='wrong.example'),dict(intake_appointment_sha256='0'*64)])
def test_peer_pin_identity_denied(tmp_path,certificates,change):
    with pytest.raises(PermissionError):configured_confirmation(tmp_path,certificates,peer_changes=change)
