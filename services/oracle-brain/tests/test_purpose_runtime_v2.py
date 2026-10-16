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
        pins_file='/own/pins.json',pins_sha256='a'*64,population_file='/own/population.json',
        projection_file='/own/projection.json',source_url_file='/own/source-url',expected_owner_role='oracle_schema_owner',
        expected_session_role='own_census_login',source_expires_at=datetime.now(timezone.utc),
        parent_observer_admission_file='/own/observer.json',parent_observer_admission_hash='b'*64,
        observer_hostname='observer.internal',observer_port=9443,observer_server_uri='spiffe://oracle/parent-observer',
        observer_client_uri='spiffe://oracle/census-client',observer_ca='/own/ca',observer_certificate='/own/cert',
        observer_key='/own/key',observer_spool='/own/spool',observer_namespace='parent-v2',
        observer_initialization_hash='c'*64,server_certificate='/own/server-cert',server_key='/own/server-key',
        client_ca='/own/client-ca',bind_host='127.0.0.1',bind_port=9444)
    if role=='metadata':common.update(provider_hostname='provider.internal',provider_port=9445,
        provider_server_uri='spiffe://oracle/census-provider',provider_client_uri='spiffe://oracle/census-worker',
        provider_ca='/own/provider-ca',provider_certificate='/own/provider-cert',provider_key='/own/provider-client-key')
    else:common.update(phase_registry_file='/own/phase.json',private_context_files={},provider_key_file='/own/provider-key',
        budget_allocation_projection_file='/own/allocation.json',ledger_url_file='/central/ledger-url',
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
