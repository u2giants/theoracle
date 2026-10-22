"""Protected independently installed migration consumer; no appointment issuer."""
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator, field_validator
from oracle_brain.operating_model.contracts import StrictRecord
from oracle_brain.operating_model.protected_inputs_v1 import ProtectedInputV1, _pinned, _parse

CONTEXT = 'uuid,text,text,text,timestamptz'
PUBLIC_SIGNATURES = (
    f'register_migration_inventory_v1({CONTEXT},bytea,uuid)',
    f'prepare_migration_batch_v1({CONTEXT},uuid,integer,uuid)',
    f'observe_migration_intake_v1({CONTEXT},uuid,bytea,uuid)',
    f'record_migration_resolution_v1({CONTEXT},uuid,uuid,integer,uuid)',
    f'current_migration_v1({CONTEXT},uuid)',
    f'reconcile_migration_command_v1({CONTEXT},uuid)',
    f'resolve_migration_citation_v1({CONTEXT},text,uuid)',
)
PRIVATE_SIGNATURES = (
    '_migration_binding_once_v1()',
    '_migration_named_path_v1(uuid,uuid,uuid,text)',
    '_migration_scope_valid_v1(jsonb,integer)',
    '_migration_context_v1(uuid,text,text,text,text,timestamptz,boolean)',
    '_migration_json_v1(bytea,integer)',
    '_migration_flags_v1()',
    '_migration_command_v1(oracle2.migration_admissions_v1,uuid,uuid,bytea,text,jsonb)',
    '_migration_inventory_v1(oracle2.migration_admissions_v1,uuid)',
    '_migration_writer_scope_current_v1(uuid)',
    '_migration_receipt_v1(oracle2.migration_admissions_v1,uuid,boolean)',
    '_migration_advance_v1(uuid)',
    '_migration_iso_v1(timestamptz)',
)
DEPENDENCIES = ('_replacement_metadata_json(jsonb)', '_replacement_scope(uuid,uuid,text)')
SIGNATURES = PUBLIC_SIGNATURES + PRIVATE_SIGNATURES + DEPENDENCIES
PRIVATE_NAMES = frozenset(s.split('(')[0] for s in PRIVATE_SIGNATURES)
PUBLIC_NAMES = frozenset(s.split('(')[0] for s in PUBLIC_SIGNATURES)
HASH = r'^[a-f0-9]{64}$'
ROLE = r'^[a-z][a-z0-9_]{0,62}$'


class MigrationConsumerConfigV1(StrictRecord):
    @field_validator('schema_version', mode='before')
    @classmethod
    def _exact_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError('exact schema version required')
        return value

    purpose: Literal['legacy-migration-consumer-v1']
    operation: Literal['snapshot-register', 'batch-prepare', 'batch-observe', 'read', 'reconcile', 'citation-read']
    admission_id: UUID
    principal_id: UUID
    workspace_id: UUID
    origin_system: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,127}$')
    session_role: str = Field(pattern=ROLE)
    expected_owner: str = Field(pattern=ROLE)
    runtime_sha256: str = Field(pattern=HASH)
    registry_sha256: str = Field(pattern=HASH)
    descriptor_sha256: str = Field(pattern=HASH)
    source_scope_sha256: str = Field(pattern=HASH)
    source_program_sha256: str = Field(pattern=HASH)
    intake_principal_id: UUID
    intake_config_sha256: str = Field(pattern=HASH)
    database_url: ProtectedInputV1
    database_ca: ProtectedInputV1
    capability_fingerprints: tuple[tuple[str, str, str], ...]
    public_capability_roles: tuple[tuple[str, tuple[str, ...]], ...]
    valid_from: AwareDatetime
    expires_at: AwareDatetime
    original_horizon: AwareDatetime

    @model_validator(mode='after')
    def _fixed(self):
        import re
        names = {s.split('(')[0] for s in SIGNATURES}
        if (self.intake_principal_id != self.principal_id or self.session_role == self.expected_owner or not self.valid_from < self.expires_at <= self.original_horizon
                or any(t.utcoffset() != timezone.utc.utcoffset(t) for t in (self.valid_from,self.expires_at,self.original_horizon))
                or len(self.capability_fingerprints) != len(names)
                or {x[0] for x in self.capability_fingerprints} != names
                or any(not re.fullmatch(HASH, h) for x in self.capability_fingerprints for h in x[1:])
                or len(self.public_capability_roles) != len(PUBLIC_NAMES)
                or {x[0] for x in self.public_capability_roles} != PUBLIC_NAMES
                or any(not 1 <= len(roles) <= 2 or len(set(roles)) != len(roles)
                    or any(not re.fullmatch(ROLE, r) or r == self.expected_owner for r in roles)
                    for _, roles in self.public_capability_roles)):
            raise ValueError('complete independent fixed consumer/catalog/ACL pins required')
        own = {'snapshot-register': ('register_migration_inventory_v1','current_migration_v1'),
            'batch-prepare': ('prepare_migration_batch_v1',),
            'batch-observe': ('observe_migration_intake_v1','record_migration_resolution_v1'),
            'read': ('current_migration_v1',), 'reconcile': ('reconcile_migration_command_v1',),
            'citation-read': ('resolve_migration_citation_v1',)}[self.operation]
        role_map = dict(self.public_capability_roles)
        if any(self.session_role not in role_map[name] for name in own):
            raise ValueError('fixed own purpose missing exact installed function role')
        return self


@dataclass(frozen=True)
class MigrationConsumerSettingsV1:
    config: MigrationConsumerConfigV1
    config_path: Path
    config_sha256: str

    @classmethod
    def load(cls, path, sha256):
        config = _parse(MigrationConsumerConfigV1, _pinned(path, sha256, 131072))
        result = cls(config, Path(path), sha256)
        result.current()
        return result

    def current(self):
        from oracle_brain.operating_model.request_deadline_v1 import request_remaining_v1
        request_remaining_v1(required=False)
        value = _parse(MigrationConsumerConfigV1, _pinned(self.config_path,self.config_sha256,131072))
        if value != self.config:
            raise PermissionError('independently installed migration input changed')
        now = datetime.now(timezone.utc)
        if not self.config.valid_from <= now < min(self.config.expires_at,self.config.original_horizon):
            raise PermissionError('original migration installation horizon expired')
        _pinned(self.config.database_ca.path,self.config.database_ca.sha256,131072)
        _pinned(self.config.database_url.path,self.config.database_url.sha256,16384)
        return min(self.config.expires_at,self.config.original_horizon)
