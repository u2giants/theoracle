"""Recoverably stop only exact owned synthetic Compose assets; delete nothing."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--directory',required=True);args=parser.parse_args(argv)
    root=Path(args.directory).resolve()
    marker=json.loads((root/'SYNTHETIC.json').read_text())
    if marker.get('synthetic') is not True:raise PermissionError('synthetic marker required')
    cmd=['docker','compose','-f',str(root/'compose.yaml')]
    ids=subprocess.check_output(cmd+['ps','-q']).decode().split()
    if not ids:raise PermissionError('exact running synthetic stack required')
    raw=subprocess.check_output(['docker','inspect',*ids]);actual=json.loads(raw)
    services={r['Config']['Labels']['com.docker.compose.service']:r for r in actual}
    if set(services)!={'gateway','executor','ledger','candidate','confirmed'}:
        raise PermissionError('exact synthetic service population required')
    for row in actual:
        if Path(row['Config']['Labels']['com.docker.compose.project.working_dir']).resolve()!=root:
            raise PermissionError('foreign resource refused')
    # Quiesce the only application writers before recovery capture.
    subprocess.run(['docker','stop',services['gateway']['Id'],services['executor']['Id']],check=True,stdout=subprocess.DEVNULL)
    backups={'containers-before-stop.json':raw}
    backups['postgres-recovery.sql']=subprocess.check_output(['docker','exec',services['ledger']['Id'],'pg_dumpall','-U','postgres'])
    for service in ('candidate','confirmed'):
        backups[service+'-data.tar']=subprocess.check_output(['docker','exec',services[service]['Id'],'tar','-C','/var/lib/falkordb/data','-cf','-','.'])
    recovery=root/'recovery';recovery.mkdir(mode=0o700)
    hashes={}
    for name,data in backups.items():
        path=recovery/name;path.write_bytes(data);path.chmod(0o600);hashes[name]=hashlib.sha256(data).hexdigest()
    subprocess.run(cmd+['stop'],check=True,stdout=subprocess.DEVNULL)
    after=json.loads(subprocess.check_output(['docker','inspect',*ids]))
    assert all(r['State']['Running'] is False for r in after)
    receipt={'stopped':True,'deleted':False,'backups':hashes,'containers':[r['Name'] for r in after]}
    target=root/'stop-receipt.json';target.write_text(json.dumps(receipt,sort_keys=True));target.chmod(0o600)
    print(json.dumps({'stopped':True,'deleted':False,'backups_verified':len(hashes),'containers':len(after)}))

if __name__=='__main__':main()
