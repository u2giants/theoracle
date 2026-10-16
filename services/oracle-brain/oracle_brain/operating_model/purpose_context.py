"""Separate V2 purpose metadata; typed records never issue authority.

Only protected startup pins, an independently admitted complete-parent observer
and the actual SQL-backed resolver may authenticate these values. Gateway
projections contain no originals, requests, candidate or private locations.
Extraction V1 contracts and documentary defaults remain separate.
"""
from datetime import datetime
from decimal import Decimal
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


class PurposePhaseRegistryV2(StrictRecord):
    """Private independently qualified phase receipt, not an issuer or permission.

    The protected external byte pin authenticates its reviewed operation meaning.
    Metadata projection contains only its digest, never these private jobs.
    """
    schema_version: Literal[2] = 2
    qualification_purpose: Literal['phase-operation-qualification-v2']
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
    source_refs: tuple[SourceRef, ...] = Field(min_length=1)
    population_digest: str = Field(pattern=HASH)
    dispatches: tuple[PurposeDispatchV2, ...] = Field(min_length=1)
    issuer_actor: UUID
    reviewer_actor: UUID
    expires_at: AwareDatetime

    @model_validator(mode='after')
    def qualified_operation(self):
        _phase(self.phase, self.purpose, self.operation)
        _population(self.workspace_id, self.source_refs, self.population_digest)
        if len({self.actor_id, self.issuer_actor, self.reviewer_actor}) != 3:
            raise ValueError('independent operation qualification required')
        if len({d.dispatch_id for d in self.dispatches}) != len(self.dispatches):
            raise ValueError('duplicate phase dispatch')
        for dispatch in self.dispatches:
            if (dispatch.source_refs != self.source_refs
                    or dispatch.model != PHASE_CONTRACTS[self.phase][2]):
                raise ValueError('qualified operation model or complete population differs')
        return self


class PurposePinsV2(StrictRecord):
    """Protected startup authority supplied externally; never HTTP or self-issued."""
    schema_version: Literal[2] = 2
    qualification_purpose: Literal['phase-operation-qualification-v2']
    phase: PurposePhaseV2
    operation: PurposeOperationV2
    runtime_hash: str = Field(pattern=HASH)
    source_registry_hash: str = Field(pattern=HASH)
    parent_registry_sha256: str = Field(pattern=HASH)
    population_admission_sha256: str = Field(pattern=HASH)
    phase_registry_sha256: str = Field(pattern=HASH)
    budget_allocation_projection_sha256: str = Field(pattern=HASH)
    descriptor_sha256: str = Field(pattern=HASH)
    projection_sha256: str = Field(pattern=HASH)
    provider_login: str = Field(pattern=LOGIN)
    worker_uri: str = Field(pattern=WORKER)
    issuer_actor: UUID
    reviewer_actor: UUID
    expires_at: AwareDatetime

    @model_validator(mode='after')
    def fixed_qualification(self):
        if (PHASE_CONTRACTS[self.phase][1] != self.operation
                or self.issuer_actor == self.reviewer_actor):
            raise ValueError('exact independently qualified startup operation required')
        return self

    @property
    def operation_approval_hash(self):
        # No extra body hash can manufacture a second operation appointment.
        return self.phase_registry_sha256


def derive_purpose_descriptor_v2(registry, population, *, pins, phase_registry_bytes_hash, now):
    """Pure sealed qualification consistency, after trusted observer/SQL admission.

    Does not read parent bytes, authorize SQL, appoint issuers or reserve budget.
    The caller must authenticate current observer output and external pins.
    """
    if (type(registry) is not PurposePhaseRegistryV2
            or type(population) is not ParentPopulationAdmissionV2
            or type(pins) is not PurposePinsV2):
        raise PermissionError('exact separate V2 startup and operation qualification required')
    if now.tzinfo is None or now.utcoffset() is None:
        raise PermissionError('aware current qualification clock required')
    # Mutable nested models must be revalidated on every use, not trusted by type.
    registry = PurposePhaseRegistryV2.model_validate(registry.model_dump(mode='python'))
    population = ParentPopulationAdmissionV2.model_validate(population.model_dump(mode='python'))
    pins = PurposePinsV2.model_validate(pins.model_dump(mode='python'))
    if (phase_registry_bytes_hash != pins.phase_registry_sha256
            or digest(population.model_dump(mode='json')) != pins.population_admission_sha256
            or registry.population_admission_sha256 != pins.population_admission_sha256
            or registry.phase != pins.phase or registry.operation != pins.operation
            or registry.runtime_hash != pins.runtime_hash or population.runtime_hash != pins.runtime_hash
            or registry.source_registry_hash != pins.source_registry_hash
            or population.source_registry_hash != pins.source_registry_hash
            or registry.parent_registry_sha256 != pins.parent_registry_sha256
            or population.parent_registry_sha256 != pins.parent_registry_sha256
            or registry.source_refs != population.source_refs
            or registry.population_digest != population.population_digest
            or registry.workspace_id != population.workspace_id
            or any(j.budget_identity_hash!=pins.budget_allocation_projection_sha256 for j in registry.dispatches)
            or registry.provider_login != pins.provider_login or registry.worker_uri != pins.worker_uri
            or registry.issuer_actor != pins.issuer_actor or registry.reviewer_actor != pins.reviewer_actor
            or registry.expires_at > min(population.expires_at, pins.expires_at)
            or now >= min(registry.expires_at, population.expires_at, pins.expires_at)):
        raise PermissionError('current externally qualified complete phase population required')
    values = registry.model_dump(mode='python')
    values.pop('qualification_purpose')
    values['phase_registry_sha256'] = phase_registry_bytes_hash
    descriptor = PurposeRunDescriptorV2.model_validate(values)
    projection = PurposeMetadataProjectionV2(descriptor=descriptor,
        descriptor_sha256=digest(descriptor.model_dump(mode='json')))
    if (projection.descriptor_sha256 != pins.descriptor_sha256
            or digest(projection.model_dump(mode='json')) != pins.projection_sha256):
        raise PermissionError('qualified descriptor/projection differs from external startup seal')
    return descriptor


class BudgetAllocationPinsV2(StrictRecord):
    """Externally qualified metadata projection of the SAME original allocation.

    Its digest identifies this projection, not original raw receipt bytes. The
    external startup appointment must authenticate origin/meaning; construction
    does not renew an allocation or reserve any amount.
    """
    schema_version: Literal[2]=2
    purpose: Literal['existing-allocation-projection-v2']='existing-allocation-projection-v2'
    original_batch_id: UUID
    allocation_hash: str=Field(pattern=HASH)
    original_receipt_hash: str=Field(pattern=HASH)
    original_ceiling_usd: Decimal=Field(gt=0,allow_inf_nan=False)
    original_expires_at: AwareDatetime
    ledger_registry_hash: str=Field(pattern=HASH)
    key_coverage_hash: str=Field(pattern=HASH)
    account_policy_hash: str=Field(pattern=HASH)

    def verify_current(self,*,trusted_projection_hash,dispatches,now):
        if (digest(self.model_dump(mode='json'))!=trusted_projection_hash
                or now.tzinfo is None or now.utcoffset() is None or now>=self.original_expires_at
                or any(j.budget_identity_hash!=trusted_projection_hash
                    or j.ledger_registry_hash!=self.ledger_registry_hash
                    or j.key_coverage_hash!=self.key_coverage_hash
                    or j.account_policy_hash!=self.account_policy_hash for j in dispatches)):
            raise PermissionError('current exact externally qualified original allocation projection required')
