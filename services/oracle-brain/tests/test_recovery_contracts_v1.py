"""Descriptive records never substitute for observed SQL/custody authority."""
from datetime import datetime,timedelta,timezone
from uuid import UUID
import json
import pytest
from pydantic import ValidationError
from oracle_brain.operating_model.recovery_contracts_v1 import *

T=datetime(2026,10,22,12,tzinfo=timezone.utc)
H='a'*64

def uid(n):return UUID(int=n)
def file(n):return RecoveryPrivateFileV1(path=f'/private/{n}',sha256=H,device=1,inode=n,uid=1000,mode=384)
def sql(n,role='recovery_owner',catalog=H):
 return RecoverySQLIdentityV1(system_identifier=str(100+n),database_oid=n,database_name=f'db{n}',database_owner='oracle2_admin',session_role=role,host='localhost',hostaddr='127.0.0.1',port=5432,database_url=file(n),tls_ca=file(100+n),schema_catalog_sha256=catalog)
def root(n):return RecoveryRootV1(root_id=uid(40),path=f'/root/{n}',device=1,inode=n,uid=1000,mode=448,profile_sha256=H)
def descriptor(kind='capture'):
 bindings=('capture','observe') if kind=='capture' else ('current-denials','deny-only-target','observe')
 return RecoveryDescriptorV1(kind=kind,operation_id=uid(1),original_capture_operation_id=None if kind=='capture' else uid(2),backup_manifest_sha256=None if kind=='capture' else H,source_head='a'*40,runtime_sha256=H,registry_sha256=H,
 workspace_ids=(uid(3),),scope_coverage=(RecoveryScopeV1(workspace_id=uid(3),appointment_id=uid(4),root_appointment_id=uid(5),scope='recovery-capture:'+str(uid(1))),),current_control_source=sql(10),purpose_bindings=tuple(RecoveryPurposeBindingV1(phase_authority=p,principal_id=uid(50+i),sql_identity=sql(10,'own_'+str(i))) for i,p in enumerate(bindings)),databases=(RecoveryDatabaseV1(participant_id=uid(20),purposes=('canonical-sql','checkpoint-sql','covered-key-ledger'),source=sql(10),target=None if kind=='capture' else sql(11,'restore_executor')),),covered_ledgers=(RecoveryLedgerV1(key_fingerprint=H,account='key-sha256:'+H,ledger_registry_sha256=H,terms_sha256=H,participant_id=uid(20)),),private_roots=(RecoveryPrivateRootV1(root_id=uid(40),purposes=('embedding-wire-custody','job-spool','model-blobs','native-custody','private-originals'),source=root(30),target=None if kind=='capture' else root(31)),),migrations=tuple(RecoveryMigrationV1(name=n,sha256=dict(OPERATIONAL_OWNER_SOURCE_PINS_V1).get(n,H)) for n in REQUIRED_CANONICAL_MIGRATIONS_V1),accepted_graphs=(),archive_limits=RecoveryArchiveLimitsV1(maximum_files=4096,maximum_member_bytes=536870912,maximum_total_bytes=1073741824),issued_at=T,expires_at=T+timedelta(seconds=3600),original_horizon=T+timedelta(seconds=3600))
def change(obj,**kw):return type(obj).model_validate({**obj.model_dump(),**kw})
def profile(d=None):
 d=d or descriptor('restore')
 c=RecoveryClaimV1(operation_id=d.operation_id,phase='restore',descriptor_sha256=digest(d.model_dump(mode='json')),claimed_at=T,original_phase_deadline=T+timedelta(seconds=3600),fresh=True)
 p=PostRestoreBindingV1(restore_operation_id=d.operation_id,original_capture_operation_id=d.original_capture_operation_id,backup_manifest_sha256=H,descriptor_sha256=c.descriptor_sha256,master_claimed_at=T,original_phase_deadline=c.original_phase_deadline,target_physical_identity=RecoveryPhysicalSQLV1(system_identifier='111',database_oid=11,database_name='db11'),actual_postrestore_catalog_sha256='b'*64,purpose_bindings=tuple(RecoveryPurposeBindingV1(phase_authority=v,principal_id=uid(70+i),sql_identity=sql(11,'target_'+str(i),'b'*64)) for i,v in enumerate(('deny-only-target','observe'))),issuer_actor=uid(80),reviewer_actor=uid(81),issued_at=T+timedelta(seconds=100),expires_at=T+timedelta(seconds=3500),original_horizon=c.original_phase_deadline)
 return d,c,p

