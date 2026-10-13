# Offline original locator operation — exact review input

Status: PREPARED; no original parsing or source admission executed.

Owner: Oracle coordinator, existing issue #27, W04/source-only census preparation. Original extraction/readings are reused, not regenerated. Root retains production, privacy, source adoption and admission decisions. Root must obtain assigned independent reviewer APPROVE of this exact source head, operator/config hashes and inputs, then pass task gates before executing. This program issues no admission.

## Exact bounded action

Read the 26 previously hashed original uploads, eight qualified original-reading groups and 33 exact retained page spans (29 PDF pages and four non-PDF records). Generate private native page/character/table-cell/picture geometry plus exact unique reading offsets. Never interpret business meaning, create obligations or candidates, replace source readings, adopt ledger rows, generate company questions or grade employees. Standard local document models do not contact an inference provider.

Targets are the previously inventoried original root, qualified receipts and private group/page inventories; no private source filenames, titles, labels or contents appear in this contract. Externally prepared configuration identifies those locators and a fresh owned private output directory. Root can inspect private locator metadata; configured inputs may not drift. Prepared config SHA256: `4c6bf1a32ffe26894e99c76440f20eda19faa58318851d0f5444058dbb82d681`. Operator SHA256: `8fc05bea47c07034d90f294665b73f0293cf1b51fb1644c9f8cd93afbdcf9175`. Both files are retained under the owning worktree's ignored `.ai/reviews/offline-locators/` directory, as `prepared-input-config.json` and `offline_locator.py`.

Literal operator pins bind original manifest, group receipts, page skeleton, qualified summary, model asset manifest and public offline fixture proof (all below in source). Metadata-only preflight passed all eight groups/33 spans/26 originals; The earlier action completed all eight groups; the repaired action has not run. All originals and reading hashes are rechecked before and after each group and after the operation; any drift stops. Existing reading parser identity is preserved separately from new locator-parser versions and model asset seal. Canonical current SourceRef workspace/revision binding remains unperformed.

## Offline assets and custody

Project-owned existing Python environment, installed Docling2.130.0/core2.99.0/parse7.22.0, pypdfium2 5.13.0 and CPU torch2.14.0 are fixed. Assets: 17 verified public files, 562,227,701 bytes. Heron layout revision8f39ad3c0b4c58e9c2d2c84a38465abf757272d8 (Apache-2.0); standard TableFormer v2.3.0 revisionfc0f2d45e2218ea24bce5045f58a389aed16dc23 (CDLA-Permissive-2.0); standard RapidOCR torch detection/recognition/classification and dictionary v3.9.2 (Apache-2.0). Public model source/license/hash manifests are retained independently; no model substitution or source credentials.

Primary references: https://docling-project.github.io/docling/usage/advanced_options/ , https://huggingface.co/docling-project/docling-layout-heron , https://huggingface.co/docling-project/docling-models , https://rapidai.github.io/RapidOCRDocs/main/en/model_licenses/ . Existing public invented fixture successfully loaded these models offline: one page, one table, eight cells, all with geometric boxes and row/column indices. That proves a local capability, not private source coverage.

Internal-worker direct invocation verifies physical read-only root, isolated network interfaces and dedicated temporary tmpfs before any input read. Each actual worker runs in bubblewrap's denied-network namespace with the host filesystem read-only, including original/cache/interpreter paths. Only dedicated output is writable; temporary storage is a separate bounded64MiB tmpfs. Parent starts no network requests. Environment drops secrets/proxy settings and disables downloads/telemetry; Docling disables external services/plugins and image-description/classification/chart/code/formula inference. Two CPU threads; per group120CPU seconds × (qualified pages + 1 initialization unit)/180wall seconds × the same units; address space8GiB; 64file handles. Output aggregate ceiling256MiB and per-file8MiB (including private parser logs); 33 per-page geometry files/eight group manifests/eight lifecycle receipts/eight logs/completion plus temporary storage remain bounded. Oversized or timed-out groups fail; no partial output is admissible without final completion proof. Parser stdout/stderr go only to0600 private logs; public output is fixed status/count/hash.

