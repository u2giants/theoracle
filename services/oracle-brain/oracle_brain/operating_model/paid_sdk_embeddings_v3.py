"""Exact paid vector reuse for pinned SDK ingestion; no IO, grants or dispatch.

A protected runtime must authenticate current SQL/semantic/custody authority
BEFORE opening private inputs, and recheck after verification and before ACK.
Typed values/hash equality alone never appoint that runtime or grant file access.
"""
from datetime import datetime
import hashlib,json,math,threading,struct
from importlib.metadata import version
from typing import Literal
from uuid import UUID
from pydantic import Field,model_validator,AwareDatetime
from graphrag_sdk.core.providers import Embedder
from .contracts import StrictRecord,digest,canonical_bytes
from .source_receipts import SourceRef
from .purpose_receipts_v2 import PhaseResponseCommitV2

HASH=r'^[a-f0-9]{64}$'

class SDKEmbeddingInputV3(StrictRecord):
    text:str=Field(min_length=1)
    text_hash:str=Field(pattern=HASH)
    usage_keys:tuple[str,...]=Field(min_length=1)
    @model_validator(mode='after')
    def exact(self):
        if hashlib.sha256(self.text.encode()).hexdigest()!=self.text_hash or len(set(self.usage_keys))!=len(self.usage_keys):
            raise ValueError('exact unique SDK embedding input required')
        return self

class SDKEmbeddingInventoryV3(StrictRecord):
    schema_version:Literal[3]=3
    purpose:Literal['qualified-sdk-ingestion-embedding-inventory-v3']='qualified-sdk-ingestion-embedding-inventory-v3'
    sdk_version:Literal['1.4.0']='1.4.0'
    projection_schema:Literal['qualified-evidence-projection-v1']='qualified-evidence-projection-v1'
    projection_digest:str=Field(pattern=HASH)
    qualified_content_hash:str=Field(pattern=HASH)
    source_refs:tuple[SourceRef,...]=Field(min_length=1)
    inputs:tuple[SDKEmbeddingInputV3,...]=Field(min_length=1,max_length=10000)
    @model_validator(mode='after')
    def unique(self):
        keys=[key for item in self.inputs for key in item.usage_keys]
        if len(set(keys))!=len(keys) or len({i.text for i in self.inputs})!=len(self.inputs):
            raise ValueError('SDK usage keys and exact strings must be unique')
        return self


def processing_embedding_inventory_v3(payload):
    """Mirror ONLY pinned actual chunk/name/fact/probe transformations."""
    from .sdk_projection import ProcessingSDKProjection,SDKProjection
    if version('graphrag-sdk')!='1.4.0':raise PermissionError('exact admitted SDK required')
    view=ProcessingSDKProjection.projection_view(payload)
    nodes,relations=SDKProjection.semantic_projection(payload)
    ordered={}
    def add(text,key):
        if not isinstance(text,str) or not text:raise ValueError('nonempty exact SDK text required')
        ordered.setdefault(text,[]).append(key)
    add('dim_check','probe:dim_check')
    for doc in view['documents']:add(doc['text'],'chunk:'+doc['document_id'])
    for observation in sorted(payload.get('observations',[]),key=lambda o:o['observation_id']):
        add(observation['value']+' ['+observation['observation_id']+']','entity:'+observation['observation_id'])
    for identifier,(_,title,_,_) in sorted(nodes.items()):add(title+' ['+identifier+']','entity:'+identifier)
    for identifier,(_,_,_,fact,_) in sorted(relations.items()):
        if fact:add(fact,'relation:'+identifier)
    return SDKEmbeddingInventoryV3(projection_digest=digest(view),qualified_content_hash=digest(payload),
        source_refs=tuple(SourceRef.model_validate_json(canonical_bytes(r)) for r in payload['source_refs']),
        inputs=tuple(SDKEmbeddingInputV3(text=text,text_hash=hashlib.sha256(text.encode()).hexdigest(),usage_keys=tuple(keys)) for text,keys in ordered.items()))

