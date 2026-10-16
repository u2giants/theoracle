"""Extraction-only metadata contracts; values alone never confer authority.

Only a separately reviewed issuer may qualify sources and seal the provider-side
inputs. Gateway projections contain identifiers and hashes, never originals.
Multi-source synthesis is not representable by the existing parent job schema.
"""
from datetime import datetime
from decimal import Decimal
import re
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from .contracts import StrictRecord, digest
from .source_receipts import SourceRef

HASH = r'^[a-f0-9]{64}$'
WORKER = r'^spiffe://oracle/[A-Za-z0-9/_-]+$'


class QualifiedProcessingSources(StrictRecord):
    """Externally sealed issuance input, not a source-admission implementation."""
    workspace_id: UUID
    actor_id: UUID
    runtime_hash: str = Field(pattern=HASH)
    source_registry_hash: str = Field(pattern=HASH)
    expected_owner_role: str = Field(pattern=r'^[a-z_][a-z0-9_]{0,62}$')
    source_refs: tuple[SourceRef, ...] = Field(min_length=1)
    issuer_actor: UUID
    reviewer_actor: UUID
    expires_at: AwareDatetime


class ProcessingEnvelope(StrictRecord):
    """Version 1 supplements, and never changes, the protected JobRegistry."""
    run_id: UUID
    worker_uri: str = Field(pattern=WORKER)
    runtime_hash: str = Field(pattern=HASH)
    source_registry_hash: str = Field(pattern=HASH)
    parent_registry_sha256: str = Field(pattern=HASH)
    ledger_registry_hash: str = Field(pattern=HASH)
    key_coverage_hash: str = Field(pattern=HASH)
    budget_allocation_hash: str = Field(pattern=HASH)
    budget_receipt_hash: str = Field(pattern=HASH)
    budget_ceiling_usd: Decimal = Field(gt=0, allow_inf_nan=False)
    budget_expires_at: AwareDatetime
    dispatch_ids: tuple[UUID, ...] = Field(min_length=1)
    source_refs: tuple[SourceRef, ...] = Field(min_length=1)
    issuer_actor: UUID
    reviewer_actor: UUID
    expires_at: AwareDatetime


class ProcessingPins(StrictRecord):
    """Trusted startup fields must come from an external reviewed descriptor."""
    runtime_hash: str = Field(pattern=HASH)
    worker_uri: str = Field(pattern=WORKER)
    source_registry_hash: str = Field(pattern=HASH)
    expected_owner_role: str = Field(pattern=r'^[a-z_][a-z0-9_]{0,62}$')
    parent_registry_sha256: str = Field(pattern=HASH)
    envelope_sha256: str = Field(pattern=HASH)
    qualification_sha256: str = Field(pattern=HASH)
    descriptor_sha256: str = Field(pattern=HASH)
    projection_sha256: str = Field(pattern=HASH)
    ledger_registry_hash: str = Field(pattern=HASH)
    key_coverage_hash: str = Field(pattern=HASH)


class ProcessingDispatch(StrictRecord):
    dispatch_id: UUID
    source_ref: SourceRef
    job_hash: str = Field(pattern=HASH)
    request_hash: str = Field(pattern=HASH)
    permission_hash: str = Field(pattern=HASH)
    model: Literal['openai/gpt-6.1-sol', 'openai/gpt-6-astra']
    processing_request_hash: str = Field(pattern=HASH)
    account_policy_hash: str = Field(pattern=HASH)
    terms_hash: str = Field(pattern=HASH)
    pricing_hash: str = Field(pattern=HASH)
    register_hash: str = Field(pattern=HASH)
    budget_identity_hash: str = Field(pattern=HASH)


