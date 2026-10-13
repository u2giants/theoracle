"""Invented fixed chain only; no registration/claim/private files."""
import copy,importlib.util,os
from pathlib import Path
import pytest
from oracle_brain.operating_model import native_page_alternate as codec,native_page_chain as chain
from test_native_alternate_operator import case,restore_pins,raw
ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('chain_operator',ROOT/'scripts/oracle2/native_alternate_chain_operator.py');op=importlib.util.module_from_spec(spec);spec.loader.exec_module(op)
def v2():
 c,v,reads,writes,reader=case();c['schema_version']=2;c['profile']='oracle-native-alternate-serialization-v2'
 for i,item in enumerate(c['inputs']):
  h=item.pop('sha256');item['stat'].update(dev=1,ino=i+1,mode=0o600,uid=os.getuid(),mtime_ns=1,ctime_ns=1)
  item['commitment']={'kind':'fixed-sha256','sha256':h} if i<7 else {'kind':'verified-parent','parent_role':'completion' if i<15 else 'group-'+item['role'].split('-')[1]+'-manifest.json','child_role':item['role']}
 return c,v,reads,writes,reader
def run(c,reader,writes,clock=lambda:100):return op.serialize_inputs(c,reader,lambda i,b:writes.update({i:b}),codec,chain,clock=clock)
def test_complete_v2_and_legacy_unchanged():
 c,v,reads,writes,reader=v2();r=run(c,reader,writes);assert len(writes)==33 and reads==list(range(48));assert r['source_qualified'] is False
@pytest.mark.parametrize('damage',['legacy','root','order','duplicate','inode','stat','parent','unknown','expired'])
def test_pre_read_refusals(damage):
 c,v,reads,writes,reader=v2()
 if damage=='legacy':c['profile']='oracle-native-alternate-serialization-v1'
 elif damage=='root':c['inputs'][0]['commitment']['sha256']='0'*64
 elif damage=='order':c['inputs'][7],c['inputs'][8]=c['inputs'][8],c['inputs'][7]
 elif damage=='duplicate':c['inputs'][47]['role']=c['inputs'][46]['role']
 elif damage=='inode':c['inputs'][1]['stat']['ino']=1
 elif damage=='stat':c['inputs'][0]['stat']['mode']=0o644
 elif damage=='parent':c['inputs'][15]['commitment']['parent_role']='completion'
 elif damage=='unknown':c['inputs'][7]['commitment']['sha256']='0'*64
 else:c['expires_at']=0
 with pytest.raises(ValueError):run(c,reader,writes)
 assert not reads and not writes
@pytest.mark.parametrize('damage',['invalidroot','wronggroup','wrongpage','unknownchild'])
def test_authenticated_chain_stops_before_dependent_reads(damage):
 c,v,reads,writes,reader=v2()
 if damage=='invalidroot':v[0]=v[0]+b' '
 elif damage=='wronggroup':v[7]=v[7]+b' '
 elif damage=='wrongpage':v[15]=v[15]+b' '
 else:c['inputs'][15]['role']='group-0-page-99.json';c['inputs'][15]['commitment']['child_role']=c['inputs'][15]['role']
 with pytest.raises(ValueError):run(c,reader,writes)
 assert not writes
 if damage=='invalidroot':assert all(i<7 for i in reads)
 elif damage=='wronggroup':assert max(reads)==7
 elif damage=='unknownchild':assert max(reads)==6
 else:assert max(reads)==15
@pytest.mark.parametrize('boundary',[7,8,15,48])
def test_expiry_interleaving_no_writes(boundary):
 c,v,reads,writes,reader=v2()
 with pytest.raises(ValueError):run(c,reader,writes,clock=lambda:200 if len(reads)>=boundary else 100)
 assert len(reads)==boundary and not writes

def test_metadata_descriptor_only_no_permission(monkeypatch):
 c,v,reads,writes,reader=v2();monkeypatch.setattr(codec,'HISTORY',c['census'])
 d={'schema_version':2,'profile':c['profile'],'inputs':[dict(x,path='/invented/c'+str(i)) for i,x in enumerate(c['inputs'])]}
 result=chain.validate_metadata_descriptor(d,codec=codec)
 assert result=={'source_only':True,'authorizes_read':False,'input_count':48,'conditional_children':41} and not reads and not writes
 for mutate in ('unknownsha','path','inode','population','legacy'):
  x=copy.deepcopy(d)
  if mutate=='unknownsha':x['inputs'][7]['commitment']['sha256']='a'*64
  elif mutate=='path':x['inputs'][0]['path']='/invented/../c0'
  elif mutate=='inode':x['inputs'][1]['stat']['ino']=1
  elif mutate=='population':x['inputs'].pop()
  else:x['schema_version']=1
  with pytest.raises(ValueError):chain.validate_metadata_descriptor(x,codec=codec)

def test_group_schema_failure_reads_no_pages():
 c,v,reads,writes,reader=v2();group=codec.decode(v[7]);group['pages'][0]['file']='arbitrary.json';v[7]=raw(group)
 completion=codec.decode(v[0]);completion['output_hashes']['group-0-manifest.json']=codec.sha(v[7]);v[0]=raw(completion)
 c['census']['completion_sha256']=codec.sha(v[0]);c['inputs'][0]['commitment']['sha256']=codec.sha(v[0]);c['inputs'][0]['stat']['size']=len(v[0]);c['inputs'][7]['stat']['size']=len(v[7])
 with pytest.raises(ValueError):run(c,reader,writes)
 assert reads==list(range(8)) and not writes

