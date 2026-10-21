"""Actual generated binary containers; no mocked parser, provider or source grant."""
import hashlib,io,zipfile
import pytest
from oracle_brain.ingest.binary_documents import (native_binary_view,BinaryRejected,DOCX,XLSX,PPTX,MAX_ORIGINAL_BYTES)

W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
S='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
P='http://schemas.openxmlformats.org/presentationml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL='http://schemas.openxmlformats.org/package/2006/relationships'
TYPES='http://schemas.openxmlformats.org/package/2006/content-types'


def package(parts):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,data in parts.items():z.writestr(name,data)
    return out.getvalue()


def content_types(part,mime):
    return f'<Types xmlns="{TYPES}"><Override PartName="/{part}" ContentType="{mime}"/></Types>'


def docx(extra=None):
    return package({'[Content_Types].xml':content_types('word/document.xml',DOCX+'.main+xml'),
        'word/document.xml':f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>设计 sends ART.</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Factory receives ART.</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>',
        'word/header1.xml':f'<w:hdr xmlns:w="{W}"><w:p><w:r><w:t>Private header</w:t></w:r></w:p></w:hdr>',**(extra or {})})


def xlsx(extra=None):
    return package({'[Content_Types].xml':content_types('xl/workbook.xml',XLSX+'.main+xml'),
        'xl/workbook.xml':f'<workbook xmlns="{S}" xmlns:r="{R}"><sheets><sheet name="设计" sheetId="1" r:id="sheet"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels':f'<Relationships xmlns="{REL}"><Relationship Id="sheet" Target="worksheets/sheet1.xml"/></Relationships>',
        'xl/sharedStrings.xml':f'<sst xmlns="{S}"><si><t>ART 批准</t></si></sst>',
        'xl/worksheets/sheet1.xml':f'<worksheet xmlns="{S}"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><f>WEBSERVICE("https://example.invalid")</f><v>17</v></c><c r="C1"><f>1+2</f></c></row></sheetData><mergeCells><mergeCell ref="A1:B1"/></mergeCells></worksheet>',**(extra or {})})


def pptx(extra=None):
    return package({'[Content_Types].xml':content_types('ppt/presentation.xml',PPTX+'.main+xml'),
        'ppt/presentation.xml':f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst><p:sldId id="1" r:id="second"/><p:sldId id="2" r:id="first"/></p:sldIdLst></p:presentation>',
        'ppt/_rels/presentation.xml.rels':f'<Relationships xmlns="{REL}"><Relationship Id="first" Target="slides/slide1.xml"/><Relationship Id="second" Target="slides/slide2.xml"/></Relationships>',
        'ppt/slides/slide1.xml':f'<p:sld xmlns:p="{P}" xmlns:a="{A}"><a:p><a:r><a:t>Second in order</a:t></a:r></a:p></p:sld>',
        'ppt/slides/slide2.xml':f'<p:sld xmlns:p="{P}" xmlns:a="{A}"><a:p><a:r><a:t>First 设计</a:t></a:r></a:p></p:sld>',
        'ppt/slides/_rels/slide2.xml.rels':f'<Relationships xmlns="{REL}"><Relationship Id="notes" Type="{R}/notesSlide" Target="../notesSlides/notesSlide2.xml"/></Relationships>',
        'ppt/notesSlides/notesSlide2.xml':f'<p:notes xmlns:p="{P}" xmlns:a="{A}"><a:p><a:r><a:t>Speaker notes</a:t></a:r></a:p></p:notes>',**(extra or {})})


def pdf(text='Actual original ART'):
    # Minimal real PDF with cross-reference table and native Helvetica text.
    stream=f'BT /F1 12 Tf 20 100 Td ({text}) Tj ET'.encode()
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
    data=b'%PDF-1.4\n';offsets=[]
    for i,obj in enumerate(objects,1):offsets.append(len(data));data+=str(i).encode()+b' 0 obj\n'+obj+b'\nendobj\n'
    xref=len(data);data+=b'xref\n0 6\n0000000000 65535 f \n'+b''.join(f'{o:010} 00000 n \n'.encode() for o in offsets)
    return data+f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode()


@pytest.mark.parametrize('make,mime',[(docx,DOCX),(xlsx,XLSX),(pptx,PPTX),(pdf,'application/pdf')])
def test_real_binary_original_hash_exact_native_character_spans_and_no_qualification(make,mime):
    raw=make();view=native_binary_view(raw,mime)
    assert view.original_sha256==hashlib.sha256(raw).hexdigest()
    assert len(view.parser_identity)==64 and view==native_binary_view(raw,mime)
    assert view.blocks and view.review_reasons and view.qualified is False
    assert len({b.locator for b in view.blocks})==len(view.blocks)
    for b in view.blocks:assert view.reading[b.start:b.end]==b.text


def test_word_real_zip_contains_unicode_table_paragraph_and_header_locators():
    v=native_binary_view(docx(),DOCX)
    assert v.blocks[0].text=='设计 sends ART.' and v.blocks[0].end==len('设计 sends ART.')
    assert v.blocks[1].locator=='word/document.xml#paragraph:2'
    assert v.blocks[2].locator=='word/header1.xml#paragraph:1'