## Exact locator limits

PDF native character boxes retain backend index/origin; Docling tables retain page, cell box and row/column spans; picture blocks retain native boxes and page dimensions. Picture rectangles are not diagram-node or connector geometry. Text/Markdown retain literal UTF-8 byte ranges; no XML/DOCX originals exist in this scope. Delimiters or page rectangles cannot certify table cells or diagram regions.

Reading alignment requires a nonempty exact substring occurring once within its already fixed page span; that entire page span is already pinned to one exact unique location in the existing qualified reading. Literal repetition on different pinned pages is permitted; repetition within the same page remains unsupported. No fuzzy/nearest match, whitespace/case normalization, empty-span substitution or whole-page support shortcut. All unsupported geometry and missing alignments stay explicit; output ALWAYS says complete_region_register=false and diagram_node_geometry=false. A later source-only census must independently decide whether complete regions and business obligations are supportable; none are inferred here.

## Validation and recovery

The public synthetic sandbox test physically attempted a write to an invented read-only original and a network connection: both refused. It checked RAM/file limits, checksum drift refusal, unsealed population refusal, empty/repeated alignment refusal and one unique alignment. Internal physical boundary also passed inside the real sandbox and denied outside it. Earlier physical-boundary proof SHA256e5bf0f03015c62ff1e2f56fbc409d005a82a70648cad9727c1f80362846b37f2 remains historical. Earlier page-budget, per-page digest, invalid-count, timeout and signal proof SHA2567c4aabd676691c77e8bfea4cf66481e89dc7c8087d8aebacab3dd0d4896f809d remains historical. Earlier alignment/table proof SHA256a91653cf74faf39c492d7c2009a7fb7238ab9503962a2785d460d9deeb5e1044 is preserved historically. Current combined public native-text/table/page-alignment proof SHA2565cb7c6773935c26696b550dc27bba4bb4592bc0e163b8900487c7fa44c4dfd1b. It includes actual offline scanned-image and two-page raster-PDF paragraph-only conversion, typed native text provenance/labels, structural references, enum/page-bound denials and protected output tests. Separate public model fixture proof is pinned in source. Tests do not parse company originals.

No source changes require rollback. A failure preserves private partial output/logs, reports only fixed refusal and never marks readiness. Root reviews the retained cause, repairs within existing scope and re-runs only under a new exact action review if inputs/source/config change. No new issue, provider dispatch, consent or credentials. The existing privacy incident record remains protected; no private labels are repeated.

