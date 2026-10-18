"""Compile ONE new invented permission for a fresh isolated native proof DB.

Offline preparation only. Root reviews exact outputs before creating database,
roles, seed, environment or executing the job. Never updates an existing target.
"""
import argparse,base64,hashlib,json,os,re,secrets,sys,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'services/oracle-brain'))
from oracle_brain.hosting.synthetic_fixture import fixture,fixed_scenario,NATIVE_TRIGGER_SCENARIO
from oracle_brain.hosting.synthetic_seed import compile_seed
from oracle_brain.hosting.native_trigger_v1 import native_python_digest


def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def sha(v):return hashlib.sha256(v).hexdigest()
def write(root,name,value):
    path=root/name;path.write_bytes(value if isinstance(value,bytes) else value.encode());path.chmod(0o600)


def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',required=True);p.add_argument('--runtime-hash',required=True)
    p.add_argument('--source-review-file',required=True);p.add_argument('--review-hash',required=True);p.add_argument('--issued-at',required=True,type=int);p.add_argument('--expires-at',required=True,type=int)
    a=p.parse_args();now=int(time.time())
    if not (now-60<=a.issued_at<=now and a.expires_at==a.issued_at+3600 and now<a.expires_at):raise PermissionError('one explicit newly reviewed one-hour test permission required')
    if not all(re.fullmatch('[a-f0-9]{64}',h) for h in (a.runtime_hash,a.review_hash)):raise PermissionError('exact reviewed source required')
    source_review=Path(a.source_review_file).read_bytes()
    if sha(source_review)!=a.review_hash or source_review.decode().strip().splitlines()[-1]!='APPROVE':raise PermissionError('genuine exact independent native source APPROVE required')
    if a.runtime_hash!=native_python_digest():raise PermissionError('actual native Python population differs from requested runtime')
    root=Path(a.directory)
    if not root.is_absolute() or root.exists():raise PermissionError('new private output directory required')
    root.mkdir(mode=0o700)
    scenario=fixed_scenario(NATIVE_TRIGGER_SCENARIO)
    _,_,payload,manifest,release=fixture(a.runtime_hash,a.review_hash,NATIVE_TRIGGER_SCENARIO)
    passwords={r:secrets.token_hex(32) for r in ('gateway','executor','projector')}
    def scram(password):
        import hmac
        salt=secrets.token_bytes(16);salted=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,4096)
        client=hmac.new(salted,b'Client Key',hashlib.sha256).digest();stored=sha(client)
        server=hmac.new(salted,b'Server Key',hashlib.sha256).digest()
        return 'SCRAM-SHA-256$4096:'+base64.b64encode(salt).decode()+'$'+base64.b64encode(bytes.fromhex(stored)).decode()+':'+base64.b64encode(server).decode()
    expiry=datetime.fromtimestamp(a.expires_at,timezone.utc).isoformat()
    registry={'schema':'oracle-public-invented-role-admission/v1','purpose':NATIVE_TRIGGER_SCENARIO,
        'runtime_hash':a.runtime_hash,'workspace_id':str(scenario.workspace),'principal_id':str(scenario.actor),
        'source_refs':payload['source_refs'],'expires_at':expiry,'synthetic_scenario':NATIVE_TRIGGER_SCENARIO,'synthetic_scenario_seal':scenario.seal()}
    role_hash=sha(canonical(registry))
    params={'runtime_hash':a.runtime_hash,'source_role_registry_hash':role_hash,'review_hash':a.review_hash,'expires_at':expiry,
        'synthetic_scenario':NATIVE_TRIGGER_SCENARIO,'synthetic_scenario_seal':scenario.seal(),**{r+'_scram':scram(v) for r,v in passwords.items()}}
    seed,*_=compile_seed(params)
    # compile_seed's fixed nonlegacy question is made truthful for this distinct fixture.
    seed=seed.replace('invented amber parcel','invented violet envelope')
    write(root,'seed-parameters.json',canonical(params));write(root,'seed.sql',seed);write(root,'source-role-registry.json',canonical(registry));write(root,'artifact.json',canonical(payload));write(root,'release.json',canonical(release.model_dump(mode='json')))
    common={'schema_version':1,'purpose':NATIVE_TRIGGER_SCENARIO,'issued_at':a.issued_at,'expires_at':a.expires_at,'runtime_hash':a.runtime_hash,'review_hash':a.review_hash}
    def pg(role):return f'postgresql://oracle_synthetic_{role}.wfdrklofsczspazshaib:{passwords[role]}@aws-0-us-east-1.pooler.supabase.com:5432/oracle_native_proof_v1'
    def enc(v):return base64.b64encode(v.encode()).decode()
    database_ca=os.environ.get('ORACLE_NATIVE_DATABASE_CA') or Path(os.environ['ORACLE_NATIVE_DATABASE_CA_FILE']).read_text()
    files={k:enc(os.environ[n]) for k,n in {'graph_ca':'ORACLE_NATIVE_GRAPH_CA','graph_cert':'ORACLE_NATIVE_GRAPH_CERT','graph_key':'ORACLE_NATIVE_GRAPH_KEY'}.items()}
    files['database_ca']=enc(database_ca)
    files['database_url']=enc(pg('executor'))
    files['graph_url']=enc('rediss://oracle_native_proof_executor_v1:'+quote(os.environ['ORACLE_NATIVE_GRAPH_EXECUTOR_PASSWORD'],safe='')+'@oracle-graph.designflow.app:16391')
    worker={**common,'source_role_registry_hash':role_hash,'files':files}
    web={**common,'release_hash':release.content_hash(),'admission_hash':release.documentary_gate_hash,
        'files':{'database_url':enc(pg('gateway')),'database_ca':files['database_ca']}}
    write(root,'worker-bundle.json',canonical(worker));write(root,'web-bundle.json',canonical(web));write(root,'passwords.json',canonical(passwords));write(root,'native-login-token',secrets.token_hex(32))
    receipt={'schema_version':1,'purpose':NATIVE_TRIGGER_SCENARIO,'job_id':str(scenario.run),'workspace_id':str(scenario.workspace),'root_appointment':str(scenario.root_appointment),
        'runtime_hash':a.runtime_hash,'review_hash':a.review_hash,'issued_at':a.issued_at,'expires_at':a.expires_at,
        'worker_bundle_sha256':sha(canonical(worker)),'web_bundle_sha256':sha(canonical(web)),'seed_sha256':sha(seed.encode()),'source_role_registry_sha256':role_hash,
        'release_hash':release.content_hash(),'artifact_hash':manifest.content_hash,'source_refs':payload['source_refs']}
    write(root,'permission-receipt.json',canonical(receipt))
    print(json.dumps({'job_id':str(scenario.run),'worker_bundle_sha256':receipt['worker_bundle_sha256'],'web_bundle_sha256':receipt['web_bundle_sha256'],'expires_at':a.expires_at}))

if __name__=='__main__':main()