def test_exact_canonical_descriptor_and_profile_roundtrip():
 for kind in ('capture','restore'):
  d=descriptor(kind);assert parse_recovery_descriptor_v1(canonical_bytes(d.model_dump(mode='json')))==d
 d,c,p=profile();assert parse_post_restore_binding_v1(canonical_bytes(p.model_dump(mode='json'))).bind_actual_master(d,c)==p

@pytest.mark.parametrize('mutate',[lambda d:change(d,backup_manifest_sha256=H),lambda d:change(d,original_capture_operation_id=uid(2)),lambda d:change(d,expires_at=T+timedelta(seconds=3601),original_horizon=T+timedelta(seconds=3601)),lambda d:change(d,workspace_ids=(uid(9),)),lambda d:change(d,covered_ledgers=()),lambda d:change(d,purpose_bindings=d.purpose_bindings[::-1]),lambda d:change(d,purpose_bindings=(d.purpose_bindings[0],d.purpose_bindings[0])),lambda d:change(d,purpose_bindings=(d.purpose_bindings[0],change(d.purpose_bindings[1],sql_identity=sql(12,'other'))))])
def test_descriptor_refuses_missing_collision_foreign_and_future_authority(mutate):
 with pytest.raises((ValueError,ValidationError)):mutate(descriptor())

@pytest.mark.parametrize('field,value',[('schema_version',True),('device',True),('mode',True),('inode',0),('path','/private/../secret'),('path','/private//secret'),('path','relative')])
def test_private_pointer_direct_construction_strict(field,value):
 with pytest.raises((ValueError,ValidationError)):change(file(1),**{field:value})

@pytest.mark.parametrize('raw',[b'{"schema_version":1,"schema_version":1}',b'{"value":NaN}',b'{}\n',bytearray(b'{}'),b' '*65537])
def test_canonical_parser_refuses_malleable_input(raw):
 with pytest.raises((ValueError,ValidationError)):parse_recovery_descriptor_v1(raw)

@pytest.mark.parametrize('field,value',[('backup_manifest_sha256','b'*64),('restore_operation_id',uid(9)),('original_capture_operation_id',uid(9)),('descriptor_sha256','b'*64),('master_claimed_at',T+timedelta(seconds=1)),('original_phase_deadline',T+timedelta(seconds=3599))])
def test_postrestore_cannot_borrow_other_master_capture_or_manifest(field,value):
 d,c,p=profile()
 with pytest.raises((ValueError,ValidationError,PermissionError)):change(p,**{field:value}).bind_actual_master(d,c)

@pytest.mark.parametrize('mutation',[lambda p:change(p,expires_at=T+timedelta(seconds=3601),original_horizon=T+timedelta(seconds=3601)),lambda p:change(p,issuer_actor=p.reviewer_actor),lambda p:change(p,purpose_bindings=p.purpose_bindings[::-1]),lambda p:change(p,purpose_bindings=(p.purpose_bindings[0],p.purpose_bindings[0])),lambda p:change(p,purpose_bindings=(p.purpose_bindings[0],change(p.purpose_bindings[1],sql_identity=sql(11,'same',H))))])
def test_postrestore_new_profile_cannot_renew_or_mislabel_observed_target(mutation):
 with pytest.raises((ValueError,ValidationError)):mutation(profile()[2])

