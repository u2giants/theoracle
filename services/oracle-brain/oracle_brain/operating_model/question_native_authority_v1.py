"""Fixed SQL024 question dispatch guards, SAME actual native/cost/custody owner."""
from datetime import datetime,timezone
from decimal import Decimal
from .contracts import digest
from .protected_inputs_v1 import _pinned,_parse
from .question_effects_v1 import ProtectedQuestionEffectsV1
from .request_deadline_v1 import request_remaining_v1
from .raw_endpoint_inventory_v1 import RawBillingBoundsV1,QueryEmbeddingBillingBoundsV1,compare_query_embedding_quote_v1,compare_synthesis_text_quote_v1
from .conversation_native_authority_v1 import ConversationWireLiabilityUnknown,conversation_wire_liability_lower_bound_v1

def current_question_dispatch_v1(control,job,broker):
    if type(control) is not ProtectedQuestionEffectsV1:raise PermissionError('actual independently appointed question owner required')
    deadline=control._active_deadline
    context=control.current_for_job_v1(job,deadline=deadline)
    a=context['admission'];allocation=broker._allocation
    if allocation is None or(str(allocation.batch_id),allocation.allocation_hash,allocation.original_receipt_hash,allocation.ceiling_usd)!=(a['allocation_batch'],a['allocation_hash'],a['allocation_receipt_hash'],Decimal(str(a['allocation_ceiling_usd']))):raise PermissionError('exact same finite central allocation required')
    if(broker._key_fingerprint,broker._registry_hash,job.processing_request.account,job.processing_request.terms_hash,job.register_hash)!=(a['key_fingerprint'],a['ledger_registry_hash'],a['account'],a['terms_hash'],a['register_hash']):raise PermissionError('actual independently admitted key/ledger/account/terms/register differs')
    control.cost_scope_v1(job,broker,deadline=deadline)
    request_remaining_v1();return context

def current_question_metadata_v1(control,job,broker,native):
    context=current_question_dispatch_v1(control,job,broker);c=control.config
    query=job.purpose=='qualified-query-embedding-v1'
    billing_type=QueryEmbeddingBillingBoundsV1 if query else RawBillingBoundsV1
    bounds=_parse(billing_type,_pinned(c.billing_bounds.path,c.billing_bounds.sha256,65536))
    request_remaining_v1();models=native.metadata_wire_v1('/embeddings/models' if query else '/models');request_remaining_v1()
    endpoints=native.metadata_wire_v1('/models/'+job.pricing.model+'/endpoints');request_remaining_v1()
    comparison=(compare_query_embedding_quote_v1 if query else compare_synthesis_text_quote_v1)(models.wire,endpoints.wire,quote=job.pricing,billing_bounds=bounds,
        expected_quote_sha256=c.pricing.sha256,expected_billing_evidence_sha256=c.billing_bounds.sha256,current_account=job.processing_request.account,
        current_key_fingerprint=broker._key_fingerprint,current_ledger_registry_hash=broker._registry_hash,current_terms_hash=job.processing_request.terms_hash,
        current_register_hash=job.register_hash,models_observed_at=models.observed_at,endpoints_observed_at=endpoints.observed_at,now=datetime.now(timezone.utc))
    from .contracts import canonical_bytes
    if _pinned(c.billing_bounds.path,c.billing_bounds.sha256,65536)!=canonical_bytes(bounds.model_dump(mode='json')):raise PermissionError('billing evidence changed')
    current_question_dispatch_v1(control,job,broker)
    broker._retain_conversation_metadata_v1(job,models,endpoints,comparison)
    return context

def validate_question_wire_v1(raw,job):
    import json
    from decimal import Decimal
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise PermissionError('duplicate paid question response; liability UNKNOWN')
            result[key]=value
        return result
    if type(raw) is not str:raise PermissionError('actual retained question wire required')
    try:data=json.loads(raw,object_pairs_hook=unique,parse_float=Decimal,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite')))
    except(ValueError,TypeError,RecursionError):raise ConversationWireLiabilityUnknown('strict actual paid question wire unavailable',conversation_wire_liability_lower_bound_v1(raw)) from None
    usage=data.get('usage') if type(data) is dict else None
    if type(usage) is not dict or usage.get('is_byok') is not False:raise ConversationWireLiabilityUnknown('shared-only actual route unknown',conversation_wire_liability_lower_bound_v1(raw))
    for field in('cost',):
        value=usage.get(field)
        if type(value) not in(str,int,Decimal) or type(value) is bool:
            raise ConversationWireLiabilityUnknown('actual question usage unknown',conversation_wire_liability_lower_bound_v1(raw))
        cost=Decimal(str(value))
        if not cost.is_finite() or cost<0:raise ConversationWireLiabilityUnknown('actual question cost unknown',conversation_wire_liability_lower_bound_v1(raw))
    for field in('prompt_tokens','total_tokens'):
        if type(usage.get(field)) is not int or usage[field]<0:raise ConversationWireLiabilityUnknown('complete actual question token usage unknown',conversation_wire_liability_lower_bound_v1(raw))
    details=usage.get('cost_details',{})
    if type(details) is not dict:raise ConversationWireLiabilityUnknown('actual upstream liability unknown',conversation_wire_liability_lower_bound_v1(raw))
    upstream=details.get('upstream_inference_cost',0)
    if type(upstream) not in(str,int,Decimal) or not Decimal(str(upstream)).is_finite() or Decimal(str(upstream))!=0:
        raise ConversationWireLiabilityUnknown('actual unexpected upstream charge',conversation_wire_liability_lower_bound_v1(raw))
    if usage['prompt_tokens']>job.input_tokens_upper_bound:raise ConversationWireLiabilityUnknown('actual input exceeds admitted full bound',conversation_wire_liability_lower_bound_v1(raw))
    if data.get('model')!=job.pricing.model:raise PermissionError('actual paid question model differs')
    if job.purpose=='qualified-answer-synthesis-v1':
        if type(usage.get('completion_tokens')) is not int or not 0<=usage['completion_tokens']<=job.pricing.max_output_tokens or usage['total_tokens']!=usage['prompt_tokens']+usage['completion_tokens']:raise ConversationWireLiabilityUnknown('actual complete synthesis usage unknown',conversation_wire_liability_lower_bound_v1(raw))
        choices=data.get('choices')
        if type(choices) is not list or len(choices)!=1 or choices[0].get('finish_reason')!='stop' or choices[0].get('message',{}).get('role')!='assistant' or type(choices[0].get('message',{}).get('content')) is not str or choices[0]['message'].get('tool_calls') or choices[0]['message'].get('function_call'):raise ValueError('one complete actual assistant synthesis required')
    elif usage['total_tokens']!=usage['prompt_tokens']:raise PermissionError('embedding reported unexpected output usage')
    return data
