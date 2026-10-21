"""Actual fixed two-consumer review composition. No original/model dispatch."""
from datetime import datetime,timezone
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime,Field,BaseModel,ConfigDict
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes,digest
from oracle_brain.operating_model.consolidation_contracts_v1 import AssertionScopeV1
from oracle_brain.operating_model.consolidation_authority_v1 import ConsolidationOutcomeUnknown
from oracle_brain.operating_model.artifact_storage import FileBlobStore,_parent_fd,_read_private_at
from .original_intake_v1 import _parse
from .consolidation_review_settings_v1 import ModelReviewSettingsV1
import os,hashlib,json
from pathlib import Path

MAX_RESPONSE=262144
class InspectModelV1(StrictRecord):
    operation:Literal['inspect'];model_id:UUID
    base_version:int=Field(strict=True,ge=1,le=2147483647)
    caller_deadline:AwareDatetime
class AssertionSelectorV1(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    assertion_id:UUID;revision:int=Field(strict=True,ge=1,le=2147483647)
class DecideModelV1(StrictRecord):
    operation:Literal['decide'];model_id:UUID
    version:int=Field(strict=True,ge=1,le=2147483647);expected_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    decision:Literal['accept','reject'];decision_kind:Literal['employee-account','process-policy','company-policy']
    scope:AssertionScopeV1
    assertions:tuple[AssertionSelectorV1,...]=Field(min_length=1,max_length=64)
    command_id:UUID;caller_deadline:AwareDatetime

def parse_review_request(raw):
    # Sole strict canonical parser already rejects duplicates/noncanonical UUIDs.
    if type(raw) is not bytes or len(raw)>65536:raise PermissionError('bounded review request required')
    value=json.loads(raw)
    if type(value) is not dict:raise PermissionError('closed review operation required')
    cls=InspectModelV1 if value.get('operation')=='inspect' else DecideModelV1 if value.get('operation')=='decide' else None
    if cls is None:raise PermissionError('fixed review operation required')
    return _parse(cls,raw)

class _ReviewBlobs(FileBlobStore):
    def __init__(self,config):
        super().__init__(Path(config.storage_root))
        self.root_identity=(config.storage_device,config.storage_inode,config.storage_uid)
    def read(self,key,expected_hash):
        self._path(key)
        parent=_parent_fd(self.root,key.split('/')[:-1],create=False,expected_root=self.root_identity)
        try:data=_read_private_at(parent,key.split('/')[-1],2*1024*1024)
        finally:os.close(parent)
        if hashlib.sha256(data).hexdigest()!=expected_hash:raise PermissionError('immutable review body changed')
        return data

class ModelReviewFactoryV1:
    def __init__(self,settings):
        if type(settings) is not ModelReviewSettingsV1:raise TypeError('fixed installed review consumers required')
        self.settings=settings;settings.current()
    def execute_v1(self,raw):
        request=parse_review_request(raw);settings=self.settings
        recorded=False
        try:
            end=settings.current();config=settings.config
            if request.model_id!=config.model_id or not datetime.now(timezone.utc)<request.caller_deadline<=end:raise PermissionError('original exact review window required')
            history,business,_=settings.consumers();blobs=_ReviewBlobs(config)
            if type(request) is InspectModelV1:
                snapshot=business.read_review_snapshot_v1(request.model_id,expected_version=request.base_version,blobs=blobs,deadline=request.caller_deadline,history_authority=history)
                result=snapshot.metadata;valid_until=snapshot.valid_until
            else:
                if request.decision_kind!=config.decision_kind:raise PermissionError('exact installed business decision kind required')
                current=business.review_metadata_v1(request.model_id,expected_version=request.version,deadline=request.caller_deadline)
                if (current['decisionKind']!=request.decision_kind or current['scopeSha256']!=digest(request.scope.model_dump(mode='json'))):raise PermissionError('actual installed decision kind or scope differs')
                if current['conflict'] or current['currentContentHash']!=request.expected_hash:raise PermissionError('current review changed; reload required')
                core,metadata,_=history._read_model_packet_v1(request.model_id,blobs=blobs,deadline=request.caller_deadline,version=request.version)
                selected={a.assertion_id:a for a in core.assertions}
                ids=tuple((a.assertion_id,a.revision) for a in request.assertions)
                if len(set(ids))!=len(ids) or any(i not in selected or selected[i].revision!=v or selected[i].scope!=request.scope for i,v in ids):raise PermissionError('exact visible assertion scope and revisions required')
                settings.current()
                event=business.review_v1(model=request.model_id,version=request.version,content_hash=request.expected_hash,decision=request.decision,
                    scope=request.scope.model_dump(mode='json'),assertions=[a.model_dump(mode='json') for a in request.assertions],
                    bundle_hash=digest({'manifest':metadata['manifest'],'scope':request.scope.model_dump(mode='json'),'assertions':sorted((str(i),v) for i,v in ids)}),
                    idempotency=request.command_id,deadline=request.caller_deadline)
                recorded=True
                fresh=business.review_metadata_v1(request.model_id,expected_version=request.version,deadline=request.caller_deadline)
                if fresh['decisionKind']!=request.decision_kind or fresh['scopeSha256']!=digest(request.scope.model_dump(mode='json')):raise PermissionError('actual decision authority changed after commit')
                history_fresh=history._metadata(request.model_id,deadline=request.caller_deadline,version=request.version)
                if {k:v for k,v in history_fresh.items() if k!='businessDecisions'}!={k:v for k,v in metadata.items() if k!='businessDecisions'}:raise PermissionError('history changed after recorded decision')
                valid_until=min(request.caller_deadline,*(datetime.fromisoformat(m['validUntil']) for m in (event,fresh,history_fresh)))
                # A recorded account decision is never generated-truth or policy approval.
                result={'modelId':str(request.model_id),'version':request.version,'decision':request.decision,'decisionKind':request.decision_kind,
                    'eventId':event['eventId'],'policyEligibility':'unknown','modelConfirmed':False,'automaticRebase':False}
            settings.current()
            if datetime.now(timezone.utc)>=valid_until:raise PermissionError('review completed after original deadline')
            response=canonical_bytes(result)
            if not 0<len(response)<=MAX_RESPONSE:raise PermissionError('review exceeds fixed readable response bound')
            if datetime.now(timezone.utc)>=valid_until:raise PermissionError('review packed after original scope deadline')
            return response,valid_until
        except Exception:
            if recorded:raise ConsolidationOutcomeUnknown('decision committed but review response unavailable; read-only reconciliation required, no retry') from None
            raise
