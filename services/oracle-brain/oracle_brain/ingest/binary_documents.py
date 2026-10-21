"""Bounded native views of original binaries, never reading/access qualification.

All bytes/text are private source material. No network, macros, formulas, fields
or links are executed. Page/part locators describe native extraction only; a
visual-review requirement is never a successful completeness/review receipt.
"""
from __future__ import annotations
import hashlib
import json
import sys
from importlib.metadata import version
import io
import posixpath
import re
import zipfile
import zlib
import lzma
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from .originals import MAX_ORIGINAL_BYTES,MAX_PDF_PAGES

DOCX='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
XLSX='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
PPTX='application/vnd.openxmlformats-officedocument.presentationml.presentation'
MAX_EXPANDED_BYTES=50*1024*1024
MAX_PARTS=2000
MAX_BLOCKS=5000
MAX_READING_CHARS=2_000_000
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    's':'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
    'p':'http://schemas.openxmlformats.org/presentationml/2006/main',
    'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}

class BinaryRejected(ValueError):
    """Terminal bounded structural refusal; no automatic repair/provider retry."""

@dataclass(frozen=True)
class NativeBlock:
    locator:str
    kind:str
    text:str
    start:int
    end:int
    # Immutable scalar metadata; formula/cached values stay explicitly separate.
    attributes:tuple[tuple[str,str],...]=()

@dataclass(frozen=True)
class NativeBinaryView:
    content_type:str
    original_sha256:str
    parser_identity:str
    reading:str
    blocks:tuple[NativeBlock,...]
    review_reasons:tuple[str,...]
    # Native text never claims semantic/visual completeness or authorization.
    qualified:bool=False

class _Builder:
    def __init__(self):self.blocks=[];self.reading='';self.reasons=set()
    def add(self,locator,kind,text,**attrs):
        if not isinstance(text,str):raise BinaryRejected('native text must be a string')
        if not text:return
        if len(self.blocks)>=MAX_BLOCKS:raise BinaryRejected('native block limit exceeded')
        prefix='\n' if self.blocks else ''
        start=len(self.reading)+len(prefix);end=start+len(text)
        if end>MAX_READING_CHARS:raise BinaryRejected('native reading limit exceeded')
        self.reading+=prefix+text
        self.blocks.append(NativeBlock(locator,kind,text,start,end,tuple(sorted((k,str(v)) for k,v in attrs.items()))))

class _Package:
    def __init__(self,data):
        try:self.zip=zipfile.ZipFile(io.BytesIO(data))
        except (zipfile.BadZipFile,ValueError) as exc:raise BinaryRejected('invalid OOXML package') from exc
        try:self._validate()
        except Exception:
            # An invalid package never leaves its opened archive behind.
            self.zip.close()
            raise
    def _validate(self):
        parts=self.zip.infolist();names=[i.filename for i in parts]
        if len(parts)>MAX_PARTS or len(names)!=len(set(names)):raise BinaryRejected('duplicate or excessive package parts')
        total=0
        for part in parts:
            name=part.filename
            if ('\\' in name or name.startswith('/') or posixpath.normpath(name)!=name.rstrip('/')
                or any(p in {'','..','.'} for p in name.rstrip('/').split('/'))):raise BinaryRejected('unsafe package path')
            if part.flag_bits&1:raise BinaryRejected('encrypted package unsupported')
            if (part.external_attr>>16)&0o170000==0o120000:raise BinaryRejected('package symlink denied')
            total+=part.file_size
            if total>MAX_EXPANDED_BYTES or (part.file_size>1024*1024 and part.file_size>200*max(1,part.compress_size)):
                raise BinaryRejected('package expansion limit exceeded')
            if any(x in name.lower() for x in ('vbaproject','embeddings/','activex/')):raise BinaryRejected('active or embedded content unsupported')
        self.names=set(names)
        self.xml('[Content_Types].xml')
        # No external target is fetched, including hyperlinks/data connections.
        for name in names:
            if name.endswith('.rels'):
                for r in self.xml(name):
                    if r.get('TargetMode','').lower()=='external':raise BinaryRejected('external package relationship denied')
    def read(self,name):
        if name not in self.names:raise BinaryRejected('required package part missing')
        try:return self.zip.read(name)
        except (zipfile.BadZipFile,RuntimeError,KeyError,NotImplementedError,
                zlib.error,lzma.LZMAError,EOFError,OSError) as exc:
            raise BinaryRejected('corrupt or unsupported package part') from exc
    def xml(self,name):
        data=self.read(name)
        if len(data)>8*1024*1024 or b'\0' in data:raise BinaryRejected('XML size or encoding unsupported')
        if re.search(br'<!\s*(DOCTYPE|ENTITY)',data,re.I):raise BinaryRejected('XML declarations with entities denied')
        try:root=ET.fromstring(data)
        except ET.ParseError as exc:raise BinaryRejected('malformed package XML') from exc
        pending=[(root,1)];count=0
        while pending:
            node,depth=pending.pop();count+=1
            if depth>128 or count>100000:raise BinaryRejected('XML structure limit exceeded')
            pending.extend((child,depth+1) for child in node)
        return root
    def target(self,part,identifier):
        rel=posixpath.join(posixpath.dirname(part),'_rels',posixpath.basename(part)+'.rels')
        matches=[r for r in self.xml(rel) if r.get('Id')==identifier]
        if len(matches)!=1:raise BinaryRejected('ambiguous or missing package relationship')
        target=posixpath.normpath(posixpath.join(posixpath.dirname(part),matches[0].get('Target','')))
        if target.startswith('../') or target.startswith('/') or target not in self.names:raise BinaryRejected('relationship outside package')
        return target
    def require_type(self,part,content_type):
        types=self.xml('[Content_Types].xml')
        found=[x.get('ContentType') for x in types if x.get('PartName')=='/'+part]
        if found!=[content_type]:raise BinaryRejected('package content type mismatch')


