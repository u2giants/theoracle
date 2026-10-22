"""Closed recovery metadata. Construction never appoints or authorizes a phase."""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
from ipaddress import ip_address
from pathlib import PurePosixPath
from typing import Annotated,Literal,Union
from uuid import UUID
from pydantic import Field,field_validator,model_validator
from .contracts import StrictRecord,canonical_bytes,digest
from .protected_inputs_v1 import _parse

SHA=Annotated[str,Field(pattern=r'^[0-9a-f]{64}$')]
Name=Annotated[str,Field(pattern=r'^[a-zA-Z_][a-zA-Z0-9_]{0,62}$')]
Phase=Literal['capture','restore','deny-import','rebuild-verify','resume-observe']
Purpose=Literal['capture','current-denials','deny-only-target','observe']
Reasons=Literal['authority-unproved','authority-expired','source-census-unavailable','source-census-stale','source-census-incomplete','snapshot-inconsistent','custody-incomplete','vector-custody-unproved','vector-model-license-unproved','once-cost-tail-unproved','target-not-empty','target-identity-drift','partial-phase-UNKNOWN','graph-census-mismatch','current-membership-denied','deadline-expired','committed-close-uncertain']

def _sorted_unique(values,key):
    keys=tuple(key(v) for v in values)
    if keys!=tuple(sorted(set(keys))):raise ValueError('complete sorted unique recovery population required')

def _instant(value):
    if not isinstance(value,datetime) or value.tzinfo is None or value.utcoffset()!=timedelta(0):raise ValueError('finite UTC recovery instant required')
    return value

class RecoveryRecordV1(StrictRecord):
    @field_validator('schema_version',mode='before',check_fields=False)
    @classmethod
    def version_type(cls,value):
        if type(value) is not int:raise ValueError('exact integer recovery schema required')
        return value
    @field_validator('serving_authorized','dispatch_authorized','automatic_retry_allowed','complete','observation_only','fresh','denied',mode='before',check_fields=False)
    @classmethod
    def boolean_type(cls,value):
        if type(value) is not bool:raise ValueError('exact recovery boolean required')
        return value

class RecoveryPrivateFileV1(RecoveryRecordV1):
    path:str=Field(min_length=1,max_length=4096)
    sha256:SHA
    device:int=Field(ge=0)
    inode:int=Field(gt=0)
    uid:int=Field(ge=0)
    mode:Literal[384]
    @field_validator('path')
    @classmethod
    def path_exact(cls,value):
        p=PurePosixPath(value)
        if not p.is_absolute() or str(p)!=value or '..' in p.parts or '\x00' in value or '\\' in value:raise ValueError('canonical recovery private path required')
        return value

class RecoverySQLIdentityV1(RecoveryRecordV1):
    system_identifier:str=Field(pattern=r'^[1-9][0-9]{0,19}$')
    database_oid:int=Field(gt=0)
    database_name:Name
    database_owner:Name
    session_role:Name
    host:str=Field(min_length=1,max_length=253)
    hostaddr:str=Field(min_length=1,max_length=64)
    port:int=Field(ge=1,le=65535)
    database_url:RecoveryPrivateFileV1
    tls_ca:RecoveryPrivateFileV1
    schema_catalog_sha256:SHA
    @field_validator('hostaddr')
    @classmethod
    def address(cls,value):
        if str(ip_address(value))!=value:raise ValueError('single canonical numeric recovery address required')
        return value
    @field_validator('host')
    @classmethod
    def hostname(cls,value):
        import re
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.:-]{0,252}',value) or ',' in value:raise ValueError('single pinned TLS recovery host required')
        return value
    def physical(self):return self.system_identifier,self.database_oid

class RecoveryRootV1(RecoveryRecordV1):
    root_id:UUID
    path:str=Field(min_length=1,max_length=4096)
    device:int=Field(ge=0)
    inode:int=Field(gt=0)
    uid:int=Field(ge=0)
    mode:Literal[448]
    profile_sha256:SHA
    _path=field_validator('path')(RecoveryPrivateFileV1.path_exact.__func__)
    def physical(self):return self.device,self.inode,self.uid

class RecoveryDatabaseV1(RecoveryRecordV1):
    participant_id:UUID
    purposes:tuple[Literal['canonical-sql','checkpoint-sql','covered-key-ledger'],...]=Field(min_length=1,max_length=3)
    source:RecoverySQLIdentityV1
    target:RecoverySQLIdentityV1|None
    @model_validator(mode='after')
    def unique(self):_sorted_unique(self.purposes,lambda v:v);return self

class RecoveryLedgerV1(RecoveryRecordV1):
    key_fingerprint:SHA
    account:str=Field(min_length=1,max_length=256)
    ledger_registry_sha256:SHA
    terms_sha256:SHA
    participant_id:UUID
    @model_validator(mode='after')
    def account_key(self):
        if self.account!='key-sha256:'+self.key_fingerprint:raise ValueError('exact covered-key recovery ledger account required')
        return self

class RecoveryPrivateRootV1(RecoveryRecordV1):
    root_id:UUID
    purposes:tuple[Literal['private-originals','model-blobs','native-custody','embedding-wire-custody','job-spool'],...]=Field(min_length=1,max_length=5)
    source:RecoveryRootV1
    target:RecoveryRootV1|None
    @model_validator(mode='after')
    def unique(self):
        _sorted_unique(self.purposes,lambda v:v)
        if self.root_id!=self.source.root_id or self.target is not None and self.target.root_id!=self.root_id:raise ValueError('exact installed root identity required')
        return self

class RecoveryMigrationV1(RecoveryRecordV1):
    name:str=Field(pattern=r'^[0-9]{3}_[a-z0-9_]+\.sql$')
    sha256:SHA

class RecoveryGraphV1(RecoveryRecordV1):
    workspace_id:UUID
    model_id:UUID
    version:int=Field(gt=0)
    model_content_sha256:SHA
    generation:UUID
    graph_name:str=Field(min_length=1,max_length=240)
    accepted_event_id:UUID
    retained_receipt_body_sha256:SHA
    record_digest:SHA
    projection_digest:SHA
    @model_validator(mode='after')
    def identity(self):
        if self.graph_name!=f'oracle_processing_v1_{self.workspace_id.hex}_{self.model_id.hex}_{self.version}_{self.generation.hex}':raise ValueError('same actual accepted graph identity required')
        return self

class RecoveryScopeV1(RecoveryRecordV1):
    workspace_id:UUID
    appointment_id:UUID
    root_appointment_id:UUID
    scope:str=Field(min_length=1,max_length=200)
    @field_validator('scope')
    @classmethod
    def explicit(cls,value):
        if '\x00' in value or '*' in value or value.strip()!=value:raise ValueError('explicit rooted recovery scope required')
        return value

class RecoveryArchiveLimitsV1(RecoveryRecordV1):
    maximum_files:int=Field(ge=1,le=4096)
    maximum_member_bytes:int=Field(ge=1,le=536870912)
    maximum_total_bytes:int=Field(ge=1,le=1073741824)

class RecoveryPurposeBindingV1(RecoveryRecordV1):
    phase_authority:Purpose
    principal_id:UUID
    sql_identity:RecoverySQLIdentityV1

class RecoveryPhysicalSQLV1(RecoveryRecordV1):
    system_identifier:str=Field(pattern=r'^[1-9][0-9]{0,19}$')
    database_oid:int=Field(gt=0)
    database_name:Name
    def physical(self):return self.system_identifier,self.database_oid

RETAINED_026_CANONICAL_MIGRATIONS_V1=('001_foundation.sql', '002_pilot.sql', '004_workflow_integrity.sql', '006_hosting_gateway_authority.sql', '007_hosting_candidate_permissions.sql', '008_hosting_runtime_permissions.sql', '009_hosting_result_permissions.sql', '010_hosting_job_permissions.sql', '011_hosting_source_processing_permissions.sql', '012_processing_compiler_capabilities.sql', '013_processing_purpose_permissions.sql', '014_replacement_source_custody.sql', '017_processing_model_history.sql', '018_original_review_reading_input.sql', '019_employee_conversations.sql', '020_meeting_capture.sql', '021_meeting_participation.sql', '022_consolidated_answer_delivery.sql', '023_maintained_research.sql', '024_question_effects.sql', '025_recommendation_actions.sql', '026_operational_recovery.sql')
REQUIRED_CANONICAL_MIGRATIONS_V1=('001_foundation.sql', '002_pilot.sql', '004_workflow_integrity.sql', '006_hosting_gateway_authority.sql', '007_hosting_candidate_permissions.sql', '008_hosting_runtime_permissions.sql', '009_hosting_result_permissions.sql', '010_hosting_job_permissions.sql', '011_hosting_source_processing_permissions.sql', '012_processing_compiler_capabilities.sql', '013_processing_purpose_permissions.sql', '014_replacement_source_custody.sql', '017_processing_model_history.sql', '018_original_review_reading_input.sql', '019_employee_conversations.sql', '020_meeting_capture.sql', '021_meeting_participation.sql', '022_consolidated_answer_delivery.sql', '023_maintained_research.sql', '024_question_effects.sql', '025_recommendation_actions.sql', '026_operational_recovery.sql', '027_legacy_migration.sql')
RETAINED_026_OWNER_SOURCE_PINS_V1=(('020_meeting_capture.sql', '79c6d0c28c91c337d88ab3680de7c83deb79700d4cd69441107479fc5a23ed7e'), ('021_meeting_participation.sql', '959a77553849616eee1d7b4eba4ed8a3bc146aaa432b7e0e2ca8d83ff17b2f7c'), ('023_maintained_research.sql', '4cec9e3111318197566a77099d234fac2229e02805d88f82a26053194b36cc66'), ('024_question_effects.sql', 'e6f956c47842e81237f24519f27f06ea644b265b086309753e412b6c5eaf91aa'), ('025_recommendation_actions.sql', '59471db44be8c27ba2c3564d2732fb5081b5d79ceff8d0d53591855f0ac51b2b'))
OPERATIONAL_OWNER_SOURCE_PINS_V1=(('020_meeting_capture.sql', '79c6d0c28c91c337d88ab3680de7c83deb79700d4cd69441107479fc5a23ed7e'), ('021_meeting_participation.sql', '959a77553849616eee1d7b4eba4ed8a3bc146aaa432b7e0e2ca8d83ff17b2f7c'), ('023_maintained_research.sql', '4cec9e3111318197566a77099d234fac2229e02805d88f82a26053194b36cc66'), ('024_question_effects.sql', 'e6f956c47842e81237f24519f27f06ea644b265b086309753e412b6c5eaf91aa'), ('025_recommendation_actions.sql', '59471db44be8c27ba2c3564d2732fb5081b5d79ceff8d0d53591855f0ac51b2b'), ('027_legacy_migration.sql', '034d60c201b100acf22d0eafac5a9b623dfc14b053140a514d57da048f091143'))

