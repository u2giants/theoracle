"""Compile ONE new invented permission for a fresh isolated native proof DB.

Offline preparation only. Root reviews exact outputs before creating database,
roles, seed, environment or executing the job. Never updates an existing target.
"""
import argparse,base64,hashlib,json,os,re,secrets,sys,time,subprocess,stat
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'services/oracle-brain'))
from oracle_brain.hosting.synthetic_fixture import fixture,fixed_scenario,NATIVE_TRIGGER_V2_SCENARIO
from oracle_brain.hosting.native_trigger_v2_sql import compile_v2_seed as compile_seed
from oracle_brain.operating_model.native_proof_v2_identity import IDENTITY
from oracle_brain.hosting.native_trigger_v2 import native_python_digest


def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def sha(v):return hashlib.sha256(v).hexdigest()
def write(root,name,value):
    raw=value if isinstance(value,bytes) else value.encode();fd=os.open(root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw)


def protected(path):
    p=Path(path)
    if not p.is_absolute():raise PermissionError('absolute private input required')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:raise PermissionError('protected private input required')
        raw=os.read(fd,4194305)
        if len(raw)>4194304:raise PermissionError('private input too large')
        return raw
    finally:os.close(fd)


def readiness(raw,head,runtime):
    r=json.loads(raw)
    if set(r)!={'source_head','runtime_hash','trigger_deployment_id','trigger_status','trigger_task','vercel_deployment_id','vercel_status'} or r['source_head']!=head or r['runtime_hash']!=runtime or r['trigger_status']!='DEPLOYED' or r['trigger_task']!=IDENTITY['task'] or r['vercel_status']!='READY' or not re.fullmatch('deployment_[a-z0-9]+',r['trigger_deployment_id']) or not re.fullmatch('dpl_[A-Za-z0-9]+',r['vercel_deployment_id']):raise PermissionError('exact authority-free prebuild and web readiness required')
    return r