def test_old_capture_expiry_is_not_new_restore_horizon():
 d,c,p=profile();assert p.issued_at>d.issued_at and p.bind_actual_master(d,c)==p
 # No capture expiry is accepted as an input or silently copied into the new operation.
 with pytest.raises(ValidationError):PostRestoreBindingV1.model_validate({**p.model_dump(),'capture_expires_at':T-timedelta(days=1)})

def test_preclaim_refusal_has_no_fabricated_claim_or_success():
 r=RecoveryPreclaimRefusalV1(observation_id=uid(1),operation_id=uid(2),attempted_phase='restore',descriptor_sha256=H,refused_at=T,quarantine_reasons=('authority-unproved',))
 assert parse_recovery_observation_v1(canonical_bytes(r.model_dump(mode='json')))==r
 for name,value in [('original_phase_deadline',T),('phase_started_at',T),('observed_result_sha256',H),('serving_authorized',True),('status','complete')]:
  with pytest.raises(ValidationError):change(r,**{name:value})

def test_claim_is_not_dispatch_or_retry_authority_and_preserves_original_deadline():
 _,c,_=profile()
 for field in ('fresh','serving_authorized','dispatch_authorized','automatic_retry_allowed'):
  with pytest.raises(ValidationError):change(c,**{field:1})
 with pytest.raises(ValidationError):change(c,original_phase_deadline=T+timedelta(seconds=3601))
 assert not c.serving_authorized and not c.dispatch_authorized and not c.automatic_retry_allowed

def census():
 d=descriptor('restore');b=d.purpose_bindings[0]
 return d,RecoveryDenyCensusV1(restore_operation_id=d.operation_id,descriptor_sha256=digest(d.model_dump(mode='json')),source_system_identifier='110',source_database_oid=10,source_database_name='db10',source_session_role=b.sql_identity.session_role,source_principal_id=b.principal_id,runtime_sha256=H,registry_sha256=H,workspace_ids=d.workspace_ids,coverage=d.scope_coverage,source_snapshot='1:2:',watermarks=tuple(RecoveryTableWatermarkV1(table=t,row_count=0,canonical_rows_sha256=H) for t in CURRENT_POLICY_TABLES_V1),sources=(),withdrawals=(),authority_denials=(),operational_denials=(),checked_at=T,valid_until=T+timedelta(seconds=30))

def test_complete_current_census_requires_every_frozen_operational_owner_without_payloads():
 d,c=census();assert len(OPERATIONAL_TABLES_V1)==56
 assert parse_recovery_deny_census_v1(canonical_bytes(c.model_dump(mode='json'))).bind_descriptive_operation(d)==c
 assert set(RecoveryTableWatermarkV1.model_fields)=={'schema_version','table','row_count','canonical_rows_sha256'}
 for i in range(len(c.watermarks)):
  with pytest.raises(ValidationError):change(c,watermarks=c.watermarks[:i]+c.watermarks[i+1:])
 with pytest.raises(ValidationError):change(c,watermarks=c.watermarks[::-1])

@pytest.mark.parametrize('field,value',[('source_principal_id',uid(999)),('source_database_oid',999),('source_session_role','foreign_role'),('descriptor_sha256','b'*64),('restore_operation_id',uid(999)),('runtime_sha256','b'*64),('registry_sha256','b'*64)])
def test_census_does_not_borrow_foreign_identity_or_hash(field,value):
 d,c=census()
 with pytest.raises(PermissionError):change(c,**{field:value}).bind_descriptive_operation(d)

@pytest.mark.parametrize('field,value',[('complete',1),('dispatch_authorized',1),('valid_until',T+timedelta(seconds=31)),('source_snapshot','not actual snapshot')])
def test_census_direct_construction_rejects_coercions_or_renewal(field,value):
 with pytest.raises(ValidationError):change(census()[1],**{field:value})