class RecoveryDescriptorV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    protocol:Literal['oracle-replacement-recovery-descriptor-v1']='oracle-replacement-recovery-descriptor-v1'
    kind:Literal['capture','restore']
    operation_id:UUID
    original_capture_operation_id:UUID|None
    backup_manifest_sha256:SHA|None
    source_head:str=Field(pattern=r'^[0-9a-f]{40}$')
    runtime_sha256:SHA
    registry_sha256:SHA
    workspace_ids:tuple[UUID,...]=Field(min_length=1,max_length=256)
    scope_coverage:tuple[RecoveryScopeV1,...]=Field(min_length=1,max_length=1024)
    current_control_source:RecoverySQLIdentityV1
    purpose_bindings:tuple[RecoveryPurposeBindingV1,...]=Field(min_length=1,max_length=3)
    databases:tuple[RecoveryDatabaseV1,...]=Field(min_length=1,max_length=64)
    covered_ledgers:tuple[RecoveryLedgerV1,...]=Field(max_length=64)
    private_roots:tuple[RecoveryPrivateRootV1,...]=Field(min_length=1,max_length=256)
    migrations:tuple[RecoveryMigrationV1,...]=Field(min_length=1,max_length=128)
    accepted_graphs:tuple[RecoveryGraphV1,...]=Field(max_length=256)
    archive_limits:RecoveryArchiveLimitsV1
    issued_at:datetime
    expires_at:datetime
    original_horizon:datetime
    @classmethod
    def _installed_union_v1(cls):return REQUIRED_CANONICAL_MIGRATIONS_V1,OPERATIONAL_OWNER_SOURCE_PINS_V1
    @model_validator(mode='after')
    def complete(self):
        for name in ('issued_at','expires_at','original_horizon'):_instant(getattr(self,name))
        if not self.issued_at<self.expires_at<=self.original_horizon or self.expires_at-self.issued_at>timedelta(seconds=3600):raise ValueError('independently finite new recovery operation required')
        if self.kind=='capture' and (self.original_capture_operation_id is not None or self.backup_manifest_sha256 is not None):raise ValueError('capture cannot pin future backup content')
        if self.kind=='restore' and (self.original_capture_operation_id is None or self.backup_manifest_sha256 is None or self.original_capture_operation_id==self.operation_id):raise ValueError('fresh restore must reference existing different capture and actual manifest')
        _sorted_unique(self.workspace_ids,str);_sorted_unique(self.scope_coverage,lambda v:(str(v.workspace_id),v.scope,str(v.appointment_id)))
        if {v.workspace_id for v in self.scope_coverage}!=set(self.workspace_ids):raise ValueError('complete exact workspace/root coverage required')
        _sorted_unique(self.databases,lambda v:str(v.participant_id));_sorted_unique(self.private_roots,lambda v:str(v.root_id));_sorted_unique(self.covered_ledgers,lambda v:(v.account,v.key_fingerprint,str(v.participant_id)))
        _sorted_unique(self.migrations,lambda v:v.name)
        required,pins=self._installed_union_v1()
        if tuple(v.name for v in self.migrations)!=required:raise ValueError('complete exact installed canonical migration union required')
        actual_pins={v.name:v.sha256 for v in self.migrations}
        if any(actual_pins[name]!=sha for name,sha in pins):raise ValueError('frozen operational owner source drift requires quarantine')
        _sorted_unique(self.accepted_graphs,lambda v:(str(v.workspace_id),str(v.model_id),v.version,str(v.generation)))
        _sorted_unique(self.purpose_bindings,lambda v:v.phase_authority)
        expected={'capture','observe'} if self.kind=='capture' else {'current-denials','deny-only-target','observe'}
        if {v.phase_authority for v in self.purpose_bindings}!=expected:raise ValueError('exact independently installed phase bindings required')
        if len({v.sql_identity.session_role for v in self.purpose_bindings})!=len(self.purpose_bindings):raise ValueError('phase bindings require distinct actual own roles')
        if any(v.sql_identity.physical()!=self.current_control_source.physical() for v in self.purpose_bindings):raise ValueError('master/current-denials/observe must use original intact control plane')
        private_sources=[v.source.physical() for v in self.private_roots]
        if len(set(private_sources))!=len(private_sources) or len({v.source.path for v in self.private_roots})!=len(self.private_roots):raise ValueError('physical private source root appears once')
        sources=[v.source.physical() for v in self.databases]
        if len(set(sources))!=len(sources):raise ValueError('physical source DB appears once')
        if sum('canonical-sql'in v.purposes for v in self.databases)!=1 or sum('checkpoint-sql'in v.purposes for v in self.databases)!=1:raise ValueError('exact canonical/checkpoint owner required')
        if self.current_control_source.physical() not in sources:raise ValueError('intact actual original control plane must be explicit')
        ledgers={v.participant_id for v in self.databases if 'covered-key-ledger'in v.purposes}
        if ledgers!={v.participant_id for v in self.covered_ledgers}:raise ValueError('all covered ledgers must be declared exactly')
        if self.kind=='capture':
            if any(v.target is not None for v in (*self.databases,*self.private_roots)):raise ValueError('capture has no restore target')
        else:
            if any(v.target is None for v in (*self.databases,*self.private_roots)):raise ValueError('complete explicit restore target set required')
            targets=[v.target.physical() for v in self.databases]
            if len(set(targets))!=len(targets) or set(targets)&set(sources):raise ValueError('fresh target DBs must be distinct')
            root_sources={v.source.physical() for v in self.private_roots};root_targets=[v.target.physical() for v in self.private_roots]
            if len(set(root_targets))!=len(root_targets) or set(root_targets)&root_sources:raise ValueError('fresh private targets must be distinct')
        if any(g.workspace_id not in self.workspace_ids for g in self.accepted_graphs):raise ValueError('foreign accepted graph denied')
        return self

class Retained026CaptureDescriptorV1(RecoveryDescriptorV1):
    """EXACT old26 descriptive capture only; never current operation authority.

    Current settings/parser/exact-class own SQL bindings reject this type. A
    retained manifest remains inspectable with missing-current-tail quarantine;
    old capture/roles/paid/source permissions are never renewed.
    """
    kind:Literal['capture']
    @classmethod
    def _installed_union_v1(cls):return RETAINED_026_CANONICAL_MIGRATIONS_V1,RETAINED_026_OWNER_SOURCE_PINS_V1


class RecoveryClaimV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    operation_id:UUID
    phase:Phase
    descriptor_sha256:SHA
    original_phase_deadline:datetime
    claimed_at:datetime
    fresh:bool
    serving_authorized:Literal[False]=False
    dispatch_authorized:Literal[False]=False
    automatic_retry_allowed:Literal[False]=False
    @model_validator(mode='after')
    def finite(self):
        _instant(self.claimed_at);_instant(self.original_phase_deadline)
        if not self.claimed_at<self.original_phase_deadline or self.original_phase_deadline-self.claimed_at>timedelta(seconds=3600):raise ValueError('original actual phase deadline required')
        return self

class RecoveryObservationV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    protocol:Literal['oracle-replacement-recovery-observation-v1']='oracle-replacement-recovery-observation-v1'
    claim_state:Literal['claimed']='claimed'
    observation_id:UUID
    operation_id:UUID
    phase:Phase
    status:Literal['complete','UNKNOWN','refused']
    original_phase_deadline:datetime
    phase_started_at:datetime
    observed_at:datetime
    backup_manifest_sha256:SHA|None
    source_census_sha256:SHA|None
    observed_result_sha256:SHA|None
    observed_file_count:int|None=Field(ge=0)
    observed_bytes:int|None=Field(ge=0)
    quarantine_reasons:tuple[Reasons,...]
    observation_only:Literal[True]=True
    serving_authorized:Literal[False]=False
    dispatch_authorized:Literal[False]=False
    automatic_retry_allowed:Literal[False]=False
    @model_validator(mode='after')
    def finite(self):
        for n in ('original_phase_deadline','phase_started_at','observed_at'):_instant(getattr(self,n))
        if not self.phase_started_at<self.original_phase_deadline or self.observed_at<self.phase_started_at:raise ValueError('actual original claim dates required')
        _sorted_unique(self.quarantine_reasons,lambda v:v);return self

class RecoveryPreclaimRefusalV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    protocol:Literal['oracle-replacement-recovery-preclaim-refusal-v1']='oracle-replacement-recovery-preclaim-refusal-v1'
    claim_state:Literal['not-claimed']='not-claimed'
    observation_id:UUID
    operation_id:UUID
    attempted_phase:Phase
    descriptor_sha256:SHA
    status:Literal['refused']='refused'
    refused_at:datetime
    quarantine_reasons:tuple[Reasons,...]=Field(min_length=1)
    observation_only:Literal[True]=True
    serving_authorized:Literal[False]=False
    dispatch_authorized:Literal[False]=False
    automatic_retry_allowed:Literal[False]=False
    @model_validator(mode='after')
    def finite(self):_instant(self.refused_at);_sorted_unique(self.quarantine_reasons,lambda v:v);return self

def parse_recovery_descriptor_v1(raw):
    if type(raw) is not bytes or not 1<=len(raw)<=65536:raise ValueError('bounded protected descriptor required')
    return _parse(RecoveryDescriptorV1,raw)

def parse_retained_capture_descriptor_v1(raw):
    """Exact known historical tuple/pins only; never new operation authority."""
    from .protected_inputs_v1 import parse_canonical_object_v1
    obj=parse_canonical_object_v1(raw,limit=65536)
    names=tuple(v.get('name') for v in obj.get('migrations',[]) if type(v) is dict)
    if names==REQUIRED_CANONICAL_MIGRATIONS_V1:value=_parse(RecoveryDescriptorV1,raw)
    elif names==RETAINED_026_CANONICAL_MIGRATIONS_V1:value=_parse(Retained026CaptureDescriptorV1,raw)
    else:raise ValueError('unknown retained capture migration version refused')
    if value.kind!='capture':raise ValueError('retained parser is capture metadata only')
    return value

def parse_recovery_observation_v1(raw):
    from .protected_inputs_v1 import parse_canonical_object_v1
    value=parse_canonical_object_v1(raw,limit=65536)
    cls=RecoveryObservationV1 if value.get('protocol')=='oracle-replacement-recovery-observation-v1' else RecoveryPreclaimRefusalV1 if value.get('protocol')=='oracle-replacement-recovery-preclaim-refusal-v1' else None
    if cls is None:raise ValueError('closed recovery observation discriminant required')
    return _parse(cls,raw)


