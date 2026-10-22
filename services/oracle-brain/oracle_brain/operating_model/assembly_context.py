"""Versioned model-only assembly contract. Types and hashes never issue authority.

The trusted compiler must read current originals and sealed extraction artifacts
before constructing this context. No provider, grant, reservation or store write
occurs here. Extraction-only JobContext/CurrentJobs defaults remain unchanged.
"""
from datetime import datetime
import json
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from .contracts import ArtifactManifest, StrictRecord, digest
from .model import BusinessOperatingModel
from .native_factory import NativeDispatchJob
from .pipeline import assembly_inputs, assembly_candidate_payload
from .semantic_acceptance import FrozenCensus, sealed
from .source_receipts import SourceReceipt


class SealedAssemblyExtraction(StrictRecord):
    manifest: ArtifactManifest
    payload: dict

    @model_validator(mode='after')
    def exact_bytes(self):
        if self.manifest.kind not in {'extraction', 'processing_extraction_v1'} or self.manifest.state != 'ready':
            raise PermissionError('assembly requires ready extraction artifacts')
        if digest(self.payload) != self.manifest.content_hash:
            raise PermissionError('extraction bytes differ from immutable content seal')
        refs, _, _ = assembly_inputs((self.payload,))
        if len(refs) != 1 or refs[0].workspace_id != self.manifest.workspace_id:
            raise PermissionError('extraction must bind one exact workspace source')
        if digest({'refs': [r.model_dump(mode='json') for r in refs]}) != self.manifest.source_digest:
            raise PermissionError('extraction source seal differs')
        return self


def assembly_messages(*, receipts, extractions, census, model_id, version, candidate_contract=None):
    """Exact full-source + immutable observation request; response is model only."""
    if candidate_contract is None:schema=BusinessOperatingModel.model_json_schema()
    elif candidate_contract=='qualified-consolidation-core-v1':
        from .consolidation_contracts_v1 import ConsolidationCoreV1
        schema=ConsolidationCoreV1.model_json_schema()
    else:raise PermissionError('unknown assembly response contract')
    response_name='BusinessOperatingModel' if candidate_contract is None else 'ConsolidationCoreV1'
    return [
        {'role': 'system', 'content': 'Assemble the complete documentary operating model across all supplied originals and immutable extractions. Preserve conflicts and missing knowledge. Reuse actual observation and finding identities with exact support. Workflows remain reported; never confer company policy. Return only this '+response_name+' JSON schema, without coverage or assessment: ' + json.dumps(schema, sort_keys=True)},
        {'role': 'user', 'content': json.dumps({
            'model_id': str(model_id), 'version': version,
            'originals': [{'source_ref': r.ref.model_dump(mode='json'), 'reading': r.reading} for r in receipts],
            'extractions': [{'manifest_hash': sealed(e.manifest), 'content_hash': e.manifest.content_hash,
                'observations': e.payload.get('observations', []), 'findings': e.payload.get('findings', [])} for e in extractions],
            'frozen_census_hash': sealed(census),
            'obligations': [o.model_dump(mode='json') for o in census.obligations],
        }, ensure_ascii=False, allow_nan=False)},
    ]


class AssemblyJobContext(StrictRecord):
    """Provider-side input only; never exposed through the metadata gateway."""
    actor_id: UUID
    runtime_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_registry_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    compiler_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    parent_registry_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    envelope_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    job: NativeDispatchJob
    receipts: tuple[SourceReceipt, ...] = Field(min_length=2)
    extractions: tuple[SealedAssemblyExtraction, ...] = Field(min_length=2)
    census: FrozenCensus
    reviewed_inventories: dict
    model_id: UUID
    model_version: int = Field(strict=True, ge=1)
    issuer_actor: UUID
    reviewer_actor: UUID
    expires_at: AwareDatetime

    @model_validator(mode='after')
    def exact_population(self):
        if self.issuer_actor == self.reviewer_actor:
            raise PermissionError('independent assembly context qualification required')
        if self.job.purpose != 'operating-audit' or self.job.artifact_id != self.model_id:
            raise PermissionError('assembly requires its own operating-audit model dispatch')
        if (self.job.processing_request.purpose != 'operating-audit'
                or set(self.job.request) != {'model','messages','max_tokens','response_format','store','stream','provider'}
                or self.job.pricing.model != self.job.request.get('model')
                or self.job.pricing.provider != self.job.processing_request.provider
                or self.job.pricing.admitted_register_hash != self.job.register_hash):
            raise PermissionError('exact assembly request, purpose and pricing required')
        if self.job.pricing.model != 'openai/gpt-6.1-sol':
            raise PermissionError('assembly generator model differs from admitted semantic protocol')
        if self.census.workspace_id != self.job.workspace_id:
            raise PermissionError('cross-workspace assembly census')
        refs = tuple(r.ref for r in self.receipts)
        if len(set(refs)) != len(refs) or any(r.workspace_id != self.job.workspace_id for r in refs):
            raise PermissionError('duplicate or cross-workspace assembly original')
        if self.census.source_refs != refs:
            raise PermissionError('assembly original order/population differs from frozen census')
        extraction_refs, observations, findings = assembly_inputs(
            tuple(e.payload for e in self.extractions), enforce_unique_sources=True)
        if tuple(extraction_refs) != refs:
            raise PermissionError('assembly cannot borrow or omit extraction sources')
        keys = [(e.manifest.artifact_id, e.manifest.version) for e in self.extractions]
        if len(set(keys)) != len(keys) or any(e.manifest.artifact_id == self.model_id for e in self.extractions):
            raise PermissionError('assembly output must be new and extraction identities unique')
        if any(e.manifest.permission_digest != self.job.permission_hash for e in self.extractions):
            raise PermissionError('assembly extraction permission seal differs')
        expected = assembly_messages(receipts=self.receipts, extractions=self.extractions,
            census=self.census, model_id=self.model_id, version=self.model_version)
        if self.job.request.get('messages') != expected or digest(self.job.request) != self.job.request_hash:
            raise PermissionError('assembly request differs from complete sealed input contract')
        return self

    def validate_candidate(self, raw: str, *, now: datetime):
        if now.tzinfo is None or now.utcoffset() is None or self.expires_at <= now:
            raise PermissionError('current assembly context required')
        from oracle_brain.provider_policy import authorize
        approval = authorize(self.job.processing_request, list(self.job.approvals), now=now)
        if self.expires_at > min(approval.expires_at, self.job.pricing.expires_at):
            raise PermissionError('assembly context outlives provider approval/pricing')
        # Revalidate mutable nested payload/request dictionaries at each use.
        type(self).model_validate(self.model_dump(mode='python'))
        refs, observations, findings = assembly_inputs(tuple(e.payload for e in self.extractions),
                                                      enforce_unique_sources=True)
        payload, evidence = assembly_candidate_payload(raw, workspace_id=self.job.workspace_id,
            refs=refs, observations=observations, findings=findings)
        actual = payload['operating_models'][0]
        if actual['model_id'] != str(self.model_id) or actual['version'] != self.model_version:
            raise PermissionError('generated assembly model identity differs from sealed intent')
        return payload, evidence
