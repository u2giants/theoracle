"""Unqualified, in-memory Docling JSON serialization preparation.

No files, ledger, provider, authority or source qualification are accessed here.
The input shape follows docling-core v2.99.0 DoclingDocument/TextItem/TableCell.
Compatibility with retained private captures requires separately admitted proof.
Native charspans are retained metadata, never offsets into serialized text.
"""
from copy import deepcopy
import hashlib
import math
import re


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
        raise ValueError('exact byte hash required')
    return value


def _integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError('invalid native integer')
    return value


def _bbox(value):
    if (not isinstance(value, dict) or value.get('coord_origin') not in {'TOPLEFT', 'BOTTOMLEFT'}
            or any(type(value.get(k)) not in (int, float) or not math.isfinite(value[k])
                   for k in ('l', 't', 'r', 'b'))):
        raise ValueError('invalid native bounding box')
    return deepcopy(value)


def _provenance(item, pages):
    values = item.get('prov')
    if not isinstance(values, list):
        raise ValueError('native provenance list required')
    for value in values:
        if not isinstance(value, dict):
            raise ValueError('invalid native provenance')
        page = _integer(value.get('page_no'), 1)
        span = value.get('charspan')
        if page not in pages or not isinstance(span, list) or len(span) != 2:
            raise ValueError('invalid native page/span')
        _integer(span[0]); _integer(span[1])
        if span[1] < span[0]:
            raise ValueError('reversed native span')
        _bbox(value.get('bbox'))
    return deepcopy(values)


def serialize_docling(document, *, original_hash, capture_hash):
    """Return an unqualified alternate; hashes are labels, not admission proof.

    Preserve text verbatim, structural references and explicit unsupported gaps.
    Cells need a single-page parent table; rich cells are not rendered or guessed.
    The caller must separately validate custody, exact input format and all limits.
    """
    original_hash, capture_hash = _hash(original_hash), _hash(capture_hash)
    if (not isinstance(document, dict) or document.get('schema_name') != 'DoclingDocument'
            or document.get('version') != '1.10.0'):
        raise ValueError('native Docling document required')
    raw_pages = document.get('pages')
    if not isinstance(raw_pages, dict):
        raise ValueError('explicit page census required')
    pages = {}
    for key, page in raw_pages.items():
        if not isinstance(key, str) or not re.fullmatch(r'[1-9][0-9]*', key):
            raise ValueError('invalid page census key')
        number = int(key)
        if not isinstance(page, dict) or _integer(page.get('page_no'), 1) != number:
            raise ValueError('page census identity mismatch')
        pages[number] = deepcopy(page)
    if sorted(pages) != list(range(1, len(pages) + 1)) or not pages:
        raise ValueError('complete contiguous page census required')
    items, gaps, refs = [], [], set()
    for kind in ('texts', 'tables', 'pictures'):
        values = document.get(kind, [])
        if not isinstance(values, list):
            raise ValueError('invalid native item collection')
        for index, item in enumerate(values):
            ref = f'#/{kind}/{index}'
            if not isinstance(item, dict) or item.get('self_ref') != ref:
                raise ValueError('native structural identity mismatch')
            refs.add(ref)
    def captions(item):
        values = item.get('captions', [])
        if (not isinstance(values, list) or any(not isinstance(c, dict)
                or c.get('$ref') not in refs or not c['$ref'].startswith('#/texts/') for c in values)):
            raise ValueError('caption must reference existing native text')
        return deepcopy(values)
    for index, item in enumerate(document.get('texts', [])):
        ref = f'#/texts/{index}'
        prov = _provenance(item, pages)
        value = item.get('text')
        if not isinstance(value, str):
            raise ValueError('native text required')
        if not prov:
            gaps.append(dict(native_identity=ref, reason='text_without_page_provenance'))
        item_pages = sorted({p['page_no'] for p in prov})
        for page in item_pages:
            items.append((page, 0, index, (), value,
                          dict(native_identity=ref, kind='native_text_region',
                               native_provenance=prov, representation_duplication=len(item_pages) > 1)))
    for index, item in enumerate(document.get('tables', [])):
        ref = f'#/tables/{index}'
        prov = _provenance(item, pages)
        caption_refs = captions(item)
        data = item.get('data')
        if not isinstance(data, dict) or not isinstance(data.get('table_cells'), list):
            raise ValueError('native table data required')
        rows, columns = _integer(data.get('num_rows')), _integer(data.get('num_cols'))
        seen = set()
        for cell in data['table_cells']:
            if not isinstance(cell, dict):
                raise ValueError('invalid native table cell')
            address = tuple(_integer(cell.get(k)) for k in ('start_row_offset_idx',
                'end_row_offset_idx', 'start_col_offset_idx', 'end_col_offset_idx'))
            r0, r1, c0, c1 = address
            if not (r0 < r1 <= rows and c0 < c1 <= columns) or address in seen:
                raise ValueError('invalid or duplicate native cell address')
            seen.add(address)
            if cell.get('bbox') is not None:
                _bbox(cell['bbox'])
            if len({p['page_no'] for p in prov}) != 1 or 'ref' in cell:
                gaps.append(dict(native_identity=(ref, *address),
                    native_provenance=prov, cell_metadata=deepcopy(cell), caption_refs=caption_refs,
                    reason='rich_cell_not_supported' if 'ref' in cell else 'cell_parent_not_single_page'))
                continue
            if not isinstance(cell.get('text'), str):
                raise ValueError('native cell text required')
            items.append((prov[0]['page_no'], 1, index, address, cell['text'],
                dict(native_identity=(ref, *address), kind='table_cell', native_provenance=prov,
                     cell_metadata=deepcopy(cell), caption_refs=caption_refs, representation_duplication=False)))
        if not data['table_cells']:
            gaps.append(dict(native_identity=ref, reason='table_without_cells',
                             native_provenance=prov, caption_refs=caption_refs))
    for index, item in enumerate(document.get('pictures', [])):
        ref = f'#/pictures/{index}'
        prov = _provenance(item, pages)
        caption_refs = captions(item)
        gaps.append(dict(native_identity=ref, reason='picture_not_transcribed',
                         native_provenance=prov, caption_refs=caption_refs))
    for kind in ('key_value_items', 'form_items', 'field_regions', 'field_items'):
        values = document.get(kind, [])
        if not isinstance(values, list):
            raise ValueError('invalid unsupported item collection')
        if values:
            gaps.append(dict(native_kind=kind, reason='unsupported_native_kind', count=len(values)))
    chunks, segments, separators, position = [], [], [], 0
    for page, _, _, _, value, metadata in sorted(items, key=lambda x: x[:4]):
        if segments:
            separators.append(dict(start=position, end=position + 1))
            chunks.append('\n'); position += 1
        start = position
        chunks.append(value); position += len(value)
        segments.append(dict(metadata, page=page, start=start, end=position,
            source_text_sha256=hashlib.sha256(value.encode('utf-8')).hexdigest(),
            original_hash=original_hash, capture_hash=capture_hash))
    text = ''.join(chunks)
    return dict(status='unqualified-native-alternate-v1', text=text,
                segments=segments, separators=separators, gaps=gaps, pages=pages,
                source_qualified=False, ledger_adopted=False, input_schema='DoclingDocument:1.10.0',
                decoder_basis='docling-core:2.99.0')