class PostRestoreBindingV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    protocol:Literal['oracle-replacement-post-restore-binding-v1']='oracle-replacement-post-restore-binding-v1'
    restore_operation_id:UUID
    original_capture_operation_id:UUID
    backup_manifest_sha256:SHA
    descriptor_sha256:SHA
    master_phase:Literal['restore']='restore'
    master_claimed_at:datetime
    original_phase_deadline:datetime
    target_physical_identity:RecoveryPhysicalSQLV1
    actual_postrestore_catalog_sha256:SHA
    purpose_bindings:tuple[RecoveryPurposeBindingV1,...]=Field(min_length=2,max_length=2)
    issuer_actor:UUID
    reviewer_actor:UUID
    issued_at:datetime
    expires_at:datetime
    original_horizon:datetime
    @model_validator(mode='after')
    def exact(self):
        for n in ('master_claimed_at','original_phase_deadline','issued_at','expires_at','original_horizon'):_instant(getattr(self,n))
        if not self.master_claimed_at<=self.issued_at<self.expires_at<=self.original_horizon<=self.original_phase_deadline:raise ValueError('postrestore cannot renew original master phase')
        if self.issuer_actor==self.reviewer_actor or self.restore_operation_id==self.original_capture_operation_id:raise ValueError('independent fresh restore installation required')
        _sorted_unique(self.purpose_bindings,lambda v:v.phase_authority)
        if tuple(v.phase_authority for v in self.purpose_bindings)!=('deny-only-target','observe') or len({v.sql_identity.session_role for v in self.purpose_bindings})!=2:raise ValueError('distinct target deny-only and observe ownroles required')
        if any(v.principal_id in (self.issuer_actor,self.reviewer_actor) or v.sql_identity.physical()!=self.target_physical_identity.physical() or v.sql_identity.database_name!=self.target_physical_identity.database_name or v.sql_identity.schema_catalog_sha256!=self.actual_postrestore_catalog_sha256 for v in self.purpose_bindings):raise ValueError('exact independently observed postrestore target bindings required')
        return self

    def bind_actual_master(self,descriptor,claim):
        if type(descriptor) is not RecoveryDescriptorV1 or type(claim) is not RecoveryClaimV1:raise TypeError('actual exact descriptor/claim metadata required')
        # This comparison is descriptive only; the factory must reread the
        # actual authenticated original-control getter before/after effects.
        if descriptor.kind!='restore' or (self.restore_operation_id,self.original_capture_operation_id,self.backup_manifest_sha256,self.descriptor_sha256)!=(descriptor.operation_id,descriptor.original_capture_operation_id,descriptor.backup_manifest_sha256,digest(descriptor.model_dump(mode='json'))):raise PermissionError('postrestore belongs to another operation/backup')
        if (claim.operation_id,claim.phase,claim.descriptor_sha256,claim.claimed_at,claim.original_phase_deadline)!=(self.restore_operation_id,self.master_phase,self.descriptor_sha256,self.master_claimed_at,self.original_phase_deadline):raise PermissionError('postrestore master claim differs')
        targets=[v.target for v in descriptor.databases if v.target is not None and v.target.physical()==self.target_physical_identity.physical() and v.target.database_name==self.target_physical_identity.database_name]
        if len(targets)!=1:raise PermissionError('target differs from actual pre-restore physical binding')
        return self


def parse_post_restore_binding_v1(raw):
    if type(raw) is not bytes or not 1<=len(raw)<=65536:raise ValueError('bounded protected postrestore profile required')
    return _parse(PostRestoreBindingV1,raw)

# Closed SQL020/021/023/024/025 union, independently frozen source manifests.
# Unknown or missing owners refuse the complete replacement census.
OPERATIONAL_TABLES_V1=('meeting_capture_admissions_v1', 'meeting_capture_enqueue_claims_v1', 'meeting_capture_enqueue_receipts_v1', 'meeting_capture_events_v1', 'meeting_capture_final_fetch_claims_v1', 'meeting_capture_heads_v1', 'meeting_capture_processing_links_v1', 'meeting_capture_revocations_v1', 'meeting_capture_worker_claims_v1', 'meeting_capture_worker_receipts_v1', 'meeting_create_stop_relation_revocations_v1', 'meeting_create_stop_relations_v1', 'meeting_final_mapping_revocations_v1', 'meeting_final_mappings_v1', 'meeting_normalization_claims_v1', 'meeting_normalization_intakes_v1', 'meeting_participant_epoch_revocations_v1', 'meeting_participant_epochs_v1', 'meeting_participation_admissions_v1', 'meeting_participation_audience_heads_v1', 'meeting_participation_delivery_events_v1', 'meeting_participation_delivery_heads_v1', 'meeting_participation_events_v1', 'meeting_participation_heads_v1', 'meeting_participation_intents_v1', 'meeting_participation_observations_v1', 'meeting_participation_revocations_v1', 'migration_admission_revocations_v1', 'migration_admissions_v1', 'migration_capture_observations_v1', 'migration_citation_bindings_v1', 'migration_events_v1', 'migration_heads_v1', 'migration_intent_observations_v1', 'migration_intents_v1', 'migration_inventories_v1', 'migration_inventory_entries_v1', 'migration_resolution_events_v1', 'migration_source_bindings_v1', 'migration_source_versions_v1', 'question_effect_admission_revocations_v1', 'question_effect_admissions_v1', 'question_effect_observations_v1', 'question_effect_operations_v1', 'recommendation_action_admissions_v1', 'recommendation_action_events_v1', 'recommendation_action_revocations_v1', 'recommendation_registrations_v1', 'recommendation_repairs_v1', 'research_admission_revocations_v1', 'research_admissions_v1', 'research_attempts_v1', 'research_events_v1', 'research_registrations_v1', 'research_run_heads_v1', 'research_state_v1')
RETAINED_026_POLICY_TABLES_V1=('appointments', 'artifact_invalidations', 'conversation_processing_admissions_v1', 'hosting_original_population_admissions_v1', 'hosting_original_source_admissions', 'hosting_request_principal_admissions', 'hosting_role_runtime_admissions', 'hosting_role_source_admissions', 'meeting_capture_admissions_v1', 'meeting_capture_enqueue_claims_v1', 'meeting_capture_enqueue_receipts_v1', 'meeting_capture_events_v1', 'meeting_capture_final_fetch_claims_v1', 'meeting_capture_heads_v1', 'meeting_capture_processing_links_v1', 'meeting_capture_revocations_v1', 'meeting_capture_worker_claims_v1', 'meeting_capture_worker_receipts_v1', 'meeting_create_stop_relation_revocations_v1', 'meeting_create_stop_relations_v1', 'meeting_final_mapping_revocations_v1', 'meeting_final_mappings_v1', 'meeting_normalization_claims_v1', 'meeting_normalization_intakes_v1', 'meeting_participant_epoch_revocations_v1', 'meeting_participant_epochs_v1', 'meeting_participation_admissions_v1', 'meeting_participation_audience_heads_v1', 'meeting_participation_delivery_events_v1', 'meeting_participation_delivery_heads_v1', 'meeting_participation_events_v1', 'meeting_participation_heads_v1', 'meeting_participation_intents_v1', 'meeting_participation_observations_v1', 'meeting_participation_revocations_v1', 'original_source_population_members_v1', 'original_source_populations_v1', 'processing_model_admission_revocations_v1', 'processing_model_admissions_v1', 'question_effect_admission_revocations_v1', 'question_effect_admissions_v1', 'question_effect_observations_v1', 'question_effect_operations_v1', 'recommendation_action_admissions_v1', 'recommendation_action_events_v1', 'recommendation_action_revocations_v1', 'recommendation_registrations_v1', 'recommendation_repairs_v1', 'recovery_admission_revocations_v1', 'recovery_operation_admissions_v1', 'research_admission_revocations_v1', 'research_admissions_v1', 'research_attempts_v1', 'research_events_v1', 'research_registrations_v1', 'research_run_heads_v1', 'research_state_v1', 'source_blocks', 'source_original_revisions', 'source_original_withdrawals_v1', 'source_reading_qualifications', 'sources')
CURRENT_POLICY_TABLES_V1=('appointments', 'artifact_invalidations', 'conversation_processing_admissions_v1', 'hosting_original_population_admissions_v1', 'hosting_original_source_admissions', 'hosting_request_principal_admissions', 'hosting_role_runtime_admissions', 'hosting_role_source_admissions', 'meeting_capture_admissions_v1', 'meeting_capture_enqueue_claims_v1', 'meeting_capture_enqueue_receipts_v1', 'meeting_capture_events_v1', 'meeting_capture_final_fetch_claims_v1', 'meeting_capture_heads_v1', 'meeting_capture_processing_links_v1', 'meeting_capture_revocations_v1', 'meeting_capture_worker_claims_v1', 'meeting_capture_worker_receipts_v1', 'meeting_create_stop_relation_revocations_v1', 'meeting_create_stop_relations_v1', 'meeting_final_mapping_revocations_v1', 'meeting_final_mappings_v1', 'meeting_normalization_claims_v1', 'meeting_normalization_intakes_v1', 'meeting_participant_epoch_revocations_v1', 'meeting_participant_epochs_v1', 'meeting_participation_admissions_v1', 'meeting_participation_audience_heads_v1', 'meeting_participation_delivery_events_v1', 'meeting_participation_delivery_heads_v1', 'meeting_participation_events_v1', 'meeting_participation_heads_v1', 'meeting_participation_intents_v1', 'meeting_participation_observations_v1', 'meeting_participation_revocations_v1', 'migration_admission_revocations_v1', 'migration_admissions_v1', 'migration_capture_observations_v1', 'migration_citation_bindings_v1', 'migration_events_v1', 'migration_heads_v1', 'migration_intent_observations_v1', 'migration_intents_v1', 'migration_inventories_v1', 'migration_inventory_entries_v1', 'migration_resolution_events_v1', 'migration_source_bindings_v1', 'migration_source_versions_v1', 'original_source_population_members_v1', 'original_source_populations_v1', 'processing_model_admission_revocations_v1', 'processing_model_admissions_v1', 'question_effect_admission_revocations_v1', 'question_effect_admissions_v1', 'question_effect_observations_v1', 'question_effect_operations_v1', 'recommendation_action_admissions_v1', 'recommendation_action_events_v1', 'recommendation_action_revocations_v1', 'recommendation_registrations_v1', 'recommendation_repairs_v1', 'recovery_admission_revocations_v1', 'recovery_operation_admissions_v1', 'research_admission_revocations_v1', 'research_admissions_v1', 'research_attempts_v1', 'research_events_v1', 'research_registrations_v1', 'research_run_heads_v1', 'research_state_v1', 'source_blocks', 'source_original_revisions', 'source_original_withdrawals_v1', 'source_reading_qualifications', 'sources')

class RecoveryTableWatermarkV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    table:Literal[*CURRENT_POLICY_TABLES_V1]
    row_count:int=Field(ge=0)
    canonical_rows_sha256:SHA

class RecoverySourceStateV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    workspace_id:UUID
    source_id:UUID
    current_revision:int=Field(gt=0)
    original_sha256:SHA|None
    status:Literal['processing','draft','confirmed','error']
    denied:bool

class RecoveryWithdrawalV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    event_id:UUID
    workspace_id:UUID
    source_id:UUID
    revision:int=Field(gt=0)
    original_sha256:SHA
    recorded_at:datetime
    _recorded=field_validator('recorded_at')(_instant)

class RecoveryAuthorityDenialV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    workspace_id:UUID
    principal_id:UUID|None
    session_role:Name|None
    appointment_id:UUID|None
    root_appointment_id:UUID|None
    scope:str|None=Field(min_length=1,max_length=200)
    reason:Literal['revoked','expired','missing-current-root','host-disabled','runtime-revoked']
    effective_at:datetime|None
    @field_validator('effective_at')
    @classmethod
    def instant(cls,value):return _instant(value) if value is not None else None


