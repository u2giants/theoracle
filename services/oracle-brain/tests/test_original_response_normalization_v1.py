"""Actual invented PDF and returned JSON; never dispatch a provider."""
import hashlib,json
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
from test_raw_original_views_v1 import pdf_fixture
from oracle_brain.hosting.raw_original_views_v1 import render_raw_pdf_views_v1,raw_pdf_view_policy_hash_v1
from oracle_brain.operating_model.original_qualification_v1 import RawOriginalPopulationV1
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.ingest.originals import (parse_original_reading_response_v1,original_review_prompt_v1,
    parse_original_review_response_v1)

@pytest.fixture(scope='module')
def context():
    data,ref=pdf_fixture()
    rendered=render_raw_pdf_views_v1(data,ref,expected_view_policy_hash=raw_pdf_view_policy_hash_v1())
    population=RawOriginalPopulationV1(population_id=uuid4(),workspace_id=ref.workspace_id,
        original_root_hash='1'*64,operation_registry_hash='2'*64,runtime_hash='3'*64,
        source_registry_hash='4'*64,raw_refs=(ref,),population_digest=digest({'raw_refs':[ref.model_dump(mode='json')]}),
        issuer_actor=uuid4(),reviewer_actor=uuid4(),expires_at=datetime.now(timezone.utc)+timedelta(minutes=10))
    return dict(rendered=rendered,population=population,principal=uuid4(),model='reader/model')

def payload():
    return {'complete':True,'pages':[{'page_number':1,'text':'不得跳过检查。Order → Check → Ship',
        'source_ambiguities':['page 1 lower corner: clipped label “Sh…”; meaning unknown']} ]}

def parsed(context,value=None):
    return parse_original_reading_response_v1(canonical_bytes(value or payload()),**context)

def review_context(context):
    return context|dict(population=context['population'].model_copy(update={'population_id':uuid4()}),
        principal=uuid4(),model='reviewer/model')

def test_actual_returned_text_late_hash_physical_locator_and_exact_utf8_span(context):
    result=parsed(context);body=json.loads(result.body)
    assert '不得跳过检查' in result.normalized_text
    assert body['reading']['pages'][0]['text']==payload()['pages'][0]['text']
    assert body['normalized_page_spans']==[{'page_number':1,'start_utf8':0,'end_utf8':len(result.normalized_text.encode())}]
    assert body['locator_map_hash']==context['rendered'].locator_map_hash
    assert body['view_manifest_hash']==context['rendered'].view_manifest_hash
    assert body['response_sha256']==hashlib.sha256(canonical_bytes(payload())).hexdigest()
    changed=payload();changed['pages'][0]['text']='different actual return'
    other=parsed(context,changed)
    assert other.body_hash!=result.body_hash and other.reading_sha256!=result.reading_sha256
    assert json.loads(other.body)['locator_map_hash']==body['locator_map_hash']

@pytest.mark.parametrize('raw',[
    b'{"complete":true,"complete":false,"pages":[]}',
    b'{"complete":true,"pages":[{"page_number":1,"text":"a","text":"b"}]}',
    b'{"complete":1,"pages":[{"page_number":1,"text":"a"}]}',
    b'{"complete":true,"pages":[{"page_number":"1","text":"a"}]}',
    b'{"complete":true,"pages":[{"page_number":true,"text":"a"}]}',
    b'{"complete":true,"pages":[{"page_number":1,"text":NaN}]}',
    b'{"complete":true,"pages":[{"page_number":1,"text":Infinity}]}',b'\xff',b'[]'])
def test_malformed_duplicate_nonfinite_coercions_refused(context,raw):
    with pytest.raises((ValueError,TypeError)):
        parse_original_reading_response_v1(raw,**context)

@pytest.mark.parametrize('damage',['missing','doubt','duplicate-id','bad-arrow','blank-ambiguity','duplicate-ambiguity'])
def test_coverage_and_diagram_guards_remain(context,damage):
    value=payload();page=value['pages'][0]
    if damage=='missing':value['pages']=[]
    elif damage=='doubt':page['uncertainties']=['cannot read']
    elif damage=='duplicate-id':page['visual_elements']=[{'element_id':'p1-a','kind':'node'}]*2
    elif damage=='bad-arrow':page['connections']=[{'from':'absent','to':'absent'}]
    elif damage=='blank-ambiguity':page['source_ambiguities']=[' ']
    else:page['source_ambiguities']*=2
    with pytest.raises(ValueError):parsed(context,value)

