"""Frozen027 descriptive/denial contracts only; no migration/store execution."""
from pathlib import Path
import hashlib
import pytest
from pydantic import TypeAdapter,ValidationError
from oracle_brain.operating_model.recovery_contracts_v1 import *
from test_recovery_contracts_v1 import descriptor,change,uid,T,H
from test_recovery_backup_custody_v1 import backup_manifest

EXPECTED={'migration_admissions_v1','migration_admission_revocations_v1','migration_inventories_v1','migration_inventory_entries_v1','migration_source_bindings_v1','migration_source_versions_v1','migration_heads_v1','migration_intents_v1','migration_events_v1','migration_intent_observations_v1','migration_resolution_events_v1','migration_citation_bindings_v1','migration_capture_observations_v1'}


def old_capture():
 d=descriptor();raw=d.model_dump();raw['migrations']=tuple(v.model_dump() for v in d.migrations if v.name!='027_legacy_migration.sql')
 return Retained026CaptureDescriptorV1.model_validate(raw)


def test_current_operations_require_every_frozen027_table_and_exact_source_pin():
 assert len(EXPECTED)==13 and EXPECTED<=set(OPERATIONAL_TABLES_V1)<=set(CURRENT_POLICY_TABLES_V1)
 assert len(OPERATIONAL_TABLES_V1)==56
 path=Path(__file__).resolve().parents[1]/'sql/027_legacy_migration.sql'
 assert hashlib.sha256(path.read_bytes()).hexdigest()=='034d60c201b100acf22d0eafac5a9b623dfc14b053140a514d57da048f091143'
 for kind in ['capture','restore']:
  d=descriptor(kind)
  with pytest.raises(ValidationError):change(d,migrations=d.migrations[:-1])
  with pytest.raises(ValidationError):change(d,migrations=d.migrations[:-1]+(change(d.migrations[-1],sha256=H),))


def test_exact_prior26_capture_is_descriptive_only_not_new_authority():
 old=old_capture();raw=canonical_bytes(old.model_dump(mode='json'))
 assert type(parse_retained_capture_descriptor_v1(raw)) is Retained026CaptureDescriptorV1
 with pytest.raises(ValidationError):parse_recovery_descriptor_v1(raw)
 with pytest.raises(ValidationError):change(old,kind='restore')
 with pytest.raises(ValidationError):change(old,migrations=old.migrations[:-1])
 with pytest.raises(ValidationError):change(old,migrations=tuple(change(v,sha256=H) if v.name=='020_meeting_capture.sql' else v for v in old.migrations))


def test_retained26_manifest_is_readable_only_with_explicit_missing_current_tail_quarantine():
 m=backup_manifest();old=old_capture();sha=digest(old.model_dump(mode='json'))
 raw=m.model_dump();raw.update(capture_descriptor=old.model_dump(),capture_descriptor_sha256=sha,capture_claim=change(m.capture_claim,descriptor_sha256=sha).model_dump(),quarantine_reasons=('once-cost-tail-unproved','snapshot-inconsistent'))
 value=ReplacementBackupManifestV1.model_validate(raw)
 assert type(value.capture_descriptor) is Retained026CaptureDescriptorV1
 assert parse_replacement_backup_manifest_v1(canonical_bytes(value.model_dump(mode='json')))==value
 with pytest.raises(ValidationError):change(value,quarantine_reasons=('snapshot-inconsistent',))
 assert value.serving_authorized is value.dispatch_authorized is False

@pytest.mark.parametrize('disposition,reason',[
 ('permission-unavailable','source-rights-unconfirmed'),('document-custody-unavailable','legacy-document-custody-unavailable'),('source-bytes-unavailable','legacy-source-bytes-unavailable'),('missing','legacy-original-missing'),('storage-read-unavailable','legacy-storage-read-unavailable'),('object-precondition-failed','legacy-object-precondition-failed'),('capture-incomplete','legacy-capture-incomplete'),('unsupported-document-media','legacy-unsupported-document-media'),('capture-coverage-gap','legacy-capture-coverage-gap')])
def test_exact_entry_failures_do_not_become_generic_permission_or_truth_denials(disposition,reason):
 value=MigrationEntryDenialV1(owner_table='migration_inventory_entries_v1',record_kind='migration-entry',record_key=MigrationEntryKeyV1(inventory_id=uid(1),sequence=1),record_row_sha256=H,reason=reason,effective_at=None)
 assert TypeAdapter(OperationalDenialV1).validate_python(value.model_dump())==value
 for patch in [{'owner_table':'migration_source_versions_v1'},{'reason':'source-disabled'},{'record_key':{'inventory_id':uid(1),'sequence':True}}]:
  with pytest.raises(ValidationError):change(value,**patch)
 source=(Path(__file__).resolve().parents[1]/'sql/026_operational_recovery.sql').read_text()
 assert "WHEN '"+disposition+"' THEN '"+reason+"'" in source


