#!/usr/bin/env python3
"""Fixed sandbox worker; launch only through the installed native guardian.

No permission or receipt is issued here. The guardian verifies genuine native
dual-scope completion and durably consumes its action BEFORE opening/mounting
captures. A standalone invocation has no supported private-processing route.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import socket
import sys
import time

LIMIT=256*1024**2


def require(value,reason):
    if not value:raise ValueError(reason)


def serialize_inputs(control,reader,writer,decoder,clock=time.time):
    """All verified control bytes precede capture bytes; one read per input."""
    require(control['profile']=='oracle-native-alternate-serialization-v1' and control['purpose']=='native-alternate-serialization','fixed operation required')
    require(control['expires_at']>clock() and control['capture_count']==33 and len(control['inputs'])==48,'fixed historical closure required')
    require([x['role'] for x in control['inputs'][:15]]==['completion','configuration','producer','custody','original_manifest','group_inventory','page_skeleton']+['group-'+str(i)+'-manifest.json' for i in range(8)],'fixed control order differs')
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


def main():
    # The actual native guardian is the admission boundary, not a caller flag.
    # Worker additionally refuses ordinary host invocation and any broad mount.
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
    mounts=Path('/proc/self/mountinfo').read_text().splitlines()
    for index in range(len(control['inputs'])):
        require(any(line.split()[4]=='/input/c'+str(index) and 'ro' in line.split()[5].split(',') for line in mounts),'read-only descriptor mount required')
    require(not Path('/home').exists() or not list(Path('/home').iterdir()),'host home must not be mounted')
    spec=importlib.util.spec_from_file_location('native_page_alternate','/code/native_alternate.py')
    decoder=importlib.util.module_from_spec(spec);spec.loader.exec_module(decoder)
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
