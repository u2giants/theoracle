"""Protected startup/source denial tests; no real provider/runtime admission."""
from datetime import datetime,timezone
from pathlib import Path
import json
import pytest
from pydantic import ValidationError
from oracle_brain.hosting.purpose_runtime import (
    PurposeProviderConfigV2,PurposeMetadataConfigV2,load_purpose_runtime_settings_v2,
    CurrentPurposeJobsV2,build_purpose_broker_v2,build_purpose_metadata_v2)
from oracle_brain.operating_model.contracts import canonical_bytes,digest


def config(role='metadata'):
    common=dict(schema_version=2,phase='census',role=role,worker_uri='spiffe://oracle/census-worker',
        budget_allocation_projection_file='/own/allocation.json',pins_file='/own/pins.json',pins_sha256='a'*64,population_file='/own/population.json',
        projection_file='/own/projection.json',source_url_file='/own/source-url',expected_owner_role='oracle_schema_owner',
        expected_session_role='own_census_login',source_expires_at=datetime.now(timezone.utc),
        parent_observer_admission_file='/own/observer.json',parent_observer_admission_hash='b'*64,
        observer_timeout_seconds=5,observer_hostname='observer.internal',observer_port=9443,observer_server_uri='spiffe://oracle/parent-observer',
        observer_client_uri='spiffe://oracle/census-client',observer_ca='/own/ca',observer_certificate='/own/cert',
        observer_key='/own/key',observer_spool='/own/spool',observer_namespace='parent-v2',
        observer_initialization_hash='c'*64,server_certificate='/own/server-cert',server_key='/own/server-key',
        client_ca='/own/client-ca',bind_host='127.0.0.1',bind_port=9444)
    if role=='metadata':common.update(provider_rpc_timeout_seconds=90,provider_hostname='provider.internal',provider_port=9445,
        provider_server_uri='spiffe://oracle/census-provider',provider_client_uri='spiffe://oracle/census-worker',
        provider_ca='/own/provider-ca',provider_certificate='/own/provider-cert',provider_key='/own/provider-client-key')
    else:common.update(phase_registry_file='/own/phase.json',private_context_files={},provider_key_file='/own/provider-key',
        ledger_url_file='/central/ledger-url',
        ledger_registry_file='/own/ledger.json',ledger_registry_hash='d'*64,coverage_admission_file='/own/coverage.json',
        coverage_admission_hash='e'*64,coverage_witness_file='/own/witness.json',coverage_observer_public_key='f'*64,
        private_receipts='/own/private-receipts')
    return common


@pytest.mark.parametrize('field',('phase_registry_file','private_context_files','provider_key_file','ledger_url_file',
    'parent_registry_file','callback','factory','raw_request','current_authorized'))
def test_metadata_startup_cannot_mount_private_parent_phase_provider_or_dynamic_authority(field):
    raw=config();raw[field]='/private/forbidden'
    with pytest.raises(ValidationError):PurposeMetadataConfigV2.model_validate(raw)


def test_fixed_provider_and_metadata_config_are_separate_strict_types():
    assert PurposeProviderConfigV2.model_validate(config('provider')).role=='provider'
    assert PurposeMetadataConfigV2.model_validate(config()).role=='metadata'
    with pytest.raises(ValidationError):PurposeProviderConfigV2.model_validate(config())
    with pytest.raises(ValidationError):PurposeMetadataConfigV2.model_validate(config('provider'))


@pytest.mark.parametrize('role',('provider','metadata'))
def test_wrong_phase_denies_before_opening_any_admission_or_private_file(tmp_path,role):
    raw=config(role);path=tmp_path/'startup.json';body=canonical_bytes(PurposeProviderConfigV2.model_validate(raw).model_dump(mode='json')
        if role=='provider' else PurposeMetadataConfigV2.model_validate(raw).model_dump(mode='json'))
    path.write_bytes(body);path.chmod(0o600)
    import hashlib
    with pytest.raises(PermissionError,match='phase/role'):
        load_purpose_runtime_settings_v2(path,hashlib.sha256(body).hexdigest(),expected_phase='assessment',expected_role=role)


@pytest.mark.parametrize('factory',(CurrentPurposeJobsV2,build_purpose_broker_v2,build_purpose_metadata_v2))
def test_no_dictionary_or_boolean_is_runtime_authority(factory):
    with pytest.raises(PermissionError):factory({'authorized':True,'phase':'census'})