def test_citation_key_and_observed_denials_are_capability_specific_and_closed():
 value=MigrationCitationKeyV1(inventory_id=uid(1),legacy_citation_id='message:'+str(uid(10)))
 for bad in ['arbitrary','message:foreign','message:'+str(uid(10)).upper(),'document:','message:'+str(uid(2))+':other']:
  if bad==value.legacy_citation_id:continue
  with pytest.raises(ValidationError):change(value,legacy_citation_id=bad)
 denial=MigrationIntentDenialV1(owner_table='migration_intents_v1',record_kind='migration-intent',record_key=IntentKeyV1(intent_id=uid(3)),record_row_sha256=H,reason='possible-effect-unreconciled',effective_at=None)
 with pytest.raises(ValidationError):change(denial,reason='safe-resend')
 source=(Path(__file__).resolve().parents[1]/'sql/026_operational_recovery.sql').read_text()
 assert 'missing foreign malformed or unknown complete migration custody' in source
 assert 'fixed.failure_event=bad.event_id' in source and 'f.sequence>=proof.sequence' in source
 assert 'c.receipt_sha256 IS DISTINCT FROM' in source and 'c.capture->' in source


def old_census():
 from test_recovery_contracts_v1 import census
 _,current=census();d=old_capture();raw=current.model_dump();raw.pop('protocol');raw.pop('restore_operation_id')
 raw.update(capture_operation_id=d.operation_id,descriptor_sha256=digest(d.model_dump(mode='json')),coverage=d.scope_coverage,watermarks=tuple(v.model_dump() for v in current.watermarks if v.table in RETAINED_026_POLICY_TABLES_V1))
 return d,Retained026CaptureCensusV1.model_validate(raw)


def test_retained_old43_census_keeps_exact_original_bytes_time_and_no_current_authority():
 old,c=old_census();raw=canonical_bytes(c.model_dump(mode='json'))
 parsed=parse_retained_capture_census_v1(raw,old)
 assert type(parsed) is Retained026CaptureCensusV1 and parsed.missing_current_tail is True
 assert canonical_bytes(parsed.model_dump(mode='json'))==raw
 assert parsed.checked_at==T and parsed.valid_until==T+timedelta(seconds=30)
 assert parsed.serving_authorized is parsed.dispatch_authorized is False
 with pytest.raises(ValidationError):RecoveryCaptureCensusV1.model_validate(c.model_dump())
 with pytest.raises(ValidationError):parse_retained_capture_census_v1(raw,descriptor())
 with pytest.raises(PermissionError):c.bind_descriptive_operation(descriptor())


def test_no_mixed_watermark_descriptor_or_new_denial_inside_old43_capture():
 old,c=old_census()
 extra=RecoveryTableWatermarkV1(table='migration_admissions_v1',row_count=0,canonical_rows_sha256=H)
 for value in [c.watermarks+(extra,),c.watermarks[1:]+(extra,),tuple(reversed(c.watermarks))]:
  with pytest.raises(ValidationError):change(c,watermarks=value)
 denial=MigrationAdmissionDenialV1(owner_table='migration_admissions_v1',record_kind='migration-admission',record_key=AdmissionKeyV1(admission_id=uid(1)),record_row_sha256=H,reason='admission-expired',effective_at=T)
 with pytest.raises(ValidationError):change(c,operational_denials=(denial.model_dump(),))
 with pytest.raises(PermissionError):change(c,descriptor_sha256='b'*64).bind_descriptive_operation(old)


def test_current_getter_cannot_adopt_an_already_typed_retained_old_census():
 old,c=old_census();d=descriptor();binding=d.purpose_bindings[0]
 with pytest.raises(ValidationError):RecoveryCurrentV1(admission_id=uid(9),operation_id=d.operation_id,phase_authority='capture',principal_id=binding.principal_id,session_role=binding.sql_identity.session_role,descriptor_bytes_hex=canonical_bytes(d.model_dump(mode='json')).hex(),descriptor_sha256=digest(d.model_dump(mode='json')),postrestore_binding_sha256=None,checked_at=T,valid_until=T+timedelta(seconds=20),original_horizon=d.original_horizon,census=c,retained_claims=(),imported_census_sha256s=())


def test_migration_denial_effective_times_cannot_be_invented_from_observation_clock():
 key=MigrationEntryKeyV1(inventory_id=uid(1),sequence=1)
 entry=MigrationEntryDenialV1(owner_table='migration_inventory_entries_v1',record_kind='migration-entry',record_key=key,record_row_sha256=H,reason='legacy-original-missing',effective_at=None)
 with pytest.raises(ValidationError):change(entry,effective_at=T)
 claim=MigrationIntentDenialV1(owner_table='migration_intents_v1',record_kind='migration-intent',record_key=IntentKeyV1(intent_id=uid(2)),record_row_sha256=H,reason='possible-effect-unreconciled',effective_at=None)
 with pytest.raises(ValidationError):change(claim,effective_at=T)
 with pytest.raises(ValidationError):change(claim,reason='operation-window-ended')
 assert change(claim,reason='operation-window-ended',effective_at=T).effective_at==T
