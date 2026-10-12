# Native alternate reading: preparation only

This is a serialization proposal, not an admitted reading or an execution approval.
No private corpus was read for this preparation. Existing originals, eight qualified
readings, native capture and receipts remain immutable. No original is parsed again.

## Existing contract and permitted boundary

`ReadingProvenance` binds original_hash, content_hash, parser_identity, content_type,
evidence_kind, page_count and review_receipt. Its strict schema has no alternate
reading collection. `authority_adapter.current` consumes exactly one current
`original` and its `original-metadata`; `holistic_runtime.read_corpus` likewise
consumes the current reading. Therefore a separate protected representation can
be prepared append-only, but cannot be silently imported as the current reading,
inherit an old review_receipt, or qualify itself as a complete visual transcription.
`read_original` requires an independent whole-original review for visual inputs;
the native UTF-8 exception applies only to actual UTF-8 originals, not OCR output.

The proposed artifact is explicitly `unqualified-native-alternate-v1`. A later
root decision and independently reviewed source-qualification contract must bind
the raw source-to-capture accuracy and completeness, parser/model provenance,
source-reading representation and any eventual source version/adoption. This
packet issues no ReadingProvenance or SourceRef and performs no ledger write.

## Exact future input boundary

The root-reviewed manifest must pin completion
8ae0e0182324b563b10d5acb2c43a87adf677c3933d35ee8ffa8a3513befc74c,
capture operator 8fc05bea47c07034d90f294665b73f0293cf1b51fb1644c9f8cd93afbdcf9175,
capture configuration 4c6bf1a32ffe26894e99c76440f20eda19faa58318851d0f5444058dbb82d681,
all 26 original byte hashes, eight unchanged qualified reading hashes, 33 page
records and every captured page/group hash chain. Independent custody proof is
79bd96fa3a837a702ad283dc2f1f613dce4de6f2f1a8801f0e11e05ede53b0ca.
Future action checks owner/modes, hashes before and after, immutable input mounts,
network denial, fresh 0700 output and 0600 files. Maximum input/output 256 MiB,
single worker, two threads, 8 GiB address space, 120 CPU seconds and 180 wall
seconds for serialization only. Exact approved operator/configuration/input hashes
are required before opening any private capture, even read-only. This proposal's
public fixture tests open no private captures.

## Representation

Order is explicit page number, native text structural index, then native table
index and native cell row/column/end addresses. It is a deterministic serialization
order, not a claim of business or visual reading order. No stripping, normalization,
case changes, fuzzy matching or substring search occurs. Each retained source_text
is appended verbatim and its Python Unicode code-point start/end recorded during
append. Empty segments have equal offsets. Separators are separately identified
formatting spans and never source evidence. Each segment additionally binds its
UTF-8 hash, original hash, capture file hash, page, native structural identity and
provenance (bbox/coordinate origin/native charspan/parent/table addresses).
Cell identity includes parent table, page and all row/column bounds. Duplicate
identities refuse; repeated text is valid and gets distinct exact addresses.
Multi-page native items retain each native provenance without guessing how text
splits across pages; repeated whole item text is declared representation duplication,
not a native charspan projection. Native caption refs are metadata pointing to
existing native text IDs, never injected labels or additional caption text.

Only native text and cell source_text enter this representation. No geometry,
IDs, labels, captions inferred from pictures, old semantic description or business
classification enter its text. Native characters and literal original-byte records
remain separate retained evidence; their future representation needs its own exact
contract. Pictures without existing native text associations remain explicit gaps.

## Native charspan finding