def test_census_retains_denied_source_and_withdrawal_without_fabricating_qualification():
 d,c=census();s=RecoverySourceStateV1(workspace_id=uid(3),source_id=uid(9),current_revision=2,original_sha256=None,status='error',denied=True)
 c=change(c,sources=(s,));assert c.sources[0].original_sha256 is None and c.sources[0].denied
 with pytest.raises(ValidationError):change(c,sources=(change(s,workspace_id=uid(999)),))
 with pytest.raises(ValidationError):change(c,sources=(s,s))
 with pytest.raises(ValidationError):change(s,status='withdrawn')
 with pytest.raises(ValidationError):change(s,denied=1)
 w=RecoveryWithdrawalV1(event_id=uid(8),workspace_id=uid(3),source_id=uid(9),revision=1,original_sha256=H,recorded_at=T)
 assert change(c,withdrawals=(w,)).withdrawals==(w,)
 with pytest.raises(ValidationError):change(c,withdrawals=(change(w,recorded_at=T+timedelta(seconds=1)),))

def test_frozen_operational_source_change_and_missing_canonical_migration_quarantine():
 d=descriptor()
 for i,m in enumerate(d.migrations):
  with pytest.raises(ValidationError):change(d,migrations=d.migrations[:i]+d.migrations[i+1:])
  if m.name in dict(OPERATIONAL_OWNER_SOURCE_PINS_V1):
   with pytest.raises(ValidationError):change(d,migrations=d.migrations[:i]+(change(m,sha256='f'*64),)+d.migrations[i+1:])

@pytest.mark.parametrize('cls,table,kind,key,reason',[
 (ResearchRegistrationDenialV1,'research_registrations_v1','research-registration',ResearchRegistrationKeyV1(workspace_id=uid(3),source_id=uid(7),revision=1),'source-rights-unconfirmed'),
 (ParticipantEpochRevocationDenialV1,'meeting_participant_epoch_revocations_v1','participant-epoch-revocation',RevocationKeyV1(revocation_id=uid(7)),'participant-epoch-revoked'),
 (CreateStopRelationRevocationDenialV1,'meeting_create_stop_relation_revocations_v1','create-stop-relation-revocation',RevocationKeyV1(revocation_id=uid(7)),'create-stop-relation-revoked'),
 (ParticipationHeadDenialV1,'meeting_participation_heads_v1','participation-head',MeetingHeadKeyV1(workspace_id=uid(3),meeting_id=uid(7)),'proactive-cooldown'),
 (QuestionOperationDenialV1,'question_effect_operations_v1','question-operation',OperationKeyV1(operation_id=uid(7)),'possible-effect-unreconciled'),
 (RecommendationRegistrationDenialV1,'recommendation_registrations_v1','recommendation-registration',RecommendationRegistrationKeyV1(workspace_id=uid(3),artifact_id=uid(7),version=1),'parent-model-superseded'),
])
def test_operational_denial_preserves_exact_owner_key_condition_without_fabricated_time(cls,table,kind,key,reason):
 entry=cls(owner_table=table,record_kind=kind,record_key=key,reason=reason,record_row_sha256=H,effective_at=None)
 d,c=census();packet=change(c,operational_denials=(entry,))
 assert parse_recovery_deny_census_v1(canonical_bytes(packet.model_dump(mode='json'))).operational_denials==(entry,)
 assert entry.effective_at is None
 for field,value in [('owner_table','sources'),('record_kind','arbitrary-runtime-text'),('reason','some-policy-denied'),('record_key',{'arbitrary':'value'}),('effective_at',T.replace(tzinfo=None))]:
  with pytest.raises(ValidationError):change(entry,**{field:value})
 with pytest.raises(ValidationError):change(packet,operational_denials=(entry,entry))

