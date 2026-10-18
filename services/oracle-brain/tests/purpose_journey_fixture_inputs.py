"""Immutable ORIGINAL-input parent; this object issues no operation authority."""
from uuid import uuid4
from test_native_factory import job as template_job
from oracle_brain.hosting.provider_runtime import JobContext,JobRegistry
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.native_factory import NativeDispatchJob
from oracle_brain.operating_model.native_provider import current_pricing
from oracle_brain.operating_model.pipeline import extraction_messages
from oracle_brain.provider_policy import ProcessingRequest,ProcessingApproval


def original_input_parent(receipts,*,actor_id,runtime_hash,batch_id,expires_at,catalog,now,account):
    processing=ProcessingRequest(provider='openrouter',account=account,endpoint='https://openrouter.ai/api/v1',
        data_classes=frozenset({'synthetic'}),purpose='source-extraction',terms_hash='b'*64)
    approval=ProcessingApproval(**processing.model_dump(),expires_at=expires_at,register_ref='invented-coherent-original-inputs')
    contexts=[]
    for receipt in receipts:
        request={**template_job().request,'messages':extraction_messages(receipt),'max_tokens':4096}
        job=NativeDispatchJob(dispatch_id=uuid4(),workspace_id=receipt.ref.workspace_id,artifact_id=uuid4(),batch_id=batch_id,
            purpose='source-extraction',attempt=1,request=request,request_hash=digest(request),permission_hash='c'*64,
            processing_request=processing,approvals=(approval,),
            pricing=current_pricing(catalog,model=request['model'],max_output_tokens=request['max_tokens'],register_hash='d'*64,now=now),
            register_hash='d'*64,input_tokens_upper_bound=2*len(canonical_bytes(request))+4096)
        contexts.append(JobContext(job=job,actor_id=actor_id,job_hash=digest(job.model_dump(mode='json')),
            permission_hash=job.permission_hash,receipt=receipt,inventories={}))
    return JobRegistry(issuer_actor=uuid4(),reviewer_actor=uuid4(),runtime_hash=runtime_hash,expires_at=expires_at,contexts=tuple(contexts))
