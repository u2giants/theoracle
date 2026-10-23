"""Descriptive custody comparisons, never real installation or native authority."""
import pytest
from pydantic import ValidationError
from test_recovery_contracts_v1 import descriptor,change,root,file,sql,uid,T,H
from datetime import timedelta
from oracle_brain.operating_model.recovery_contracts_v1 import *


def custody(kind='capture'):
 d=descriptor(kind);r=change(root(99),root_id=uid(99),path='/backup')
 leaf=('recovery-backup-capture:' if kind=='capture' else 'recovery-backup-retained-read:')+str(d.operation_id)+':'+str(r.root_id)
 coverage=tuple(sorted((*d.scope_coverage,RecoveryScopeV1(workspace_id=uid(3),appointment_id=uid(90),root_appointment_id=uid(5),scope=leaf),RecoveryScopeV1(workspace_id=uid(3),appointment_id=uid(91),root_appointment_id=uid(5),scope='recovery-backup-retention-policy:'+H)),key=lambda v:(str(v.workspace_id),v.scope,str(v.appointment_id))))
 d=change(d,scope_coverage=coverage)
 def native(identity,n):
  base=f'/run/oracle-recovery/{d.operation_id}/{uid(20)}'
  source=identity.model_dump();source.update(database_url=change(identity.database_url,path=base+'/database-url').model_dump(),tls_ca=change(identity.tls_ca,path=base+'/ca.pem').model_dump())
  paths=sorted({str(v) for v in PurePosixPath(base+'/service').parents},key=lambda v:(len(PurePosixPath(v).parts),v))
  wrapped=RecoveryContainerSQLIdentityV1(**source,ancestors=tuple(RecoveryContainerDirectoryV1(path=v,device=1,inode=500+i,uid=1000,mode=448 if v in (base,str(PurePosixPath(base).parent)) else 493) for i,v in enumerate(paths)))
  return RecoveryNativeContainerV1(container_id=str(n)*64,image_id=H,container_name='owned'+str(n),service_file=change(file(n),path=base+f'/service-{n}'),native_sql_identity=wrapped)
 p=BackupCustodyV1(operation_id=d.operation_id,kind=kind,descriptor_sha256=digest(d.model_dump(mode='json')),principal_id=next(v.principal_id for v in d.purpose_bindings if v.phase_authority==('capture' if kind=='capture' else 'deny-only-target')),phase_authority='capture' if kind=='capture' else 'deny-only-target',root_identity=r,scope_coverage=coverage,manifest=None if kind=='capture' else change(file(71),path='/backup/manifest.json'),archive=None if kind=='capture' else change(file(72),path='/backup/archive.tar'),archive_inventory=None if kind=='capture' else change(file(73),path='/backup/inventory.json'),native_participants=(RecoveryNativeParticipantV1(participant_id=uid(20),source=native(d.databases[0].source,1),target=None if kind=='capture' else native(d.databases[0].target,2)),),retention_policy_sha256=H,minimum_retain_until=T+timedelta(days=30),issuer_actor=uid(80),reviewer_actor=uid(81),issued_at=T,expires_at=d.expires_at,original_horizon=d.original_horizon)
 return d,p

@pytest.mark.parametrize('kind',['capture','restore'])
def test_canonical_custody_exact_population_and_historical_retention(kind):
 d,p=custody(kind)
 assert parse_backup_custody_v1(canonical_bytes(p.model_dump(mode='json'))).bind_descriptive_operation(d)==p
 assert p.minimum_retain_until>p.expires_at # metadata is not a later read/deletion grant

@pytest.mark.parametrize('field,value',[('schema_version',True),('operation_id',uid(900)),('descriptor_sha256','b'*64),('principal_id',uid(900)),('issuer_actor',uid(81)),('phase_authority','deny-only-target'),('expires_at',T+timedelta(seconds=3601)),('manifest',file(50)),('scope_coverage',()),('native_participants',())])
def test_capture_refuses_collision_renewal_future_and_missing_pins(field,value):
 d,p=custody()
 with pytest.raises((ValueError,PermissionError,ValidationError)):change(p,**{field:value}).bind_descriptive_operation(d)