def test_capability_specific_denials_cannot_be_relabelled_as_broad_authority_loss():
 for reason in ('proactive-disabled','proactive-cooldown'):
  entry=ParticipationHeadDenialV1(owner_table='meeting_participation_heads_v1',record_kind='participation-head',record_key=MeetingHeadKeyV1(workspace_id=uid(3),meeting_id=uid(7)),reason=reason,record_row_sha256=H,effective_at=None)
  with pytest.raises(ValidationError):change(entry,reason='admission-revoked')
 for reason in ('source-disabled','source-rights-unconfirmed'):
  entry=ResearchRegistrationDenialV1(owner_table='research_registrations_v1',record_kind='research-registration',record_key=ResearchRegistrationKeyV1(workspace_id=uid(3),source_id=uid(7),revision=1),reason=reason,record_row_sha256=H,effective_at=None)
  with pytest.raises(ValidationError):change(entry,reason='host-disabled')


def test_operational_deny_census_rejects_foreign_key_workspace():
 entry=ParticipationHeadDenialV1(owner_table='meeting_participation_heads_v1',record_kind='participation-head',record_key=MeetingHeadKeyV1(workspace_id=uid(999),meeting_id=uid(7)),reason='proactive-disabled',record_row_sha256=H,effective_at=None)
 with pytest.raises(ValidationError):change(census()[1],operational_denials=(entry,))


def test_actual_sql_shaped_nested_schema_one_records_parse_without_fabricating_authority():
 d,old=census();raw=old.model_dump(mode='json')
 raw['checked_at']=T.isoformat();raw['valid_until']=(T+timedelta(seconds=30)).isoformat()
 raw['watermarks']=[{'schema_version':1,'table':table,'row_count':0,'canonical_rows_sha256':H} for table in CURRENT_POLICY_TABLES_V1]
 raw['operational_denials']=[{'schema_version':1,'owner_table':'meeting_capture_final_fetch_claims_v1','record_kind':'final-fetch-claim','record_key':{'schema_version':1,'fetch_claim_id':str(uid(900))},'record_row_sha256':H,'reason':'possible-effect-unreconciled','effective_at':None}]
 observed=RecoveryDenyCensusV1.model_validate_json(canonical_bytes(raw))
 assert observed.bind_descriptive_operation(d)==observed
 assert observed.operational_denials[0].record_key.fetch_claim_id==uid(900)
 assert observed.checked_at==T and not observed.serving_authorized
 # The SQL return can be canonically represented for target import without
 # changing its actual instant or manufacturing a source/currentness grant.
 assert observed.model_dump(mode='json')['checked_at']==T.isoformat().replace('+00:00','Z')
 bad=json.loads(canonical_bytes(raw));bad['operational_denials'][0]['record_key']['schema_version']=True
 with pytest.raises(ValidationError):RecoveryDenyCensusV1.model_validate_json(canonical_bytes(bad))

@pytest.mark.parametrize('table,kind,key',[('meeting_capture_final_fetch_claims_v1','final-fetch-claim','fetch_claim_id'),('meeting_capture_enqueue_claims_v1','enqueue-claim','claim_id')])
def test_new_once_claim_denials_use_exact_pk_and_never_broaden_reasons(table,kind,key):
 from pydantic import TypeAdapter
 adapter=TypeAdapter(OperationalDenialV1)
 raw={'schema_version':1,'owner_table':table,'record_kind':kind,'record_key':{'schema_version':1,key:str(uid(900))},'record_row_sha256':H,'reason':'possible-effect-unreconciled','effective_at':None}
 value=adapter.validate_json(canonical_bytes(raw));assert value.reason=='possible-effect-unreconciled'
 for field,alter in [('owner_table','meeting_capture_events_v1'),('reason','host-disabled'),('record_key',{'schema_version':1,'event_id':str(uid(900))})]:
  with pytest.raises(ValidationError):adapter.validate_json(canonical_bytes({**raw,field:alter}))