class ProcessingRunDescriptor(StrictRecord):
    run_id: UUID
    workspace_id: UUID
    actor_id: UUID
    worker_uri: str = Field(pattern=WORKER)
    runtime_hash: str = Field(pattern=HASH)
    source_registry_hash: str = Field(pattern=HASH)
    parent_registry_sha256: str = Field(pattern=HASH)
    envelope_sha256: str = Field(pattern=HASH)
    ledger_registry_hash: str = Field(pattern=HASH)
    key_coverage_hash: str = Field(pattern=HASH)
    purpose: Literal['source-extraction'] = 'source-extraction'
    source_refs: tuple[SourceRef, ...] = Field(min_length=1)
    dispatches: tuple[ProcessingDispatch, ...] = Field(min_length=1)
    issuer_actor: UUID
    reviewer_actor: UUID
    expires_at: AwareDatetime

    @model_validator(mode='after')
    def exact_population(self):
        refs = self.source_refs
        if (self.issuer_actor == self.reviewer_actor
                or len(set(refs)) != len(refs)
                or len({r.source_id for r in refs}) != len(refs)
                or any(r.workspace_id != self.workspace_id or not re.fullmatch(HASH, r.parser_id) for r in refs)
                or len({d.dispatch_id for d in self.dispatches}) != len(self.dispatches)
                or set(d.source_ref for d in self.dispatches) != set(refs)):
            raise ValueError('independent exact extraction population required')
        return self


class ProcessingProjection(StrictRecord):
    """Separate metadata-only schema; no arbitrary dict or raw-string fields."""
    descriptor: ProcessingRunDescriptor
    descriptor_sha256: str = Field(pattern=HASH)

    @model_validator(mode='after')
    def seal(self):
        if digest(self.descriptor.model_dump(mode='json')) != self.descriptor_sha256:
            raise ValueError('processing descriptor seal mismatch')
        return self