# Root-ratified v4: exact per-owner closed keys/reasons, never arbitrary dictionaries.
class AdmissionKeyV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    admission_id:UUID

class RevocationKeyV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    revocation_id:UUID

class MeetingHeadKeyV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    workspace_id:UUID
    meeting_id:UUID

class ClaimKeyV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    claim_id:UUID

class FetchClaimKeyV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    fetch_claim_id:UUID

class IntentKeyV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    intent_id:UUID

class RunKeyV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    run_id:UUID

class OperationKeyV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    operation_id:UUID

class ObservationKeyV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    observation_id:UUID

class ResearchRegistrationKeyV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    workspace_id:UUID
    source_id:UUID
    revision:int=Field(gt=0)

class RecommendationRegistrationKeyV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    workspace_id:UUID
    artifact_id:UUID
    version:int=Field(gt=0)

class _OperationalDenialBaseV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    record_row_sha256:SHA
    effective_at:datetime|None
    @field_validator('effective_at')
    @classmethod
    def instant(cls,value):return _instant(value) if value is not None else None

class CaptureAdmissionRevocationDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['meeting_capture_revocations_v1']
    record_kind:Literal['capture-admission-revocation']
    record_key:RevocationKeyV1
    reason:Literal['admission-revoked']

class ParticipantEpochRevocationDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['meeting_participant_epoch_revocations_v1']
    record_kind:Literal['participant-epoch-revocation']
    record_key:RevocationKeyV1
    reason:Literal['participant-epoch-revoked']

class FinalMappingRevocationDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['meeting_final_mapping_revocations_v1']
    record_kind:Literal['final-mapping-revocation']
    record_key:RevocationKeyV1
    reason:Literal['final-mapping-revoked']

class CreateStopRelationRevocationDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['meeting_create_stop_relation_revocations_v1']
    record_kind:Literal['create-stop-relation-revocation']
    record_key:RevocationKeyV1
    reason:Literal['create-stop-relation-revoked']

class CaptureAdmissionDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['meeting_capture_admissions_v1']
    record_kind:Literal['capture-admission']
    record_key:AdmissionKeyV1
    reason:Literal['admission-expired','admission-not-effective','operation-window-ended']

class CaptureHeadDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['meeting_capture_heads_v1']
    record_kind:Literal['capture-head']
    record_key:MeetingHeadKeyV1
    reason:Literal['capture-closed','operation-UNKNOWN']

class CaptureWorkerClaimDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['meeting_capture_worker_claims_v1']
    record_kind:Literal['capture-worker-claim']
    record_key:ClaimKeyV1
    reason:Literal['operation-window-ended','possible-effect-unreconciled']

class NormalizationClaimDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['meeting_normalization_claims_v1']
    record_kind:Literal['normalization-claim']
    record_key:ClaimKeyV1
    reason:Literal['operation-window-ended','possible-effect-unreconciled']

class ParticipationAdmissionRevocationDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['meeting_participation_revocations_v1']
    record_kind:Literal['participation-admission-revocation']
    record_key:RevocationKeyV1
    reason:Literal['admission-revoked']

class ParticipationAdmissionDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['meeting_participation_admissions_v1']
    record_kind:Literal['participation-admission']
    record_key:AdmissionKeyV1
    reason:Literal['admission-expired','admission-not-effective']

class ParticipationHeadDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['meeting_participation_heads_v1']
    record_kind:Literal['participation-head']
    record_key:MeetingHeadKeyV1
    reason:Literal['host-disabled','proactive-disabled','proactive-limit-reached','proactive-cooldown','active-intent-present']

class ParticipantObservationDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['meeting_participation_observations_v1']
    record_kind:Literal['participant-observation']
    record_key:ObservationKeyV1
    reason:Literal['operation-window-ended']

class ParticipationDeliveryDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['meeting_participation_delivery_heads_v1']
    record_kind:Literal['participation-delivery']
    record_key:IntentKeyV1
    reason:Literal['operation-UNKNOWN','possible-effect-unreconciled','operation-suppressed','effect-already-observed','operation-window-ended']

class ResearchRegistrationDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['research_registrations_v1']
    record_kind:Literal['research-registration']
    record_key:ResearchRegistrationKeyV1
    reason:Literal['source-disabled','source-rights-unconfirmed','registration-superseded']

class ResearchAdmissionRevocationDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['research_admission_revocations_v1']
    record_kind:Literal['research-admission-revocation']
    record_key:AdmissionKeyV1
    reason:Literal['admission-revoked']

class ResearchAdmissionDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['research_admissions_v1']
    record_kind:Literal['research-admission']
    record_key:AdmissionKeyV1
    reason:Literal['admission-expired','admission-not-effective']

class ResearchStateDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['research_state_v1']
    record_kind:Literal['research-state']
    record_key:ResearchRegistrationKeyV1
    reason:Literal['refresh-exhausted','refresh-not-due','active-intent-present']

class ResearchRunDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['research_run_heads_v1']
    record_kind:Literal['research-run']
    record_key:RunKeyV1
    reason:Literal['operation-UNKNOWN','possible-effect-unreconciled','effect-already-observed','operation-window-ended']

class QuestionAdmissionRevocationDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['question_effect_admission_revocations_v1']
    record_kind:Literal['question-admission-revocation']
    record_key:AdmissionKeyV1
    reason:Literal['admission-revoked']

class QuestionAdmissionDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['question_effect_admissions_v1']
    record_kind:Literal['question-admission']
    record_key:AdmissionKeyV1
    reason:Literal['admission-expired','admission-not-effective']

class QuestionOperationDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['question_effect_operations_v1']
    record_kind:Literal['question-operation']
    record_key:OperationKeyV1
    reason:Literal['operation-window-ended','possible-effect-unreconciled','effect-already-observed']

class RecommendationAdmissionRevocationDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['recommendation_action_revocations_v1']
    record_kind:Literal['recommendation-admission-revocation']
    record_key:AdmissionKeyV1
    reason:Literal['admission-revoked']

class RecommendationAdmissionDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['recommendation_action_admissions_v1']
    record_kind:Literal['recommendation-admission']
    record_key:AdmissionKeyV1
    reason:Literal['admission-expired','admission-not-effective']

class RecommendationRegistrationDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['recommendation_registrations_v1']
    record_kind:Literal['recommendation-registration']
    record_key:RecommendationRegistrationKeyV1
    reason:Literal['parent-model-superseded']

class FinalFetchClaimDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['meeting_capture_final_fetch_claims_v1']
    record_kind:Literal['final-fetch-claim']
    record_key:FetchClaimKeyV1
    reason:Literal['operation-window-ended','possible-effect-unreconciled']

class EnqueueClaimDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['meeting_capture_enqueue_claims_v1']
    record_kind:Literal['enqueue-claim']
    record_key:ClaimKeyV1
    reason:Literal['operation-window-ended','possible-effect-unreconciled']

class MigrationEntryKeyV1(RecoveryRecordV1):
    inventory_id:UUID
    sequence:int=Field(ge=1,le=10000)

class MigrationCitationKeyV1(RecoveryRecordV1):
    inventory_id:UUID
    legacy_citation_id:str=Field(min_length=1,max_length=256)
    @field_validator('legacy_citation_id')
    @classmethod
    def exact_origin(cls,value):
        parts=value.split(':')
        if len(parts)!=2 or parts[0] not in ('message','document') or str(UUID(parts[1]))!=parts[1]:raise ValueError('exact retained legacy citation identity required')
        return value

class MigrationAdmissionDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['migration_admissions_v1']
    record_kind:Literal['migration-admission']
    record_key:AdmissionKeyV1
    effective_at:datetime
    reason:Literal['admission-expired','admission-not-effective']

class MigrationAdmissionRevocationDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['migration_admission_revocations_v1']
    record_kind:Literal['migration-admission-revocation']
    record_key:AdmissionKeyV1
    effective_at:datetime
    reason:Literal['admission-revoked']

class MigrationIntentDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['migration_intents_v1']
    record_kind:Literal['migration-intent']
    record_key:IntentKeyV1
    reason:Literal['operation-window-ended','possible-effect-unreconciled']
    @model_validator(mode='after')
    def actual_onset(self):
        if (self.reason=='operation-window-ended')!=(self.effective_at is not None):raise ValueError('only ended window has actual known deadline; uncertain onset stays null')
        return self


class MigrationObservationDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['migration_intent_observations_v1']
    record_kind:Literal['migration-observation']
    record_key:ObservationKeyV1
    effective_at:None
    reason:Literal['possible-effect-unreconciled']

class MigrationEntryDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['migration_inventory_entries_v1']
    record_kind:Literal['migration-entry']
    record_key:MigrationEntryKeyV1
    effective_at:None
    reason:Literal['source-rights-unconfirmed','legacy-document-custody-unavailable','legacy-source-bytes-unavailable','legacy-original-missing','legacy-storage-read-unavailable','legacy-object-precondition-failed','legacy-capture-incomplete','legacy-unsupported-document-media','legacy-capture-coverage-gap']

class MigrationCitationDenialV1(_OperationalDenialBaseV1):
    owner_table:Literal['migration_citation_bindings_v1']
    record_kind:Literal['migration-citation']
    record_key:MigrationCitationKeyV1
    effective_at:None
    reason:Literal['legacy-citation-revision-changed']

Retained026OperationalDenialV1=Annotated[Union[FinalFetchClaimDenialV1,EnqueueClaimDenialV1,CaptureAdmissionRevocationDenialV1,ParticipantEpochRevocationDenialV1,FinalMappingRevocationDenialV1,CreateStopRelationRevocationDenialV1,CaptureAdmissionDenialV1,CaptureHeadDenialV1,CaptureWorkerClaimDenialV1,NormalizationClaimDenialV1,ParticipationAdmissionRevocationDenialV1,ParticipationAdmissionDenialV1,ParticipationHeadDenialV1,ParticipantObservationDenialV1,ParticipationDeliveryDenialV1,ResearchRegistrationDenialV1,ResearchAdmissionRevocationDenialV1,ResearchAdmissionDenialV1,ResearchStateDenialV1,ResearchRunDenialV1,QuestionAdmissionRevocationDenialV1,QuestionAdmissionDenialV1,QuestionOperationDenialV1,RecommendationAdmissionRevocationDenialV1,RecommendationAdmissionDenialV1,RecommendationRegistrationDenialV1],Field(discriminator='record_kind')]
OperationalDenialV1=Annotated[Union[MigrationAdmissionDenialV1,MigrationAdmissionRevocationDenialV1,MigrationIntentDenialV1,MigrationObservationDenialV1,MigrationEntryDenialV1,MigrationCitationDenialV1,FinalFetchClaimDenialV1,EnqueueClaimDenialV1,CaptureAdmissionRevocationDenialV1,ParticipantEpochRevocationDenialV1,FinalMappingRevocationDenialV1,CreateStopRelationRevocationDenialV1,CaptureAdmissionDenialV1,CaptureHeadDenialV1,CaptureWorkerClaimDenialV1,NormalizationClaimDenialV1,ParticipationAdmissionRevocationDenialV1,ParticipationAdmissionDenialV1,ParticipationHeadDenialV1,ParticipantObservationDenialV1,ParticipationDeliveryDenialV1,ResearchRegistrationDenialV1,ResearchAdmissionRevocationDenialV1,ResearchAdmissionDenialV1,ResearchStateDenialV1,ResearchRunDenialV1,QuestionAdmissionRevocationDenialV1,QuestionAdmissionDenialV1,QuestionOperationDenialV1,RecommendationAdmissionRevocationDenialV1,RecommendationAdmissionDenialV1,RecommendationRegistrationDenialV1],Field(discriminator='record_kind')]

