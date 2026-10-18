"""Explicit private V2 native profiles; legacy source defaults stay unchanged.

Pure validation never appoints actors, qualifies phase operations or issues
semantic admission. Runtime must authenticate current external phase pins,
parent observer, SQL scope and existing shared Budget before using these inputs.
"""
from copy import deepcopy
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field,model_validator

from .acceptance_profiles import (
    CensusContext,AssessmentContext,POLICY,validate_context,validate_payload)
from .purpose_assembly_v2 import AssemblyJobContextV2
from .contracts import StrictRecord,canonical_bytes,digest
from .native_factory import NativeDispatchJob,validate_embedding_response
from .purpose_context import HASH,PHASE_CONTRACTS,PurposeDispatchV2,PurposeRunDescriptorV2
from .source_receipts import SourceRef


class DerivedEmbeddingContextV2(StrictRecord):
    """Only sealed qualified derived documents; no originals or legacy scope."""
    schema_version: Literal[2]=2
    actor_id: UUID
    workspace_id: UUID
    runtime_hash: str=Field(pattern=HASH)
    permission_hash: str=Field(pattern=HASH)
    qualified_artifact_id: UUID
    qualified_artifact_version: int=Field(strict=True,ge=1)
    qualified_content_hash: str=Field(pattern=HASH)
    projection_digest: str=Field(pattern=HASH)
    source_refs: tuple[SourceRef,...]=Field(min_length=1)
    # This view must separately match the actual currently qualified artifact.
    projection: dict
    qualified_payload: dict

    @model_validator(mode='after')
    def sanitized_projection(self):
        from .sdk_projection import ProcessingSDKProjection
        view=self.projection
        if (digest(self.qualified_payload)!=self.qualified_content_hash
                or ProcessingSDKProjection.projection_view(self.qualified_payload)!=view):
            raise PermissionError('derived view differs from exact sealed qualified content')
        if (set(view)!={'schema_version','schema','candidate_hash','qualified_model_hash','source_refs','documents'}
                or view['schema_version']!=1 or view['schema']!='qualified-evidence-projection-v1'
                or digest(view)!=self.projection_digest
                or view['source_refs']!=[r.model_dump(mode='json') for r in self.source_refs]
                or len({r.source_id for r in self.source_refs})!=len(self.source_refs)
                or any(r.workspace_id!=self.workspace_id for r in self.source_refs)
                or not isinstance(view['documents'],list) or len(view['documents'])!=len(self.source_refs)):
            raise PermissionError('exact sealed qualified evidence projection required')
        import hashlib,json
        from .model import BusinessOperatingModel
        for doc,ref in zip(view['documents'],self.source_refs):
            if (set(doc)!={'document_id','source_ref','content_hash','text'}
                    or doc['source_ref']!=ref.model_dump(mode='json')
                    or not isinstance(doc['text'],str)
                    or hashlib.sha256(doc['text'].encode()).hexdigest()!=doc['content_hash']):
                raise PermissionError('derived document identity differs')
            body=json.loads(doc['text'])
            if (set(body)!={'projection_schema','original_source_ref','qualified_model','observations','findings'}
                    or body['projection_schema']!=view['schema'] or body['original_source_ref']!=doc['source_ref']
                    or digest(body['qualified_model'])!=view['qualified_model_hash']):
                raise PermissionError('derived document contains unsupported material')
            BusinessOperatingModel.model_validate_json(canonical_bytes(body['qualified_model']))
            expected='qualified_doc_'+digest({'model_hash':view['qualified_model_hash'],
                'candidate_hash':view['candidate_hash'],'source_ref':doc['source_ref'],
                'derived_content_hash':doc['content_hash']})
            if doc['document_id']!=expected:
                raise PermissionError('derived document seal differs')
        return self

    def request(self):
        value=dict(model='openai/text-embedding-3-small',
            input=[d['text'] for d in self.projection['documents']],dimensions=256,
            encoding_format='float',store=False,provider=deepcopy(POLICY))
        if len(canonical_bytes(value))>1_990_000:
            raise PermissionError('qualified derived embedding exceeds native envelope')
        return value


from .paid_sdk_embeddings_v3 import SDKEmbeddingInventoryV3,processing_embedding_inventory_v3

class DerivedSDKEmbeddingContextV3(DerivedEmbeddingContextV2):
    """Explicit separately qualified SDK chunk/name/fact/probe population."""
    schema_version: Literal[3]=3
    inventory: SDKEmbeddingInventoryV3

    @model_validator(mode='after')
    def exact_sdk_inventory(self):
        if self.inventory!=processing_embedding_inventory_v3(self.qualified_payload):
            raise PermissionError('SDK embedding inventory differs from sealed qualified projection')
        return self

    def request(self):
        value=dict(model='openai/text-embedding-3-small',input=[i.text for i in self.inventory.inputs],
            dimensions=256,encoding_format='float',store=False,provider=deepcopy(POLICY))
        if len(canonical_bytes(value))>1_990_000:raise PermissionError('SDK embedding inventory exceeds native envelope')
        return value