def derive_processing_descriptor(registry, envelope, qualification, *, pins, now: datetime):
    """Issuer-side pure derivation; runtime loader must verify external byte pins.

    The parent registry is validated by the unchanged CurrentJobs implementation.
    Source qualification here is externally sealed input; SQL/dual-grant live
    checks remain mandatory and are not implemented or issued by this function.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('aware actual clock required')
    contexts = registry.contexts
    refs = tuple(dict.fromkeys(ctx.receipt.ref for ctx in contexts))
    actors = {ctx.actor_id for ctx in contexts}
    workspaces = {ctx.job.workspace_id for ctx in contexts}
    if (len(actors) != 1 or len(workspaces) != 1
            or qualification.actor_id not in actors or qualification.workspace_id not in workspaces
            or len(envelope.dispatch_ids) != len(contexts)
            or set(envelope.dispatch_ids) != {ctx.job.dispatch_id for ctx in contexts}
            or len(envelope.source_refs) != len(refs) or set(envelope.source_refs) != set(refs)
            or len(qualification.source_refs) != len(refs) or set(qualification.source_refs) != set(refs)
            or len({r.source_id for r in refs}) != len(refs)):
        raise PermissionError('exact qualified actor, source and dispatch population required')
    if (not now < envelope.expires_at <= min(registry.expires_at, qualification.expires_at, envelope.budget_expires_at)
            or any(value != pins.runtime_hash for value in (registry.runtime_hash, envelope.runtime_hash, qualification.runtime_hash))
            or any(value != pins.source_registry_hash for value in (envelope.source_registry_hash, qualification.source_registry_hash))
            or qualification.expected_owner_role != pins.expected_owner_role
            or envelope.worker_uri != pins.worker_uri
            or envelope.parent_registry_sha256 != pins.parent_registry_sha256
            or envelope.ledger_registry_hash != pins.ledger_registry_hash
            or envelope.key_coverage_hash != pins.key_coverage_hash
            or registry.issuer_actor == registry.reviewer_actor
            or (envelope.issuer_actor, envelope.reviewer_actor) != (registry.issuer_actor, registry.reviewer_actor)
            or (qualification.issuer_actor, qualification.reviewer_actor) != (registry.issuer_actor, registry.reviewer_actor)):
        raise PermissionError('current independent externally pinned processing admission required')
    budget_hash = digest({key: envelope.model_dump(mode='json')[key] for key in (
        'ledger_registry_hash', 'key_coverage_hash', 'budget_allocation_hash',
        'budget_receipt_hash', 'budget_ceiling_usd', 'budget_expires_at')})
    dispatches = []
    from oracle_brain.provider_policy import authorize
    from .pipeline import extraction_messages
    for ctx in contexts:
        job = ctx.job
        request = job.processing_request
        if (job.purpose != 'source-extraction' or request.purpose != 'source-extraction'
                or job.request.get('messages') != extraction_messages(ctx.receipt)
                or set(job.request) != {'model','messages','max_tokens','response_format','store','stream','provider'}
                or job.request_hash != digest(job.request)
                or ctx.job_hash != digest(job.model_dump(mode='json'))
                or job.permission_hash != ctx.permission_hash
                or job.pricing.model != job.request.get('model')
                or job.pricing.provider != request.provider
                or job.pricing.admitted_register_hash != job.register_hash
                or not now < envelope.expires_at <= job.pricing.expires_at):
            raise PermissionError('exact source-only job, model, request and pricing required')
        approval = authorize(request, list(job.approvals), now=now)
        if envelope.expires_at > approval.expires_at:
            raise PermissionError('processing descriptor outlives provider approval')
        source_ids = {r.source_id for r in refs}
        if any(UUID(alias) not in source_ids for alias in ctx.receipt.aliases):
            raise PermissionError('permission-relevant source alias omitted')
        policy = request.model_dump(mode='json')
        dispatches.append(ProcessingDispatch(
            dispatch_id=job.dispatch_id, source_ref=ctx.receipt.ref, job_hash=ctx.job_hash,
            request_hash=job.request_hash, permission_hash=ctx.permission_hash,
            model=job.request['model'], processing_request_hash=digest(policy),
            account_policy_hash=digest({k: v for k, v in policy.items() if k != 'terms_hash'}),
            terms_hash=request.terms_hash, pricing_hash=digest(job.pricing.model_dump(mode='json')),
            register_hash=job.register_hash, budget_identity_hash=budget_hash))
    return ProcessingRunDescriptor(
        run_id=envelope.run_id, workspace_id=qualification.workspace_id, actor_id=qualification.actor_id,
        worker_uri=envelope.worker_uri, runtime_hash=envelope.runtime_hash,
        source_registry_hash=envelope.source_registry_hash, parent_registry_sha256=envelope.parent_registry_sha256,
        envelope_sha256=pins.envelope_sha256,
        ledger_registry_hash=envelope.ledger_registry_hash, key_coverage_hash=envelope.key_coverage_hash,
        source_refs=tuple(sorted(refs, key=lambda r: r.source_id.int)),
        dispatches=tuple(sorted(dispatches, key=lambda d: d.dispatch_id.int)),
        issuer_actor=envelope.issuer_actor, reviewer_actor=envelope.reviewer_actor, expires_at=envelope.expires_at)


class ProcessingAuthorityProof(StrictRecord):
    """Return type for an actual trusted SQL-backed hold; never HTTP input.

    Constructing this record proves no authority. The configured SQL adapter
    must derive all values from its actual bound session and checked minima.
    """
    workspace_id: UUID
    actor_id: UUID
    source_ref: SourceRef
    runtime_hash: str = Field(pattern=HASH)
    source_registry_hash: str = Field(pattern=HASH)
    descriptor_sha256: str = Field(pattern=HASH)
    parent_registry_sha256: str = Field(pattern=HASH)
    envelope_sha256: str = Field(pattern=HASH)
    purpose: Literal['source-extraction'] = 'source-extraction'
    session_role: str = Field(pattern=r'^[a-z_][a-z0-9_]{0,62}$')
    profile: Literal['source-reader', 'candidate-compiler', 'gateway-metadata']
    checked_at: AwareDatetime
    expires_at: AwareDatetime
