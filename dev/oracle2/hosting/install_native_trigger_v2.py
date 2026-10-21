"""One-time v2 S03 installation. Dry-run default; partial state is never retried.

Only fixed mapped migrations and freshly sealed v2 seed enter a NEW database.
All diagnostics are withheld because PostgreSQL exceptions can contain SCRAM.
"""
import argparse,contextlib,io,json,os,re,subprocess,sys,time
from pathlib import Path
from urllib.parse import urlsplit,unquote
import psycopg
from psycopg import sql
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'services/oracle-brain'))
from oracle_brain.operating_model.native_proof_v2_identity import IDENTITY
from oracle_brain.hosting.native_trigger_v2_sql import compile_v2_seed,compile_v2_migration,MIGRATIONS,ROLE_MAP
from oracle_brain.hosting.native_trigger_v2 import native_python_digest,decode_bundle
from prepare_native_trigger_v2 import protected,sha,write,canonical

DATABASE=IDENTITY['database']
ROLES=tuple(ROLE_MAP.values())
LOGINS=tuple(IDENTITY[k] for k in ('gateway','executor','projector'))

def require(ok,message):
 if not ok:raise PermissionError(message)

def collision_check(c):
 require(not c.execute('SELECT 1 FROM pg_database WHERE datname=%s',(DATABASE,)).fetchall(),'new DB exists; never replay')
 require(not c.execute('SELECT rolname FROM pg_roles WHERE rolname=ANY(%s)',(list(ROLES),)).fetchall(),'any new role collision forbids installation')

def compiled_inputs(root,source_review):
 r=json.loads(protected(root/'permission-receipt.json'));p=json.loads(protected(root/'seed-parameters.json'));seed=protected(root/'seed.sql')
 require(r['purpose']==IDENTITY['purpose'] and r['job_id']==IDENTITY['run'] and r['workspace_id']==IDENTITY['workspace'] and r['root_appointment']==IDENTITY['root_appointment'],'exact v2 scope required')
 require(p['synthetic_scenario']==IDENTITY['purpose'] and p['runtime_hash']==r['runtime_hash']==native_python_digest() and p['review_hash']==r['review_hash']==sha(source_review),'actual source pins differ')
 require(source_review.decode().strip().splitlines()[-1]=='APPROVE','genuine source APPROVE required')
 require(time.time()<r['expires_at']-150 and r['expires_at']==r['issued_at']+3600,'original one-hour permission too short; never reissue')
 require(seed==compile_v2_seed(p)[0].encode() and sha(seed)==r['seed_sha256'],'fixed seed changed')
 decode_bundle(protected(root/'worker-bundle.json'),r['worker_bundle_sha256'])
 scripts=[compile_v2_migration(n) for n in MIGRATIONS]
 migration_root=Path(__file__).resolve().parents[3]/'services/oracle-brain/sql'
 scripts.append((migration_root/'016_native_trigger_proof_v2.sql').read_bytes())
 return r,seed,scripts

def verify_roles(c):
 rows=c.execute('SELECT rolname,rolcanlogin,rolinherit,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,rolconfig FROM pg_roles WHERE rolname=ANY(%s)',(list(ROLES),)).fetchall()
 require(len(rows)==7,'exact seven new roles required')
 for name,login,inherit,su,db,role,repl,bypass,config in rows:
  require(login==(name in LOGINS) and not any((inherit,su,db,role,repl,bypass)),'new role has unexpected authority')
  memberships=c.execute('SELECT p.rolname,m.admin_option FROM pg_auth_members m JOIN pg_roles p ON p.oid=m.roleid JOIN pg_roles u ON u.oid=m.member WHERE u.rolname=%s',(name,)).fetchall()
  expected=IDENTITY['groups']['gateway'] if name==IDENTITY['gateway'] else IDENTITY['groups']['executor']
  require(memberships==[(expected,False)] if login else memberships==[],'new role membership differs')
  if login:require(config is not None and 'role='+expected in config,'new login default role differs')
  require(not c.execute('SELECT has_database_privilege(%s,%s,\'CONNECT\')',(name,'oracle_native_proof_v1')).fetchone()[0],'new role enters old v1 database')
 old=c.execute("SELECT rolname FROM pg_roles WHERE rolname NOT IN ('postgres','supabase_admin') AND rolname<>current_user AND rolname<>ALL(%s) AND (rolname LIKE 'oracle2_%%' OR rolname LIKE 'oracle_synthetic_%%' OR rolname LIKE 'oracle_native_%%')",(list(ROLES),)).fetchall()
 for (name,) in old:require(not c.execute('SELECT has_database_privilege(%s,%s,\'CONNECT\')',(name,DATABASE)).fetchone()[0],'old principal enters v2DB')