Pinned primary SDK sources:
[TextItem 2.99.0](https://github.com/docling-project/docling-core/blob/v2.99.0/docling_core/types/doc/items/text.py),
[native reading order 2.130.0](https://github.com/docling-project/docling/blob/v2.130.0/docling/models/stages/reading_order/readingorder_model.py).
TextItem keeps distinct untreated `orig` and sanitized `text`. Reading-order code
creates spans from intermediate text before document item processing. Thus a raw
span is not automatically an index into retained sanitized source_text; the 70
reported spans exceeding retained text length are preserved unchanged. Their exact
historical cause is not asserted. New serialization offsets are a separate namespace
and cannot repair or reinterpret native spans. This proposal does not reconstruct
discarded orig or claim source_text is the untouched original document.

## Generic serialization core and public roundtrip fixtures

This pure core accepts prevalidated segment descriptors. A future operator must
derive descriptors only from the reviewed captured files and pinned manifest;
this core is not a trust boundary and cannot qualify arbitrary caller mappings.

```python
import hashlib
import re

def serialize(pages):
    text, segments, separators, seen = '', [], [], set()
    last_page = 0
    for page, items in pages:
        if type(page) is not int or page <= last_page:
            raise ValueError('invalid page census')
        last_page = page
        for item in items:
            kind, ref, value, provenance = item
            if kind not in ('native_text_region', 'table_cell'):
                raise ValueError('invalid segment kind')
            if not isinstance(ref, tuple) or not ref:
                raise ValueError('invalid structural identity')
            pattern = r'#/texts/[0-9]+' if kind == 'native_text_region' else r'#/tables/[0-9]+'
            if not isinstance(ref[0], str) or not re.fullmatch(pattern, ref[0]):
                raise ValueError('invalid structural reference')
            key = (page, kind, ref)
            if key in seen:
                raise ValueError('duplicate segment identity')
            seen.add(key)
            if not isinstance(value, str) or not isinstance(provenance, dict):
                raise ValueError('invalid native segment')
            if text:
                separators.append((len(text), len(text) + 1))
                text += '\n'
            start = len(text)
            text += value
            end = len(text)
            segments.append(dict(page=page, kind=kind, native_identity=ref,
                start=start, end=end, source_text_sha256=hashlib.sha256(value.encode()).hexdigest(),
                native_provenance=provenance))
            if text[start:end] != value:
                raise ValueError('roundtrip failure')
    return text, segments, separators

def public_tests():
    provenance = {'charspan': [0, 99], 'caption_refs': ['#/texts/1']}
    pages = [(1, [('native_text_region', ('#/texts/0',), 'Repeated Ω', provenance),
                  ('native_text_region', ('#/texts/1',), 'Public caption', {}),
                  ('table_cell', ('#/tables/0', 0, 1, 0, 1), 'Repeated Ω', {})]),
             (2, [('native_text_region', ('#/texts/0',), 'Repeated Ω', {}),
                  ('table_cell', ('#/tables/1', 0, 1, 0, 1), '', {})])]
    text, segments, separators = serialize(pages)
    values = [item[2] for _, items in pages for item in items]
    assert len(segments) == 5
    assert [text[s['start']:s['end']] for s in segments] == values
    assert segments[0]['native_provenance']['charspan'] == [0, 99]
    assert segments[0]['native_provenance']['caption_refs'] == ['#/texts/1']
    assert all(text[a:b] == '\n' for a, b in separators)
    assert [s['source_text_sha256'] for s in segments] == [hashlib.sha256(v.encode()).hexdigest() for v in values]
    for bad in ([(1, pages[0][1] + [pages[0][1][0]])], list(reversed(pages)),
                [(1, [('picture_region', ('#/pictures/0',), 'Invented', {})])],
                [(1, [('native_text_region', ('authored-label',), 'Public', {})])]):
        try:
            serialize(bad)
        except ValueError:
            pass
        else:
            raise AssertionError('invalid fixture accepted')
    return {'public_roundtrip_cases': 5, 'public_denial_cases': 4}
```

No private representation or qualification receipt exists from this preparation.
The remaining qualification gate is accuracy/completeness against the original,
not whether deterministic offsets can be recorded. No company question generation,
grading, provider dispatch, source import or semantic acceptance is authorized here.