class _RecoveryCensusBaseV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    descriptor_sha256:SHA
    source_system_identifier:str=Field(pattern=r'^[1-9][0-9]{0,19}$')
    source_database_oid:int=Field(gt=0)
    source_database_name:Name
    source_session_role:Name
    source_principal_id:UUID
    runtime_sha256:SHA
    registry_sha256:SHA
    workspace_ids:tuple[UUID,...]=Field(min_length=1,max_length=256)
    coverage:tuple[RecoveryScopeV1,...]=Field(min_length=1,max_length=1024)
    source_snapshot:str=Field(min_length=1,max_length=1024,pattern=r'^[0-9]+:[0-9]+:[0-9,]*$')
    watermarks:tuple[RecoveryTableWatermarkV1,...]=Field(min_length=len(CURRENT_POLICY_TABLES_V1),max_length=len(CURRENT_POLICY_TABLES_V1))
    sources:tuple[RecoverySourceStateV1,...]=Field(max_length=4096)
    withdrawals:tuple[RecoveryWithdrawalV1,...]=Field(max_length=16384)
    authority_denials:tuple[RecoveryAuthorityDenialV1,...]=Field(max_length=16384)
    operational_denials:tuple[OperationalDenialV1,...]=Field(max_length=32768)
    checked_at:datetime
    valid_until:datetime
    complete:Literal[True]=True
    serving_authorized:Literal[False]=False
    dispatch_authorized:Literal[False]=False
    @classmethod
    def _policy_tables_v1(cls):return CURRENT_POLICY_TABLES_V1
    @classmethod
    def _descriptor_type_v1(cls):return RecoveryDescriptorV1
    @model_validator(mode='after')
    def population(self):
        _instant(self.checked_at);_instant(self.valid_until)
        if not self.checked_at<self.valid_until<=self.checked_at+timedelta(seconds=30):raise ValueError('actual original bounded current-denials window required')
        _sorted_unique(self.workspace_ids,str);_sorted_unique(self.coverage,lambda v:(str(v.workspace_id),v.scope,str(v.appointment_id)))
        if {v.workspace_id for v in self.coverage}!=set(self.workspace_ids):raise ValueError('complete exact rooted deny coverage required')
        if tuple(v.table for v in self.watermarks)!=self._policy_tables_v1():raise ValueError('complete exact canonical and operational owner population required')
        _sorted_unique(self.sources,lambda v:(str(v.workspace_id),str(v.source_id)))
        _sorted_unique(self.withdrawals,lambda v:(str(v.workspace_id),str(v.source_id),v.revision,str(v.event_id)))
        _sorted_unique(self.authority_denials,lambda v:canonical_bytes(v.model_dump(mode='json')))
        _sorted_unique(self.operational_denials,lambda v:canonical_bytes(v.model_dump(mode='json')))
        if any(getattr(v.record_key,'workspace_id',self.workspace_ids[0]) not in self.workspace_ids for v in self.operational_denials):raise ValueError('foreign operational denial workspace refused')
        if any(v.workspace_id not in self.workspace_ids for v in (*self.sources,*self.withdrawals,*self.authority_denials)):raise ValueError('foreign workspace deny census refused')
        if any(v.recorded_at>self.checked_at for v in self.withdrawals):raise ValueError('future withdrawal refused')
        return self

    def _bind_descriptive(self,descriptor,kind,purpose,operation):
        if type(descriptor) is not self._descriptor_type_v1() or descriptor.kind!=kind:raise PermissionError('exact census operation descriptor required')
        binding=next(v for v in descriptor.purpose_bindings if v.phase_authority==purpose)
        expected=(descriptor.operation_id,digest(descriptor.model_dump(mode='json')),descriptor.current_control_source.system_identifier,descriptor.current_control_source.database_oid,descriptor.current_control_source.database_name,binding.sql_identity.session_role,binding.principal_id,descriptor.runtime_sha256,descriptor.registry_sha256,descriptor.workspace_ids,descriptor.scope_coverage)
        actual=(operation,self.descriptor_sha256,self.source_system_identifier,self.source_database_oid,self.source_database_name,self.source_session_role,self.source_principal_id,self.runtime_sha256,self.registry_sha256,self.workspace_ids,self.coverage)
        if actual!=expected or self.valid_until>descriptor.expires_at:raise PermissionError('foreign or renewed descriptive census refused')
        return self

class RecoveryDenyCensusV1(_RecoveryCensusBaseV1):
    protocol:Literal['oracle-replacement-current-denials-v1']='oracle-replacement-current-denials-v1'
    restore_operation_id:UUID
    def bind_descriptive_operation(self,descriptor):
        return self._bind_descriptive(descriptor,'restore','current-denials',self.restore_operation_id)

class RecoveryCaptureCensusV1(_RecoveryCensusBaseV1):
    protocol:Literal['oracle-replacement-capture-denials-v1']='oracle-replacement-capture-denials-v1'
    capture_operation_id:UUID
    def bind_descriptive_operation(self,descriptor):
        return self._bind_descriptive(descriptor,'capture','capture',self.capture_operation_id)


class Retained026CaptureCensusV1(RecoveryCaptureCensusV1):
    """EXACT old43 captured watermark/denial metadata, never current permission."""
    watermarks:tuple[RecoveryTableWatermarkV1,...]=Field(min_length=len(RETAINED_026_POLICY_TABLES_V1),max_length=len(RETAINED_026_POLICY_TABLES_V1))
    operational_denials:tuple[Retained026OperationalDenialV1,...]=Field(max_length=32768)
    @classmethod
    def _policy_tables_v1(cls):return RETAINED_026_POLICY_TABLES_V1
    @classmethod
    def _descriptor_type_v1(cls):return Retained026CaptureDescriptorV1
    @property
    def missing_current_tail(self):return True


def parse_retained_capture_census_v1(raw,descriptor):
    """Backup inspection only; exact descriptor version selects exact schema.

    Historical checked/valid timestamps stay byte-for-byte, never a new lease.
    Current getters do not call this parser or accept its old record type.
    """
    if type(raw) is not bytes or not 1<=len(raw)<=1048576:raise ValueError('bounded retained capture census required')
    if type(descriptor) is Retained026CaptureDescriptorV1:cls=Retained026CaptureCensusV1
    elif type(descriptor) is RecoveryDescriptorV1:cls=RecoveryCaptureCensusV1
    else:raise TypeError('exact known captured descriptor required')
    return _parse(cls,raw).bind_descriptive_operation(descriptor)


def parse_recovery_deny_census_v1(raw):
    if type(raw) is not bytes or not 1<=len(raw)<=1048576:raise ValueError('bounded complete deny census required')
    return _parse(RecoveryDenyCensusV1,raw)

class RecoveryCurrentV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    protocol:Literal['oracle-replacement-recovery-current-v1']='oracle-replacement-recovery-current-v1'
    admission_id:UUID
    operation_id:UUID
    phase_authority:Purpose
    principal_id:UUID
    session_role:Name
    descriptor_bytes_hex:str=Field(min_length=2,max_length=131072,pattern=r'^(?:[0-9a-f]{2})+$')
    descriptor_sha256:SHA
    postrestore_binding_bytes_hex:str|None=Field(min_length=2,max_length=131072,pattern=r'^(?:[0-9a-f]{2})+$')
    postrestore_binding_sha256:SHA|None
    backup_custody_sha256:SHA|None=None
    checked_at:datetime
    valid_until:datetime
    original_horizon:datetime
    census:Annotated[Union[RecoveryDenyCensusV1,RecoveryCaptureCensusV1],Field(discriminator='protocol')]|None
    original_capture_claim:RecoveryClaimV1|None=None
    original_capture_observations:tuple[RecoveryObservationV1,...]=Field(default=(),max_length=64)
    retained_claims:tuple[RecoveryClaimV1,...]=Field(max_length=5)
    imported_census_sha256s:tuple[SHA,...]=Field(max_length=4096)
    serving_authorized:Literal[False]=False
    dispatch_authorized:Literal[False]=False
    @model_validator(mode='after')
    def exact(self):
        import hashlib
        for n in ('checked_at','valid_until','original_horizon'):_instant(getattr(self,n))
        if not self.checked_at<self.valid_until<=min(self.original_horizon,self.checked_at+timedelta(seconds=30)):raise ValueError('actual bounded recovery currentness required')
        raw=bytes.fromhex(self.descriptor_bytes_hex)
        if hashlib.sha256(raw).hexdigest()!=self.descriptor_sha256:raise ValueError('actual descriptor bytes/hash mismatch')
        d=parse_recovery_descriptor_v1(raw)
        if d.operation_id!=self.operation_id:raise ValueError('current context belongs to foreign operation')
        if (self.postrestore_binding_bytes_hex is None)!=(self.postrestore_binding_sha256 is None):raise ValueError('complete actual postrestore profile bytes required')
        if self.postrestore_binding_bytes_hex is not None:
            raw=bytes.fromhex(self.postrestore_binding_bytes_hex)
            if hashlib.sha256(raw).hexdigest()!=self.postrestore_binding_sha256:raise ValueError('actual postrestore bytes/hash mismatch')
            p=parse_post_restore_binding_v1(raw)
            if p.restore_operation_id!=self.operation_id or p.descriptor_sha256!=self.descriptor_sha256:raise ValueError('foreign actual postrestore profile')
            bindings=p.purpose_bindings
        else:bindings=d.purpose_bindings
        matches=[b for b in bindings if b.phase_authority==self.phase_authority and b.principal_id==self.principal_id and b.sql_identity.session_role==self.session_role]
        if len(matches)!=1:raise ValueError('actual current purpose/role differs from installed binding')
        if (self.census is not None)!=(self.phase_authority in ('capture','current-denials')):raise ValueError('only own capture/current-denials returns complete current census')
        if self.census is not None and ((type(self.census) is RecoveryCaptureCensusV1)!=(self.phase_authority=='capture')):raise ValueError('capture and restore censuses cannot be relabelled')
        if self.census is not None:self.census.bind_descriptive_operation(d)
        _sorted_unique(self.retained_claims,lambda v:v.phase);_sorted_unique(self.imported_census_sha256s,lambda v:v)
        if any(c.operation_id!=self.operation_id or c.descriptor_sha256!=self.descriptor_sha256 or c.fresh for c in self.retained_claims):raise ValueError('retained claims cannot mint a fresh phase')
        if self.postrestore_binding_bytes_hex is None and self.imported_census_sha256s:raise ValueError('only target metadata reports applied denial imports')
        if d.kind=='capture' and (self.original_capture_claim is not None or self.original_capture_observations):raise ValueError('capture cannot borrow historical restore evidence')
        if self.original_capture_claim is not None:
            c=self.original_capture_claim
            if c.operation_id!=d.original_capture_operation_id or c.phase!='capture' or c.fresh:raise ValueError('exact retained original capture claim required')
        if self.original_capture_observations and self.original_capture_claim is None:raise ValueError('retained capture observations need actual retained capture claim')
        _sorted_unique(self.original_capture_observations,lambda v:str(v.observation_id))
        for o in self.original_capture_observations:
            if o.operation_id!=d.original_capture_operation_id or o.phase!='capture' or o.backup_manifest_sha256!=d.backup_manifest_sha256 or o.original_phase_deadline!=self.original_capture_claim.original_phase_deadline:raise ValueError('foreign historical capture observation refused')

        return self