def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',required=True);p.add_argument('--runtime-hash',required=True)
    p.add_argument('--source-review-file',required=True);p.add_argument('--review-hash',required=True);p.add_argument('--issued-at',required=True,type=int);p.add_argument('--expires-at',required=True,type=int)
    p.add_argument('--readiness-file',required=True);p.add_argument('--readiness-sha256',required=True)
    p.add_argument('--issuance-intent',required=True);p.add_argument('--action-review-file',required=True);p.add_argument('--action-review-sha256',required=True)
    a=p.parse_args();now=int(time.time())
    repo=Path(__file__).resolve().parents[3];head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=repo,text=True).strip():raise PermissionError('frozen clean source required')
    ready=protected(a.readiness_file)
    if sha(ready)!=a.readiness_sha256:raise PermissionError('readiness bytes changed')
    readiness(ready,head,a.runtime_hash)
    action=Path(a.action_review_file).read_bytes()
    if sha(action)!=a.action_review_sha256 or action.decode().strip().splitlines()[-1]!='APPROVE':raise PermissionError('exact issuer action APPROVE required')
    subprocess.run(['ai-task-gates','check','--before','production','--reviewer-approval',a.action_review_file],cwd=repo,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if not (now-60<=a.issued_at<=now and a.expires_at==a.issued_at+3600 and now<a.expires_at):raise PermissionError('one explicit newly reviewed one-hour test permission required')
    if not all(re.fullmatch('[a-f0-9]{64}',h) for h in (a.runtime_hash,a.review_hash)):raise PermissionError('exact reviewed source required')
    source_review=Path(a.source_review_file).read_bytes()
    if sha(source_review)!=a.review_hash or source_review.decode().strip().splitlines()[-1]!='APPROVE' or ('`'+head+'`') not in source_review.decode():raise PermissionError('genuine exact independent native source APPROVE required')
    if a.runtime_hash!=native_python_digest():raise PermissionError('actual native Python population differs from requested runtime')
    root=Path(a.directory)
    if not root.is_absolute() or root.exists():raise PermissionError('new private output directory required')
    if not a.issued_at<=int(time.time())<=a.issued_at+60:raise PermissionError('issuance clock changed; no stale authority')
    intent=Path(a.issuance_intent);parent=intent.parent;info=parent.lstat()
    if not intent.is_absolute() or parent.is_symlink() or not parent.is_dir() or info.st_uid!=os.getuid() or info.st_mode&0o077:raise PermissionError('private exclusive issuance custody required')
    write(parent,intent.name,canonical({'purpose':IDENTITY['purpose'],'job_id':IDENTITY['run'],'source_head':head,'issued_at':a.issued_at,'expires_at':a.expires_at,'output_directory':str(root),'readiness_sha256':a.readiness_sha256}))
    root.mkdir(mode=0o700)
    scenario=fixed_scenario(NATIVE_TRIGGER_V2_SCENARIO)
    _,_,payload,manifest,release=fixture(a.runtime_hash,a.review_hash,NATIVE_TRIGGER_V2_SCENARIO)
    passwords={r:secrets.token_hex(32) for r in ('gateway','executor','projector')}
    def scram(password):
        import hmac
        salt=secrets.token_bytes(16);salted=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,4096)
        client=hmac.new(salted,b'Client Key',hashlib.sha256).digest();stored=sha(client)
        server=hmac.new(salted,b'Server Key',hashlib.sha256).digest()
        return 'SCRAM-SHA-256$4096:'+base64.b64encode(salt).decode()+'$'+base64.b64encode(bytes.fromhex(stored)).decode()+':'+base64.b64encode(server).decode()
    expiry=datetime.fromtimestamp(a.expires_at,timezone.utc).isoformat()
    registry={'schema':'oracle-public-invented-role-admission/v1','purpose':NATIVE_TRIGGER_V2_SCENARIO,
        'runtime_hash':a.runtime_hash,'workspace_id':str(scenario.workspace),'principal_id':str(scenario.actor),
        'source_refs':payload['source_refs'],'expires_at':expiry,'synthetic_scenario':NATIVE_TRIGGER_V2_SCENARIO,'synthetic_scenario_seal':scenario.seal()}
    role_hash=sha(canonical(registry))
    params={'runtime_hash':a.runtime_hash,'source_role_registry_hash':role_hash,'review_hash':a.review_hash,'expires_at':expiry,
        'synthetic_scenario':NATIVE_TRIGGER_V2_SCENARIO,'synthetic_scenario_seal':scenario.seal(),**{r+'_scram':scram(v) for r,v in passwords.items()}}
    seed,*_=compile_seed(params)
    # compile_seed's fixed nonlegacy question is made truthful for this distinct fixture.
    # V2 compiler already binds its silver-envelope question.
    write(root,'seed-parameters.json',canonical(params));write(root,'seed.sql',seed);write(root,'source-role-registry.json',canonical(registry));write(root,'artifact.json',canonical(payload));write(root,'release.json',canonical(release.model_dump(mode='json')))
    common={'schema_version':1,'purpose':NATIVE_TRIGGER_V2_SCENARIO,'issued_at':a.issued_at,'expires_at':a.expires_at,'runtime_hash':a.runtime_hash,'review_hash':a.review_hash}
    def pg(role):return f"postgresql://{IDENTITY[role]}.wfdrklofsczspazshaib:{passwords[role]}@aws-0-us-east-1.pooler.supabase.com:5432/{IDENTITY['database']}"
    def enc(v):return base64.b64encode(v.encode()).decode()
    database_ca=os.environ.get('ORACLE_NATIVE_DATABASE_CA') or Path(os.environ['ORACLE_NATIVE_DATABASE_CA_FILE']).read_text()
    files={k:enc(os.environ[n]) for k,n in {'graph_ca':'ORACLE_NATIVE_GRAPH_CA','graph_cert':'ORACLE_NATIVE_GRAPH_CERT','graph_key':'ORACLE_NATIVE_GRAPH_KEY'}.items()}
    files['database_ca']=enc(database_ca)
    files['database_url']=enc(pg('executor'))
    files['graph_url']=enc('rediss://'+IDENTITY['graph_executor']+':'+quote(os.environ['ORACLE_NATIVE_GRAPH_EXECUTOR_PASSWORD'],safe='')+'@oracle-graph.designflow.app:16391')
    worker={**common,'source_role_registry_hash':role_hash,'files':files}
    web={**common,'release_hash':release.content_hash(),'admission_hash':release.documentary_gate_hash,
        'files':{'database_url':enc(pg('gateway')),'database_ca':files['database_ca']}}
    write(root,'worker-bundle.json',canonical(worker));write(root,'web-bundle.json',canonical(web));write(root,'passwords.json',canonical(passwords));write(root,'native-login-token',secrets.token_hex(32))
    receipt={'schema_version':1,'source_head':head,'purpose':NATIVE_TRIGGER_V2_SCENARIO,'job_id':str(scenario.run),'workspace_id':str(scenario.workspace),'root_appointment':str(scenario.root_appointment),
        'runtime_hash':a.runtime_hash,'review_hash':a.review_hash,'issued_at':a.issued_at,'expires_at':a.expires_at,
        'worker_bundle_sha256':sha(canonical(worker)),'web_bundle_sha256':sha(canonical(web)),'seed_sha256':sha(seed.encode()),'source_role_registry_sha256':role_hash,
        'release_hash':release.content_hash(),'artifact_hash':manifest.content_hash,'source_refs':payload['source_refs']}
    write(root,'permission-receipt.json',canonical(receipt))
    print(json.dumps({'job_id':str(scenario.run),'worker_bundle_sha256':receipt['worker_bundle_sha256'],'web_bundle_sha256':receipt['web_bundle_sha256'],'expires_at':a.expires_at}))

if __name__=='__main__':
    try:main()
    except BaseException:
        print('{"state":"denied","details":"suppressed; preserve issuance intent and partial output, never retry"}');sys.exit(1)