def test_embedding_has_own_metadata_only_provider_login_and_no_gateway_variant():
    raw=config();raw['phase']='embedding'
    with pytest.raises(PermissionError,match='no gateway'):
        PurposeMetadataConfigV2.model_validate(raw)

@pytest.mark.parametrize('field,values',[
 ('observer_timeout_seconds',[None,0,-1,5.01,float('inf'),float('nan')]),
 ('provider_rpc_timeout_seconds',[None,0,-1,90.01,float('inf'),float('nan')])])
def test_explicit_independent_observer_and_provider_deadlines_required(field,values):
    for value in values:
        raw=config()
        if value is None:raw.pop(field)
        else:raw[field]=value
        with pytest.raises(ValidationError):PurposeMetadataConfigV2.model_validate(raw)


def test_only_embedding_provider_can_mount_current_semantic_registry():
    raw=config('provider');raw['semantic_registry_file']='/private/qualified-registry'
    with pytest.raises(PermissionError):PurposeProviderConfigV2.model_validate(raw)
    raw=config('provider');raw['phase']='embedding'
    with pytest.raises(PermissionError):PurposeProviderConfigV2.model_validate(raw)
    raw.update(semantic_registry_file='/own/registry',semantic_registry_sha256='1'*64,
        semantic_appointment_file='/own/appointment',semantic_appointment_sha256='2'*64)
    assert PurposeProviderConfigV2.model_validate(raw).phase=='embedding'


@pytest.mark.parametrize('mutation', [None, 'version', 'missing', 'extra', 'foreign-scope'])
def test_embedding_current_constructs_actual_strict_schema3_registry(tmp_path, monkeypatch, mutation):
    from datetime import timedelta
    from types import SimpleNamespace
    from uuid import uuid4
    import hashlib
    import oracle_brain.hosting.purpose_runtime as runtime
    import oracle_brain.operating_model.purpose_qualification_v3 as qualification
    now=datetime.now(timezone.utc);start=now-timedelta(seconds=1);end=now+timedelta(minutes=1)
    workspace,issuer,reviewer=uuid4(),uuid4(),uuid4()
    pins=dict(schema_version=3,workspace_id=str(workspace),runtime_hash='a'*64,
        compiler_profile='candidate-compiler',issuer_actor=str(issuer),reviewer_actor=str(reviewer),
        valid_from=start.isoformat(),expires_at=end.isoformat(),
        purpose='captured-assembly-semantic-admission-v3')
    scope=dict(qualification_purpose=pins['purpose'],workspace_id=str(workspace),runtime_hash='a'*64,
        compiler_profile='candidate-compiler',issuer_actor=str(issuer),reviewer_actor=str(reviewer))
    item=dict(schema_version=3,admission_hash='b'*64,revoked=False,
        valid_from=start.isoformat(),expires_at=end.isoformat(),**scope)
    item['record_seal']=digest(item)
    registry=dict(schema_version=3,revoked=False,valid_from=start.isoformat(),
        expires_at=end.isoformat(),admissions=[item],**scope)
    if mutation=='version':pins['schema_version']=1
    elif mutation=='missing':del pins['runtime_hash']
    elif mutation=='extra':pins['authorized']=True
    elif mutation=='foreign-scope':pins['workspace_id']=str(uuid4())
    def write(name,value):
        body=canonical_bytes(value);path=tmp_path/name;path.write_bytes(body);path.chmod(0o600)
        return str(path),hashlib.sha256(body).hexdigest()
    appointment_path,appointment_hash=write('appointment.json',pins)
    registry_path,registry_hash=write('registry.json',registry)
    settings=SimpleNamespace(config=SimpleNamespace(semantic_appointment_file=appointment_path,
        semantic_appointment_sha256=appointment_hash,semantic_registry_file=registry_path,
        semantic_registry_sha256=registry_hash),resolver=object())
    context=SimpleNamespace(embedding=object());connection=object();calls=[]
    def boundary(**kwargs):
        assert kwargs['resolver'] is settings.resolver and kwargs['connection'] is connection
        # Exercise the actual protected registry, not a stub appointment constructor.
        hashes=kwargs['semantic_registry'].current(kwargs['now']);calls.append(hashes)
        return hashes
    monkeypatch.setattr(qualification,'verify_embedding_projection_v3',boundary)
    if mutation is None:
        assert runtime._embedding_current_v3(settings,context,now=now,connection=connection)==frozenset({'b'*64})
        assert calls==[frozenset({'b'*64})]
    else:
        with pytest.raises((ValidationError,PermissionError)):
            runtime._embedding_current_v3(settings,context,now=now,connection=connection)
        assert not calls
