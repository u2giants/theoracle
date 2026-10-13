"""Invented fixed8/33/26 control chains; no permission or private reads."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import pytest
from oracle_brain.operating_model import native_page_alternate as codec
from test_native_page_alternate import page
ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('operator',ROOT/'scripts/oracle2/native_alternate_operator.py')
operator=importlib.util.module_from_spec(spec);spec.loader.exec_module(operator)

@pytest.fixture(autouse=True)
def restore_pins():
    before=codec.PINS.copy()
    yield
    codec.PINS.clear();codec.PINS.update(before)

def raw(v):return json.dumps(v,separators=(',',':')).encode()
def case():
    controls={};aliases=[];groups=[];skeleton=[];captures={};manifests={}
    for i in range(8):
        original=hashlib.sha256(str(i).encode()).hexdigest();sources=['alias-'+str(n) for n in range(i*3,i*3+3+(2 if i==7 else 0))]
        aliases.extend(dict(source_id=s,sha256=original,bytes=1) for s in sources)
        g=dict(original_sha256=original,reading_sha256='b'*64,parser_id='invented',source_ids=sources,page_records=5 if i==0 else 4);groups.append(g);refs=[]
        for n in range(1,g['page_records']+1):
            p=page();p.update(original_sha256=original,source_ids=sources,native_page_number=n)
            for loc in p['native_locators']:
                loc['page']=n
                if 'parent_table_provenance' in loc:loc['parent_table_provenance']['page']=n
            name=f'group-{i}-page-{n}.json';captures[name]=raw(p)
            refs.append(dict(file=name,sha256=codec.sha(captures[name]),bytes=len(captures[name]),page_number=n,locator_count=2))
            skeleton.append(dict(region_locator=dict(original_sha256=original,page_number=n)))
        name=f'group-{i}-manifest.json';manifests[name]=raw(dict(group_index=i,page_count=len(refs),pages=refs,alignment_status_counts={},complete_region_register=False))
    census=dict(native_groups=8,original_uploads=26,native_pages=33,configuration_sha256='c'*64,operator_sha256='d'*64)
    completion=dict(groups=8,uploads=26,page_records=33,originals_and_readings_unchanged=True,complete_region_register=False,diagram_node_geometry_qualified=False,private_provider_calls=0,ledger_writes=0,config_sha256='c'*64,operator_sha256='d'*64,output_hashes={n:codec.sha(b) for n,b in manifests.items()})
    controls.update(completion=raw(completion),configuration=raw(dict(scope='original-locators',operator_sha256='d'*64,**codec.PINS)),producer=b'INVENTED PRODUCER',custody=b'INVENTED CUSTODY',original_manifest=raw(aliases),group_inventory=raw(groups),page_skeleton=raw(skeleton));controls.update(manifests)
    # Pure fixtures replace expected hash pins only in memory; no authority is issued.
    for role,key in (('original_manifest','original_manifest_sha256'),('group_inventory','group_inventory_sha256'),('page_skeleton','page_skeleton_sha256')):codec.PINS[key]=codec.sha(controls[role])
    config=dict(scope='original-locators',operator_sha256=codec.sha(controls['producer']),original_root='/invented',cache_root='/invented',output='/invented',python='/invented',group_inventory_file='/invented',page_skeleton_file='/invented',**codec.PINS)
    controls['configuration']=raw(config);census['operator_sha256']=codec.sha(controls['producer']);census['configuration_sha256']=codec.sha(controls['configuration']);census['custody_sha256']=codec.sha(controls['custody'])
    completion.update(operator_sha256=census['operator_sha256'],config_sha256=census['configuration_sha256']);controls['completion']=raw(completion);census['completion_sha256']=codec.sha(controls['completion'])
    allfiles={**controls,**captures};inputs=[dict(role=n,sha256=codec.sha(b),stat={'size':len(b)}) for n,b in allfiles.items()]
    control=dict(profile='oracle-native-alternate-serialization-v1',purpose='native-alternate-serialization',expires_at=200,capture_count=33,runtime_bytes=1,census=census,inputs=inputs)
    reads=[];writes={};values=list(allfiles.values())
    def reader(index,maximum):reads.append(index);return values[index][:maximum]
    return control,values,reads,writes,reader

def test_exact_chain_one_read_control_before_capture_utf8_outputs():
    c,v,reads,writes,reader=case();r=operator.serialize_inputs(c,reader,lambda i,b:writes.update({i:b}),codec,clock=lambda:100)
    assert reads==list(range(48)) and len(writes)==33 and r['artifact_count']==33
    assert json.loads(writes[0])['text']=='Ω🙂 X ' and not r['source_qualified']

@pytest.mark.parametrize('damage',['purpose','expired','hash','size','budget','control','pagechain','inventory','nocapturedtext'])
def test_refusals_write_nothing(damage):
    c,v,reads,writes,reader=case()
    if damage=='purpose':c['purpose']='source-extraction'
    elif damage=='expired':c['expires_at']=100
    elif damage=='hash':c['inputs'][15]['sha256']='e'*64
    elif damage=='size':c['inputs'][0]['stat']['size']+=1
    elif damage=='budget':c['runtime_bytes']=operator.LIMIT
    elif damage=='control':
        x=json.loads(v[0]);x['groups']=9;v[0]=raw(x);c['inputs'][0].update(sha256=codec.sha(v[0]),stat={'size':len(v[0])})
    elif damage=='pagechain':c['inputs'][15]['role']='group-7-page-999.json'
    elif damage=='inventory':
        x=json.loads(v[4]);x[0]['source_id']=x[1]['source_id'];v[4]=raw(x);c['inputs'][4].update(sha256=codec.sha(v[4]),stat={'size':len(v[4])})
    else:
        class Empty:
            decode=staticmethod(codec.decode);validate_controls=staticmethod(codec.validate_controls)
            @staticmethod
            def serialize_page(*a,**kw):return {'segments':[]}
        with pytest.raises(ValueError):operator.serialize_inputs(c,reader,lambda i,b:writes.update({i:b}),Empty,clock=lambda:100)
        assert not writes;return
    with pytest.raises(ValueError):operator.serialize_inputs(c,reader,lambda i,b:writes.update({i:b}),codec,clock=lambda:100)
    assert not writes
    if damage in ('control','inventory'):assert all(i<15 for i in reads)

def test_standalone_worker_denies():
    r=subprocess.run([sys.executable,str(ROOT/'scripts/oracle2/native_alternate_operator.py')],input=b'',capture_output=True)
    assert r.returncode!=0

def test_control_order_refuses_before_any_content_reads():
    c,v,reads,writes,reader=case();c['inputs'][0],c['inputs'][1]=c['inputs'][1],c['inputs'][0]
    with pytest.raises(ValueError):operator.serialize_inputs(c,reader,lambda i,b:writes.update({i:b}),codec,clock=lambda:100)
    assert not reads and not writes

def test_expiry_between_control_and_pages_reads_no_capture():
    c,v,reads,writes,reader=case()
    def clock():return 200 if len(reads)>=15 else 100
    with pytest.raises(ValueError):operator.serialize_inputs(c,reader,lambda i,b:writes.update({i:b}),codec,clock=clock)
    assert reads==list(range(15)) and not writes

def test_per_file_output_bound_refuses_before_writes():
    c,v,reads,writes,reader=case()
    class Large:
        decode=staticmethod(codec.decode);validate_controls=staticmethod(codec.validate_controls)
        @staticmethod
        def serialize_page(*a,**kw):return {'segments':[{'utf8_start':0,'utf8_end':1}],'text':'x'*(8*1024**2)}
    with pytest.raises(ValueError):operator.serialize_inputs(c,reader,lambda i,b:writes.update({i:b}),Large,clock=lambda:100)
    assert not writes