@pytest.mark.parametrize('damage',['missing','invented','duplicate','doubt','coerced','missing-page','extra-page'])
def test_complete_independent_review_requires_exact_intrinsic_ambiguities(context,damage):
    result=parsed(context);value={'complete_supported':True,'checked_pages':[1],
        'verified_source_ambiguities':payload()['pages'][0]['source_ambiguities']}
    if damage=='missing':value['verified_source_ambiguities']=[]
    elif damage=='invented':value['verified_source_ambiguities']=['unseen gap']
    elif damage=='duplicate':value['verified_source_ambiguities']*=2
    elif damage=='doubt':value['uncertainties']=['unverified gap']
    elif damage=='coerced':value['complete_supported']='true'
    elif damage=='missing-page':value['checked_pages']=[]
    else:value['checked_pages']=[1,2]
    with pytest.raises(ValueError):parse_original_review_response_v1(canonical_bytes(value),reading=result,**review_context(context))

def test_exact_reading_shown_and_verified_original_ambiguity_remains_business_unknown(context):
    result=parsed(context);rc=review_context(context)
    prompt=json.loads(original_review_prompt_v1(result,**rc))
    assert prompt['normalized_text']==result.normalized_text
    assert prompt['reading_body_hash']==result.body_hash
    value={'complete_supported':True,'checked_pages':[1],
        'verified_source_ambiguities':payload()['pages'][0]['source_ambiguities']}
    review=parse_original_review_response_v1(canonical_bytes(value),reading=result,**rc)
    assert json.loads(review.body)['reading_body_hash']==result.body_hash
    assert review.normalized_text==result.normalized_text
    assert 'meaning unknown' in review.normalized_text
    for bad in (rc|{'principal':context['principal']},rc|{'model':context['model']}):
        with pytest.raises(ValueError):original_review_prompt_v1(result,**bad)

def test_tampered_reading_or_physical_map_or_foreign_population_refused(context):
    result=parsed(context)
    with pytest.raises(ValueError):original_review_prompt_v1(replace(result,normalized_text='forged'),**review_context(context))
    with pytest.raises(ValueError):parsed(context|{'rendered':replace(context['rendered'],locator_map_hash='0'*64)})
    with pytest.raises(ValueError):parsed(context|{'population':context['population'].model_copy(update={'raw_refs':()})})


def test_multiple_actual_pdf_pages_bind_each_normalized_utf8_span(context):
    import io,pypdfium2 as pdfium
    data,_=pdf_fixture();original=pdfium.PdfDocument(data);pdf=pdfium.PdfDocument.new()
    pdf.import_pages(original,[0,0]);out=io.BytesIO();pdf.save(out);pdf.close();original.close()
    data=out.getvalue();ref=context['rendered'].raw_ref.model_copy(update={
        'original_sha256':hashlib.sha256(data).hexdigest(),'byte_count':len(data)})
    rendered=render_raw_pdf_views_v1(data,ref,expected_view_policy_hash=raw_pdf_view_policy_hash_v1())
    population=context['population'].model_copy(update={'raw_refs':(ref,),
        'population_digest':digest({'raw_refs':[ref.model_dump(mode='json')]})})
    value={'complete':True,'pages':[{'page_number':1,'text':'第一步不得跳过'},
        {'page_number':2,'text':'第二步仅在完成检查后发货'}]}
    result=parsed(context|dict(rendered=rendered,population=population),value)
    spans=json.loads(result.body)['normalized_page_spans'];raw=result.normalized_text.encode()
    assert [s['page_number'] for s in spans]==[1,2]
    assert spans[0]['start_utf8']==0 and spans[1]['end_utf8']==len(raw)
    assert raw[spans[0]['end_utf8']:spans[1]['start_utf8']]==b'\n'
    assert '第一步不得跳过' in raw[spans[0]['start_utf8']:spans[0]['end_utf8']].decode()
    assert '第二步仅在完成检查后发货' in raw[spans[1]['start_utf8']:spans[1]['end_utf8']].decode()