@pytest.mark.parametrize('part',['manifest','archive','archive_inventory'])
def test_restore_requires_every_actual_existing_file(part):
 d,p=custody('restore')
 with pytest.raises(ValidationError):change(p,**{part:None})

@pytest.mark.parametrize('which',['root-overlap','scope-gap','file-outside','manifest-drift','native-foreign','service-foreign','missing-target'])
def test_custody_refuses_actual_physical_scope_and_namespace_mismatch(which):
 d,p=custody('restore')
 with pytest.raises((ValueError,PermissionError,ValidationError)):
  if which=='root-overlap':p=change(p,root_identity=d.private_roots[0].source)
  elif which=='scope-gap':p=change(p,scope_coverage=d.scope_coverage[:-1])
  elif which=='file-outside':p=change(p,archive=change(p.archive,path='/foreign/archive.tar'))
  elif which=='manifest-drift':p=change(p,manifest=change(p.manifest,sha256='b'*64))
  elif which=='native-foreign':p=change(p,native_participants=(change(p.native_participants[0],source=change(p.native_participants[0].source,native_sql_identity=change(p.native_participants[0].source.native_sql_identity,system_identifier='999'))),))
  elif which=='service-foreign':p=change(p,native_participants=(change(p.native_participants[0],source=change(p.native_participants[0].source,service_file=file(900))),))
  elif which=='missing-target':p=change(p,native_participants=(change(p.native_participants[0],target=None),))
  p.bind_descriptive_operation(d)


def test_existing_startup_can_omit_custody_but_cannot_accept_arbitrary_profile():
 from oracle_brain.operating_model.protected_inputs_v1 import _parse
 c=RecoveryStartupConfigV1(descriptor=file(1),postrestore_binding=None,issuer_actor=uid(80),reviewer_actor=uid(81))
 raw=c.model_dump(mode='json');raw.pop('backup_custody')
 assert parse_recovery_startup_v1(canonical_bytes(raw)).backup_custody is None
 with pytest.raises(ValidationError):change(c,backup_custody={'path':'/whatever'})


def test_private_population_race_and_overflow_never_become_consistent():
 p=RecoveryPrivateRootObservationV1(root_id=uid(40),actual_root_identity=root(30),enumeration_before_sha256=H,enumeration_after_sha256=H,member_count=0,bytes=0,started_at=T,finished_at=T)
 for field,value in [('enumeration_after_sha256','b'*64),('root_id',uid(900)),('member_count',4097),('bytes',1073741825),('finished_at',T-timedelta(seconds=1))]:
  with pytest.raises(ValidationError):change(p,**{field:value})


def backup_manifest():
 d,p=custody()
 c=RecoveryClaimV1(operation_id=d.operation_id,phase='capture',descriptor_sha256=digest(d.model_dump(mode='json')),claimed_at=T,original_phase_deadline=T+timedelta(seconds=3600),fresh=False)
 snapshot=RecoveryParticipantSnapshotV1(participant_id=uid(20),physical_sql=RecoveryPhysicalSQLV1(system_identifier='110',database_oid=10,database_name='db10'),database_owner='oracle2_admin',session_role='recovery_owner',exported_snapshot_id='00000003-0000001B-1',transaction_snapshot='1:2:',snapshot_observed_at=T,dump_member=f'databases/{uid(20)}.dump',dump_sha256=H,dump_bytes=5,actual_toc_sha256=H,actual_inventory_sha256=H)
 observed=RecoveryPrivateRootObservationV1(root_id=uid(40),actual_root_identity=d.private_roots[0].source,enumeration_before_sha256=H,enumeration_after_sha256=H,member_count=0,bytes=0,started_at=T,finished_at=T)
 staging=tuple(RecoveryRetainedNativeFileV1(operation_id=d.operation_id,participant_id=uid(20),kind=k,relative_name=f'{d.operation_id}/pending/{uid(20)}.{k}',private_file=change(file(80+i),path=f'/backup/{d.operation_id}/pending/{uid(20)}.{k}'),byte_count=5 if k=='dump' else 10) for i,k in enumerate(('dump','toc')))
 return ReplacementBackupManifestV1(original_capture_operation_id=d.operation_id,capture_descriptor=d,capture_descriptor_sha256=c.descriptor_sha256,capture_claim=c,capture_census_sha256=H,retention_policy_sha256=H,minimum_retain_until=T+timedelta(days=30),started_at=T,finished_at=T,archive_sha256=H,archive_inventory_sha256=H,native_staging=staging,participant_snapshots=(snapshot,),private_root_observations=(observed,),quarantine_reasons=('snapshot-inconsistent',))


