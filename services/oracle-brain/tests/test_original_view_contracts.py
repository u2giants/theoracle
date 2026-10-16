"""Invented review metadata proves pure binding only, not actual qualification."""
from dataclasses import asdict
import hashlib
import pytest
from test_binary_documents import docx
from oracle_brain.ingest.binary_documents import native_binary_view,DOCX
from oracle_brain.ingest.originals import ReadingProvenance
from oracle_brain.ingest.original_view_contracts import *

def sha(text):return hashlib.sha256(text.encode()).hexdigest()

@pytest.fixture
def case():
    original=docx();native=native_binary_view(original,DOCX)
    view=OriginalViewV1(view_id='page1',kind='page',anchor='page:1',image_sha256='1'*64,
        width=100,height=200,covered_locators=tuple(b.locator for b in native.blocks))
    manifest=OriginalViewManifestV1(original_sha256=native.original_sha256,content_type=DOCX,
        byte_count=len(original),native_inventory_hash=seal(asdict(native)),renderer_hash='2'*64,
        renderer_profile_hash='3'*64,renderer_binary_hash='4'*64,fonts_hash='5'*64,views=(view,))
    reading='😀 '+native.reading
    p=ReadingProvenance(original_hash=native.original_sha256,content_hash=sha(reading),parser_identity='6'*64,
        content_type=DOCX,evidence_kind='visual_transcription',page_count=1,review_receipt='7'*64)
    entries=tuple(QualifiedReadingLocatorV1(source_locator=b.locator,view_id='page1',image_sha256='1'*64,
        region=(0,i*10,80,10),start=b.start+2,end=b.end+2,quote=b.text,quote_sha256=sha(b.text),
        basis='exact-native',ambiguous=False,review_receipt=p.review_receipt) for i,b in enumerate(native.blocks))
    mapping=QualifiedReadingLocatorMapV1(original_sha256=native.original_sha256,reading_sha256=sha(reading),
        parser_identity=p.parser_identity,review_receipt=p.review_receipt,manifest_hash=seal(manifest.model_dump(mode='json')),
        native_inventory_hash=manifest.native_inventory_hash,entries=entries)
    return dict(native=native,manifest=manifest,mapping=mapping,original=original,reading=reading,current_provenance=p)

def test_unicode_current_reading_mapping_is_distinct_from_native_offsets(case):
    validate_original_view_lineage(**case)
    assert case['mapping'].entries[0].start==2
    assert len('😀 '.encode())==5
    assert case['native'].qualified is False

@pytest.mark.parametrize('field',['original_sha256','reading_sha256','parser_identity','review_receipt','manifest_hash','native_inventory_hash'])
def test_wrong_revision_reading_review_or_render_seal_denies(case,field):
    case['mapping']=case['mapping'].model_copy(update={field:'f'*64})
    with pytest.raises(ValueError):validate_original_view_lineage(**case)

@pytest.mark.parametrize('change',[{'start':5},{'end':9999},{'ambiguous':True},{'quote':'invented'},
    {'quote_sha256':'f'*64},{'view_id':'orphan'},{'image_sha256':'f'*64},{'region':(-1,0,10,10)},
    {'region':(90,0,20,10)},{'review_receipt':'f'*64}])
def test_inexact_or_ambiguous_citation_denies(case,change):
    m=case['mapping'];case['mapping']=m.model_copy(update={'entries':(m.entries[0].model_copy(update=change),*m.entries[1:])})
    with pytest.raises(ValueError):validate_original_view_lineage(**case)

@pytest.mark.parametrize('damage',['missing','duplicate','extra','overlap','unread','unsupported','inventory'])
def test_every_inventory_region_accounted_without_invented_completeness(case,damage):
    m=case['mapping'];v=case['manifest']
    if damage=='missing':m=m.model_copy(update={'entries':m.entries[:-1]})
    elif damage=='duplicate':m=m.model_copy(update={'entries':(*m.entries[:-1],m.entries[0])})
    elif damage=='extra':m=m.model_copy(update={'entries':(*m.entries,m.entries[0].model_copy(update={'source_locator':'unknown'}))})
    elif damage=='overlap':m=m.model_copy(update={'entries':(m.entries[0],m.entries[1].model_copy(update={'start':0}),*m.entries[2:])})
    elif damage=='unread':v=v.model_copy(update={'unread_locators':('unknown',)})
    elif damage=='unsupported':v=v.model_copy(update={'unsupported':('hidden animation',)})
    else:v=v.model_copy(update={'views':(v.views[0].model_copy(update={'covered_locators':v.views[0].covered_locators[:-1]}),)})
    case['manifest']=v;case['mapping']=m.model_copy(update={'manifest_hash':seal(v.model_dump(mode='json'))})
    with pytest.raises(ValueError):validate_original_view_lineage(**case)

def test_visual_normalization_requires_explicit_reviewed_basis(case):
    m=case['mapping'];e=m.entries[0];reading=case['reading'].replace(e.quote,'Design receives ART.',1)
    delta=len('Design receives ART.')-len(e.quote)
    entries=(e.model_copy(update={'quote':'Design receives ART.','quote_sha256':sha('Design receives ART.'),'end':e.end+delta}),
        *(x.model_copy(update={'start':x.start+delta,'end':x.end+delta}) for x in m.entries[1:]))
    case['reading']=reading;case['current_provenance']=case['current_provenance'].model_copy(update={'content_hash':sha(reading)})
    case['mapping']=m.model_copy(update={'reading_sha256':sha(reading),'entries':entries})
    with pytest.raises(ValueError,match='native mapping'):validate_original_view_lineage(**case)
    case['mapping']=case['mapping'].model_copy(update={'entries':(entries[0].model_copy(update={'basis':'independently-reviewed-visual'}),*entries[1:])})
    validate_original_view_lineage(**case)

def test_duplicate_inventory_and_boolean_pixel_precision_are_rejected(case):
    v=case['manifest'].views[0]
    with pytest.raises(ValueError):OriginalViewV1.model_validate(v.model_dump()|{'covered_locators':(v.covered_locators[0],)*2})
    with pytest.raises(ValueError):QualifiedReadingLocatorV1.model_validate(case['mapping'].entries[0].model_dump()|{'region':(True,0,10,10)})
