#!/usr/bin/env python3
"""Owned invented mount/process proof only; never installation attestation."""
import argparse
import json
import pathlib
import subprocess
import tempfile
import uuid

IMAGE='node@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20'
PHASES=('census','assembly','assessment','embedding')

def docker(*args):
    return subprocess.check_output(['docker',*args],text=True,stderr=subprocess.PIPE,timeout=30).strip()

def prove(root):
    root=pathlib.Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    owner='oracle-purpose-'+uuid.uuid4().hex
    paths={phase:root/phase for phase in PHASES}
    for phase,path in paths.items():
        path.mkdir(mode=0o755)
        (path/'context.json').write_text(json.dumps({'phase':phase,'invented':True}))
        (path/'context.json').chmod(0o444)
    # Budget authority has its own mount root, never the private phase parent.
    budget=root/'central-budget';budget.mkdir(mode=0o755)
    (budget/'account.json').write_text('{"invented_account":"no-private-source-content"}')
    (budget/'account.json').chmod(0o444)
    parent=root/'parent.registry';parent.write_text('INVENTED_FULL_PRIVATE_PARENT');parent.chmod(0o444)
    (paths['census']/'escape').symlink_to(parent)
    for suffix in ('-journal','-wal','-shm','.backup'):
        (root/('parent.registry'+suffix)).write_text('INVENTED_SIBLING_PRIVATE_CONTENT')
    result={'schema_version':2,'synthetic':True,'installation_admission':False,'phases':{}}
    probe=r'''
const fs=require('fs');const assert=require('assert');
const phase=process.argv[1];assert.equal(JSON.parse(fs.readFileSync('/run/phase/context.json')).phase,phase);
assert.equal(JSON.parse(fs.readFileSync('/run/budget/account.json')).invented_account,'no-private-source-content');
for(const path of ['/var/run/docker.sock','/run/parent.registry','/run/phase/../parent.registry','/run/phase/escape','/run/parent.registry-wal','/run/parent.registry-journal','/run/parent.registry.backup','/proc/1/root/run/parent.registry'])assert(!fs.existsSync(path),path);
for(const other of ['census','assembly','assessment','embedding'])assert(!fs.existsSync('/run/'+other+'/context.json'));
assert.throws(()=>fs.writeFileSync('/run/phase/new','x'));assert.throws(()=>fs.writeFileSync('/run/budget/new','x'));
assert.notEqual(process.getuid(),0);assert(/CapEff:\s+0+\n/.test(fs.readFileSync('/proc/self/status','utf8')));
console.log(JSON.stringify({own_phase:phase,siblings_absent:true,parent_absent:true,read_only:true,nonroot:true,no_capabilities:true}));
'''
    for phase,path in paths.items():
        name=owner+'-'+phase
        if subprocess.run(['docker','inspect',name],capture_output=True).returncode==0:raise RuntimeError('owned test name collision')
        created=False
        try:
            docker('create','--name',name,'--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges=true','--user','65534:65534','--pids-limit','32','--label','oracle.purpose.synthetic=true','--mount','type=bind,src='+str(path)+',dst=/run/phase,readonly','--mount','type=bind,src='+str(budget)+',dst=/run/budget,readonly',IMAGE,'node','-e',probe,phase)
            created=True
            actual=json.loads(docker('inspect',name))[0]
            assert actual['HostConfig']['NetworkMode']=='none'
            assert actual['HostConfig']['PidMode']=='' and not actual['HostConfig']['Privileged']
            assert actual['HostConfig']['ReadonlyRootfs'] and actual['Config']['User']=='65534:65534'
            assert len(actual['Mounts'])==2 and all(not m['RW'] for m in actual['Mounts'])
            assert {m['Source'] for m in actual['Mounts']}=={str(path),str(budget)}
            docker('start',name)
            assert docker('wait',name)=='0'
            result['phases'][phase]=json.loads(docker('logs',name))
        finally:
            if created:
                check=json.loads(docker('inspect',name))[0]
                assert check['Config']['Labels']['oracle.purpose.synthetic']=='true'
                docker('rm',name)
    result['success']=True
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--result',required=True,type=pathlib.Path)
    args=parser.parse_args()
    # Keep invented evidence in this invocation's unique scratch directory.
    with tempfile.TemporaryDirectory(prefix='oracle-purpose-mount-') as temporary:
        root=pathlib.Path(temporary);root.chmod(0o755)
        result=prove(root)
    args.result.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    print('four isolated phase processes passed; no installation authority')

if __name__=='__main__':main()