def main():
 p=argparse.ArgumentParser();p.add_argument('--directory',required=True);p.add_argument('--database-ca-file',required=True);p.add_argument('--source-review-file',required=True);p.add_argument('--apply',action='store_true');p.add_argument('--action-review-file');p.add_argument('--action-review-sha256');a=p.parse_args()
 root=Path(a.directory);require(root.is_absolute() and not root.is_symlink() and root.stat().st_uid==os.getuid() and not root.stat().st_mode&0o077,'private issuer custody required')
 repo=Path(__file__).resolve().parents[3];head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
 source=Path(a.source_review_file).read_bytes();r,seed,scripts=compiled_inputs(root,source)
 require(r['source_head']==head and ('`'+head+'`') in source.decode(),'frozen approved source changed')
 require(not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=repo,text=True).strip(),'clean source required')
 from cryptography import x509
 from cryptography.hazmat.primitives import hashes
 ca=Path(a.database_ca_file);cert=x509.load_pem_x509_certificate(ca.read_bytes())
 require(cert.fingerprint(hashes.SHA256()).hex()=='807025ad50d4ed219d2c9c7d299c004f824eb00cf7f65afef607d07b72e6cafa','trusted S03 CA required')
 raw=os.environ['ORACLE_NATIVE_ADMIN_URL'];u=urlsplit(raw)
 require(u.scheme in ('postgresql','postgres') and u.hostname=='aws-0-us-east-1.pooler.supabase.com' and u.port==5432 and bool(database_tenant(u.username,'postgres')) and u.path=='/postgres' and bool(u.password) and not u.query and not u.fragment,'exact S03 administrative target required')
 kw={'sslmode':'verify-full','sslrootcert':str(ca),'connect_timeout':10}
 with psycopg.connect(raw,autocommit=True,**kw) as c:
  require(c.pgconn.ssl_in_use and c.execute('SELECT current_database(),current_user').fetchone()==('postgres','postgres'),'authenticated actual S03 identity required')
  require(c.execute('SELECT rolcreatedb AND rolcreaterole FROM pg_roles WHERE rolname=current_user').fetchone()[0],'issuer capability absent')
  collision_check(c)
  summary={'target_project_sha256':TARGET_PINS['native_supabase_project'],'new_database':DATABASE,'job_id':r['job_id'],'new_roles':list(ROLES),'seed_sha256':r['seed_sha256'],'migration_sha256':{n:sha(b) for n,b in zip((*MIGRATIONS,'016_native_trigger_proof_v2.sql'),scripts)},'mode':'apply' if a.apply else 'dry-run'}
  if not a.apply:return summary
  require(a.action_review_file and a.action_review_sha256,'exact installation action approval required')
  review=Path(a.action_review_file).read_bytes();require(sha(review)==a.action_review_sha256 and review.decode().strip().splitlines()[-1]=='APPROVE','exact action APPROVE required')
  for action in ('database','production'):subprocess.run(['ai-task-gates','check','--before',action,'--reviewer-approval',a.action_review_file],cwd=repo,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  require(time.time()<r['expires_at']-150,'remaining original permission insufficient')
  collision_check(c)
  write(root,'installation-intent.json',canonical(summary))
  c.execute(sql.SQL("CREATE DATABASE {} OWNER postgres TEMPLATE template0 ENCODING 'UTF8'").format(sql.Identifier(DATABASE)))
  c.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM PUBLIC').format(sql.Identifier(DATABASE)))
 new_url=psycopg.conninfo.make_conninfo(raw,dbname=DATABASE,**kw)
 with psycopg.connect(new_url) as c:
  require(c.pgconn.ssl_in_use and c.execute('SELECT current_database(),current_user').fetchone()==(DATABASE,'postgres'),'actual new DB identity differs')
  require(c.execute("SELECT count(*) FROM pg_namespace WHERE nspname='oracle2'").fetchone()[0]==0,'empty namespace required')
  for b in scripts:c.execute(b.decode())
  c.execute(seed.decode())
  for role in LOGINS:c.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(DATABASE),sql.Identifier(role)))
  verify_roles(c)
  from uuid import UUID
  require(c.execute('SELECT run_id FROM oracle2.operating_view_runs').fetchall()==[(UUID(IDENTITY['run']),)],'exact single v2 job required')
 write(root,'installation-result.json',canonical(summary))
 return summary

if __name__=='__main__':
 try:
  with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):result=main()
  print(json.dumps(result))
 except BaseException:
  print('{"state":"denied","details":"suppressed; preserve any partial new database, no retry"}');sys.exit(1)
