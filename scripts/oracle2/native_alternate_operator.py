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
    """Deterministic byte accounting; test readers contain invented JSON only."""
    require(control['profile']=='oracle-native-alternate-serialization-v1'
        and control['purpose']=='native-alternate-serialization','fixed operation required')
    require(control['expires_at']>clock() and type(control['capture_count']) is int
        and len(control['inputs'])==control['capture_count']+1,'fixed current capture census required')
    used=control['runtime_bytes'];out_used=0;hashes=[];payloads=[];pages=0
    for index,item in enumerate(control['inputs']):
        require(clock()<control['expires_at'],'purpose expired during reading')
        maximum=min(item['stat']['size'],LIMIT-used)
        require(maximum>=0,'aggregate input exceeds bound')
        raw=reader(index,maximum+1)
        require(type(raw) is bytes and len(raw)==item['stat']['size'] and len(raw)<=maximum,'input size differs or exceeds bound')
        used+=len(raw)
        require(hashlib.sha256(raw).hexdigest()==item['sha256'],'actual input hash differs')
        if index==control['capture_count']:
            # Original-register metadata is bound/retained, not reparsed into
            # company claims, permissions or a qualified current SourceRef.
            continue
        document=json.loads(raw)
        artifact=decoder(document,original_hash=item['original_hash'],capture_hash=item['sha256'])
        pages+=len(artifact['pages'])
        require(artifact['status']=='unqualified-native-alternate-v1' and artifact['source_qualified'] is False
            and artifact['ledger_adopted'] is False,'qualification is outside this action')
        payload=json.dumps(artifact,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
        out_used+=len(payload);require(out_used<=LIMIT,'aggregate output exceeds bound')
        require(clock()<control['expires_at'],'purpose expired before output')
        payloads.append(payload);hashes.append(hashlib.sha256(payload).hexdigest())
    require(pages==control['census']['native_pages'] and len(payloads)==control['census']['native_groups'],'native page/group census differs')
    for index,payload in enumerate(payloads):
        require(clock()<control['expires_at'],'purpose expired before output')
        writer(index,payload)
    return dict(status='unqualified-native-alternate-v1',artifact_count=control['capture_count'],output_bytes=out_used,
        outputs_sha256=hashlib.sha256(json.dumps(hashes,separators=(',',':')).encode()).hexdigest(),
        source_qualified=False,ledger_adopted=False)


def main():
    # The actual native guardian is the admission boundary, not a caller flag.
    # Worker additionally refuses ordinary host invocation and any broad mount.
    require(os.getpid() in (1,2) and socket.if_nameindex()==[(1,'lo')],'isolated namespace required')
    raw=sys.stdin.buffer.read(1024**2+1);require(len(raw)<=1024**2,'control exceeds bound')
    control=json.loads(raw)
    require(set(control)=={'profile','purpose','limits','inputs','capture_count','expires_at','runtime_bytes','census'},'exact guardian control required')
    require(control['capture_count']==8 and control['census']['native_groups']==8
        and control['census']['native_pages']==33 and control['census']['original_uploads']==26,'fixed historical census required')
    expected=dict(input_bytes=LIMIT,output_bytes=LIMIT,workers=1,threads=2,address_space_bytes=8*1024**3,
                  cpu_seconds=120,wall_seconds=180,network='none')
    require(control['limits']==expected,'fixed sandbox limits required')
    resource.setrlimit(resource.RLIMIT_NPROC,(1,1))
    require(resource.getrlimit(resource.RLIMIT_AS)==(8*1024**3,)*2
        and resource.getrlimit(resource.RLIMIT_CPU)==(120,120),'actual resource limits required')
    mounts=Path('/proc/self/mountinfo').read_text().splitlines()
    for index in range(len(control['inputs'])):
        require(any(line.split()[4]=='/input/c'+str(index) and 'ro' in line.split()[5].split(',') for line in mounts),'read-only descriptor mount required')
    require(not Path('/home').exists() or not list(Path('/home').iterdir()),'host home must not be mounted')
    spec=importlib.util.spec_from_file_location('native_alternate','/code/native_alternate.py')
    decoder=importlib.util.module_from_spec(spec);spec.loader.exec_module(decoder)
    def reader(index,maximum):
        fd=os.open('/input/c'+str(index),os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as stream:return stream.read(maximum)
    def writer(index,payload):
        fd=os.open('/output/c'+str(index)+'.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as out:out.write(payload);out.flush();os.fsync(out.fileno())
    receipt=serialize_inputs(control,reader,writer,decoder.serialize_docling)
    print(json.dumps(receipt,sort_keys=True))


if __name__=='__main__':
    try:main()
    except Exception:
        print('native alternate worker stopped; unqualified partials retained',file=sys.stderr);sys.exit(1)