class PurposePrivateContextV2(StrictRecord):
    """One private phase only; never gateway-visible or an operation admission."""
    schema_version: Literal[2]=2
    phase: Literal['census','assembly','assessment','embedding']
    job: NativeDispatchJob
    census: CensusContext|None=None
    assembly: AssemblyJobContextV2|None=None
    assessment: AssessmentContext|None=None
    embedding: DerivedEmbeddingContextV2|DerivedSDKEmbeddingContextV3|None=None

    @model_validator(mode='after')
    def one_phase_only(self):
        fields={name:getattr(self,name) for name in PHASE_CONTRACTS}
        if (fields[self.phase] is None
                or any(value is not None for name,value in fields.items() if name!=self.phase)
                or self.job.purpose!=PHASE_CONTRACTS[self.phase][0]
                or self.job.request.get('model')!=PHASE_CONTRACTS[self.phase][2]
                or self.job.pricing.model!=self.job.request.get('model')
                or self.job.processing_request.purpose!=self.job.purpose
                or digest(self.job.request)!=self.job.request_hash):
            raise PermissionError('one fixed independently qualified private phase required')
        if self.phase=='assembly' and self.assembly.job!=self.job:
            raise PermissionError('assembly private context job differs')
        return self

    @property
    def context(self):return getattr(self,self.phase)

    def validate_current(self,descriptor,dispatch,*,now:datetime):
        from oracle_brain.provider_policy import authorize
        if type(descriptor) is not PurposeRunDescriptorV2 or type(dispatch) is not PurposeDispatchV2:
            raise PermissionError('exact current admitted V2 descriptor required')
        type(self).model_validate(self.model_dump(mode='python'))
        job=self.job;context=self.context
        policy=job.processing_request.model_dump(mode='json')
        expected={'job_hash':digest(job.model_dump(mode='json')),'request_hash':job.request_hash,
            'permission_hash':job.permission_hash,'context_hash':digest(self.model_dump(mode='json')),
            'processing_request_hash':digest(policy),
            'account_policy_hash':digest({k:v for k,v in policy.items() if k!='terms_hash'}),
            'account_identity_hash':digest({k:policy[k] for k in ('provider','account','endpoint')}),
            'terms_hash':policy['terms_hash'],'pricing_hash':digest(job.pricing.model_dump(mode='json')),
            'register_hash':job.register_hash,
            'approvals_hash':digest({'approvals':[a.model_dump(mode='json') for a in job.approvals]})}
        if (descriptor.phase!=self.phase or descriptor.dispatch(dispatch.dispatch_id)!=dispatch
                or job.dispatch_id!=dispatch.dispatch_id or job.workspace_id!=descriptor.workspace_id
                or context.actor_id!=descriptor.actor_id or context.runtime_hash!=descriptor.runtime_hash
                or any(getattr(dispatch,k)!=v for k,v in expected.items())
                or now>=descriptor.expires_at):
            raise PermissionError('private native input differs from qualified operation receipt')
        approval=authorize(job.processing_request,list(job.approvals),now=now)
        if descriptor.expires_at>min(approval.expires_at,job.pricing.expires_at):
            raise PermissionError('phase exceeds actual provider approval or pricing horizon')
        refs=tuple(r.ref for r in context.receipts) if self.phase=='assembly' else (
            context.source_refs if self.phase=='embedding' else tuple(r.ref for r in context.scope.receipts))
        if refs!=descriptor.source_refs:
            raise PermissionError('private phase borrowed, omitted or reordered original')
        if self.phase in {'census','assessment'}:
            validate_context(context,job.request,trusted_context_hash=digest(context.model_dump(mode='json')),
                runtime_hash=descriptor.runtime_hash,permission_hash=job.permission_hash,now=now)
        elif self.phase=='embedding':
            if context.permission_hash!=job.permission_hash or job.request!=context.request():
                raise PermissionError('embedding must use exact qualified derived content only')
        # AssemblyJobContext validates exact complete request at model construction;
        # response callback validates all support without persistence side effects.
        return job

    def validate_response(self,response,descriptor,dispatch,*,now):
        self.validate_current(descriptor,dispatch,now=now)
        if self.phase=='assembly':return self.assembly.validate_candidate(response,now=now)
        if self.phase=='embedding':
            return validate_embedding_response(response,count=(len(self.embedding.inventory.inputs)
                if type(self.embedding) is DerivedSDKEmbeddingContextV3 else len(self.embedding.source_refs)))
        context=self.context
        return validate_payload(context,self.job.request,response,
            trusted_context_hash=digest(context.model_dump(mode='json')),
            runtime_hash=descriptor.runtime_hash,permission_hash=self.job.permission_hash,now=now)
