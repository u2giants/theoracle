"""Pure alternate serialization of the reviewed custom native page snapshots.

This format is derived from offline-original-locators.md, not DoclingDocument.
No file access, authority, model call or adoption is provided here.
"""
import hashlib
import json
import math
import re

VERSIONS={'docling':'2.130.0','docling-core':'2.99.0','docling-parse':'7.22.0','pypdfium2':'5.13.0','torch':'2.14.0+cpu'}
PINS={'original_manifest_sha256':'59b92c2b28d629732f5e5fb5895325d636173c7fc2ff7e84158f6f98f8fc6a7e',
'group_inventory_sha256':'b236778237d7c0c64c8cb73995b8d7430493e492a3c28a357e0efc24bdd26bfe',
'page_skeleton_sha256':'f650543d3d6d6fcf0b24da3ff5d9bc839d657aac9350c719ad847056eb0509d7',
'qualified_summary_sha256':'d4fd637709a1280c917b1a6debf11b2a3f84690847fedcae51706d22ca33cfea',
'asset_manifest_sha256':'aa7b4bc8b884c464a8721c85a1875f34931a3b7b24fcc2329d0a0f398327fa2e',
'offline_fixture_proof_sha256':'a55c9011b9d6f5813ae2244efb508436c7e4431edebf29a2c6874445bab344db'}

HISTORY={'native_groups':8,'original_uploads':26,'native_pages':33,
'completion_sha256':'8ae0e0182324b563b10d5acb2c43a87adf677c3933d35ee8ffa8a3513befc74c',
'configuration_sha256':'4c6bf1a32ffe26894e99c76440f20eda19faa58318851d0f5444058dbb82d681',
'operator_sha256':'8fc05bea47c07034d90f294665b73f0293cf1b51fb1644c9f8cd93afbdcf9175',
'custody_sha256':'79bd96fa3a837a702ad283dc2f1f613dce4de6f2f1a8801f0e11e05ede53b0ca'}


def require(ok,reason):
    if not ok:raise ValueError(reason)

def sha(raw):return hashlib.sha256(raw).hexdigest()
def integer(n,minimum=0):return type(n) is int and n>=minimum
def digest(v):return isinstance(v,str) and re.fullmatch('[a-f0-9]{64}',v) is not None
def ref(v,kind=None):return isinstance(v,str) and re.fullmatch(r'#/(?:body|furniture|(?:texts|tables|pictures|groups)/[0-9]+)',v) is not None and (kind is None or v.startswith('#/'+kind+'/'))
def box(v,nullable=False):
    if v is None and nullable:return
    require(type(v) is dict and set(v)=={'l','t','r','b','coord_origin'},'native bbox differs')
    require(v['coord_origin'] in ('TOPLEFT','BOTTOMLEFT') and all(type(v[k]) in (int,float) and math.isfinite(v[k]) for k in ('l','t','r','b')),'native bbox values differ')
def span(v):require(type(v) is list and len(v)==2 and all(integer(n) for n in v) and v[1]>=v[0],'native charspan differs')
def links(item):
    for key in ('parent_ref','captions','references','footnotes'):
        if key not in item:continue
        values=[item[key]] if key=='parent_ref' else item[key]
        require(type(values) is list and all(ref(v) for v in values),'native structural links differ')

def decode(raw):
    def unique(pairs):
        out={}
        for k,v in pairs:require(k not in out,'duplicate JSON field');out[k]=v
        return out
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite JSON')))


