"""Pure staged v2 validators; unchanged v1 codec is passed explicitly.
No reads, permission, registration, SourceRef or execution authority.
"""
def validate_roots(records, *, census, codec):
    require=codec.require;sha=codec.sha;decode=codec.decode;digest=codec.digest;integer=codec.integer;PINS=codec.PINS
    require(set(records)=={'completion','configuration','producer','custody','original_manifest','group_inventory','page_skeleton'},'exact seven roots required')
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
    seen=set();bindings={}
    for i,g in enumerate(groups):
        require(digest(g['original_sha256']) and digest(g['reading_sha256']) and integer(g['page_records'],1) and isinstance(g['parser_id'],str),'group identity differs')
        for source in g['source_ids']:
            require(source not in seen and source in originals and originals[source]['sha256']==g['original_sha256'],'group alias differs');seen.add(source)
        own=[p for p in pages if p['region_locator']['original_sha256']==g['original_sha256']]
        nums=[p['region_locator']['page_number'] for p in own]
        require(len(nums)==g['page_records'] and len(set(nums))==len(nums) and all(integer(n,1) for n in nums),'group page census differs')
        name='group-'+str(i)+'-manifest.json'
        require(digest(completion['output_hashes'].get(name)), 'group parent commitment missing')
        bindings[name]={'sha256':completion['output_hashes'][name],'group':g,'numbers':sorted(nums),'index':i}
    require(set(completion['output_hashes'])==set(bindings) and seen==set(originals) and len({g['original_sha256'] for g in groups})==census['native_groups'], 'complete historical root closure required')
    return bindings


def validate_group(raw, *, name, binding, codec):
    require=codec.require;decode=codec.decode;sha=codec.sha;digest=codec.digest;integer=codec.integer
    require(sha(raw)==binding['sha256'],'completion/group chain differs')
    manifest=decode(raw);i=binding['index'];g=binding['group'];nums=binding['numbers']
    require(set(manifest)=={'group_index','page_count','pages','alignment_status_counts','complete_region_register'} and manifest['group_index']==i and manifest['page_count']==len(nums) and manifest['complete_region_register'] is False,'group manifest differs')
    require(type(manifest['pages']) is list and [p['page_number'] for p in manifest['pages']]==nums,'manifest page order differs')
    expected={}
    for p in manifest['pages']:
        filename='group-'+str(i)+'-page-'+str(p['page_number'])+'.json'
        require(set(p)=={'file','sha256','bytes','page_number','locator_count'} and p['file']==filename and digest(p['sha256']) and integer(p['bytes'],1) and p['bytes']<=8*1024**2 and integer(p['locator_count']),'page hash chain differs')
        require(filename not in expected,'duplicate page identity')
        expected[filename]={'sha256':p['sha256'],'bytes':p['bytes'],'page':p['page_number'],'original_hash':g['original_sha256'],'reading_hash':g['reading_sha256'],'parser_id':g['parser_id'],'source_ids':g['source_ids'],'locator_count':p['locator_count']}
    return expected


def validate_metadata_descriptor(descriptor, *, codec):
    """Source-only metadata shape check; no stat/read/admission performed.

    Current external stat, genuine custody and guardian registration remain
    mandatory. This function neither authenticates them nor issues authority.
    """
    require=codec.require
    require(type(descriptor) is dict and set(descriptor)=={'schema_version','profile','inputs'} and descriptor['schema_version']==2 and descriptor['profile']=='oracle-native-alternate-serialization-v2','exact v2 metadata descriptor required')
    inputs=descriptor['inputs'];require(type(inputs) is list and len(inputs)==48,'fixed metadata population required')
    roots=['completion','configuration','producer','custody','original_manifest','group_inventory','page_skeleton']
    groups=['group-'+str(i)+'-manifest.json' for i in range(8)]
    require([x['role'] for x in inputs[:15]]==roots+groups,'fixed metadata control order required')
    pins={'completion':codec.HISTORY['completion_sha256'],'configuration':codec.HISTORY['configuration_sha256'],'producer':codec.HISTORY['operator_sha256'],'custody':codec.HISTORY['custody_sha256'],'original_manifest':codec.PINS['original_manifest_sha256'],'group_inventory':codec.PINS['group_inventory_sha256'],'page_skeleton':codec.PINS['page_skeleton_sha256']}
    paths=set();inodes=set();roles=set();total=0
    import re
    for i,item in enumerate(inputs):
        require(type(item) is dict and set(item)=={'path','role','stat','commitment'},'exact metadata input required')
        path=item['path'];require(isinstance(path,str) and path.startswith('/') and not any(x in ('','..','.') for x in path.split('/')[1:]) and path not in paths,'fixed unique absolute path required');paths.add(path)
        st=item['stat'];require(type(st) is dict and set(st)=={'dev','ino','size','mode','uid','mtime_ns','ctime_ns'} and all(type(v) is int and v>=0 for v in st.values()) and st['mode']==0o600 and 0<st['size']<=8*1024**2,'metadata stat commitment differs')
        require((st['dev'],st['ino']) not in inodes,'duplicate metadata inode');inodes.add((st['dev'],st['ino']));total+=st['size']
        role=item['role'];require(isinstance(role,str) and role not in roles,'duplicate metadata role');roles.add(role)
        if i<7:require(item['commitment']=={'kind':'fixed-sha256','sha256':pins[role]},'fixed metadata root pin required')
        else:
            if i>=15:require(re.fullmatch(r'group-[0-7]-page-[1-9][0-9]*\.json',role),'fixed metadata page identity required')
            parent='completion' if i<15 else 'group-'+role.split('-')[1]+'-manifest.json'
            require(item['commitment']=={'kind':'verified-parent','parent_role':parent,'child_role':role},'typed metadata parent required')
    require(total<=256*1024**2,'metadata aggregate bound exceeded')
    return {'source_only':True,'authorizes_read':False,'input_count':48,'conditional_children':41}
