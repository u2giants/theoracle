"""Separate V2 purpose metadata; typed records never issue authority.

Only protected startup pins, an independently admitted complete-parent observer
and the actual SQL-backed resolver may authenticate these values. Gateway
projections contain no originals, requests, candidate or private locations.
Extraction V1 contracts and documentary defaults remain separate.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from .contracts import StrictRecord, digest
from .source_receipts import SourceRef

HASH = r'^[0-9a-f]{64}$'
LOGIN = r'^[a-z_][a-z0-9_]{0,62}$'
WORKER = r'^spiffe://oracle/[A-Za-z0-9/_-]+$'
PurposePhaseV2 = Literal['census', 'assembly', 'assessment', 'embedding']
PurposeV2 = Literal['source-census', 'operating-audit', 'independent-source-semantic-acceptance', 'source-extraction']
PurposeOperationV2 = Literal['chat', 'embedding']
PHASE_CONTRACTS = {
    'census': ('source-census', 'chat', 'openai/gpt-6.1-sol'),
    'assembly': ('operating-audit', 'chat', 'openai/gpt-6.1-sol'),
    'assessment': ('independent-source-semantic-acceptance', 'chat', 'openai/gpt-6-astra'),
    'embedding': ('source-extraction', 'embedding', 'openai/text-embedding-3-small'),
}


def source_population_digest(refs):
    """Exact ordered source identity only, never an appointment or observer."""
    return digest({'source_refs': [ref.model_dump(mode='json') for ref in refs]})


def _population(workspace, refs, expected):
    import re
    if (not refs or len(set(refs)) != len(refs)
            or len({ref.source_id for ref in refs}) != len(refs)
            or any(ref.workspace_id != workspace or not re.fullmatch(HASH, ref.parser_id) for ref in refs)
            or source_population_digest(refs) != expected):
        raise ValueError('exact ordered complete purpose source population required')


def _phase(phase, purpose, operation):
    if PHASE_CONTRACTS[phase][:2] != (purpose, operation):
        raise ValueError('fixed V2 phase purpose and operation differ')


class ParentPopulationAdmissionV2(StrictRecord):
    """Externally pinned observer output; loaders never issue this authority."""
    schema_version: Literal[2] = 2
    workspace_id: UUID
    parent_registry_sha256: str = Field(pattern=HASH)
    runtime_hash: str = Field(pattern=HASH)
    source_registry_hash: str = Field(pattern=HASH)
    source_refs: tuple[SourceRef, ...] = Field(min_length=1)
    population_digest: str = Field(pattern=HASH)
    issuer_actor: UUID
    reviewer_actor: UUID
    expires_at: AwareDatetime

    @model_validator(mode='after')
    def exact_population(self):
        _population(self.workspace_id, self.source_refs, self.population_digest)
        if self.issuer_actor == self.reviewer_actor:
            raise ValueError('independent complete-parent issuance required')
        return self


class PurposeDispatchV2(StrictRecord):
    schema_version: Literal[2] = 2
    dispatch_id: UUID
    source_refs: tuple[SourceRef, ...] = Field(min_length=1)
    job_hash: str = Field(pattern=HASH)
    request_hash: str = Field(pattern=HASH)
    permission_hash: str = Field(pattern=HASH)
    context_hash: str = Field(pattern=HASH)
    model: Literal['openai/gpt-6.1-sol', 'openai/gpt-6-astra', 'openai/text-embedding-3-small']
    processing_request_hash: str = Field(pattern=HASH)
    account_policy_hash: str = Field(pattern=HASH)
    terms_hash: str = Field(pattern=HASH)
    pricing_hash: str = Field(pattern=HASH)
    register_hash: str = Field(pattern=HASH)
    approvals_hash: str = Field(pattern=HASH)
    budget_identity_hash: str = Field(pattern=HASH)
    ledger_registry_hash: str = Field(pattern=HASH)
    key_coverage_hash: str = Field(pattern=HASH)


class PurposeRunDescriptorV2(StrictRecord):
    schema_version: Literal[2] = 2
    run_id: UUID
    workspace_id: UUID
    actor_id: UUID
    provider_login: str = Field(pattern=LOGIN)
    worker_uri: str = Field(pattern=WORKER)
    phase: PurposePhaseV2
    purpose: PurposeV2
    operation: PurposeOperationV2
    runtime_hash: str = Field(pattern=HASH)
    source_registry_hash: str = Field(pattern=HASH)
    parent_registry_sha256: str = Field(pattern=HASH)
    population_admission_sha256: str = Field(pattern=HASH)
    phase_registry_sha256: str = Field(pattern=HASH)
    population_digest: str = Field(pattern=HASH)
    source_refs: tuple[SourceRef, ...] = Field(min_length=1)
    dispatches: tuple[PurposeDispatchV2, ...] = Field(min_length=1)
    issuer_actor: UUID
    reviewer_actor: UUID
    expires_at: AwareDatetime

    @model_validator(mode='after')
    def exact_population(self):
        _phase(self.phase, self.purpose, self.operation)
        _population(self.workspace_id, self.source_refs, self.population_digest)
        if (self.issuer_actor == self.reviewer_actor
                or self.actor_id in {self.issuer_actor, self.reviewer_actor}
                or len({item.dispatch_id for item in self.dispatches}) != len(self.dispatches)
                or any(item.source_refs != self.source_refs
                       or item.model != PHASE_CONTRACTS[self.phase][2] for item in self.dispatches)):
            raise ValueError('independent exact full-population purpose dispatches required')
        return self

    def dispatch(self, dispatch_id):
        matches = [item for item in self.dispatches if item.dispatch_id == dispatch_id]
        if not isinstance(dispatch_id, UUID) or len(matches) != 1:
            raise PermissionError('unique exact purpose dispatch required')
        return matches[0]


class PurposeMetadataProjectionV2(StrictRecord):
    schema_version: Literal[2] = 2
    descriptor: PurposeRunDescriptorV2
    descriptor_sha256: str = Field(pattern=HASH)

    @model_validator(mode='after')
    def exact_descriptor(self):
        if digest(self.descriptor.model_dump(mode='json')) != self.descriptor_sha256:
            raise ValueError('purpose metadata descriptor seal differs')
        return self


class PurposeAuthorityProofV2(StrictRecord):
    """SQL adapter output only; fields/type cannot authenticate their own origin."""
    schema_version: Literal[2] = 2
    run_id: UUID
    workspace_id: UUID
    actor_id: UUID
    admitted_provider_login: str = Field(pattern=LOGIN)
    actual_caller_login: str = Field(pattern=LOGIN)
    dispatch_id: UUID
    phase: PurposePhaseV2
    purpose: PurposeV2
    operation: PurposeOperationV2
    source_refs: tuple[SourceRef, ...] = Field(min_length=1)
    population_digest: str = Field(pattern=HASH)
    runtime_hash: str = Field(pattern=HASH)
    source_registry_hash: str = Field(pattern=HASH)
    descriptor_sha256: str = Field(pattern=HASH)
    parent_registry_sha256: str = Field(pattern=HASH)
    population_admission_sha256: str = Field(pattern=HASH)
    phase_registry_sha256: str = Field(pattern=HASH)
    projection_sha256: str = Field(pattern=HASH)
    dispatch_hash: str = Field(pattern=HASH)
    job_hash: str = Field(pattern=HASH)
    request_hash: str = Field(pattern=HASH)
    permission_hash: str = Field(pattern=HASH)
    session_role: str = Field(pattern=LOGIN)
    profile: Literal['source-reader', 'gateway-metadata']
    checked_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode='after')
    def bounded_current_shape(self):
        _phase(self.phase, self.purpose, self.operation)
        _population(self.workspace_id, self.source_refs, self.population_digest)
        if self.expires_at <= self.checked_at:
            raise ValueError('finite purpose proof horizon must follow actual check')
        if self.phase == 'embedding' and self.profile != 'gateway-metadata':
            raise ValueError('embedding proof requires metadata-only capability')
        if ((self.profile == 'source-reader' or self.phase == 'embedding')
                and self.actual_caller_login != self.admitted_provider_login):
            raise ValueError('actual provider login differs from admitted provider')
        if self.session_role not in {self.actual_caller_login, 'oracle2_'+self.profile.replace('-', '_')}:
            raise ValueError('purpose proof actual caller role differs')
        return self


def verify_purpose_authority_proof_v2(proof, descriptor, dispatch, *,
        projection_sha256, actual_caller_login, profile, now):
    """Consistency/freshness only, AFTER the trusted SQL adapter's real hold.

    Never deserialize a proof from HTTP or substitute this check for SQL origin,
    current complete-parent observation, provider policy or dispatch admission.
    """
    from datetime import timedelta
    if (type(proof) is not PurposeAuthorityProofV2
            or type(descriptor) is not PurposeRunDescriptorV2
            or type(dispatch) is not PurposeDispatchV2
            or not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None):
        raise PermissionError('actual typed current SQL purpose proof required')
    projection = PurposeMetadataProjectionV2(descriptor=descriptor,
        descriptor_sha256=digest(descriptor.model_dump(mode='json')))
    expected = dict(run_id=descriptor.run_id, workspace_id=descriptor.workspace_id,
        actor_id=descriptor.actor_id, admitted_provider_login=descriptor.provider_login,
        dispatch_id=dispatch.dispatch_id, phase=descriptor.phase, purpose=descriptor.purpose,
        operation=descriptor.operation, source_refs=descriptor.source_refs,
        population_digest=descriptor.population_digest, runtime_hash=descriptor.runtime_hash,
        source_registry_hash=descriptor.source_registry_hash,
        descriptor_sha256=digest(descriptor.model_dump(mode='json')),
        parent_registry_sha256=descriptor.parent_registry_sha256,
        population_admission_sha256=descriptor.population_admission_sha256,
        phase_registry_sha256=descriptor.phase_registry_sha256,
        projection_sha256=projection_sha256, dispatch_hash=digest(dispatch.model_dump(mode='json')),
        job_hash=dispatch.job_hash, request_hash=dispatch.request_hash,
        permission_hash=dispatch.permission_hash, actual_caller_login=actual_caller_login,
        profile=profile)
    if (descriptor.dispatch(dispatch.dispatch_id) != dispatch
            or digest(projection.model_dump(mode='json')) != projection_sha256
            or any(getattr(proof, key) != value for key, value in expected.items())
            or not proof.checked_at <= now < min(proof.expires_at, descriptor.expires_at)
            or now-proof.checked_at > timedelta(seconds=5)
            or proof.expires_at > descriptor.expires_at):
        raise PermissionError('current SQL purpose proof differs from sealed dispatch')
    return None