def _paragraph_text(node):
    result=[]
    pending=list(reversed(list(node)))
    while pending:
        child=pending.pop()
        # Nested text-box paragraphs receive their own stable locator.
        if child.tag in {f'{{{NS["w"]}}}p',f'{{{NS["a"]}}}p'}:continue
        if child.tag in {f'{{{NS["w"]}}}t',f'{{{NS["a"]}}}t'}:result.append(child.text or '')
        elif child.tag==f'{{{NS["w"]}}}tab':result.append('\t')
        elif child.tag in {f'{{{NS["w"]}}}br',f'{{{NS["a"]}}}br'}:result.append('\n')
        else:pending.extend(reversed(list(child)))
    return ''.join(result)


def _word(package,builder):
    package.require_type('word/document.xml','application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml')
    parts=['word/document.xml']+sorted(n for n in package.names if re.fullmatch(r'word/(header\d+|footer\d+|footnotes|endnotes|comments)\.xml',n))
    for part in parts:
        root=package.xml(part)
        for index,p in enumerate(root.iter(f'{{{NS["w"]}}}p'),1):
            text=_paragraph_text(p)
            builder.add(f'{part}#paragraph:{index}','paragraph',text,part=part)
        if any(node.tag.split('}')[-1] in {'drawing','pict','object','del','ins','instrText','fldChar','altChunk'} for node in root.iter()):
            builder.reasons.add('Word drawings, fields, revisions or imported content need original visual review')
    builder.reasons.add('Word native text does not qualify layout, charts or visual completeness')


def _sheet(package,builder):
    package.require_type('xl/workbook.xml','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml')
    shared=[]
    if 'xl/sharedStrings.xml' in package.names:
        shared=[''.join(t.text or '' for t in si.iter(f'{{{NS["s"]}}}t')) for si in package.xml('xl/sharedStrings.xml')]
    workbook=package.xml('xl/workbook.xml');seen=set()
    for sheet in workbook.findall('s:sheets/s:sheet',NS):
        name=sheet.get('name','');part=package.target('xl/workbook.xml',sheet.get(f'{{{NS["r"]}}}id',''))
        if part in seen:raise BinaryRejected('duplicate worksheet target')
        seen.add(part);root=package.xml(part)
        merges=tuple(m.get('ref','') for m in root.findall('s:mergeCells/s:mergeCell',NS));cells=set()
        for cell in root.findall('.//s:sheetData/s:row/s:c',NS):
            ref=cell.get('r','')
            coordinate=re.fullmatch(r'([A-Z]{1,3})([1-9][0-9]{0,6})',ref)
            if coordinate is None:raise BinaryRejected('invalid cell coordinate')
            column=0
            for letter in coordinate.group(1):column=column*26+ord(letter)-ord('A')+1
            if column>16384 or int(coordinate.group(2))>1048576:
                raise BinaryRejected('invalid cell coordinate')
            if ref in cells:raise BinaryRejected('duplicate cell coordinate')
            cells.add(ref)
            v=cell.find('s:v',NS);value=v.text or '' if v is not None else ''
            if cell.get('t')=='s':
                if not re.fullmatch(r'[0-9]+',value):raise BinaryRejected('invalid shared string index')
                try:value=shared[int(value)]
                except (ValueError,IndexError):raise BinaryRejected('invalid shared string index') from None
            elif cell.get('t')=='inlineStr':value=''.join(t.text or '' for t in cell.findall('.//s:t',NS))
            formula=cell.find('s:f',NS);attrs=dict(sheet=name,cell=ref,merges=';'.join(merges),cell_type=cell.get('t','n'))
            if formula is not None:
                attrs.update(formula=formula.text or '',cached_value=value,executed='false',cached_value_trusted='false')
                if v is None:builder.reasons.add('Spreadsheet formula has no cached value')
                # Formula text remains visible even when cached value is absent.
                text=f'Formula: {formula.text or ""}\nCached value: {value}'
            else:text=value
            builder.add(f'{part}#cell:{ref}','formula_cell' if formula is not None else 'cell',text,**attrs)
    builder.reasons.add('Spreadsheet native values do not qualify formatting, charts, hidden state or formula freshness')


