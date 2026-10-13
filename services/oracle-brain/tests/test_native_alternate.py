"""Invented Docling JSON only; no private capture or original access."""
from copy import deepcopy
import hashlib

import pytest

from oracle_brain.operating_model.native_alternate import serialize_docling


HASH = 'a' * 64
BOX = dict(l=0, t=10, r=20, b=0, coord_origin='BOTTOMLEFT')


def provenance(page=1):
    return dict(page_no=page, bbox=deepcopy(BOX), charspan=[0, 99])


def fixture():
    return dict(schema_name='DoclingDocument', version='1.10.0',
        pages={'1': dict(page_no=1), '2': dict(page_no=2)},
        texts=[dict(self_ref='#/texts/0', text='Repeated Ω', prov=[provenance(), provenance(2)]),
               dict(self_ref='#/texts/1', text='', prov=[provenance()])],
        tables=[dict(self_ref='#/tables/0', prov=[provenance()],
            data=dict(num_rows=1, num_cols=1, table_cells=[dict(text='Repeated Ω',
                start_row_offset_idx=0, end_row_offset_idx=1,
                start_col_offset_idx=0, end_col_offset_idx=1, bbox=deepcopy(BOX))]))],
        pictures=[dict(self_ref='#/pictures/0', prov=[provenance()],
                       captions=[{'$ref': '#/texts/0'}])])


def run(document):
    return serialize_docling(document, original_hash=HASH, capture_hash='b' * 64)


def test_roundtrip_preserves_native_spans_unicode_empty_cells_and_duplication():
    original = fixture()
    before = deepcopy(original)
    result = run(original)
    values = ['Repeated Ω', '', 'Repeated Ω', 'Repeated Ω']
    assert [result['text'][s['start']:s['end']] for s in result['segments']] == values
    assert [s['source_text_sha256'] for s in result['segments']] == [
        hashlib.sha256(v.encode()).hexdigest() for v in values]
    assert all(result['text'][s['start']:s['end']] == '\n' for s in result['separators'])
    assert result['segments'][0]['native_provenance'][0]['charspan'] == [0, 99]
    assert result['segments'][0]['representation_duplication'] is True
    assert result['segments'][2]['native_identity'] == ('#/tables/0', 0, 1, 0, 1)
    assert result['gaps'][0]['reason'] == 'picture_not_transcribed'
    assert original == before
    assert result['status'] == 'unqualified-native-alternate-v1'
    assert result['source_qualified'] is result['ledger_adopted'] is False
    result['segments'][0]['native_provenance'][0]['charspan'][1] = 1
    assert original == before


@pytest.mark.parametrize('kind', ['rich', 'multipage', 'missing'])
def test_cells_with_unsupported_parent_or_rich_content_are_explicit_gaps(kind):
    doc = fixture()
    table = doc['tables'][0]
    if kind == 'rich':
        table['data']['table_cells'][0]['ref'] = {'$ref': '#/texts/0'}
    elif kind == 'multipage':
        table['prov'].append(provenance(2))
    else:
        table['prov'] = []
    result = run(doc)
    assert not any(s['kind'] == 'table_cell' for s in result['segments'])
    assert any('cell' in g['reason'] for g in result['gaps'])


def test_native_kinds_and_unlocated_text_are_never_silently_lost():
    doc = fixture()
    doc['texts'][0]['prov'] = []
    doc['key_value_items'] = [{'self_ref': '#/key_value_items/0'}]
    result = run(doc)
    assert {g['reason'] for g in result['gaps']} >= {
        'unsupported_native_kind', 'text_without_page_provenance'}


@pytest.mark.parametrize('damage', ['page_hole', 'page_mismatch', 'text_id', 'table_id',
    'duplicate_cell', 'bad_cell_bounds', 'reversed_span', 'bool_span', 'missing_text',
    'nonfinite_box', 'unknown_caption', 'duplicate_page_provenance', 'missing_schema', 'schema_version'])
def test_malformed_native_records_refuse(damage):
    doc = fixture()
    cell = doc['tables'][0]['data']['table_cells'][0]
    if damage == 'page_hole': del doc['pages']['1']
    elif damage == 'page_mismatch': doc['pages']['1']['page_no'] = 2
    elif damage == 'text_id': doc['texts'][0]['self_ref'] = '#/texts/9'
    elif damage == 'table_id': doc['tables'][0]['self_ref'] = '#/tables/9'
    elif damage == 'duplicate_cell': doc['tables'][0]['data']['table_cells'].append(deepcopy(cell))
    elif damage == 'bad_cell_bounds': cell['end_row_offset_idx'] = 2
    elif damage == 'reversed_span': doc['texts'][0]['prov'][0]['charspan'] = [3, 1]
    elif damage == 'bool_span': doc['texts'][0]['prov'][0]['charspan'] = [False, 1]
    elif damage == 'missing_text': del doc['texts'][0]['text']
    elif damage == 'nonfinite_box': doc['texts'][0]['prov'][0]['bbox']['l'] = float('nan')
    elif damage == 'unknown_caption': doc['pictures'][0]['captions'] = [{'$ref': '#/texts/8'}]
    elif damage == 'duplicate_page_provenance': doc['texts'][0]['prov'].append(provenance())
    elif damage == 'missing_schema': del doc['schema_name']
    elif damage == 'schema_version': doc['version'] = '1.11.0'
    with pytest.raises(ValueError): run(doc)


def test_hash_labels_must_be_exact_but_never_grant_admission():
    with pytest.raises(ValueError):
        serialize_docling(fixture(), original_hash='unknown', capture_hash=HASH)


def test_table_caption_and_empty_table_are_explicit_metadata():
    doc = fixture()
    doc['tables'][0]['captions'] = [{'$ref': '#/texts/1'}]
    assert run(doc)['segments'][2]['caption_refs'] == [{'$ref': '#/texts/1'}]
    doc['tables'][0]['data']['table_cells'] = []
    assert any(g['reason'] == 'table_without_cells' for g in run(doc)['gaps'])
