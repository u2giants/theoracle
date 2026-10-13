#!/usr/bin/env python3
"""Offline source packet checks; never installs, builds, imports or admits analytics."""
import argparse
import hashlib
import json
from pathlib import Path
import re

LIMIT=64*1024*1024
CHUNK=1024*1024
CBC_HASHES={
    'linux/arm64/cbc':'90e1ee27a969cb2f54a02a2edbe8b1f5e4ba8e2b293e44584d96dbc750ba559b',
    'linux/i32/cbc':'62911eb74138f5c9b74876f03db6209d8443a9042483343059b57678892ac7c2',
    'linux/i64/cbc':'2e17077752aa52b06385ad248c9e90bb4f1ce34038c34c94e1012ca6adea5cc7',
    'osx/i64/cbc':'9eeb33c515945620d89dfc2efef9c6740b559e14a6603153a156c6e288a5765b',
    'win/i32/cbc.exe':'7d930a6301cf0f0da0d7fdfa94f49d31aec00d6dfde6097e01dbf004111e4fdb',
    'win/i64/cbc.exe':'fb4642eca630f6263c365975aca7e87917cbe82ed7e6ccb79804e2f1f812419c',
}

def inspect_packet(packet,lock_bytes,recipe_bytes,context_bytes):
    if packet.get('schema_version')!=1 or packet.get('product_admission')!='unavailable':
        raise ValueError('source preparation cannot confer analytical admission')
    if not packet.get('rights') or any(value is not False for value in packet['rights'].values()):
        raise ValueError('source preparation rights must remain denied')
    if packet.get('artifact_limit_bytes')!=LIMIT or packet.get('chunk_limit_bytes')!=CHUNK:
        raise ValueError('fixed multipart limits required')
    if hashlib.sha256(lock_bytes).hexdigest()!=packet.get('requirements_sha256'):
        raise ValueError('analytical lock identity mismatch')
    if hashlib.sha256(recipe_bytes).hexdigest()!=packet.get('recipe_sha256'):
        raise ValueError('analytical recipe identity mismatch')
    if hashlib.sha256(context_bytes).hexdigest()!=packet.get('context_sha256'):
        raise ValueError('analytical build context identity mismatch')
    artifacts=packet.get('artifacts')
    if not isinstance(artifacts,list) or not artifacts:
        raise ValueError('complete source artifact inventory required')
    ids=set();names=set();total=0;chunks=0;missing_notices=[]
    for artifact in artifacts:
        name=artifact.get('filename');identity=artifact.get('id');size=artifact.get('bytes')
        if (not isinstance(identity,str) or not identity or identity in ids
                or not isinstance(name,str) or not name or name in names
                or Path(name).name!=name or '/' in name or '\\' in name or name in {'.','..'}):
            raise ValueError('unique fixed source identities required')
        if type(size) is not int or not 0<size<=LIMIT:
            raise ValueError('each intact source artifact must fit 64 MiB')
        if not isinstance(artifact.get('sha256'),str) or not re.fullmatch('[0-9a-f]{64}',artifact['sha256']):
            raise ValueError('exact source hash required')
        if not isinstance(artifact.get('url'),str) or not artifact['url'].startswith('https://'):
            raise ValueError('primary source URL required')
        notices=artifact.get('notices')
        if not isinstance(notices,dict) or not notices:missing_notices.append(identity)
        else:
            for notice in notices.values():
                if not re.fullmatch('[0-9a-f]{64}',notice.get('sha256','')):
                    raise ValueError('exact preserved notice hash required')
                if 'text' in notice and hashlib.sha256(notice['text'].encode()).hexdigest()!=notice['sha256']:
                    raise ValueError('preserved notice text differs from original hash')
        ids.add(identity);names.add(name);total+=size;chunks+=(size+CHUNK-1)//CHUNK
    if not {'pm4py','pulp'}<=ids:raise ValueError('PM4Py and intact PuLP sources required')
    locked=dict(re.findall(r'^([a-zA-Z0-9_-]+)==([^\s\\]+)',lock_bytes.decode(),re.MULTILINE))
    versions={artifact['id']:artifact['version'] for artifact in artifacts}
    if any(versions.get(name)!=version for name,version in locked.items()):
        raise ValueError('locked dependency source inventory incomplete')
    pulp=next(a for a in artifacts if a['id']=='pulp')
    prefix='pulp-3.3.0/pulp/solverdir/cbc/'
    if {item['path']:item['sha256'] for item in pulp.get('binary_inventory',[])}!={prefix+name:seal for name,seal in CBC_HASHES.items()}:
        raise ValueError('unchanged six-binary inventory required')
    expected_notices={'pulp-3.3.0/LICENSE'}|{prefix+name.rsplit('/',1)[0]+'/coin-license.txt' for name in CBC_HASHES}
    if set(pulp.get('notices',{}))!=expected_notices:
        raise ValueError('all seven original PuLP notices required')
    # Pure diagnostics only: opaque hashes/flags never become approval or signatures.
    blockers=list(packet.get('unresolved_associations',[]))
    blockers.extend('notice coverage unavailable: '+name for name in missing_notices)
    blockers.extend('receipt unavailable: '+name for name in packet.get('required_receipts',{}))
    if not packet.get('source_revision'):blockers.append('exact analytical product revision unavailable')
    if not packet.get('image_digest'):blockers.append('immutable analytical image unavailable')
    blockers.append('intact source payload byte verification and authenticated multipart reconstruction not executed')
    return {'state':'source_prepared','product_admission':False,'delivery_admitted':False,
            'artifact_count':len(artifacts),'total_source_bytes':total,'chunks':chunks,
            'single_artifact_fit':total<=LIMIT,'blockers':blockers}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory-only',action='store_true',help='Check public descriptors; never claim delivery')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    folder=root/'dev/oracle2/analytics'
    result=inspect_packet(json.loads((folder/'source-manifest.json').read_text()),
                          (folder/'requirements.lock').read_bytes(),(folder/'Dockerfile').read_bytes(),
                          (folder/'Dockerfile.dockerignore').read_bytes())
    print(json.dumps(result,sort_keys=True))
    return 0 if args.inventory_only else 3

if __name__=='__main__':raise SystemExit(main())
