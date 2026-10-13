"""Public invented snapshot fields copied only from the pinned producer contract."""
import copy
import pytest
from oracle_brain.operating_model import native_page_alternate as codec


def page():
    bbox=dict(l=0,t=10,r=10,b=0,coord_origin='BOTTOMLEFT')
    return dict(original_sha256='a'*64,reading_sha256='b'*64,qualified_reading_parser_id='invented',locator_parser_versions=codec.VERSIONS.copy(),asset_manifest_sha256=codec.PINS['asset_manifest_sha256'],source_ids=['invented'],native_page_number=1,unresolved=[],complete_region_register=False,diagram_node_geometry=False,native_locators=[dict(kind='native_text_region',page=1,native_text_id='#/texts/0',native_label_enum='text',bbox=bbox,charspan=[0,99],source_text='Ω🙂',alignment_status='missing_in_page',alignment=None),dict(kind='table_cell',page=1,parent_table_id='#/tables/0',parent_table_provenance=dict(page=1,bbox=bbox,charspan=[0,1]),bbox=None,row=0,row_end=1,column=0,column_end=1,source_text=' X ',alignment_status='ambiguous_in_page',alignment=None)])

def run(p):return codec.serialize_page(p,capture_hash='c'*64,expected_original='a'*64,expected_page=1)

def test_utf8_exact_native_order_and_raw_charspan_retention():
    result=run(page());assert result['text']=='Ω🙂 X '
    assert [(s['utf8_start'],s['utf8_end']) for s in result['segments']]==[(0,6),(6,9)]
    assert result['segments'][0]['native_metadata']['charspan']==[0,99]
    assert not any(result[k] for k in ('source_qualified','source_ref_issued','ledger_adopted','provider_authority','semantic_qualified'))

def test_nonrepresented_records_remain_explicit_without_text_injection():
    p=page();p['native_locators'].append(dict(kind='native_character',page=1,native_index=0,coordinate_origin='bottom_left',backend='pdfium',bbox=[0,0,1,1],source_text='never injected',alignment_status='unique',alignment={'quote':'never injected','start':0,'end':14}))
    result=run(p);assert result['text']=='Ω🙂 X ' and result['unrepresented_gaps'][0]['kind']=='native_character'
    assert 'never injected' not in str(result)

@pytest.mark.parametrize('damage',['schema','page','hash','version','duplicate','span','bbox','text','cell','link','status'])
def test_hostile_fields_refuse(damage):
    p=page();item=p['native_locators'][0]
    if damage=='schema':p['schema_name']='DoclingDocument'
    elif damage=='page':item['page']=2
    elif damage=='hash':p['original_sha256']='f'*64
    elif damage=='version':p['locator_parser_versions']={}
    elif damage=='duplicate':p['native_locators'].append(copy.deepcopy(p['native_locators'][1]))
    elif damage=='span':item['charspan']=[-1,2]
    elif damage=='bbox':item['bbox']['l']=float('nan')
    elif damage=='text':del item['source_text']
    elif damage=='cell':p['native_locators'][1]['column_end']=0
    elif damage=='link':item['parent_ref']='untrusted'
    else:item['alignment_status']='qualified'
    with pytest.raises(ValueError):run(p)

def test_duplicate_json_fields_and_nonfinite_refuse():
    for raw in (b'{"a":1,"a":2}',b'{"a":NaN}'):
        with pytest.raises(ValueError):codec.decode(raw)
