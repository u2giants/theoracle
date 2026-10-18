"""Actual invented PDF rendering and image parts; no model or paid call."""
import base64,hashlib,io,copy
from dataclasses import replace
from uuid import uuid4
import pytest
from PIL import Image,ImageDraw
from oracle_brain.ingest.originals import _views
from oracle_brain.hosting.raw_original_views_v1 import (render_raw_pdf_views_v1,raw_pdf_view_policy_hash_v1,
    raw_pdf_multimodal_messages_v1,verify_raw_pdf_multimodal_messages_v1)
from oracle_brain.operating_model.original_qualification_v1 import RawOriginalRefV1

def pdf_fixture(*,oversized=False):
    import pypdfium2 as pdfium
    image=Image.new('RGB',(4001,8) if oversized else (240,120),'white')
    draw=ImageDraw.Draw(image);draw.text((4,4),'Order -> Check -> Ship',fill='black')
    draw.rectangle((2,30,100,90),outline='black');draw.line((50,30,50,90),fill='black')
    pdf=pdfium.PdfDocument.new();page=pdf.new_page(240,120);item=pdfium.PdfImage.new(pdf)
    bitmap=pdfium.PdfBitmap.from_pil(image);item.set_bitmap(bitmap)
    item.set_matrix(pdfium.PdfMatrix(240,0,0,120,0,0));page.insert_obj(item);page.gen_content()
    output=io.BytesIO();pdf.save(output);page.close();pdf.close();bitmap.close()
    raw=output.getvalue();ref=RawOriginalRefV1(workspace_id=uuid4(),source_id=uuid4(),revision=1,
        original_sha256=hashlib.sha256(raw).hexdigest(),byte_count=len(raw),media_type='application/pdf',
        filename='invented-workflow.pdf',custody_locator_seal_sha256='a'*64)
    return raw,ref

def test_actual_pdf_all_views_and_genuine_image_parts_match_legacy_default_bytes():
    data,ref=pdf_fixture();rendered=render_raw_pdf_views_v1(data,ref,expected_view_policy_hash=raw_pdf_view_policy_hash_v1())
    legacy,native=_views(data,'application/pdf')
    assert rendered.views==tuple(legacy) and rendered.native_text==tuple(native)
    assert [v.kind for v in rendered.views]==['pdf-page',*['pdf-detail']*4,'pdf-embedded-image','pdf-embedded-image-rotated']
    messages=raw_pdf_multimodal_messages_v1(rendered,'Fixed invented reading task')
    images=[x['image_url'] for x in messages[1]['content'] if x['type']=='image_url']
    assert len(images)==len(rendered.views)==7
    for actual,view in zip(images,rendered.views):
        assert actual['detail']=='high' and actual['url'].startswith('data:image/png;base64,')
        assert base64.b64decode(actual['url'].split(',',1)[1],validate=True)==view.png
    assert verify_raw_pdf_multimodal_messages_v1(rendered,'Fixed invented reading task',messages)==messages

@pytest.mark.parametrize('damage',['last-view','remote-url','text-base64','png','detail','role'])
def test_closed_complete_image_parts_reject_omission_or_substitution(damage):
    data,ref=pdf_fixture();rendered=render_raw_pdf_views_v1(data,ref,expected_view_policy_hash=raw_pdf_view_policy_hash_v1())
    messages=raw_pdf_multimodal_messages_v1(rendered,'Fixed task');bad=copy.deepcopy(messages)
    if damage=='last-view':bad[1]['content'].pop()
    elif damage=='remote-url':bad[1]['content'][2]['image_url']['url']='https://example.invalid/image.png'
    elif damage=='text-base64':bad[1]['content'][2]={'type':'text','text':bad[1]['content'][2]['image_url']['url']}
    elif damage=='png':bad[1]['content'][2]['image_url']['url']='data:image/png;base64,ZmFrZQ=='
    elif damage=='detail':bad[1]['content'][2]['image_url']['detail']='low'
    else:bad[0]['role']='tool'
    with pytest.raises(PermissionError,match='complete PNG'):verify_raw_pdf_multimodal_messages_v1(rendered,'Fixed task',bad)

def test_new_raw_pdf_refuses_actual_oversized_embedded_artwork_without_legacy_change():
    data,ref=pdf_fixture(oversized=True)
    # Existing opt-out path remains its historical behavior; new fixed raw path
    # never invokes a model with a silently downsampled supplemental image.
    legacy,_=_views(data,'application/pdf')
    assert max(v.width for v in legacy if v.kind=='pdf-embedded-image')==4000
    with pytest.raises(ValueError,match='native PDF artwork exceeds unchanged 4000px'):
        render_raw_pdf_views_v1(data,ref,expected_view_policy_hash=raw_pdf_view_policy_hash_v1())

def test_raw_original_hash_and_policy_must_match_before_render(monkeypatch):
    data,ref=pdf_fixture()
    def forbidden(*args,**kwargs):raise AssertionError('render before byte/policy binding')
    monkeypatch.setattr('oracle_brain.hosting.raw_original_views_v1.originals._views',forbidden)
    for raw,policy in ((data+b'wrong',raw_pdf_view_policy_hash_v1()),(data,'0'*64)):
        with pytest.raises(PermissionError):render_raw_pdf_views_v1(raw,ref,expected_view_policy_hash=policy)

def test_new_parser_fingerprint_tracks_actual_source_without_rewriting_historical_refs(monkeypatch):
    from pathlib import Path
    from oracle_brain.ingest import originals
    from oracle_brain.operating_model.source_receipts import SourceRef
    actual=originals.parser_identity(reader_model='fixture-reader',reviewer_model='fixture-reviewer',config_id='fixture')
    original=Path.read_bytes
    def prior_source(path):
        return b'prior-invented-reviewed-parser-source' if path==Path(originals.__file__) else original(path)
    with monkeypatch.context() as scoped:
        scoped.setattr(Path,'read_bytes',prior_source)
        historical=originals.parser_identity(reader_model='fixture-reader',reviewer_model='fixture-reviewer',config_id='fixture')
    assert actual!=historical
    # Pure compatibility only: old registered identities retain their byte values;
    # actual SQL history/serving is covered by the retained role fixtures.
    old=SourceRef(workspace_id=uuid4(),source_id=uuid4(),revision=1,original_sha256='a'*64,
        reading_sha256='b'*64,parser_id=historical)
    assert SourceRef.model_validate_json(old.model_dump_json()).parser_id==historical
    assert originals.parser_identity(reader_model='fixture-reader',reviewer_model='fixture-reviewer',config_id='fixture')==actual