class PaidSDKEmbeddingPinsV3(StrictRecord):
    """Exact externally appointed phase/custody pins, not their own authority."""
    context_hash:str=Field(pattern=HASH)
    commit_hash:str=Field(pattern=HASH)
    native_receipt_hash:str=Field(pattern=HASH)
    descriptor_hash:str=Field(pattern=HASH)
    operation_approval_hash:str=Field(pattern=HASH)
    parent_registry_hash:str=Field(pattern=HASH)
    allocation_hash:str=Field(pattern=HASH)
    population_digest:str=Field(pattern=HASH)
    ledger_identity_hash:str=Field(pattern=HASH)
    key_fingerprint:str=Field(pattern=HASH)

class PaidSDKEmbeddingWitnessV3(StrictRecord):
    schema_version:Literal[3]=3
    purpose:Literal['observed-paid-sdk-embedding-v3']='observed-paid-sdk-embedding-v3'
    workspace_id:UUID
    dispatch_id:UUID
    qualified_artifact_id:UUID
    qualified_artifact_version:int=Field(strict=True,ge=1)
    context_hash:str=Field(pattern=HASH)
    job_hash:str=Field(pattern=HASH)
    request_hash:str=Field(pattern=HASH)
    inventory_hash:str=Field(pattern=HASH)
    projection_digest:str=Field(pattern=HASH)
    qualified_content_hash:str=Field(pattern=HASH)
    phase_commit_hash:str=Field(pattern=HASH)
    native_receipt_hash:str=Field(pattern=HASH)
    raw_response_hash:str=Field(pattern=HASH)
    vectors_hash:str=Field(pattern=HASH)
    committed_at:AwareDatetime
    # Historical own-phase commit horizon, not a current compiler/read grant.
    phase_valid_until:AwareDatetime

def sdk_float32_vector(vector):
    """Exact retained SDK vecf32 storage representation, not normalization."""
    if len(vector)!=256:raise ValueError('exact 256-dimensional SDK vector required')
    try:values=tuple(struct.unpack('!f',struct.pack('!f',float(v)))[0] for v in vector)
    except (OverflowError,ValueError,TypeError,struct.error):raise ValueError('vector cannot be represented by SDK vecf32') from None
    if any(not math.isfinite(v) for v in values) or not any(v!=0 for v in values):
        raise ValueError('SDK vecf32 vector is nonfinite or zero after cast')
    return values


class PaidSDKEmbeddingDataV3(StrictRecord):
    witness:PaidSDKEmbeddingWitnessV3
    inventory:SDKEmbeddingInventoryV3
    vectors:tuple[tuple[float,...],...]
    @model_validator(mode='after')
    def exact(self):
        if (len(self.vectors)!=len(self.inventory.inputs) or self.witness.projection_digest!=self.inventory.projection_digest
                or self.witness.qualified_content_hash!=self.inventory.qualified_content_hash or digest(self.inventory.model_dump(mode='json'))!=self.witness.inventory_hash
                or digest({'vectors':self.vectors})!=self.witness.vectors_hash
                or any(len(v)!=256 or not any(x!=0 for x in v) or any(not math.isfinite(x) for x in v) for v in self.vectors)):
            raise ValueError('complete exact finite nonzero paid vector population required')
        for vector in self.vectors:sdk_float32_vector(vector)
        return self


