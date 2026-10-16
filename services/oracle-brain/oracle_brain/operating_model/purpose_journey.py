"""Pure purpose-worker job contract; infrastructure belongs in hosting."""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, Field, model_validator
from .contracts import StrictRecord, SourceRef
HASH = r'^[0-9a-f]{64}$'
PHASES = ('census','extraction','assembly','assessment','compile')

def _require(value,message):
    if not value: raise PermissionError(message)


class PurposeWorkerJobV2(StrictRecord):
    schema_version: Literal[2] = 2
    purpose: Literal['replacement-documentary-journey-v2'] = 'replacement-documentary-journey-v2'
    job_id: UUID
    journey_id: UUID
    workspace_id: UUID
    actor_id: UUID
    operation: Literal['dispatch','consume']='dispatch'
    consume_of_job_id: UUID|None=None
    resume_journal_hash: str|None=Field(default=None,pattern=HASH)
    phase: Literal['census', 'extraction', 'assembly', 'assessment', 'compile']
    source_refs: tuple[SourceRef, ...]
    source_id: UUID | None = None
    allocation_hash: str = Field(pattern=HASH)
    parent_journal_hash: str | None = Field(default=None, pattern=HASH)
    prior_receipt_hash: str | None = Field(default=None, pattern=HASH)
    nonce: str = Field(pattern=r'^[0-9a-f]{32}$')
    runtime_hash: str = Field(pattern=HASH)
    admission_hash: str = Field(pattern=HASH)
    dispatch_id: UUID | None = None
    request_hash: str | None = Field(default=None, pattern=HASH)
    phase_registry_sha256: str | None = Field(default=None, pattern=HASH)
    expires_at: AwareDatetime
    original_horizon: AwareDatetime

    @model_validator(mode='after')
    def exact_population_and_phase(self):
        _require((self.operation=='consume')==(self.consume_of_job_id is not None and self.resume_journal_hash is not None)
            and (self.operation=='consume' or (self.consume_of_job_id is None and self.resume_journal_hash is None))
            and self.consume_of_job_id!=self.job_id,'explicit exact externally admitted consume target required')
        _require(3 <= len(self.source_refs) <= 4096
                 and len({r.source_id for r in self.source_refs}) == len(self.source_refs)
                 and all(r.workspace_id == self.workspace_id for r in self.source_refs),
                 'complete distinct three-plus original population required')
        _require(self.expires_at <= self.original_horizon, 'phase cannot extend original allocation horizon')
        _require((self.phase == 'extraction') == (self.source_id is not None)
                 and (self.source_id is None or self.source_id in {r.source_id for r in self.source_refs}),
                 'exact extraction source key required')
        _require((self.phase == 'census') == (self.parent_journal_hash is None and self.prior_receipt_hash is None),
                 'only initial census has no predecessor')
        if self.phase != 'census':
            _require(self.parent_journal_hash is not None and self.prior_receipt_hash is not None,
                     'exact already committed predecessor required')
        provider_fields = (self.dispatch_id, self.request_hash, self.phase_registry_sha256)
        _require(all(v is None for v in provider_fields) if self.phase == 'compile'
                 else all(v is not None for v in provider_fields), 'fixed phase dispatch metadata required')
        return self

    @property
    def phase_key(self):
        return self.phase + (':' + str(self.source_id) if self.source_id else '')