class RecoveryStartupConfigV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    protocol:Literal['oracle-replacement-recovery-startup-v1']='oracle-replacement-recovery-startup-v1'
    descriptor:RecoveryPrivateFileV1
    backup_custody:RecoveryPrivateFileV1|None=None
    archive_runtime_manifest:RecoveryPrivateFileV1|None=None
    postrestore_binding:RecoveryPrivateFileV1|None
    issuer_actor:UUID
    reviewer_actor:UUID
    @model_validator(mode='after')
    def independent(self):
        if self.issuer_actor==self.reviewer_actor:raise ValueError('independent installed recovery startup required')
        return self


class RecoveryContainerDirectoryV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    path:str
    device:int=Field(ge=0)
    inode:int=Field(gt=0)
    uid:int=Field(ge=0)
    mode:Literal[448,493]
    _path=field_validator('path')(RecoveryPrivateFileV1.path_exact.__func__)

class RecoveryContainerSQLIdentityV1(RecoverySQLIdentityV1):
    """Tagged native-only files. Never interpreted as host protected pointers."""
    location:Literal['container-local']='container-local'
    ancestors:tuple[RecoveryContainerDirectoryV1,...]=Field(min_length=1,max_length=32)
    @model_validator(mode='after')
    def directories(self):
        paths=tuple(v.path for v in self.ancestors)
        if paths!=tuple(sorted(set(paths),key=lambda v:(len(PurePosixPath(v).parts),v))):raise ValueError('complete sorted exact container ancestor metadata required')
        return self