def test_spreadsheet_literal_formulas_cached_values_merges_never_execute():
    v=native_binary_view(xlsx(),XLSX);cells={dict(b.attributes)['cell']:b for b in v.blocks}
    assert cells['A1'].text=='ART 批准'
    attrs=dict(cells['B1'].attributes)
    assert attrs['formula']=='WEBSERVICE("https://example.invalid")' and attrs['cached_value']=='17'
    assert attrs['executed']=='false' and attrs['cached_value_trusted']=='false' and attrs['merges']=='A1:B1'
    assert 'no cached value' in ' '.join(v.review_reasons)


def test_presentation_uses_actual_relationship_order_and_retains_notes():
    v=native_binary_view(pptx(),PPTX)
    assert [b.text for b in v.blocks]==['First 设计','Speaker notes','Second in order']
    assert v.blocks[0].locator.startswith('ppt/slides/slide2.xml#')
    assert dict(v.blocks[-1].attributes)['slide']=='2'


@pytest.mark.parametrize('extra,reason',[
    ({'../escaped.xml':'x'},'unsafe'),({'word/vbaProject.bin':b'not executed'},'active'),
    ({'word/_rels/document.xml.rels':f'<Relationships xmlns="{REL}"><Relationship Id="x" Target="https://example.invalid" TargetMode="External"/></Relationships>'},'external'),
    ({'word/header1.xml':'<!DOCTYPE x [<!ENTITY e "bad">]><x>&e;</x>'},'entities'),
    ({'word/header1.xml':'<bad'},'malformed'),
    ({'word/header1.xml':'x'*(2*1024*1024)},'expansion'),
])
def test_hostile_real_zip_fails_closed(extra,reason):
    with pytest.raises(BinaryRejected,match=reason):native_binary_view(docx(extra),DOCX)


def test_duplicate_zip_parts_and_wrong_declared_type_refused():
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        z.writestr('[Content_Types].xml','<x/>')
        with pytest.warns(UserWarning):z.writestr('[Content_Types].xml','<x/>')
    with pytest.raises(BinaryRejected,match='duplicate'):native_binary_view(out.getvalue(),DOCX)
    with pytest.raises(BinaryRejected,match='content type'):native_binary_view(docx(),XLSX)


@pytest.mark.parametrize('data,mime',[(b'',DOCX),(b'x'*(MAX_ORIGINAL_BYTES+1),DOCX),(b'broken',DOCX),(b'%PDF-broken','application/pdf')])
def test_empty_oversize_and_corrupt_originals_rejected(data,mime):
    with pytest.raises(BinaryRejected):native_binary_view(data,mime)


def test_nested_word_textbox_is_not_double_counted_and_revisions_need_review():
    body=f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>Outer</w:t></w:r><w:drawing><w:p><w:r><w:t>Box</w:t></w:r></w:p></w:drawing><w:del><w:r><w:delText>Deleted</w:delText></w:r></w:del></w:p></w:body></w:document>'
    v=native_binary_view(docx({'word/document.xml':body}),DOCX)
    assert [b.text for b in v.blocks][:2]==['Outer','Box']
    assert 'Deleted' not in v.reading and any('revisions' in r for r in v.review_reasons)


def test_missing_cached_value_is_not_false_zero_and_negative_shared_index_denies():
    v=native_binary_view(xlsx(),XLSX)
    c=next(b for b in v.blocks if dict(b.attributes).get('cell')=='C1')
    assert dict(c.attributes)['cached_value']=='' and 'Cached value: ' in c.text
    bad=f'<worksheet xmlns="{S}"><sheetData><row><c r="A1" t="s"><v>-1</v></c></row></sheetData></worksheet>'
    with pytest.raises(BinaryRejected,match='shared string'):native_binary_view(xlsx({'xl/worksheets/sheet1.xml':bad}),XLSX)


def test_duplicate_cell_coordinate_and_relationship_escape_deny():
    bad=f'<worksheet xmlns="{S}"><sheetData><row><c r="A1"><v>1</v></c><c r="A1"><v>2</v></c></row></sheetData></worksheet>'
    with pytest.raises(BinaryRejected,match='duplicate cell'):native_binary_view(xlsx({'xl/worksheets/sheet1.xml':bad}),XLSX)
    rel=f'<Relationships xmlns="{REL}"><Relationship Id="sheet" Target="../../escape.xml"/></Relationships>'
    with pytest.raises(BinaryRejected,match='outside package'):native_binary_view(xlsx({'xl/_rels/workbook.xml.rels':rel}),XLSX)


def test_encrypted_flag_symlink_and_utf16_entity_document_deny():
    raw=bytearray(docx())
    # Both real ZIP metadata records declare encrypted input; no decryption call.
    for signature,offset in ((b'PK\x03\x04',6),(b'PK\x01\x02',8)):
        pos=raw.find(signature);raw[pos+offset]|=1
    with pytest.raises(BinaryRejected,match='encrypted'):native_binary_view(bytes(raw),DOCX)
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        item=zipfile.ZipInfo('link');item.external_attr=(0o120777<<16);z.writestr(item,'target')
    with pytest.raises(BinaryRejected,match='symlink'):native_binary_view(out.getvalue(),DOCX)
    bad='<!DOCTYPE x [<!ENTITY e "bad">]><x>&e;</x>'.encode('utf-16')
    with pytest.raises(BinaryRejected,match='encoding'):native_binary_view(docx({'word/header1.xml':bad}),DOCX)