def serialize_page(page,*,capture_hash,expected_original,expected_page):
    base={'original_sha256','reading_sha256','qualified_reading_parser_id','locator_parser_versions','asset_manifest_sha256','source_ids','native_locators','unresolved','complete_region_register','diagram_node_geometry','native_page_number'}
    require(type(page) is dict and set(page) in (base,base|{'docling_page_dimensions'}),'custom native page schema differs')
    require(digest(capture_hash) and page['original_sha256']==expected_original and digest(expected_original)
        and page['native_page_number']==expected_page and integer(expected_page,1),'native page identity differs')
    require(digest(page['reading_sha256']) and isinstance(page['qualified_reading_parser_id'],str)
        and bool(page['qualified_reading_parser_id']) and page['locator_parser_versions']==VERSIONS
        and page['asset_manifest_sha256']==PINS['asset_manifest_sha256'],'historical parser provenance differs')
    require(page['complete_region_register'] is False and page['diagram_node_geometry'] is False,'capture cannot qualify geometry')
    require(type(page['source_ids']) is list and page['source_ids'] and len(set(page['source_ids']))==len(page['source_ids'])
        and all(isinstance(s,str) and s for s in page['source_ids']),'native alias identities differ')
    require(type(page['native_locators']) is list and type(page['unresolved']) is list and all(isinstance(v,str) for v in page['unresolved']),'native locator population differs')
    if 'docling_page_dimensions' in page:
        d=page['docling_page_dimensions'];require(type(d) is dict and set(d)=={'width','height'} and all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in d.values()),'native dimensions differ')
    text='';segments=[];gaps=[];seen=set()
    for index,item in enumerate(page['native_locators']):
        require(type(item) is dict and item.get('page')==expected_page,'locator page differs')
        kind=item.get('kind');links(item)
        optional={'parent_ref','captions','references','footnotes'}
        schemas={'native_text_region':{'kind','page','native_text_id','native_label_enum','bbox','charspan','source_text','alignment_status','alignment'},
            'table_cell':{'kind','page','parent_table_id','parent_table_provenance','source_text','alignment_status','bbox','row','row_end','column','column_end','alignment'},
            'picture_region':{'kind','page','bbox','native_picture_id','alignment','diagram_node_qualified'},
            'native_character':{'kind','page','native_index','coordinate_origin','backend','bbox','source_text','alignment_status','alignment'},
            'literal_byte_range':{'kind','page','byte_start','byte_end','alignment_status','alignment'}}
        require(kind in schemas and schemas[kind]<=set(item) and set(item)<=schemas[kind]|optional,'native locator schema differs')

        if kind not in ('native_text_region','table_cell'):
            require(kind in ('native_character','literal_byte_range','picture_region'),'unknown native locator kind')
            gaps.append({'locator_index':index,'kind':kind,'reason':'representation_not_admitted','retained_native_metadata':{k:v for k,v in item.items() if k not in ('source_text','alignment')},'source_text_present':'source_text' in item})
            continue
        require(isinstance(item.get('source_text'),str),'supported locator source text missing')
        require(item.get('alignment_status') in ('unique','empty','ambiguous_in_page','missing_in_page') and 'alignment' in item,'native alignment record missing')
        if kind=='native_text_region':
            require(ref(item.get('native_text_id'),'texts') and isinstance(item.get('native_label_enum'),str),'native text identity differs')
            identity=(kind,item['native_text_id'],expected_page,index)
            box(item.get('bbox'));span(item.get('charspan'))
        else:
            require(ref(item.get('parent_table_id'),'tables'),'native table identity differs')
            require(all(integer(item.get(k)) for k in ('row','row_end','column','column_end')) and item['row_end']>item['row'] and item['column_end']>item['column'],'native cell address differs')
            parent=item.get('parent_table_provenance');require(type(parent) is dict and set(parent)=={'page','bbox','charspan'} and parent['page']==expected_page,'native table provenance differs')
            box(parent['bbox']);span(parent['charspan']);box(item.get('bbox'),True)
            identity=(kind,item['parent_table_id'],expected_page,item['row'],item['row_end'],item['column'],item['column_end'])
        require(identity not in seen,'duplicate native cell identity');seen.add(identity)
        start=len(text.encode('utf-8'));text+=item['source_text'];end=len(text.encode('utf-8'))
        segments.append({'locator_index':index,'utf8_start':start,'utf8_end':end,'source_text_sha256':sha(item['source_text'].encode()),'capture_sha256':capture_hash,'original_sha256':expected_original,'page':expected_page,'native_metadata':item})
    return {'status':'unqualified-native-alternate-v1','format':'custom-native-page-snapshot-v1','source_qualified':False,'source_ref_issued':False,'ledger_adopted':False,'provider_authority':False,'semantic_qualified':False,'text':text,'segments':segments,'unrepresented_gaps':gaps,'unresolved':page['unresolved'],'native_page_number':expected_page,'original_sha256':expected_original,'capture_sha256':capture_hash}


