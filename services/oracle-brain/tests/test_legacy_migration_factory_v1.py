"""Real fixed controller/installed types with invented recording boundaries.

No SQL authority/RLS/intake custody is claimed by these orchestration tests.
Actual SQL and current source fixture proof remain separately mandatory.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import hashlib

import psycopg
import pytest

from oracle_brain.hosting.legacy_migration_v1 import LegacyMigrationFactoryV1, MigrationIntakeUnknown
from oracle_brain.hosting.original_intake_v1 import OriginalIntakeFactoryV1
from oracle_brain.migration.legacy_export_reader_v1 import (
    TechnicalLegacyExportReaderV1, LegacyExportProfileV1, TechnicalLegacyScopeV1,
    TechnicalLegacySnapshotV1, ExportedLegacyMessageV1, actual_export_program_sha256_v1,
)
from oracle_brain.migration.migration_authority_v1 import MigrationAuthorityV1
from oracle_brain.migration.migration_settings_v1 import (
    MigrationConsumerConfigV1, MigrationConsumerSettingsV1, SIGNATURES, PUBLIC_NAMES,
)
from oracle_brain.operating_model.contracts import canonical_bytes, digest
from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
from test_original_intake_v1 import settings as intake_settings


def pin(path, raw):
    path.write_bytes(raw);path.chmod(0o600)
    return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest())


def protected_model(cls, values):
    import json
    return cls.model_validate_json(json.dumps(dict(schema_version=1,**values),default=str))


@pytest.fixture
def installed(tmp_path,monkeypatch):
    intake_dir=tmp_path/'intake';intake_dir.mkdir(mode=0o700)
    intake=OriginalIntakeFactoryV1(intake_settings(intake_dir))
    c=intake.settings.config
    scope=protected_model(TechnicalLegacyScopeV1,dict(source_database_identity=uuid4(),employee_id=uuid4(),
        auth_user_id=uuid4(),auth_provider='microsoft',channel_id=uuid4(),message_ids=[uuid4()],document_ids=[]))
    ca=pin(tmp_path/'ca',b'invented recording-only CA')
    source_url=pin(tmp_path/'source-url',psycopg.conninfo.make_conninfo(host='127.0.0.1',port=5432,
        dbname='invented_source',user='source_reader',password='invented-only',sslmode='verify-full',sslrootcert=ca['path']).encode())
    now=datetime.now(timezone.utc);until=now+timedelta(seconds=50)
    profile=protected_model(LegacyExportProfileV1,dict(purpose='technical-legacy-channel-export-v1',permission_producer_kind='technical-channel-v1',
        source_scope=scope.model_dump(mode='json'),database_url=source_url,database_ca=ca,session_role='source_reader',source_catalog_sha256='a'*64,
        source_program_sha256=actual_export_program_sha256_v1(),max_original_bytes=1024*1024,valid_from=now-timedelta(seconds=1),expires_at=until,original_horizon=until))
    profile_pin=pin(tmp_path/'source-profile',canonical_bytes(profile.model_dump(mode='json')))
    operations=('snapshot-register','batch-prepare','batch-observe','read','reconcile','citation-read')
    roles=dict(zip(operations,('migration_snapshot','migration_prepare','migration_observe','migration_read','migration_receipt','migration_citation')))
    public_roles={name:(roles['snapshot-register'],) for name in PUBLIC_NAMES}
    public_roles.update(prepare_migration_batch_v1=(roles['batch-prepare'],),observe_migration_intake_v1=(roles['batch-observe'],),
        record_migration_resolution_v1=(roles['batch-observe'],),current_migration_v1=(roles['snapshot-register'],roles['read']),
        reconcile_migration_command_v1=(roles['reconcile'],),resolve_migration_citation_v1=(roles['citation-read'],))
    consumers=[]
    for op in operations:
        role=roles[op]
        url=pin(tmp_path/(role+'-url'),psycopg.conninfo.make_conninfo(host='127.0.0.1',port=5432,dbname='invented_target',
            user=role,password='invented-only',sslmode='verify-full',sslrootcert=ca['path']).encode())
        config=protected_model(MigrationConsumerConfigV1,dict(purpose='legacy-migration-consumer-v1',operation=op,admission_id=uuid4(),
            principal_id=c.principal_id,workspace_id=c.workspace_id,origin_system='invented_legacy',session_role=role,expected_owner='invented_owner',
            runtime_sha256='a'*64,registry_sha256='b'*64,descriptor_sha256=profile_pin['sha256'],source_scope_sha256=digest(scope.sql_scope_v1()),
            source_program_sha256=profile.source_program_sha256,intake_principal_id=c.principal_id,intake_config_sha256=intake.settings.config_sha256,
            database_url=url,database_ca=ca,capability_fingerprints=[(s.split('(')[0],'c'*64,'d'*64) for s in SIGNATURES],
            public_capability_roles=sorted(public_roles.items()),valid_from=now-timedelta(seconds=1),expires_at=until,original_horizon=until))
        selected=pin(tmp_path/(role+'-config'),canonical_bytes(config.model_dump(mode='json')))
        consumers.append(MigrationAuthorityV1(MigrationConsumerSettingsV1.load(selected['path'],selected['sha256'])))
    source=TechnicalLegacyExportReaderV1(profile_pin['path'],profile_pin['sha256'],consumers[0])
    factory=LegacyMigrationFactoryV1(**dict(zip(('register','prepare','observe','read','reconcile','citation'),consumers)),source=source,intake=intake)
    body=b'invented exact message'
    message=ExportedLegacyMessageV1(scope.message_ids[0],'e'*64,hashlib.sha256(body).hexdigest(),len(body),body)
    entry=dict(legacy_kind='message',legacy_id=str(message.legacy_id),metadata_sha256=message.metadata_sha256,permission_sha256='f'*64,
        original_sha256=message.original_sha256,byte_count=len(body),media_type='text/plain',disposition='message-eligible')
    inv=uuid4();command=uuid4();intent=uuid4();key=uuid4();deadline=datetime.now(timezone.utc)+timedelta(seconds=20)
    status=dict(schema_version=1,inventory_id=str(inv),inventory_entries_sha256=digest([entry]),revision=1,
        read_sequence=1,applied_sequence=0,valid_until=deadline.isoformat())
    snapshot=TechnicalLegacySnapshotV1(canonical_bytes(dict(inventory_id=str(inv),entries=[entry])),(message,),'a'*64,deadline)
    instruction=dict(intent_id=str(intent),legacy_id=str(message.legacy_id),legacy_kind='message',media_type='text/plain',metadata_sha256=message.metadata_sha256,source_id=None,
        expected_head=0,idempotency_key=str(key),original_sha256=message.original_sha256,byte_count=len(body),original_dispatch_deadline=deadline.isoformat())
    state=SimpleNamespace(factory=factory,consumers=consumers,source=source,intake=intake,message=message,status=status,
        snapshot=snapshot,instruction=instruction,inv=inv,command=command,intent=intent,key=key,deadline=deadline,
        source_reads=0,intakes=[],observations=[],prepare_state='prepared',source_failure_at=None,lost_ack=False)
    def observe_source(self,*,caller_deadline):
        self._time(caller_deadline);state.source_reads+=1
        if state.source_reads==state.source_failure_at:raise PermissionError('invented source withdrawal')
        return state.snapshot
    def status_read(self,inventory_id,*,caller_deadline):
        self._time(caller_deadline);assert inventory_id==state.inv
        return dict(state.status)
    def prepare(self,inventory_id,expected_head,command_id,receipt,*,caller_deadline):
        self._time(caller_deadline)
        return dict(state.status,state=state.prepare_state,intake_instructions=[state.instruction] if state.prepare_state=='prepared' else [],observation_instructions=[])
    def intake_text(self,**kwargs):
        state.intakes.append(kwargs)
        if state.lost_ack:raise OSError('invented lost finalize ACK')
        return object()  # Controller must not trust this as a receipt or grant.
    def observe(self,intent_id,config_hash,command_id,receipt,*,caller_deadline):
        self._time(caller_deadline);state.observations.append((intent_id,config_hash,command_id,caller_deadline))
        return dict(state.status,state='custody-observed',observation_only=True,receipt_read_only=False)
    monkeypatch.setattr(TechnicalLegacyExportReaderV1,'snapshot_v1',observe_source)
    monkeypatch.setattr(MigrationAuthorityV1,'status_v1',status_read)
    monkeypatch.setattr(MigrationAuthorityV1,'prepare_v1',prepare)
    monkeypatch.setattr(MigrationAuthorityV1,'observe_v1',observe)
    monkeypatch.setattr(OriginalIntakeFactoryV1,'intake_text_v1',intake_text)
    return state


def test_empty_target_bootstrap_never_mints_viewer_or_source_uuid(installed):
    f=installed
    with _request_fence_v1(float(__import__('time').monotonic()+25)):
        result=f.factory.import_batch_v1(f.inv,1,f.command,caller_deadline=f.deadline)
    assert len(f.intakes)==1 and len(f.observations)==1
    sent=f.intakes[0]
    assert sent['source_id'] is None and sent['expected_head']==0 and sent['idempotency_key']==f.key
    assert sent['data']==f.message.data and sent['caller_deadline']==f.deadline
    assert f.source_reads==4  # initial, before intake, after custody, final
    assert result['qualification'] is False and result['company_acceptance'] is False
    assert 'data' not in result and 'source_id' not in result
    with pytest.raises(PermissionError,match='viewer unavailable'):
        f.factory.resolve_citation_v1(f.inv,'message:'+str(f.message.legacy_id),caller_deadline=f.deadline)


def test_unknown_prepare_receipt_never_dispatches(installed):
    f=installed;f.prepare_state='UNKNOWN'
    with _request_fence_v1(float(__import__('time').monotonic()+25)):
        assert f.factory.import_batch_v1(f.inv,1,f.command,caller_deadline=f.deadline)['operation']=='batch-UNKNOWN'
    assert not f.intakes and not f.observations


def test_current_population_change_before_effect_keeps_intent_without_intake(installed):
    f=installed;f.source_failure_at=2
    with _request_fence_v1(float(__import__('time').monotonic()+25)),pytest.raises(PermissionError):
        f.factory.import_batch_v1(f.inv,1,f.command,caller_deadline=f.deadline)
    assert not f.intakes


def test_lost_ack_has_one_intake_then_separate_explicit_metadata_observation(installed):
    f=installed;f.lost_ack=True
    with _request_fence_v1(float(__import__('time').monotonic()+25)):
        with pytest.raises(MigrationIntakeUnknown) as unknown:
            f.factory.import_batch_v1(f.inv,1,f.command,caller_deadline=f.deadline)
        assert unknown.value.intent_id==f.intent and len(f.intakes)==1 and not f.observations
        result=f.factory.observe_intent_v1(f.intent,uuid4(),caller_deadline=f.deadline)
    assert len(f.intakes)==1 and len(f.observations)==1
    assert result['observation_only'] is True and result['receipt_read_only'] is False
    assert result['dispatch_authorized'] is False


def test_stale_cas_and_changed_instruction_hash_never_reach_intake(installed):
    f=installed
    with _request_fence_v1(float(__import__('time').monotonic()+25)):
        with pytest.raises(PermissionError):f.factory.import_batch_v1(f.inv,0,f.command,caller_deadline=f.deadline)
        f.instruction['original_sha256']='0'*64
        with pytest.raises(MigrationIntakeUnknown):f.factory.import_batch_v1(f.inv,1,f.command,caller_deadline=f.deadline)
    assert not f.intakes


def test_actual_installed_types_reject_configured_fake_viewer_without_silent_none(installed):
    f=installed
    with pytest.raises(TypeError):
        LegacyMigrationFactoryV1(**dict(zip(('register','prepare','observe','read','reconcile','citation'),f.consumers)),
            source=f.source,intake=f.intake,viewer=object())


def test_source_withdrawal_after_custody_keeps_unknown_and_no_observation_or_retry(installed):
    f=installed;f.source_failure_at=3
    with _request_fence_v1(float(__import__('time').monotonic()+25)),pytest.raises(MigrationIntakeUnknown):
        f.factory.import_batch_v1(f.inv,1,f.command,caller_deadline=f.deadline)
    assert len(f.intakes)==1 and not f.observations


def test_final_read_loss_after_real_boundary_records_remains_typed_unknown(installed):
    from oracle_brain.migration.migration_authority_v1 import MigrationOutcomeUnknown
    f=installed;f.source_failure_at=4
    with _request_fence_v1(float(__import__('time').monotonic()+25)),pytest.raises(MigrationOutcomeUnknown):
        f.factory.import_batch_v1(f.inv,1,f.command,caller_deadline=f.deadline)
    assert len(f.intakes)==1 and len(f.observations)==1


def test_fixed_pdf_dispatch_uses_actual_captured_bytes_not_text_or_caller_path(installed,monkeypatch):
    from oracle_brain.migration.legacy_export_reader_v1 import ExportedLegacyDocumentV1
    from oracle_brain.operating_model.protected_inputs_v1 import parse_canonical_object_v1
    f=installed;data=b'%PDF-1.4\ninvented current captured original\n%%EOF\n'
    doc=ExportedLegacyDocumentV1(f.message.legacy_id,'e'*64,hashlib.sha256(data).hexdigest(),len(data),data,{'invented_recording_only':True})
    entry=dict(legacy_kind='document',legacy_id=str(doc.legacy_id),metadata_sha256=doc.metadata_sha256,permission_sha256='f'*64,
        original_sha256=doc.original_sha256,byte_count=doc.byte_count,media_type='application/pdf',disposition='document-current-capture-eligible')
    f.status['inventory_entries_sha256']=digest([entry])
    f.snapshot=TechnicalLegacySnapshotV1(canonical_bytes(dict(inventory_id=str(f.inv),entries=[dict(entry,capture=doc.capture)])),(),
        'a'*64,f.deadline,documents=(doc,))
    f.instruction.update(legacy_kind='document',media_type='application/pdf',original_sha256=doc.original_sha256,byte_count=doc.byte_count)
    def pdf(self,**kwargs):f.intakes.append(kwargs);return object()
    monkeypatch.setattr(OriginalIntakeFactoryV1,'intake_pdf_v1',pdf)
    with _request_fence_v1(float(__import__('time').monotonic()+25)):
        f.factory.import_batch_v1(f.inv,1,f.command,caller_deadline=f.deadline)
    assert len(f.intakes)==1 and f.intakes[0]['data']==data
    assert f.intakes[0]['filename']=='legacy_'+str(doc.legacy_id)+'.pdf'
    assert f.intakes[0]['source_id'] is None and len(f.observations)==1


@pytest.mark.parametrize('kind,media',[('message','application/pdf'),('document','text/plain'),('claim','application/pdf')])
def test_mismatched_kind_media_is_never_a_generic_dispatch_selector(installed,kind,media):
    f=installed;f.instruction.update(legacy_kind=kind,media_type=media)
    with _request_fence_v1(float(__import__('time').monotonic()+25)):
        with pytest.raises(MigrationIntakeUnknown):
            f.factory.import_batch_v1(f.inv,1,f.command,caller_deadline=f.deadline)
    assert f.intakes==[] and f.observations==[]