```python
"""Reviewed offline geometry only; this program cannot issue source admission."""
import hashlib, json, math, os, re, resource, subprocess, sys, time
from pathlib import Path

MAX_OUTPUT = 256 * 1024**2
PYTHON = '/home/ahazan/.codex/worktrees/oracle-operating-model/oracle/services/oracle-brain/.venv/bin/python'
VERSIONS = {'docling':'2.130.0','docling-core':'2.99.0','docling-parse':'7.22.0','pypdfium2':'5.13.0','torch':'2.14.0+cpu'}
ENV = {'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_DATASETS_OFFLINE':'1',
       'HF_HUB_DISABLE_TELEMETRY':'1','DO_NOT_TRACK':'1','TOKENIZERS_PARALLELISM':'false',
       'OMP_NUM_THREADS':'2','MKL_NUM_THREADS':'2'}
PINS = {'original_manifest_sha256':'59b92c2b28d629732f5e5fb5895325d636173c7fc2ff7e84158f6f98f8fc6a7e',
        'group_inventory_sha256':'b236778237d7c0c64c8cb73995b8d7430493e492a3c28a357e0efc24bdd26bfe',
        'page_skeleton_sha256':'f650543d3d6d6fcf0b24da3ff5d9bc839d657aac9350c719ad847056eb0509d7',
        'qualified_summary_sha256':'d4fd637709a1280c917b1a6debf11b2a3f84690847fedcae51706d22ca33cfea',
        'asset_manifest_sha256':'aa7b4bc8b884c464a8721c85a1875f34931a3b7b24fcc2329d0a0f398327fa2e',
        'offline_fixture_proof_sha256':'a55c9011b9d6f5813ae2244efb508436c7e4431edebf29a2c6874445bab344db'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unique(pairs):
    result = {}
    for key,value in pairs:
        if key in result: raise ValueError('duplicate field')
        result[key] = value
    return result


def load(path):
    return json.loads(Path(path).read_bytes(), object_pairs_hook=unique)


def checked(path, expected):
    path = Path(path)
    if path.is_symlink() or not path.is_file(): raise ValueError('invalid retained file')
    raw = path.read_bytes()
    if sha(raw) != expected: raise ValueError('input drift')
    return raw


def verify(config):
    if set(config) != set(PINS)|{'scope','original_root','cache_root','output','python','group_inventory_file','page_skeleton_file','operator_sha256'}:
        raise ValueError('closed reviewed configuration required')
    if config.get('scope') != 'original-locators' or any(config.get(k)!=v for k,v in PINS.items()):
        raise ValueError('exact reviewed input population required')
    if config.get('python') != PYTHON or config.get('operator_sha256') != sha(Path(__file__).read_bytes()):
        raise ValueError('reviewed operator/interpreter identity required')
    root, cache = Path(config['original_root']), Path(config['cache_root'])
    for path in (root,cache):
        if not path.is_absolute() or path.is_symlink(): raise ValueError('fixed root required')
    original = json.loads(checked(root/'original-manifest.json',PINS['original_manifest_sha256']))
    groups = json.loads(checked(config['group_inventory_file'],PINS['group_inventory_sha256']))
    pages = json.loads(checked(config['page_skeleton_file'],PINS['page_skeleton_sha256']))
    checked(root/'qualified-original-readings-v1/summary.json',PINS['qualified_summary_sha256'])
    assets = json.loads(checked(cache/'asset-manifest.json',PINS['asset_manifest_sha256']))
    checked(cache/'offline-fixture-proof.json',PINS['offline_fixture_proof_sha256'])
    if (len(original),len(groups),len(pages)) != (26,8,33): raise ValueError('population drift')
    originals = {x['source_id']:x for x in original}
    if len(originals)!=26 or sum(len(g['source_ids']) for g in groups)!=26: raise ValueError('alias drift')
    seen=set()
    for g in groups:
        reading_path=root/'qualified-original-readings-v1'/(g['original_sha256']+'.json')
        d=json.loads(checked(reading_path,g['qualified_receipt_sha256']))
        if sha(d['text'].encode())!=g['reading_sha256'] or d['provenance']['original_hash']!=g['original_sha256']:
            raise ValueError('qualified reading drift')
        for identity in g['source_ids']:
            if identity in seen or identity not in originals: raise ValueError('duplicate source')
            seen.add(identity);entry=originals[identity]
            raw=checked(root/'originals'/identity,entry['sha256'])
            if len(raw)!=entry['bytes'] or entry['sha256']!=g['original_sha256']: raise ValueError('original drift')
        own=[p for p in pages if p['region_locator']['original_sha256']==g['original_sha256']]
        if len(own)!=g['page_records']: raise ValueError('page drift')
        budget(g['page_records'])
        numbers=[p['region_locator']['page_number'] for p in own]
        if any(type(n) is not int or n<1 for n in numbers) or len(set(numbers))!=len(numbers): raise ValueError('duplicate fixed pages')
        for p in own:
            if d['text'][p['start']:p['end']]!=p['quote'] or d['text'].count(p['quote'])!=1:
                raise ValueError('page alignment drift')
    if len({g['original_sha256'] for g in groups})!=8 or sum(g['page_records'] for g in groups)!=33: raise ValueError('fixed page census drift')
    for asset in assets['files']:
        path=Path(asset['file'])
        if path.is_absolute() or '..' in path.parts: raise ValueError('asset path escape')
        raw=checked(cache/path,asset['sha256'])
        if len(raw)!=asset['bytes']: raise ValueError('asset drift')
    return groups,pages


def sandbox(command, output, temporary):
    # Every host path including originals, models and interpreter is read-only.
    return ['bwrap','--die-with-parent','--unshare-net','--ro-bind','/','/',
            '--bind',str(output),str(output),'--size',str(64*1024**2),'--tmpfs','/tmp',
            '--proc','/proc','--dev','/dev',*command]


def save(output,name,value):
    data=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    current=sum(p.stat().st_size for p in output.rglob('*') if p.is_file())
    if len(data)>8*1024**2 or current+len(data)>MAX_OUTPUT: raise ValueError('output ceiling')
    fd=os.open(output/name,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f: f.write(data);f.flush();os.fsync(f.fileno())


def alignment_status(value,page):
    if not isinstance(value,str) or not value: return 'empty'
    count=page['quote'].count(value)
    return 'unique' if count==1 else 'ambiguous_in_page' if count>1 else 'missing_in_page'


def align(value,page,reading):
    # The whole pinned page span is unique; literal repetition on another page is safe.
    if alignment_status(value,page)!='unique': return None
    start=page['start']+page['quote'].index(value);end=start+len(value)
    if reading[start:end]!=value: raise ValueError('alignment invariant')
    return {'start':start,'end':end,'quote':reading[start:end]}


def structural_ref(value):
    if not isinstance(value,str) or not re.fullmatch(r'#/(?:body|furniture|(?:texts|tables|pictures|groups)/[0-9]+)',value):
        raise ValueError('native structural reference required')
    return value


def native_links(item):
    result={}
    if item.parent is not None: result['parent_ref']=structural_ref(item.parent.cref)
    for name in ('captions','references','footnotes'):
        refs=getattr(item,name,None)
        if refs: result[name]=[structural_ref(ref.cref) for ref in refs]
    return result


def native_text(item,prov,page,reading,dimensions):
    from docling_core.types.doc import DocItemLabel
    if not isinstance(item.self_ref,str) or not re.fullmatch(r'#/texts/[0-9]+',item.self_ref):
        raise ValueError('native text identity required')
    if not isinstance(item.label,DocItemLabel) or not isinstance(item.text,str):
        raise ValueError('native text enum required')
    if prov.page_no!=page['region_locator']['page_number']: raise ValueError('native text page mismatch')
    box=prov.bbox
    coords=[box.l,box.t,box.r,box.b]
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in coords): raise ValueError('finite text geometry required')
    if min(box.l,box.r)<-.1 or max(box.l,box.r)>dimensions.width+.1 or min(box.t,box.b)<-.1 or max(box.t,box.b)>dimensions.height+.1:
        raise ValueError('native text bounds required')
    span=list(prov.charspan)
    if len(span)!=2 or any(type(v) is not int or v<0 for v in span) or span[1]<span[0]: raise ValueError('native text character span required')
    return {'kind':'native_text_region','page':prov.page_no,'native_text_id':item.self_ref,
        'native_label_enum':item.label.value,**native_links(item),
        'bbox':box.model_dump(mode='json'),'charspan':span,'source_text':item.text,
        'alignment_status':alignment_status(item.text,page),'alignment':align(item.text,page,reading)}


def native_cell(table,cell,page,reading):
    if len(table.prov)!=1 or not isinstance(table.self_ref,str) or not re.fullmatch(r'#/tables/[0-9]+',table.self_ref):
        raise ValueError('native structural table identity required')
    parent=table.prov[0]
    if parent.page_no!=page['region_locator']['page_number'] or not isinstance(cell.text,str):
        raise ValueError('native cell/page identity required')
    spans=[cell.start_row_offset_idx,cell.end_row_offset_idx,cell.start_col_offset_idx,cell.end_col_offset_idx]
    if any(type(v) is not int or v<0 for v in spans) or spans[1]<=spans[0] or spans[3]<=spans[2]:
        raise ValueError('native cell span required')
    return {'kind':'table_cell','page':parent.page_no,'parent_table_id':table.self_ref,**native_links(table),
        'parent_table_provenance':{'page':parent.page_no,'bbox':parent.bbox.model_dump(mode='json'),'charspan':list(parent.charspan)},
        'source_text':cell.text,'alignment_status':alignment_status(cell.text,page),
        'bbox':None if cell.bbox is None else cell.bbox.model_dump(mode='json'),
        'row':spans[0],'row_end':spans[1],'column':spans[2],'column_end':spans[3],
        'alignment':align(cell.text,page,reading)}


def sandbox_boundary():
    # Direct invocation of the internal worker must not bypass physical custody.
    mounts=[line.split() for line in Path('/proc/self/mountinfo').read_text().splitlines()]
    roots=[row for row in mounts if row[4]=='/']
    if len(roots)!=1 or 'ro' not in roots[0][5].split(','):
        raise ValueError('read-only host root required')
    interfaces={line.split(':',1)[0].strip() for line in Path('/proc/net/dev').read_text().splitlines() if ':' in line}
    if interfaces-{'lo'}:
        raise ValueError('isolated network namespace required')
    temporary=[row for row in mounts if row[4]=='/tmp']
    if len(temporary)!=1 or temporary[0][temporary[0].index('-')+1]!='tmpfs':
        raise ValueError('dedicated temporary tmpfs required')


def budget(page_count):
    if type(page_count) is not int or not 1<=page_count<=40: raise ValueError('invalid fixed page count')
    return {'page_count':page_count,'units':page_count+1,'cpu_seconds':120*(page_count+1),'wall_seconds':180*(page_count+1)}


def save_pages(output,index,result,page_numbers):
    numbers=sorted(page_numbers)
    if not numbers or len(set(numbers))!=len(numbers): raise ValueError('duplicate native pages')
    locators=result.pop('native_locators');dimensions=result.pop('docling_page_dimensions',{})
    if any(x.get('page') not in numbers for x in locators): raise ValueError('locator page drift')
    refs=[]
    for number in numbers:
        name='group-'+str(index)+'-page-'+str(number)+'.json'
        record={**result,'native_page_number':number,'native_locators':[x for x in locators if x['page']==number]}
        if str(number) in dimensions: record['docling_page_dimensions']=dimensions[str(number)]
        save(output,name,record)
        raw=(output/name).read_bytes();refs.append({'file':name,'sha256':sha(raw),'bytes':len(raw),'page_number':number,'locator_count':len(record['native_locators'])})
    statuses={key:sum(x.get('alignment_status')==key for x in locators) for key in
              ('unique','empty','ambiguous_in_page','missing_in_page')}
    save(output,'group-'+str(index)+'-manifest.json',{'group_index':index,'page_count':len(numbers),'pages':refs,
        'alignment_status_counts':statuses,'complete_region_register':False})


def worker(config,index):
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_AS,(8*1024**3,8*1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE,(8*1024**2,8*1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))
    sandbox_boundary()
    os.environ.update(ENV);os.environ['HF_HOME']='/tmp/empty-hf-cache'
    import importlib.metadata
    if any(importlib.metadata.version(k)!=v for k,v in VERSIONS.items()): raise ValueError('installed parser version drift')
    groups,pages=verify(config);group=groups[index]
    limits=budget(group['page_records']);resource.setrlimit(resource.RLIMIT_CPU,(limits['cpu_seconds'],limits['cpu_seconds']))
    root=Path(config['original_root']);cache=Path(config['cache_root']);output=Path(config['output'])
    data=load(root/'qualified-original-readings-v1'/(group['original_sha256']+'.json'))
    reading=data['text'];raw=(root/'originals'/group['source_ids'][0]).read_bytes()
    page_by_number={p['region_locator']['page_number']:p for p in pages if p['region_locator']['original_sha256']==group['original_sha256']}
    result={'original_sha256':group['original_sha256'],'reading_sha256':group['reading_sha256'],
            'qualified_reading_parser_id':group['parser_id'],'locator_parser_versions':VERSIONS,
            'asset_manifest_sha256':PINS['asset_manifest_sha256'],'source_ids':group['source_ids'],'native_locators':[],
            'unresolved':[],'complete_region_register':False,'diagram_node_geometry':False}
    kind=group['file_type']
    if kind in {'application/pdf','image/png'}:
        from io import BytesIO
        from docling.datamodel.pipeline_options import PdfPipelineOptions,RapidOcrOptions,AcceleratorOptions,AcceleratorDevice
        from docling.document_converter import DocumentConverter,PdfFormatOption,ImageFormatOption
        from docling.datamodel.base_models import InputFormat,DocumentStream
        options=PdfPipelineOptions(artifacts_path=cache,enable_remote_services=False,allow_external_plugins=False,
            do_ocr=True,do_table_structure=True,do_picture_description=False,do_picture_classification=False,
            do_chart_extraction=False,do_code_enrichment=False,do_formula_enrichment=False,document_timeout=limits['wall_seconds'],
            accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU,num_threads=2),
            ocr_options=RapidOcrOptions(backend='torch',det_model_path=str(cache/'RapidOcr/PP-OCRv6_det_small.pth'),
                cls_model_path=str(cache/'RapidOcr/ch_ptocr_mobile_v2.0_cls_mobile.pth'),
                rec_model_path=str(cache/'RapidOcr/PP-OCRv6_rec_small.pth'),rec_keys_path=str(cache/'RapidOcr/ppocrv6_dict.txt'),print_verbose=False))
        converter=DocumentConverter(format_options={InputFormat.PDF:PdfFormatOption(pipeline_options=options),InputFormat.IMAGE:ImageFormatOption(pipeline_options=options)})
        doc=converter.convert(DocumentStream(name='input.pdf' if kind=='application/pdf' else 'input.png',stream=BytesIO(raw))).document
        if len(doc.pages)!=group['page_records']: raise ValueError('native page population mismatch')
        result['docling_page_dimensions']={str(n):page.size.model_dump(mode='json') for n,page in doc.pages.items()}
        for item in doc.texts:
            for prov in item.prov:
                page=page_by_number.get(prov.page_no)
                if page is None or prov.page_no not in doc.pages: raise ValueError('native text page outside fixed reading')
                result['native_locators'].append(native_text(item,prov,page,reading,doc.pages[prov.page_no].size))
        for table in doc.tables:
            if len(table.prov)!=1: result['unresolved'].append('table page ambiguous');continue
            page=page_by_number.get(table.prov[0].page_no)
            if page is None: raise ValueError('table page outside fixed reading')
            for cell in table.data.table_cells:
                result['native_locators'].append(native_cell(table,cell,page,reading))
        for picture in doc.pictures:
            for prov in picture.prov:
                result['native_locators'].append({'kind':'picture_region','page':prov.page_no,
                    'bbox':prov.bbox.model_dump(mode='json'),'native_picture_id':structural_ref(picture.self_ref),**native_links(picture),'alignment':None,'diagram_node_qualified':False})
        if kind=='application/pdf':
            import pypdfium2 as pdf
            native=pdf.PdfDocument(raw)
            for n in range(len(native)):
                page=native[n];text=page.get_textpage();fixed=page_by_number[n+1]
                # Native characters remain source geometries, not independent semantic regions.
                for i in range(text.count_chars()):
                    value=text.get_text_range(i,1)
                    result['native_locators'].append({'kind':'native_character','page':n+1,'native_index':i,'coordinate_origin':'bottom_left','backend':'pdfium',
                        'bbox':list(text.get_charbox(i)),'source_text':value,'alignment_status':alignment_status(value,fixed),'alignment':align(value,fixed,reading)})
                text.close();page.close()
            native.close()
    elif kind in {'text/plain','text/markdown'}:
        native=raw.decode('utf-8');fixed=next(iter(page_by_number.values()));byte_start=0
        for line in native.splitlines(keepends=True):
            byte_end=byte_start+len(line.encode());result['native_locators'].append({'kind':'literal_byte_range',
                'page':fixed['region_locator']['page_number'],'byte_start':byte_start,'byte_end':byte_end,'alignment_status':alignment_status(line.rstrip('\r\n'),fixed),'alignment':align(line.rstrip('\r\n'),fixed,reading)});byte_start=byte_end
        # Delimiters alone cannot certify table cells or diagram geometry.
        result['unresolved'].append('no independent table or diagram geometry in literal text')
    else: raise ValueError('unreviewed format')
    verify(config)
    save_pages(output,index,result,page_by_number)


def run_group(command,env,output,index,page_count):
    limits=budget(page_count)
    # Record only safe lifecycle metadata; never argv, exception text or private logs.
    before=resource.getrusage(resource.RUSAGE_CHILDREN);started=time.monotonic()
    code=None;reason='completed';log=output/('parser-'+str(index)+'.private.log')
    try:
        with log.open('xb') as stream:
            process=subprocess.run(command,env=env,stdout=stream,stderr=stream,timeout=limits['wall_seconds'],check=False)
        code=process.returncode
        if code!=0: reason='nonzero_exit'
    except subprocess.TimeoutExpired:
        reason='TimeoutExpired'
    except OSError:
        reason='launch_failed'
    finally:
        if log.exists(): log.chmod(0o600)
        after=resource.getrusage(resource.RUSAGE_CHILDREN)
        receipt={'group_index':index,'elapsed_seconds':time.monotonic()-started,
            'returncode':code,'reason':reason,'user_cpu_seconds':after.ru_utime-before.ru_utime,
            'system_cpu_seconds':after.ru_stime-before.ru_stime,
            'children_maxrss_kib':after.ru_maxrss,'maxrss_scope':'cumulative_child_maximum',
            'bounds':{'virtual_address_space_bytes':8*1024**3,'cpu_seconds':limits['cpu_seconds'],'wall_seconds':limits['wall_seconds'],'qualified_page_count':page_count,'budget_units':limits['units'],
                'threads':2,'file_bytes':8*1024**2,'aggregate_bytes':MAX_OUTPUT,'workers':1}}
        save(output,'lifecycle-'+str(index)+'.json',receipt)
    return reason=='completed' and code==0


def main(config_path,config_hash):
    os.umask(0o077)
    raw=checked(config_path,config_hash);config=json.loads(raw,object_pairs_hook=unique)
    if Path(config_path).stat().st_mode&0o077: raise ValueError('protected configuration required')
    groups,pages=verify(config);output=Path(config['output'])
    if (not output.is_absolute() or output.exists() or output.is_symlink() or output.resolve()!=output
            or any(output.is_relative_to(Path(config[k]).resolve()) for k in ('original_root','cache_root'))): raise ValueError('fresh protected output required')
    output.mkdir(mode=0o700);temporary=output/'tmp';temporary.mkdir(mode=0o700)
    env={k:v for k,v in os.environ.items() if k in {'PATH','LANG','LC_ALL'}};env.update(ENV)
    for index in range(len(groups)):
        command=sandbox([config['python'],str(Path(__file__).resolve()),'_worker',str(config_path),config_hash,str(index)],output,temporary)
        if not run_group(command,env,output,index,groups[index]['page_records']): raise ValueError('bounded parser failed')
        if sum(p.stat().st_size for p in output.rglob('*') if p.is_file())>MAX_OUTPUT: raise ValueError('output ceiling')
    verify(config)
    files=[p for p in output.glob('group-*-manifest.json')]
    if len(files)!=8 or sum(load(p)['page_count'] for p in files)!=33: raise ValueError('output population drift')
    proof={'groups':len(files),'uploads':26,'page_records':33,'originals_and_readings_unchanged':True,
        'complete_region_register':False,'private_provider_calls':0,'ledger_writes':0,
        'output_hashes':{p.name:sha(p.read_bytes()) for p in files},'config_sha256':config_hash,
        'operator_sha256':sha(Path(__file__).read_bytes()),'diagram_node_geometry_qualified':False}
    save(output,'completion.json',proof);print(json.dumps({'status':'prepared-locators','groups':len(files),'complete':False,'proof_sha256':sha((output/'completion.json').read_bytes())}))


if __name__=='__main__':
    try:
        if len(sys.argv)>1 and sys.argv[1]=='_worker':
            worker(json.loads(checked(sys.argv[2],sys.argv[3])),int(sys.argv[4]))
        elif len(sys.argv)==3: main(sys.argv[1],sys.argv[2])
        else: raise ValueError('reviewed pinned config required')
    except BaseException:
        print('offline locator operation refused',file=sys.stderr);sys.exit(1)
```