def test_actual_per_participant_snapshot_manifest_cannot_claim_consistent_recovery():
 m=backup_manifest()
 assert parse_replacement_backup_manifest_v1(canonical_bytes(m.model_dump(mode='json')))==m
 assert m.consistency=='UNKNOWN' and not m.serving_authorized and not m.dispatch_authorized
 for field,value in [('consistency','consistent'),('serving_authorized',True),('quarantine_reasons',()),('participant_snapshots',()),('private_root_observations',()),('original_capture_operation_id',uid(900)),('finished_at',T+timedelta(seconds=3601)),('capture_claim',change(m.capture_claim,fresh=True))]:
  with pytest.raises(ValidationError):change(m,**{field:value})

@pytest.mark.parametrize('field,value',[('session_role','other'),('physical_sql',RecoveryPhysicalSQLV1(system_identifier='999',database_oid=10,database_name='db10')),('snapshot_observed_at',T+timedelta(seconds=1)),('dump_member','databases/foreign.dump'),('exported_snapshot_id','caller guess'),('dump_bytes',536870913)])
def test_manifest_refuses_foreign_snapshot_and_fabricated_physical_members(field,value):
 m=backup_manifest()
 with pytest.raises(ValidationError):change(m,participant_snapshots=(change(m.participant_snapshots[0],**{field:value}),))


def test_capture_census_keeps_restore_protocol_and_authority_separate():
 from test_recovery_contracts_v1 import census
 _,old=census();d,p=custody()
 raw=old.model_dump();raw.pop('protocol');raw.pop('restore_operation_id')
 binding=d.purpose_bindings[0]
 raw.update(capture_operation_id=d.operation_id,descriptor_sha256=digest(d.model_dump(mode='json')),source_session_role=binding.sql_identity.session_role,source_principal_id=binding.principal_id,coverage=d.scope_coverage)
 capture=RecoveryCaptureCensusV1.model_validate(raw)
 assert capture.bind_descriptive_operation(d)==capture
 with pytest.raises(PermissionError):capture.bind_descriptive_operation(descriptor('restore'))
 with pytest.raises(ValidationError):parse_recovery_deny_census_v1(canonical_bytes(capture.model_dump(mode='json')))
 with pytest.raises(ValidationError):RecoveryCaptureCensusV1.model_validate({**capture.model_dump(),'restore_operation_id':uid(900)})


def test_retained_original_capture_expiry_remains_history_not_new_authority():
 m=backup_manifest();assert m.finished_at<m.minimum_retain_until
 # No fresh read/restore permissions or new expiry can be inserted in history.
 for field,value in [('current_permission',True),('expires_at',T+timedelta(days=30)),('automatic_retry_allowed',True)]:
  with pytest.raises(ValidationError):change(m,**{field:value})



def test_absent_dump_inventory_pin_preserves_readonly_profile_without_granting_dump():
 d,p=custody();body=p.model_dump(mode='json')
 body['native_participants'][0]['source'].pop('dump_inventory_sha256')
 parsed=parse_backup_custody_v1(canonical_bytes(body))
 assert parsed.native_participants[0].source.dump_inventory_sha256 is None
 with pytest.raises(ValidationError):change(p.native_participants[0].source,dump_inventory_sha256='not-a-hash')