class RecoveryNativeContainerV1(RecoveryRecordV1):
    """Separately installed physical native executor pins; never credentials."""
    schema_version:Literal[1]=1
    container_id:SHA
    image_id:SHA
    container_name:str=Field(pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$')
    service_file:RecoveryPrivateFileV1
    native_sql_identity:RecoveryContainerSQLIdentityV1
    dump_inventory_sha256:SHA|None=None

class RecoveryNativeParticipantV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    participant_id:UUID
    source:RecoveryNativeContainerV1
    target:RecoveryNativeContainerV1|None

class RecoveryInheritedBackupFileV1(RecoveryRecordV1):
    """Observed immutable inherited handle; never a path or custody grant."""
    fd:int=Field(ge=3,le=2147483647)
    device:int=Field(ge=0)
    inode:int=Field(gt=0)
    uid:int=Field(ge=0)
    mode:Literal[384]=384
    link_count:Literal[1]=1
    size:int=Field(ge=1,le=1073741824)
    sha256:SHA
    @field_validator('mode','link_count',mode='before')
    @classmethod
    def exact_integer(cls,value):
        if type(value) is not int:raise ValueError('exact observed file integer required')
        return value

class RecoveryArchiveChildRequestV1(RecoveryRecordV1):
    """Small fixed control packet; actual installed parent is the only producer.

    Three distinct inherited read-only inputs, no paths/SQL/provider/keys/argv.
    Expected seals and DTO construction cannot authenticate current custody.
    The child may not replace original wall/monotonic ends with a fresh window.
    Complete runtime closure and actual enforced memory remain independent pins.
    """
    protocol:Literal['oracle-recovery-archive-check-v1']='oracle-recovery-archive-check-v1'
    operation_id:UUID
    descriptor_sha256:SHA
    custody_sha256:SHA
    runtime_closure_sha256:SHA
    archive_limit:int=Field(ge=1,le=1073741824)
    memory_limit_bytes:int=Field(ge=1,le=9223372036854775807)
    original_deadline:datetime
    original_monotonic_end:float
    archive:RecoveryInheritedBackupFileV1
    inventory:RecoveryInheritedBackupFileV1
    manifest:RecoveryInheritedBackupFileV1
    @field_validator('original_monotonic_end',mode='before')
    @classmethod
    def finite_original_monotonic(cls,value):
        from math import isfinite
        if type(value) is not float or not isfinite(value) or value<=0:raise ValueError('exact finite original monotonic end required')
        return value
    @model_validator(mode='after')
    def closed(self):
        _instant(self.original_deadline)
        files=(self.archive,self.inventory,self.manifest)
        if len({v.fd for v in files})!=3 or len({(v.device,v.inode) for v in files})!=3:raise ValueError('three distinct immutable inherited files required')
        if sum(v.size for v in files)>self.archive_limit:raise ValueError('complete final triplet exceeds descriptor aggregate')
        return self

class RecoveryArchiveChildResultV1(RecoveryRecordV1):
    """Actual successful structural observation only; no recovery activation."""
    protocol:Literal['oracle-recovery-archive-checked-v1']='oracle-recovery-archive-checked-v1'
    operation_id:UUID
    descriptor_sha256:SHA
    custody_sha256:SHA
    runtime_closure_sha256:SHA
    archive_sha256:SHA
    inventory_sha256:SHA
    manifest_sha256:SHA
    file_count:int=Field(ge=1,le=4096)
    total_bytes:int=Field(ge=1,le=1073741824)
    actual_memory_limit_bytes:int=Field(ge=1,le=9223372036854775807)
    actual_max_rss_kib:int=Field(ge=0)
    actual_user_seconds:float=Field(ge=0,allow_inf_nan=False)
    actual_system_seconds:float=Field(ge=0,allow_inf_nan=False)
    source_authenticated:Literal[False]=False
    serving_authorized:Literal[False]=False
    dispatch_authorized:Literal[False]=False
    automatic_retry_allowed:Literal[False]=False
    @field_validator('source_authenticated',mode='before')
    @classmethod
    def exact_source_boolean(cls,value):
        if type(value) is not bool:raise ValueError('exact observed source boolean required')
        return value
    @field_validator('actual_user_seconds','actual_system_seconds',mode='before')
    @classmethod
    def exact_observed_seconds(cls,value):
        if type(value) is not float:raise ValueError('exact observed child usage required')
        return value


def parse_recovery_archive_child_request_v1(raw):
    if type(raw) is not bytes or not 1<=len(raw)<=65536:raise ValueError('bounded complete fixed archive child control required')
    return _parse(RecoveryArchiveChildRequestV1,raw)

# Installed-runtime metadata is separate from the unchanged archive ceilings.
# Fixed finite source limits do not enlarge any installed resource allowance.
RUNTIME_CENSUS_MAX_FILES_V1=65536
RUNTIME_CENSUS_LINE_LIMIT_V1=65536
RUNTIME_CENSUS_MAX_BYTES_V1=RUNTIME_CENSUS_MAX_FILES_V1*(RUNTIME_CENSUS_LINE_LIMIT_V1+1)
RUNTIME_FILE_AGGREGATE_LIMIT_V1=34359738368

class RecoveryRuntimeFileV1(RecoveryRecordV1):
    kind:Literal['interpreter','entrypoint','own-source','stdlib','dependency','native-loader']
    path:str=Field(min_length=1,max_length=4096)
    device:int=Field(ge=0)
    inode:int=Field(gt=0)
    uid:int=Field(ge=0)
    mode:Literal[292,365,420,493]
    size:int=Field(ge=0,le=RUNTIME_FILE_AGGREGATE_LIMIT_V1)
    sha256:SHA
    @field_validator('path')
    @classmethod
    def canonical_path(cls,value):
        p=PurePosixPath(value)
        if not p.is_absolute() or str(p)!=value or '..' in p.parts or '\x00' in value or '\n' in value or '\r' in value or '\\' in value:raise ValueError('exact installed runtime path required')
        return value
    @field_validator('mode',mode='before')
    @classmethod
    def exact_mode(cls,value):
        if type(value) is not int:raise ValueError('exact installed runtime mode required')
        return value

class RecoveryRuntimeRootV1(RecoveryRecordV1):
    path:str=Field(min_length=1,max_length=4096)
    device:int=Field(ge=0)
    inode:int=Field(gt=0)
    uid:int=Field(ge=0)
    mode:Literal[365,448,493]
    _path=field_validator('path')(RecoveryRuntimeFileV1.canonical_path.__func__)
    _mode=field_validator('mode',mode='before')(RecoveryRuntimeFileV1.exact_mode.__func__)

class RecoveryRuntimeCensusRecordV1(RecoveryRecordV1):
    sequence:int=Field(ge=1,le=RUNTIME_CENSUS_MAX_FILES_V1)
    file:RecoveryRuntimeFileV1

class RecoveryArchiveRuntimeManifestV1(RecoveryRecordV1):
    """ONE logical installed manifest: small header plus exact streamed census.

    Startup independently pins this and custody. Header binds full custody SHA;
    custody has no runtime-manifest pointer. Neither labels nor file hashes prove
    arbitrary future import/dlopen enforcement or independently qualify runtime.
    """
    protocol:Literal['oracle-recovery-archive-runtime-v1']='oracle-recovery-archive-runtime-v1'
    purpose:Literal['archive-check-only']='archive-check-only'
    operation_id:UUID
    descriptor_sha256:SHA
    custody_sha256:SHA
    interpreter:RecoveryRuntimeFileV1
    entrypoint:RecoveryRuntimeFileV1
    installed_roots:tuple[RecoveryRuntimeRootV1,...]=Field(min_length=1,max_length=32)
    import_paths:tuple[str,...]=Field(min_length=1,max_length=32)
    interpreter_flags:tuple[Literal['-I','-S','-B'],...]
    census:RecoveryPrivateFileV1
    census_bytes:int=Field(ge=1,le=RUNTIME_CENSUS_MAX_BYTES_V1)
    file_count:int=Field(ge=2,le=RUNTIME_CENSUS_MAX_FILES_V1)
    total_file_bytes:int=Field(ge=1,le=RUNTIME_FILE_AGGREGATE_LIMIT_V1)
    memory_limit_bytes:int=Field(ge=1,le=9223372036854775807)
    memory_headroom_bytes:int=Field(ge=1,le=9223372036854775807)
    resource_evidence_sha256:SHA
    issuer_actor:UUID
    reviewer_actor:UUID
    valid_from:datetime
    expires_at:datetime
    original_horizon:datetime
    @model_validator(mode='after')
    def closed(self):
        for n in ('valid_from','expires_at','original_horizon'):_instant(getattr(self,n))
        if not self.valid_from<self.expires_at<=self.original_horizon or self.expires_at-self.valid_from>timedelta(seconds=3600):raise ValueError('independently finite installed runtime window required')
        if self.issuer_actor==self.reviewer_actor:raise ValueError('same independent startup installer/reviewer required')
        if self.interpreter.kind!='interpreter' or self.interpreter.mode not in (365,493) or self.entrypoint.kind!='entrypoint':raise ValueError('fixed actual interpreter and entrypoint required')
        if self.interpreter.path==self.entrypoint.path or (self.interpreter.device,self.interpreter.inode)==(self.entrypoint.device,self.entrypoint.inode):raise ValueError('distinct actual interpreter and entrypoint required')
        if self.interpreter_flags!=('-I','-S','-B'):raise ValueError('isolated fixed interpreter flags required')
        _sorted_unique(self.installed_roots,lambda v:v.path)
        roots=tuple(PurePosixPath(v.path) for v in self.installed_roots)
        if any(a.is_relative_to(b) or b.is_relative_to(a) for i,a in enumerate(roots) for b in roots[i+1:]):raise ValueError('complete nonoverlapping installed roots required')
        if len(set(self.import_paths))!=len(self.import_paths):raise ValueError('duplicate import path refused')
        for path in self.import_paths:
            RecoveryRuntimeFileV1.canonical_path(path)
            if not any(PurePosixPath(path).is_relative_to(root) for root in roots):raise ValueError('import path outside exact installed roots')
        if any(not any(PurePosixPath(v.path).is_relative_to(root) for root in roots) for v in (self.interpreter,self.entrypoint)):raise ValueError('interpreter/entrypoint must be included in complete installed census roots')
        if any(PurePosixPath(self.census.path).is_relative_to(root) for root in roots):raise ValueError('runtime census cannot include its own future header or census hash')
        return self

    def bind_descriptive_operation(self,descriptor,custody,custody_sha256):
        if type(descriptor) is not RecoveryDescriptorV1 or type(custody) is not BackupCustodyV1:raise TypeError('exact current operation/custody required')
        if (self.operation_id,self.descriptor_sha256,self.custody_sha256)!=(descriptor.operation_id,digest(descriptor.model_dump(mode='json')),custody_sha256):raise PermissionError('runtime belongs to another operation or custody')
        if (self.issuer_actor,self.reviewer_actor)!=(custody.issuer_actor,custody.reviewer_actor):raise PermissionError('runtime installer/reviewer differs from same custody installation')
        if not max(descriptor.issued_at,custody.issued_at)<=self.valid_from<self.expires_at<=min(descriptor.expires_at,descriptor.original_horizon,custody.expires_at,custody.original_horizon,self.original_horizon):raise PermissionError('runtime cannot renew current operation/custody')
        for runtime in self.installed_roots:
            here=PurePosixPath(runtime.path)
            for private in (custody.root_identity,*(r for p in descriptor.private_roots for r in (p.source,p.target) if r is not None)):
                there=PurePosixPath(private.path)
                if here.is_relative_to(there) or there.is_relative_to(here):raise PermissionError('runtime roots overlap backup/private original custody')
        return self


def parse_recovery_archive_runtime_manifest_v1(raw):
    if type(raw) is not bytes or not 1<=len(raw)<=65536:raise ValueError('bounded canonical runtime header required')
    return _parse(RecoveryArchiveRuntimeManifestV1,raw)

class RecoveryPhysicalResourceV1(RecoveryRecordV1):
    """Independent prospective filesystem budget; DTO/evidence SHA is not authority.

    Actual current installed custody must authenticate the complete profile, then
    the concrete owner observes this filesystem and available capacity BEFORE any
    create/dump. Headroom explicitly covers allocation/inodes/other usage; no
    statvfs observation proves a quota, issuer authority or safe parsing heap.
    """
    filesystem_id:int=Field(ge=0,le=18446744073709551615)
    filesystem_device:int=Field(ge=0,le=18446744073709551615)
    physical_byte_limit:int=Field(ge=1,le=9223372036854775807)
    headroom_bytes:int=Field(ge=1,le=9223372036854775807)
    resource_evidence_sha256:SHA

    def required_bytes_v1(self,descriptor,root):
        if type(descriptor) is not RecoveryDescriptorV1 or type(root) is not RecoveryRootV1:raise TypeError('exact installed descriptor/root required')
        if self.filesystem_device!=root.device:raise PermissionError('resource filesystem differs from custody root')
        # Complete final triplet <= A, complete retained pending dump+TOC <= A.
        required=2*descriptor.archive_limits.maximum_total_bytes+self.headroom_bytes
        if required>self.physical_byte_limit:raise PermissionError('installed physical allowance cannot hold retained staging and final output')
        return required

class BackupCustodyV1(RecoveryRecordV1):
    """Prospective independently installed custody, not a read/effect grant.

    Capture creates only operation-UUID scoped immutable output under an already
    private disjoint root. Restore reads existing retained bytes under NEW
    authority; expired capture never renews. Retention is not deletion authority.
    Concrete own SQL026 must authenticate this exact protected profile hash and
    complete rooted coverage before/after every private/native effect.
    """
    schema_version:Literal[1]=1
    protocol:Literal['oracle-replacement-backup-custody-v1']='oracle-replacement-backup-custody-v1'
    operation_id:UUID
    kind:Literal['capture','restore']
    descriptor_sha256:SHA
    principal_id:UUID
    phase_authority:Literal['capture','deny-only-target']
    root_identity:RecoveryRootV1
    scope_coverage:tuple[RecoveryScopeV1,...]=Field(min_length=1,max_length=1024)
    manifest:RecoveryPrivateFileV1|None
    archive:RecoveryPrivateFileV1|None
    archive_inventory:RecoveryPrivateFileV1|None
    native_participants:tuple[RecoveryNativeParticipantV1,...]=Field(min_length=1,max_length=64)
    physical_resource:RecoveryPhysicalResourceV1|None=None
    retention_policy_sha256:SHA
    minimum_retain_until:datetime
    issuer_actor:UUID
    reviewer_actor:UUID
    issued_at:datetime
    expires_at:datetime
    original_horizon:datetime
    @model_validator(mode='after')
    def closed(self):
        for n in ('minimum_retain_until','issued_at','expires_at','original_horizon'):_instant(getattr(self,n))
        if not self.issued_at<self.expires_at<=self.original_horizon or self.expires_at-self.issued_at>timedelta(seconds=3600):raise ValueError('finite original backup custody window required')
        if self.issuer_actor==self.reviewer_actor or self.principal_id in (self.issuer_actor,self.reviewer_actor):raise ValueError('independent custody installation required')
        expected='capture' if self.kind=='capture' else 'deny-only-target'
        if self.phase_authority!=expected:raise ValueError('custody purpose cannot renew or borrow capture')
        _sorted_unique(self.scope_coverage,lambda v:(str(v.workspace_id),v.scope,str(v.appointment_id)))
        _sorted_unique(self.native_participants,lambda v:str(v.participant_id))
        pointers=(self.manifest,self.archive,self.archive_inventory)
        if self.kind=='capture':
            if any(v is not None for v in pointers) or any(v.target is not None for v in self.native_participants):raise ValueError('capture cannot pin future files or targets')
        else:
            if any(v is None for v in pointers) or any(v.target is None for v in self.native_participants):raise ValueError('restore requires existing complete protected file and target set')
            if len({v.path for v in pointers})!=3 or len({(v.device,v.inode) for v in pointers})!=3:raise ValueError('retained manifest/archive/inventory must be distinct actual files')
            for v in pointers:
                if not PurePosixPath(v.path).is_relative_to(PurePosixPath(self.root_identity.path)):raise ValueError('retained files outside current custody root')
        return self

    def bind_descriptive_operation(self,descriptor):
        """Exact comparison only. A constructed profile cannot authenticate SQL."""
        if type(descriptor) is not RecoveryDescriptorV1:raise TypeError('exact recovery descriptor required')
        if (self.operation_id,self.kind,self.descriptor_sha256)!=(descriptor.operation_id,descriptor.kind,digest(descriptor.model_dump(mode='json'))):raise PermissionError('custody belongs to foreign operation/descriptor')
        if not descriptor.issued_at<=self.issued_at<self.expires_at<=min(descriptor.expires_at,descriptor.original_horizon,self.original_horizon):raise PermissionError('custody cannot extend installed operation')
        if self.scope_coverage!=descriptor.scope_coverage:raise PermissionError('complete installed custody coverage differs')
        binding=next((b for b in descriptor.purpose_bindings if b.phase_authority==self.phase_authority),None)
        if binding is None or binding.principal_id!=self.principal_id:raise PermissionError('custody principal differs from own installed purpose')
        custody_path=PurePosixPath(self.root_identity.path)
        for item in descriptor.private_roots:
            for root in (item.source,item.target):
                if root is not None:
                    path=PurePosixPath(root.path)
                    if self.root_identity.physical()==root.physical() or custody_path.is_relative_to(path) or path.is_relative_to(custody_path):raise PermissionError('backup custody root overlaps private input/target root')
        leaf=('recovery-backup-capture:' if self.kind=='capture' else 'recovery-backup-retained-read:')+str(self.operation_id)+':'+str(self.root_identity.root_id)
        policy='recovery-backup-retention-policy:'+self.retention_policy_sha256
        for workspace in descriptor.workspace_ids:
            scopes={v.scope for v in self.scope_coverage if v.workspace_id==workspace}
            if not {leaf,policy}<=scopes:raise PermissionError('complete independently rooted custody and retention leaves required')
        if tuple(v.participant_id for v in self.native_participants)!=tuple(v.participant_id for v in descriptor.databases):raise PermissionError('complete exact native DB participant population required')
        for native,db in zip(self.native_participants,descriptor.databases):
            for container,identity in ((native.source,db.source),(native.target,db.target)):
                if (container is None)!=(identity is None):raise PermissionError('native source/target population differs')
                if container is None:continue
                observed=container.native_sql_identity
                if (observed.physical(),observed.database_name,observed.database_owner,observed.session_role)!=(identity.physical(),identity.database_name,identity.database_owner,identity.session_role):raise PermissionError('native actual physical SQL/role identity differs')
                prefix=PurePosixPath('/run/oracle-recovery')/str(self.operation_id)/str(db.participant_id)
                files=(container.service_file,observed.database_url,observed.tls_ca)
                if any(not PurePosixPath(v.path).is_relative_to(prefix) for v in files):raise PermissionError('native file outside fixed preinstalled participant namespace')
                expected={str(parent) for v in files for parent in PurePosixPath(v.path).parents}
                if {v.path for v in observed.ancestors}!=expected:raise PermissionError('complete independently pinned native ancestor set required')
                private={str(prefix),str(prefix.parent)}
                if any(v.mode!=448 for v in observed.ancestors if v.path in private):raise PermissionError('operation and participant credential directories must remain private')

        if self.kind=='restore' and self.manifest.sha256!=descriptor.backup_manifest_sha256:raise PermissionError('restore must pin actual existing manifest bytes')
        return self

class RecoveryParticipantSnapshotV1(RecoveryRecordV1):
    """One actual participant cut; never an enterprise consistency promise."""
    schema_version:Literal[1]=1
    participant_id:UUID
    physical_sql:RecoveryPhysicalSQLV1
    database_owner:Name
    session_role:Name
    exported_snapshot_id:str=Field(pattern=r'^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{8}-[1-9][0-9]{0,9}$')
    transaction_snapshot:str=Field(pattern=r'^[0-9]+:[0-9]+:(?:[0-9]+(?:,[0-9]+)*)?$')
    snapshot_observed_at:datetime
    dump_member:str
    dump_sha256:SHA
    dump_bytes:int=Field(ge=1,le=536870912)
    actual_toc_sha256:SHA
    actual_inventory_sha256:SHA
    @model_validator(mode='after')
    def actual(self):
        _instant(self.snapshot_observed_at)
        if self.dump_member!='databases/'+str(self.participant_id)+'.dump':raise ValueError('fixed participant dump member required')
        return self

class RecoveryPrivateRootObservationV1(RecoveryRecordV1):
    schema_version:Literal[1]=1
    root_id:UUID
    actual_root_identity:RecoveryRootV1
    enumeration_before_sha256:SHA
    enumeration_after_sha256:SHA
    member_count:int=Field(ge=0,le=4096)
    bytes:int=Field(ge=0,le=1073741824)
    started_at:datetime
    finished_at:datetime
    @model_validator(mode='after')
    def actual(self):
        _instant(self.started_at);_instant(self.finished_at)
        if self.root_id!=self.actual_root_identity.root_id or self.finished_at<self.started_at:raise ValueError('exact observed private root identity/time required')
        if self.enumeration_before_sha256!=self.enumeration_after_sha256:raise ValueError('racing private root population must quarantine')
        return self


def parse_backup_custody_v1(raw):
    # Exact retained read-only profiles may omit ONLY the newly optional native
    # inventory pin. Missing pin never permits dump. No global parser weakening.
    from .protected_inputs_v1 import parse_canonical_object_v1
    obj=parse_canonical_object_v1(raw,limit=65536)
    value=BackupCustodyV1.model_validate_json(raw);expected=value.model_dump(mode='json')
    if 'physical_resource' not in obj:expected.pop('physical_resource')
    for actual,wanted in zip(obj['native_participants'],expected['native_participants']):
        for side in ('source','target'):
            if actual[side] is not None and 'dump_inventory_sha256' not in actual[side]:wanted[side].pop('dump_inventory_sha256')
    if canonical_bytes(expected)!=raw:raise ValueError('exact current or retained read-only backup custody bytes required')
    return value


def parse_recovery_startup_v1(raw):
    """Keep exact legacy startup bytes; only the new absent custody field defaults.

    No other omitted/default field, whitespace, duplicate or altered canonical
    record is accepted. This is not a generic canonical-parser relaxation.
    """
    from .protected_inputs_v1 import parse_canonical_object_v1
    obj=parse_canonical_object_v1(raw,limit=65536)
    value=RecoveryStartupConfigV1.model_validate_json(raw)
    expected=value.model_dump(mode='json')
    if 'backup_custody' not in obj:expected.pop('backup_custody')
    if 'archive_runtime_manifest' not in obj:expected.pop('archive_runtime_manifest')
    if canonical_bytes(expected)!=raw:raise ValueError('exact current or retained legacy startup bytes required')
    return value

class RecoveryRetainedNativeFileV1(RecoveryRecordV1):
    """Complete historical staging evidence, never a fresh file-read grant.

    Failed/late/partial staging remains retained outside accepted manifests.
    A fresh restore reads its independently current retained archive, never an
    expired capture path. Runtime never renames/deletes/overwrites these files.
    """
    schema_version:Literal[1]=1
    operation_id:UUID
    participant_id:UUID
    kind:Literal['dump','toc']
    relative_name:str
    private_file:RecoveryPrivateFileV1
    byte_count:int=Field(ge=1,le=536870912)
    complete:Literal[True]=True
    actual_exit_code:Literal[0]=0
    @field_validator('actual_exit_code',mode='before')
    @classmethod
    def exact_exit(cls,value):
        if type(value) is not int:raise ValueError('exact observed native exit integer required')
        return value
    @model_validator(mode='after')
    def fixed(self):
        expected=str(self.operation_id)+'/pending/'+str(self.participant_id)+'.'+self.kind
        if self.relative_name!=expected or not self.private_file.path.endswith('/'+expected):raise ValueError('exact actual operation native staging namespace required')
        if self.kind=='toc' and self.byte_count>1048576:raise ValueError('bounded native TOC custody required')
        if self.private_file.sha256=='e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855':raise ValueError('empty native staging is incomplete')
        return self

class ReplacementBackupManifestV1(RecoveryRecordV1):
    """Immutable descriptive structural capture, ALWAYS inconsistent/quarantined.

    Each participant retains its own actual exported snapshot. A manifest does
    not manufacture a common cut, surviving current policy/cost tail, vector
    license/read authority, readiness, a restore admission or deletion authority.
    Expired original capture remains history; new restore must use fresh custody.
    """
    schema_version:Literal[1]=1
    protocol:Literal['oracle-replacement-backup-manifest-v1']='oracle-replacement-backup-manifest-v1'
    original_capture_operation_id:UUID
    capture_descriptor:RecoveryDescriptorV1|Retained026CaptureDescriptorV1
    capture_descriptor_sha256:SHA
    capture_claim:RecoveryClaimV1
    capture_census_member:Literal['control/capture-census.json']='control/capture-census.json'
    capture_census_sha256:SHA
    retention_policy_sha256:SHA
    minimum_retain_until:datetime
    started_at:datetime
    finished_at:datetime
    archive_sha256:SHA
    archive_inventory_sha256:SHA
    native_staging:tuple[RecoveryRetainedNativeFileV1,...]=Field(min_length=2,max_length=128)
    participant_snapshots:tuple[RecoveryParticipantSnapshotV1,...]=Field(min_length=1,max_length=64)
    private_root_observations:tuple[RecoveryPrivateRootObservationV1,...]=Field(min_length=1,max_length=256)
    consistency:Literal['UNKNOWN']='UNKNOWN'
    quarantine_reasons:tuple[Reasons,...]=Field(min_length=1)
    serving_authorized:Literal[False]=False
    dispatch_authorized:Literal[False]=False
    automatic_retry_allowed:Literal[False]=False
    @model_validator(mode='after')
    def descriptive(self):
        for n in ('minimum_retain_until','started_at','finished_at'):_instant(getattr(self,n))
        d=self.capture_descriptor;c=self.capture_claim
        if type(d) is Retained026CaptureDescriptorV1 and 'once-cost-tail-unproved' not in self.quarantine_reasons:raise ValueError('retained26 capture lacks current027 tail; explicit quarantine required')
        if d.kind!='capture' or d.operation_id!=self.original_capture_operation_id or digest(d.model_dump(mode='json'))!=self.capture_descriptor_sha256:raise ValueError('exact original capture descriptor required')
        if (c.operation_id,c.phase,c.descriptor_sha256,c.fresh)!=(d.operation_id,'capture',self.capture_descriptor_sha256,False):raise ValueError('actual retained original capture claim required')
        if not c.claimed_at<=self.started_at<=self.finished_at<=c.original_phase_deadline:raise ValueError('capture cannot renew its actual original phase horizon')
        _sorted_unique(self.participant_snapshots,lambda v:str(v.participant_id));_sorted_unique(self.private_root_observations,lambda v:str(v.root_id));_sorted_unique(self.quarantine_reasons,lambda v:v)
        if 'snapshot-inconsistent' not in self.quarantine_reasons:raise ValueError('separate cuts must retain consistency quarantine')
        if tuple(v.participant_id for v in self.participant_snapshots)!=tuple(v.participant_id for v in d.databases):raise ValueError('complete actual DB snapshot set required')
        _sorted_unique(self.native_staging,lambda v:(str(v.participant_id),v.kind))
        expected_staging={(v.participant_id,kind) for v in d.databases for kind in ('dump','toc')}
        if {(v.participant_id,v.kind) for v in self.native_staging}!=expected_staging or any(v.operation_id!=d.operation_id for v in self.native_staging):raise ValueError('complete exact native staging evidence required')
        if sum(v.byte_count for v in self.native_staging)>d.archive_limits.maximum_total_bytes:raise ValueError('complete pending aggregate ceiling exceeded')
        for snapshot in self.participant_snapshots:
            dump=next(v for v in self.native_staging if v.participant_id==snapshot.participant_id and v.kind=='dump')
            toc=next(v for v in self.native_staging if v.participant_id==snapshot.participant_id and v.kind=='toc')
            if (dump.private_file.sha256,dump.byte_count,toc.private_file.sha256)!=(snapshot.dump_sha256,snapshot.dump_bytes,snapshot.actual_toc_sha256):raise ValueError('actual complete retained dump/TOC differs from captured snapshot')

        for observed,participant in zip(self.participant_snapshots,d.databases):
            if (observed.physical_sql.physical(),observed.physical_sql.database_name,observed.database_owner,observed.session_role)!=(participant.source.physical(),participant.source.database_name,participant.source.database_owner,participant.source.session_role):raise ValueError('actual original DB snapshot identity differs')
            if not self.started_at<=observed.snapshot_observed_at<=self.finished_at:raise ValueError('snapshot time outside actual capture')
        if tuple(v.root_id for v in self.private_root_observations)!=tuple(v.root_id for v in d.private_roots):raise ValueError('complete actual private root observation set required')
        for observed,participant in zip(self.private_root_observations,d.private_roots):
            if observed.actual_root_identity!=participant.source or not self.started_at<=observed.started_at<=observed.finished_at<=self.finished_at:raise ValueError('actual private root identity/time differs')
        if sum(v.member_count for v in self.private_root_observations)+3*len(self.participant_snapshots)+1>d.archive_limits.maximum_files:raise ValueError('capture archive member ceiling exceeded')
        if sum(v.bytes for v in self.private_root_observations)+sum(v.dump_bytes for v in self.participant_snapshots)>d.archive_limits.maximum_total_bytes:raise ValueError('capture archive aggregate ceiling exceeded')
        return self


def parse_replacement_backup_manifest_v1(raw,*,metadata_bound=1048576):
    # Legacy bound stays exact. Only current admitted custody may pass descriptor A.
    if type(metadata_bound) is not int or not 1<=metadata_bound<=1073741824:raise ValueError('exact bounded metadata ceiling required')
    if type(raw) is not bytes or not 1<=len(raw)<=metadata_bound:raise ValueError('bounded complete backup manifest bytes required')
    return _parse(ReplacementBackupManifestV1,raw)
