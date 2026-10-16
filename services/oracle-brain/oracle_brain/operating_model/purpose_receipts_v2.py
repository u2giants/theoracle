"""Observed authorized phase-commit metadata, never an admission or signer."""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime,Field,model_validator
from .contracts import StrictRecord
from .purpose_context import HASH,LOGIN,PHASE_CONTRACTS,source_population_digest
from .source_receipts import SourceRef


class PhaseResponseCommitV2(StrictRecord):
    schema_version: Literal[2]=2
    purpose: Literal['observed-authorized-phase-commit-v2']='observed-authorized-phase-commit-v2'
    time_basis: Literal['local-source-guarded-response-commit-v2']='local-source-guarded-response-commit-v2'
    phase: Literal['census','extraction','assembly','assessment','embedding']
    operation: Literal['chat','embedding']
    processing_purpose: str
    dispatch_id: UUID
    workspace_id: UUID
    actor_id: UUID
    provider_login: str=Field(pattern=LOGIN)
    actual_caller_login: str=Field(pattern=LOGIN)
    runtime_hash: str=Field(pattern=HASH)
    descriptor_hash: str=Field(pattern=HASH)
    operation_approval_hash: str=Field(pattern=HASH)
    population_digest: str=Field(pattern=HASH)
    source_refs: tuple[SourceRef,...]=Field(min_length=1)
    context_hash: str=Field(pattern=HASH)
    parent_registry_hash: str=Field(pattern=HASH)
    current_proof_hash: str=Field(pattern=HASH)
    parent_witness_hash: str=Field(pattern=HASH)
    account_policy_hash: str=Field(pattern=HASH)
    model: str
    valid_until: AwareDatetime
    job_hash: str=Field(pattern=HASH)
    request_hash: str=Field(pattern=HASH)
    permission_hash: str=Field(pattern=HASH)
    budget_identity_hash: str=Field(pattern=HASH)
    raw_response_hash: str=Field(pattern=HASH)
    native_custody_receipt_hash: str=Field(pattern=HASH)
    committed_at: AwareDatetime

    @model_validator(mode='after')
    def fixed_observation(self):
        purpose,operation=('source-extraction','chat') if self.phase=='extraction' else PHASE_CONTRACTS[self.phase][:2]
        if (self.processing_purpose!=purpose or self.operation!=operation
                or self.provider_login!=self.actual_caller_login
                or self.committed_at>=self.valid_until
                or self.model!=('openai/gpt-6.1-sol' if self.phase=='extraction' else PHASE_CONTRACTS[self.phase][2])
                or self.population_digest!=source_population_digest(self.source_refs)
                or any(r.workspace_id!=self.workspace_id for r in self.source_refs)
                or len({r.source_id for r in self.source_refs})!=len(self.source_refs)):
            raise PermissionError('exact own-provider observed phase commit required')
        return self