def verify_paid_sdk_embedding_v3(private,commit,native_record,raw,*,pins):
    """Pure historical custody binding, NOT private-file/current SQL authorization."""
    from .purpose_profiles_v2 import PurposePrivateContextV2,DerivedSDKEmbeddingContextV3
    from .native_factory import validate_embedding_response
    from oracle_brain.provider_policy import authorize
    if (type(private) is not PurposePrivateContextV2 or private.phase!='embedding'
            or type(private.embedding) is not DerivedSDKEmbeddingContextV3
            or type(commit) is not PhaseResponseCommitV2 or type(pins) is not PaidSDKEmbeddingPinsV3
            or type(raw) is not bytes or len(raw)>16*1024*1024):
        raise PermissionError('exact V3 embedding private phase, successful observed commit and pinned custody required')
    type(private).model_validate(private.model_dump(mode='python'))
    type(commit).model_validate(commit.model_dump(mode='python'))
    type(pins).model_validate(pins.model_dump(mode='python'))
    context=private.embedding;job=private.job
    if (digest(private.model_dump(mode='json'))!=pins.context_hash
            or digest(commit.model_dump(mode='json'))!=pins.commit_hash
            or digest(native_record)!=pins.native_receipt_hash
            or commit.phase!='embedding' or commit.context_hash!=pins.context_hash
            or commit.native_custody_receipt_hash!=pins.native_receipt_hash
            or commit.job_hash!=digest(job.model_dump(mode='json')) or commit.request_hash!=job.request_hash
            or commit.dispatch_id!=job.dispatch_id or commit.workspace_id!=job.workspace_id
            or commit.actor_id!=context.actor_id or commit.runtime_hash!=context.runtime_hash
            or commit.permission_hash!=job.permission_hash or context.permission_hash!=job.permission_hash
            or commit.source_refs!=context.source_refs or commit.model!=job.request['model']
            or commit.descriptor_hash!=pins.descriptor_hash or commit.operation_approval_hash!=pins.operation_approval_hash
            or commit.parent_registry_hash!=pins.parent_registry_hash or commit.budget_identity_hash!=pins.allocation_hash
            or commit.population_digest!=pins.population_digest or job.request!=context.request()):
        raise PermissionError('paid SDK embedding differs from exact independently appointed phase')
    policy=job.processing_request.model_dump(mode='json')
    if commit.account_policy_hash!=digest({k:v for k,v in policy.items() if k!='terms_hash'}):
        raise PermissionError('paid SDK embedding account policy differs')
    authorize(job.processing_request,list(job.approvals),now=commit.committed_at)
    if commit.committed_at>=job.pricing.expires_at:raise PermissionError('paid SDK embedding committed after pricing expiry')
    expected={'dispatch_id','reservation_id','failed','raw_response','request_hash','permission_hash','job_hash','register_hash',
        'pricing_hash','key_fingerprint','ledger_identity_hash','raw_response_hash','wire_custody'}
    raw_hash=hashlib.sha256(raw).hexdigest()
    if (type(native_record) is not dict or set(native_record)!=expected or native_record['failed'] is not False
            or native_record['raw_response_hash']!=raw_hash or commit.raw_response_hash!=raw_hash
            or native_record['raw_response']!=raw.decode('utf-8')
            or native_record['request_hash']!=job.request_hash or native_record['permission_hash']!=job.permission_hash
            or native_record['job_hash']!=commit.job_hash or native_record['register_hash']!=job.register_hash
            or native_record['pricing_hash']!=digest(job.pricing.model_dump(mode='json'))
            or native_record['key_fingerprint']!=pins.key_fingerprint or native_record['ledger_identity_hash']!=pins.ledger_identity_hash
            or native_record['dispatch_id']!=str(job.dispatch_id)):
        raise PermissionError('actual successful complete native embedding custody required')
    UUID(native_record['reservation_id'])
    wire=native_record['wire_custody']
    expected_wire={'dispatch_id','reservation_id','request_hash','permission_hash','job_hash','key_fingerprint','ledger_identity_hash',
        'raw_sha256','captured_bytes','complete','truncated'}
    if (type(wire) is not dict or set(wire)!=expected_wire or wire['complete'] is not True or wire['truncated'] is not False
            or type(wire['captured_bytes']) is not int or wire['captured_bytes']!=len(raw) or wire['raw_sha256']!=raw_hash
            or any(wire[k]!=native_record[k] for k in expected_wire&expected)):
        raise PermissionError('actual complete native embedding wire metadata differs')
    def unique(pairs):
        out={}
        for key,value in pairs:
            if key in out:raise ValueError('duplicate embedding wire field')
            out[key]=value
        return out
    response=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite embedding wire')))
    validate_embedding_response(response,count=len(context.inventory.inputs))
    if [v['index'] for v in response['data']]!=list(range(len(context.inventory.inputs))):
        raise ValueError('native embedding indices reordered')
    vectors=tuple(tuple(float(x) for x in row['embedding']) for row in response['data'])
    witness=PaidSDKEmbeddingWitnessV3(workspace_id=job.workspace_id,dispatch_id=job.dispatch_id,
        qualified_artifact_id=context.qualified_artifact_id,qualified_artifact_version=context.qualified_artifact_version,
        context_hash=pins.context_hash,job_hash=commit.job_hash,request_hash=job.request_hash,
        inventory_hash=digest(context.inventory.model_dump(mode='json')),projection_digest=context.projection_digest,
        qualified_content_hash=context.qualified_content_hash,phase_commit_hash=pins.commit_hash,native_receipt_hash=pins.native_receipt_hash,
        raw_response_hash=raw_hash,vectors_hash=digest({'vectors':vectors}),committed_at=commit.committed_at,phase_valid_until=commit.valid_until)
    return PaidSDKEmbeddingDataV3(witness=witness,inventory=context.inventory,vectors=vectors)

