"""Exact complete multimodal native envelope; validation grants no access."""
from .raw_original_views_v1 import RawPDFViewsV1,verify_raw_pdf_multimodal_messages_v1
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.native_factory import RawOriginalDispatchJobV1
from oracle_brain.operating_model.raw_multimodal_pricing_v1 import raw_multimodal_reservation_maximum_v1


def validate_raw_original_request_v1(job,rendered,prompt,*,expected_quote_sha256,now):
    """Protected caller authenticates current SQL/observer/custody/quote first.

    Byte counts concern the native envelope. Image tokens come ONLY from the
    independently appointed model-specific quote, never base64 text length.
    """
    if type(job) is not RawOriginalDispatchJobV1 or type(rendered) is not RawPDFViewsV1:
        raise PermissionError('exact raw native job and actual PDF views required')
    job=RawOriginalDispatchJobV1.model_validate_json(job.model_dump_json())
    q=job.pricing;r=job.request
    expected={'model','messages','max_tokens','response_format','store','stream','provider'}
    if (set(r)!=expected or r['model']!=q.model or type(r['max_tokens']) is not int
            or r['max_tokens']!=q.max_output_tokens or r['response_format']!={'type':'json_object'}
            or r['store'] is not False or r['stream'] is not False
            or r['provider']!={'only':['openai'],'allow_fallbacks':False,'require_parameters':True,'data_collection':'deny'}):
        raise PermissionError('exact fixed raw native transport required')
    verify_raw_pdf_multimodal_messages_v1(rendered,prompt,r['messages'])
    sizes=[len(v.png) for v in rendered.views]
    text_bytes=sum(len(m['content'].encode()) if type(m['content']) is str else
        sum(len(p['text'].encode()) for p in m['content'] if p['type']=='text') for m in r['messages'])
    if (rendered.raw_ref!=job.raw_ref or rendered.view_manifest_hash!=job.view_manifest_hash
            or rendered.locator_map_hash!=job.locator_map_hash
            or q.view_count!=len(sizes) or q.total_image_bytes!=sum(sizes)
            or q.largest_image_bytes!=max(sizes)
            or q.text_input_tokens_upper_bound<text_bytes+1024*len(r['messages'])
            or digest(r)!=job.request_hash):
        raise PermissionError('complete actual view/text/quote request binding differs')
    envelope=canonical_bytes({'dispatch_id':str(job.dispatch_id),'request_hash':job.request_hash,'request':r})
    if len(envelope)>2_000_000:
        raise PermissionError('unchanged native envelope cannot contain every actual view')
    maximum=raw_multimodal_reservation_maximum_v1(q,expected_quote_sha256=expected_quote_sha256,
        input_tokens_upper_bound=job.input_tokens_upper_bound,purpose=job.purpose,now=now)
    return envelope,maximum