def test_pdf_empty_native_page_remains_unqualified_and_limits_fail_closed(monkeypatch):
    import oracle_brain.ingest.binary_documents as module
    v=native_binary_view(pdf(''),'application/pdf')
    assert not v.blocks and not v.qualified and any('visual transcription' in r for r in v.review_reasons)
    monkeypatch.setattr(module,'MAX_READING_CHARS',3)
    with pytest.raises(BinaryRejected,match='character limit'):native_binary_view(pdf(),'application/pdf')
    with pytest.raises(BinaryRejected,match='reading limit'):native_binary_view(docx(),DOCX)
    monkeypatch.setattr(module,'MAX_BLOCKS',1)
    monkeypatch.setattr(module,'MAX_READING_CHARS',1000)
    with pytest.raises(BinaryRejected,match='block limit'):native_binary_view(docx(),DOCX)


def test_xml_structure_and_pdf_page_limits_are_terminal(monkeypatch):
    import oracle_brain.ingest.binary_documents as module
    deep='<x>'*130+'text'+'</x>'*130
    with pytest.raises(BinaryRejected,match='structure limit'):native_binary_view(docx({'word/header1.xml':deep}),DOCX)
    monkeypatch.setattr(module,'MAX_PDF_PAGES',0)
    with pytest.raises(BinaryRejected,match='page limit'):native_binary_view(pdf(),'application/pdf')


@pytest.mark.parametrize('ref',['XFE1','ZZZ1','A1048577','A9999999','ZZZ9999999'])
def test_spreadsheet_out_of_range_coordinates_are_terminal(ref):
    sheet=f'<worksheet xmlns="{S}"><sheetData><row><c r="{ref}"><v>literal</v></c></row></sheetData></worksheet>'
    with pytest.raises(BinaryRejected,match='invalid cell coordinate'):
        native_binary_view(xlsx({'xl/worksheets/sheet1.xml':sheet}),XLSX)


@pytest.mark.parametrize('ref',['A1','XFD1','A1048576','XFD1048576'])
def test_spreadsheet_exact_coordinate_boundaries_preserve_native_span(ref):
    sheet=f'<worksheet xmlns="{S}"><sheetData><row><c r="{ref}"><v>设计 ART</v></c></row></sheetData></worksheet>'
    view=native_binary_view(xlsx({'xl/worksheets/sheet1.xml':sheet}),XLSX)
    block,=view.blocks
    assert block.locator==f'xl/worksheets/sheet1.xml#cell:{ref}'
    assert view.reading[block.start:block.end]=='设计 ART' and not view.qualified


def _damage_zip_part(raw,name,*,compression=None,broken_deflate=False):
    # Alter real ZIP records, preserving a structurally readable directory.
    import struct
    data=bytearray(raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        info=archive.getinfo(name)
        if compression is not None:
            struct.pack_into('<H',data,info.header_offset+8,compression)
            position=archive.start_dir
            for part in archive.infolist():
                lengths=struct.unpack_from('<HHH',data,position+28)
                if part.filename==name:
                    struct.pack_into('<H',data,position+10,compression)
                    break
                position+=46+sum(lengths)
        if broken_deflate:
            name_length,extra_length=struct.unpack_from('<HH',data,info.header_offset+26)
            # BFINAL=1/BTYPE=3 is an invalid native DEFLATE block type.
            data[info.header_offset+30+name_length+extra_length]=7
    return bytes(data)


@pytest.mark.parametrize('damage',['unsupported-compression','corrupt-deflate'])
def test_actual_zip_decoder_failures_are_terminal_and_close_initialization(monkeypatch,damage):
    raw=_damage_zip_part(docx(),'[Content_Types].xml',
        compression=99 if damage=='unsupported-compression' else None,
        broken_deflate=damage=='corrupt-deflate')
    original=zipfile.ZipFile;opened=[]
    def tracked(*args,**kwargs):
        archive=original(*args,**kwargs);opened.append(archive);return archive
    monkeypatch.setattr(zipfile,'ZipFile',tracked)
    with pytest.raises(BinaryRejected,match='corrupt or unsupported'):
        native_binary_view(raw,DOCX)
    assert len(opened)==1 and opened[0].fp is None


def test_archive_closed_on_post_initialization_parse_refusal(monkeypatch):
    original=zipfile.ZipFile;opened=[]
    def tracked(*args,**kwargs):
        archive=original(*args,**kwargs);opened.append(archive);return archive
    raw=docx({'word/document.xml':'<malformed'})
    monkeypatch.setattr(zipfile,'ZipFile',tracked)
    with pytest.raises(BinaryRejected,match='malformed'):
        native_binary_view(raw,DOCX)
    assert len(opened)==1 and opened[0].fp is None