class PaidProjectionEmbedderV3(Embedder):
    """No provider. Exact immutable vector lookup; protected caller owns authority."""
    model_name='openai/text-embedding-3-small'
    def __init__(self,data):
        if type(data) is not PaidSDKEmbeddingDataV3:raise PermissionError('verified paid SDK data required')
        self.data=PaidSDKEmbeddingDataV3.model_validate(data.model_dump(mode='python'))
        self._by_text={item.text:i for i,item in enumerate(self.data.inventory.inputs)}
        self._observed=set();self._denied=[];self._lock=threading.Lock()
    def embed_query(self,text,**kwargs):
        with self._lock:
            if type(text) is not str or text not in self._by_text:
                self._denied.append(hashlib.sha256(str(text).encode()).hexdigest())
                raise PermissionError('SDK requested text outside exact paid ingestion inventory')
            i=self._by_text[text];self._observed.add(i)
            return list(self.data.vectors[i])
    def assert_no_denials(self):
        with self._lock:
            if self._denied:raise PermissionError('SDK swallowed an unauthorized embedding request')
    def vector_for_usage(self,key):
        for i,item in enumerate(self.data.inventory.inputs):
            if key in item.usage_keys:return self.data.vectors[i]
        raise PermissionError('graph vector usage outside paid inventory')
    def assert_observed(self,usage_keys):
        self.assert_no_denials()
        with self._lock:
            for key in usage_keys:
                indices=[i for i,item in enumerate(self.data.inventory.inputs) if key in item.usage_keys]
                if len(indices)!=1 or indices[0] not in self._observed:raise PermissionError('SDK omitted a required paid vector input')


class PaidSDKProjectionProofV3(StrictRecord):
    schema_version:Literal[3]=3
    embedding_protocol:Literal['paid-sdk-embedding-v3']='paid-sdk-embedding-v3'
    embedding_inventory_hash:str=Field(pattern=HASH)
    embedding_context_hash:str=Field(pattern=HASH)
    embedding_native_receipt_hash:str=Field(pattern=HASH)
    embedding_wire_hash:str=Field(pattern=HASH)
    embedding_commit_hash:str=Field(pattern=HASH)
    embedding_vectors_hash:str=Field(pattern=HASH)
    embedding_coverage_hash:str=Field(pattern=HASH)