def validate_controls(records,*,census):
    """Called on actual verified control bytes BEFORE any page snapshot read."""
    pins={'completion':census['completion_sha256'],'configuration':census['configuration_sha256'],'producer':census['operator_sha256'],'custody':census['custody_sha256'],
        'original_manifest':PINS['original_manifest_sha256'],'group_inventory':PINS['group_inventory_sha256'],'page_skeleton':PINS['page_skeleton_sha256']}
    require(all(sha(records[k])==v for k,v in pins.items()),'actual historical control hash differs')
    completion=decode(records['completion']);config=decode(records['configuration'])
    aliases=decode(records['original_manifest']);groups=decode(records['group_inventory']);pages=decode(records['page_skeleton'])
    require(set(completion)=={'groups','uploads','page_records','originals_and_readings_unchanged','complete_region_register','private_provider_calls','ledger_writes','output_hashes','config_sha256','operator_sha256','diagram_node_geometry_qualified'},'historical completion schema differs')
    require(set(config)==set(PINS)|{'scope','original_root','cache_root','output','python','group_inventory_file','page_skeleton_file','operator_sha256'},'historical configuration schema differs')
    require(completion['groups']==census['native_groups'] and completion['uploads']==census['original_uploads'] and completion['page_records']==census['native_pages'] and completion['originals_and_readings_unchanged'] is True and completion['complete_region_register'] is False and completion['diagram_node_geometry_qualified'] is False and completion['private_provider_calls']==0 and completion['ledger_writes']==0,'historical completion differs')
    require(completion['config_sha256']==census['configuration_sha256'] and completion['operator_sha256']==census['operator_sha256'],'historical producer/config differs')
    require(config['scope']=='original-locators' and config['operator_sha256']==census['operator_sha256'] and all(config.get(k)==v for k,v in PINS.items()),'historical configuration pins differ')
    require(type(aliases) is list and len(aliases)==census['original_uploads'] and type(groups) is list and len(groups)==census['native_groups'] and type(pages) is list and len(pages)==census['native_pages'],'historical inventory census differs')
    originals={a['source_id']:a for a in aliases};require(len(originals)==len(aliases),'duplicate aliases')
    expected={};seen=set()
    for i,g in enumerate(groups):
        require(digest(g['original_sha256']) and digest(g['reading_sha256']) and integer(g['page_records'],1) and isinstance(g['parser_id'],str),'group identity differs')
        for source in g['source_ids']:
            require(source not in seen and source in originals and originals[source]['sha256']==g['original_sha256'],'group alias differs');seen.add(source)
        own=[p for p in pages if p['region_locator']['original_sha256']==g['original_sha256']]
        nums=[p['region_locator']['page_number'] for p in own]
        require(len(nums)==g['page_records'] and len(set(nums))==len(nums) and all(integer(n,1) for n in nums),'group page census differs')
        name='group-'+str(i)+'-manifest.json';manifest=decode(records[name])
        require(set(manifest)=={'group_index','page_count','pages','alignment_status_counts','complete_region_register'} and manifest['group_index']==i and manifest['page_count']==len(nums) and manifest['complete_region_register'] is False,'group manifest differs')
        require(completion['output_hashes'].get(name)==sha(records[name]),'completion/group chain differs')
        require(type(manifest['pages']) is list and [p['page_number'] for p in manifest['pages']]==sorted(nums),'manifest page order differs')
        for p in manifest['pages']:
            filename='group-'+str(i)+'-page-'+str(p['page_number'])+'.json'
            require(set(p)=={'file','sha256','bytes','page_number','locator_count'} and p['file']==filename and digest(p['sha256']) and integer(p['bytes'],1) and p['bytes']<=8*1024**2 and integer(p['locator_count']),'page hash chain differs')
            expected[filename]={'sha256':p['sha256'],'bytes':p['bytes'],'page':p['page_number'],'original_hash':g['original_sha256'],'reading_hash':g['reading_sha256'],'parser_id':g['parser_id'],'source_ids':g['source_ids'],'locator_count':p['locator_count']}
    require(len({g['original_sha256'] for g in groups})==census['native_groups'],'distinct original groups required')
    require(seen==set(originals) and len(expected)==census['native_pages'] and len(completion['output_hashes'])==census['native_groups'],'complete historical closure required')
    return expected