def _presentation(package,builder):
    package.require_type('ppt/presentation.xml','application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml')
    presentation=package.xml('ppt/presentation.xml');seen=set()
    for index,slide in enumerate(presentation.findall('p:sldIdLst/p:sldId',NS),1):
        part=package.target('ppt/presentation.xml',slide.get(f'{{{NS["r"]}}}id',''))
        if part in seen:raise BinaryRejected('duplicate slide target')
        seen.add(part)
        for paragraph,p in enumerate(package.xml(part).iter(f'{{{NS["a"]}}}p'),1):
            builder.add(f'{part}#paragraph:{paragraph}','slide_paragraph',_paragraph_text(p),slide=index)
        rel=posixpath.join(posixpath.dirname(part),'_rels',posixpath.basename(part)+'.rels')
        if rel in package.names:
            for r in package.xml(rel):
                if r.get('Type','').endswith('/notesSlide'):
                    notes=package.target(part,r.get('Id',''))
                    for paragraph,p in enumerate(package.xml(notes).iter(f'{{{NS["a"]}}}p'),1):
                        builder.add(f'{notes}#paragraph:{paragraph}','slide_notes',_paragraph_text(p),slide=index)
    builder.reasons.add('Presentation native text does not qualify diagrams, connectors, animation or visual ordering')


def _pdf(data,builder):
    import pypdfium2 as pdfium
    try:doc=pdfium.PdfDocument(data)
    except Exception as exc:raise BinaryRejected('PDF could not be opened without credentials') from exc
    try:
        if not 0<len(doc)<=MAX_PDF_PAGES:raise BinaryRejected('PDF page limit exceeded')
        for i in range(len(doc)):
            page=doc[i]
            try:
                textpage=page.get_textpage()
                try:
                    if textpage.count_chars()>MAX_READING_CHARS:raise BinaryRejected('PDF native character limit exceeded')
                    text=textpage.get_text_range()
                finally:textpage.close()
                builder.add(f'page:{i+1}','pdf_page',text,page=i+1)
                if not text.strip():builder.reasons.add('PDF page has no native text; visual transcription required')
            finally:page.close()
    except BinaryRejected:raise
    except Exception as exc:raise BinaryRejected('PDF native text extraction failed') from exc
    finally:doc.close()
    builder.reasons.add('PDF native text does not qualify images, tables, connectors or visual completeness')


def native_binary_view(data:bytes,content_type:str)->NativeBinaryView:
    """Native-only structural evidence; caller must obtain real reading qualification."""
    if type(data) is not bytes or not 0<len(data)<=MAX_ORIGINAL_BYTES:raise BinaryRejected('original byte limit exceeded')
    builder=_Builder()
    if content_type=='application/pdf':
        if not data.startswith(b'%PDF-'):raise BinaryRejected('PDF signature mismatch')
        _pdf(data,builder)
    elif content_type in {DOCX,XLSX,PPTX}:
        package=_Package(data)
        try:{DOCX:_word,XLSX:_sheet,PPTX:_presentation}[content_type](package,builder)
        finally:package.zip.close()
    else:raise BinaryRejected('unsupported binary content type')
    if not builder.blocks:builder.reasons.add('No native text; original visual transcription required')
    versions={'protocol':'native-binary-view-v1','python':list(sys.version_info[:3]),'content_type':content_type}
    if content_type=='application/pdf':versions['pypdfium2']=version('pypdfium2')
    identity=hashlib.sha256(Path(__file__).read_bytes()+json.dumps(versions,sort_keys=True).encode()).hexdigest()
    return NativeBinaryView(content_type,hashlib.sha256(data).hexdigest(),identity,builder.reading,
        tuple(builder.blocks),tuple(sorted(builder.reasons)))
