#!/usr/bin/env python3
"""Fixed sandbox worker; launch only through the installed native guardian.

No permission or receipt is issued here. The supported action requires the
installed guardian, which verifies genuine dual-scope completion and consumes
its action before private content reads. Worker checks alone do not verify that
action, prove one-use consumption or authorize an OS owner to process captures.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import socket
import stat
import types
import sys
import time

LIMIT=256*1024**2
DECODER_SHA256="84cbcb3119bb6858915bd4538d5527e5ba6a716ab76a914c6db27f0e4202291d"


def require(value,reason):
    if not value:raise ValueError(reason)


def serialize_inputs(control,reader,writer,decoder,clock=time.time):
    """All verified control bytes precede capture bytes; one read per input."""
    require(control['profile']=='oracle-native-alternate-serialization-v1' and control['purpose']=='native-alternate-serialization','fixed operation required')
    require(control['expires_at']>clock() and control['capture_count']==33 and len(control['inputs'])==48,'fixed historical closure required')
    require([x['role'] for x in control['inputs'][:15]]==['completion','configuration','producer','custody','original_manifest','group_inventory','page_skeleton']+['group-'+str(i)+'-manifest.json' for i in range(8)],'fixed control order differs')
    require(type(control['runtime_bytes']) is int and 0<=control['runtime_bytes']<=LIMIT,'invalid runtime byte budget')
    require(all(type(item['stat']['size']) is int and 0<item['stat']['size']<=8*1024**2 for item in control['inputs']),'invalid fixed input sizes')
    require(sum(item['stat']['size'] for item in control['inputs'])+control['runtime_bytes']<=LIMIT,'aggregate input exceeds bound')
    used=control['runtime_bytes'];records={};payloads=[];out_used=0;hashes=[];supported=0
    def read(index):
        nonlocal used
        item=control['inputs'][index];require(clock()<control['expires_at'],'purpose expired during reading')
        maximum=min(item['stat']['size'],8*1024**2,LIMIT-used);require(maximum>=0,'aggregate input exceeds bound')
        raw=reader(index,maximum+1)
        require(type(raw) is bytes and len(raw)==item['stat']['size'] and len(raw)<=maximum,'input size differs or exceeds bound')
        used+=len(raw);require(hashlib.sha256(raw).hexdigest()==item['sha256'],'actual input hash differs')
        return raw
    # Fixed first seven metadata controls, then eight group manifests.
    for i,item in enumerate(control['inputs'][:15]):records[item['role']]=read(i)
    expected=decoder.validate_controls(records,census=control['census'])
    require([x['role'] for x in control['inputs'][15:]]==list(expected),'exact captured page inventory/order differs')
    for index,item in enumerate(control['inputs'][15:],15):
        bound=expected[item['role']]
        require(item['sha256']==bound['sha256'] and item['stat']['size']==bound['bytes'],'page descriptor differs from verified control chain')
        page=decoder.decode(read(index))
        require(page.get('reading_sha256')==bound['reading_hash'] and page.get('qualified_reading_parser_id')==bound['parser_id'] and page.get('source_ids')==bound['source_ids'] and len(page.get('native_locators',[]))==bound['locator_count'],'page historical group binding differs')
        artifact=decoder.serialize_page(page,capture_hash=item['sha256'],expected_original=bound['original_hash'],expected_page=bound['page'])
        supported+=sum(s['utf8_end']>s['utf8_start'] for s in artifact['segments'])
        payload=json.dumps(artifact,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
        require(len(payload)<=8*1024**2,'per-file output exceeds bound')
        out_used+=len(payload);require(out_used<=LIMIT,'aggregate output exceeds bound')
        payloads.append(payload);hashes.append(hashlib.sha256(payload).hexdigest())
    require(supported>0,'no captured supported text')
    for index,payload in enumerate(payloads):
        require(clock()<control['expires_at'],'purpose expired before output');writer(index,payload)
    return dict(status='unqualified-native-alternate-v1',artifact_count=33,output_bytes=out_used,
        outputs_sha256=hashlib.sha256(json.dumps(hashes,separators=(',',':')).encode()).hexdigest(),source_qualified=False,ledger_adopted=False)


def validate_mounts(lines,input_count,output_info):
    """Defense in depth for the guardian recipe; never proof of admission."""
    mounts={}
    for line in lines:
        fields=line.split();require(len(fields)>8 and '-' in fields,'malformed mount record')
        path=fields[4];require(path not in mounts,'duplicate mount target')
        mounts[path]=(set(fields[5].split(',')),fields[fields.index('-')+1])
    required={'/','/code/operator.py','/code/native_alternate.py','/output','/proc','/dev','/dev/pts'}|{'/input/c'+str(i) for i in range(input_count)}
    devices={'/dev/'+n for n in ('null','zero','full','random','urandom','tty')}
    require(required<=set(mounts) and set(mounts)<=required|devices,'unexpected or absent mount')
    for path in {'/','/code/operator.py','/code/native_alternate.py'}|{'/input/c'+str(i) for i in range(input_count)}:
        require('ro' in mounts[path][0],'code/runtime/input mount must be read-only')
    require('rw' in mounts['/output'][0] and stat.S_ISDIR(output_info.st_mode) and stat.S_IMODE(output_info.st_mode)==0o700 and output_info.st_uid==os.getuid(),'owned private output mount required')
    require(mounts['/proc'][1]=='proc' and mounts['/dev'][1]=='tmpfs' and mounts['/dev/pts'][1]=='devpts','isolated kernel mounts required')
    for path in devices&set(mounts):require(mounts[path][1]=='devtmpfs','unexpected device mount')


def load_decoder(path,expected=DECODER_SHA256):
    info=Path(path).lstat();require(stat.S_ISREG(info.st_mode),'regular pinned decoder required')
    raw=Path(path).read_bytes();require(hashlib.sha256(raw).hexdigest()==expected,'fixed public decoder differs')
    module=types.ModuleType('native_page_alternate')
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module


def main():
    # The actual native guardian is the admission boundary, not a caller flag.
    # Namespace/mount/code checks provide defense in depth. An OS owner can
    # invoke a matching isolated worker; these checks issue no authority.
    require(os.getpid() in (1,2) and socket.if_nameindex()==[(1,'lo')],'isolated namespace required')
    raw=sys.stdin.buffer.read(1024**2+1);require(len(raw)<=1024**2,'control exceeds bound')
    control=json.loads(raw)
    require(set(control)=={'profile','purpose','limits','inputs','capture_count','expires_at','runtime_bytes','census'},'exact guardian control required')
    require(control['capture_count']==33 and control['census']['native_groups']==8
        and control['census']['native_pages']==33 and control['census']['original_uploads']==26,'fixed historical census required')
    expected=dict(input_bytes=LIMIT,output_bytes=LIMIT,per_file_bytes=8*1024**2,workers=1,threads=2,address_space_bytes=8*1024**3,
                  cpu_seconds=120,wall_seconds=180,network='none')
    require(control['limits']==expected,'fixed sandbox limits required')
    resource.setrlimit(resource.RLIMIT_NPROC,(1,1))
    require(resource.getrlimit(resource.RLIMIT_AS)==(8*1024**3,)*2
        and resource.getrlimit(resource.RLIMIT_CPU)==(120,120),'actual resource limits required')
    validate_mounts(Path('/proc/self/mountinfo').read_text().splitlines(),len(control['inputs']),Path('/output').lstat())
    require(not Path('/output').is_symlink() and not list(Path('/output').iterdir()),'fresh empty output required')
    decoder=load_decoder('/code/native_alternate.py')
    require(control['census']==decoder.HISTORY,'fixed historical source pins required')
    def reader(index,maximum):
        fd=os.open('/input/c'+str(index),os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as stream:return stream.read(maximum)
    def writer(index,payload):
        fd=os.open('/output/c'+str(index)+'.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as out:out.write(payload);out.flush();os.fsync(out.fileno())
    receipt=serialize_inputs(control,reader,writer,decoder)
    print(json.dumps(receipt,sort_keys=True))


if __name__=='__main__':
    try:main()
    except Exception:
        print('native alternate worker stopped; unqualified partials retained',file=sys.stderr);sys.exit(1)