def test_standalone_v2_has_no_authority():
 import subprocess,sys
 r=subprocess.run([sys.executable,str(ROOT/'scripts/oracle2/native_alternate_chain_operator.py')],input=b'',capture_output=True)
 assert r.returncode!=0

@pytest.mark.parametrize('damage',['input-list','item','role','stat','size'])
def test_malformed_shape_clean_refusal_before_any_reads(damage):
 c,v,reads,writes,reader=v2()
 if damage=='input-list':c['inputs']=None
 elif damage=='item':c['inputs'][0]=None
 elif damage=='role':del c['inputs'][0]['role']
 elif damage=='stat':c['inputs'][0]['stat']=None
 else:del c['inputs'][0]['stat']['size']
 with pytest.raises(ValueError):run(c,reader,writes)
 assert not reads and not writes

def test_source_contract_actual_code_hashes_and_legacy_decoder_pin():
 import hashlib,json
 contract=json.loads((ROOT/'scripts/oracle2/contracts/native_alternate_chain_v2.json').read_text())
 for name,h in contract['code_sha256'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h
 assert contract['authorizes_read'] is False and contract['legacy_approval_accepted'] is False
 assert op.CHAIN_SHA256==contract['code_sha256']['services/oracle-brain/oracle_brain/operating_model/native_page_chain.py']
 assert op.DECODER_SHA256=='84cbcb3119bb6858915bd4538d5527e5ba6a716ab76a914c6db27f0e4202291d'

@pytest.mark.parametrize('prefix',[1,17,32])
def test_mid_write_expiry_retains_unqualified_prefix_without_completion(prefix):
 c,v,reads,writes,reader=v2();completion=[]
 def writer(index,payload):writes[index]=payload
 with pytest.raises(ValueError,match='expired before output'):
  completion.append(op.serialize_inputs(c,reader,writer,codec,chain,clock=lambda:200 if len(writes)>=prefix else 100))
 assert reads==list(range(48)) and list(writes)==list(range(prefix)) and not completion
 for payload in writes.values():
  artifact=codec.decode(payload)
  assert artifact['source_qualified'] is False and artifact['ledger_adopted'] is False and artifact['source_ref_issued'] is False

@pytest.mark.parametrize('index',[0,15])
@pytest.mark.parametrize('role',[None,False,[],{}])
def test_nonstring_root_page_roles_fail_before_reads(index,role):
 c,v,reads,writes,reader=v2();c['inputs'][index]['role']=role
 with pytest.raises(ValueError):run(c,reader,writes)
 assert not reads and not writes

def test_worker_current_uid_is_authoritative_before_any_read():
 c,v,reads,writes,reader=v2();c['inputs'][15]['stat']['uid']=os.getuid()+1
 with pytest.raises(ValueError,match='private unique inode'):run(c,reader,writes)
 assert not reads and not writes

@pytest.mark.parametrize('mutation',['atime','dev','ino','uid','gid','mode','nlink','size','mtime_ns','ctime_ns'])
def test_actual_main_input_reader_integrity_fields(tmp_path,monkeypatch,mutation):
    from types import SimpleNamespace
    path=tmp_path/'invented-input';path.write_bytes(b'invented native bytes');path.chmod(0o600)
    os.utime(path,(1000000000,1000000000));before=path.stat()
    declared=dict(dev=before.st_dev,ino=before.st_ino,size=before.st_size,mode=0o600,
                  uid=before.st_uid,mtime_ns=before.st_mtime_ns,ctime_ns=before.st_ctime_ns)
    real_open=os.open;real_fstat=os.fstat;calls=[]
    def opened(name,flags,*args,**kwargs):
        assert name=='/input/c0' and flags & os.O_NOFOLLOW
        return real_open(path,flags,*args,**kwargs)
    def observed(fd):
        info=real_fstat(fd);calls.append(info)
        if len(calls)==1:return info
        fields={name:getattr(info,name) for name in ('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns','st_atime')}
        if mutation=='atime':fields['st_atime']=before.st_atime+100
        else:fields['st_'+mutation]+=1
        return SimpleNamespace(**fields)
    monkeypatch.setattr(op.os,'open',opened);monkeypatch.setattr(op.os,'fstat',observed)
    if mutation=='atime':assert op.read_mounted_input({'inputs':[{'stat':declared}]},0,8*1024**2)==b'invented native bytes'
    else:
        with pytest.raises(ValueError,match='input changed during read'):
            op.read_mounted_input({'inputs':[{'stat':declared}]},0,8*1024**2)
    assert len(calls)==2

def test_actual_main_reader_rejects_hardlinked_input_before_read(tmp_path,monkeypatch):
    path=tmp_path/'input';path.write_bytes(b'invented');path.chmod(0o600);os.link(path,tmp_path/'alias')
    info=path.stat();declared=dict(dev=info.st_dev,ino=info.st_ino,size=info.st_size,mode=0o600,uid=info.st_uid,mtime_ns=info.st_mtime_ns,ctime_ns=info.st_ctime_ns)
    real_open=os.open
    monkeypatch.setattr(op.os,'open',lambda name,flags:real_open(path,flags))
    with pytest.raises(ValueError,match='input stat moved'):op.read_mounted_input({'inputs':[{'stat':declared}]},0,8*1024**2)