Bounded repair: only virtual address-space limit changes4GiB to8GiB, with one sequential worker. The initial reviewed run preserved group0 and refused on group1 with CPU allocator ENOMEM117,571,584-byte allocation. Existing protected source/config/partial bytes were copied with a SHA manifest before this edit. Fresh output uses a distinct not-yet-created owned path outside temporary storage. Originals will not rerun before fresh exact independent review. Host capacity verified by root October12,2026 2:24 PM EDT:63GiB physical/35GiB available; swap heavily used. No OCR disable, source omission or model replacement.

Observability-only repair: all AS8 bounds remain unchanged. Each group now retains a private safe lifecycle receipt (index, monotonic elapsed, returncode or constant TimeoutExpired/launch_failed reason, child user/system CPU deltas, cumulative child maximum RSS in Linux KiB, exact configured bounds). No argv, exception text, private paths or parser values are copied into receipts. Prior AS8 cause remains unproved; no memory/CPU/wall conclusion inferred. Fresh distinct output requires new exact action review before original execution.

Public lifecycle fixture passed real child timeout, real SIGTERM exit (-15) and successful child execution. Safe receipts contain no sentinel parser content, argv, exception text or paths. Proof SHA256 `6a87147e26acd860b81d4ee905ffeb4a3f7ad956ae6830c06544e2c5a06c15c0`. Metadata-only source/model preflight still verifies8groups/33spans; no original rerun.

Worker CPU seconds are 120 × (qualified page count + 1 initialization unit); parent wall seconds are 180 × the same units. The fixed 33 unique qualified page records across eight original groups determine 41 total units. Each group has 1–40 validated pages. Parsing remains sequential with two threads and an 8 GiB virtual-address-space ceiling. Per-page geometry files retain native page numbers and are at most 8 MiB each; group manifests contain only counts, hashes and references. Aggregate output remains 256 MiB. Original execution requires fresh exact action review.

Native cell and character source text remains exclusively in protected private geometry files. Each cell preserves its structural Docling table identity and native parent page/bounding-box/character-span provenance. Text alignment outcomes use only unique, empty, ambiguous_in_page or missing_in_page. Pictures acquire no invented source text or labels. Original readings, parser models and page-scaled resource limits remain unchanged.

Native Docling text items now retain strict text identities, structural parents, SDK enum labels, existing page/bounding-box/character-span provenance, source text and exact alignment/status in private geometry files. Existing native table/picture caption and reference links are retained only when explicitly present; no association is inferred. Native text capture restores layout/OCR custody without classifying business sections or diagram meaning. The fresh repaired action remains unexecuted until independent exact approval.
