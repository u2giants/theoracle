"""Target-checked one-time new DB installation; never upgrades/reissues a ledger.

Dry run is default. Actual creation requires root's exact reviewed action gate.
Failure preserves the new database for recovery; no DROP/cleanup or retry path.
"""
import argparse,hashlib,json,os,re,sys
from pathlib import Path
from urllib.parse import urlsplit
import psycopg
from psycopg import sql
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'services/oracle-brain'))
from oracle_brain.hosting.synthetic_seed import compile_seed
from oracle_brain.hosting.synthetic_fixture import NATIVE_TRIGGER_SCENARIO,fixed_scenario

DATABASE='oracle_native_proof_v1'
ROLES=('oracle2_gateway_metadata','oracle2_source_reader','oracle2_candidate_compiler','oracle2_documentary_executor','oracle_synthetic_gateway','oracle_synthetic_executor','oracle_synthetic_projector')
MIGRATIONS=('001_foundation.sql','002_pilot.sql','004_workflow_integrity.sql','006_hosting_gateway_authority.sql','007_hosting_candidate_permissions.sql','008_hosting_runtime_permissions.sql','009_hosting_result_permissions.sql','010_hosting_job_permissions.sql','015_native_trigger_proof.sql')


def require(v,msg):
 if not v:raise PermissionError(msg)


def read(root,name):
 p=root/name;info=p.lstat();require(p.is_file() and not p.is_symlink() and not info.st_mode&0o077,'protected exact issuer output required');return p.read_bytes()


def main():
 p=argparse.ArgumentParser();p.add_argument('--directory',required=True);p.add_argument('--database-ca-file',required=True);p.add_argument('--apply',action='store_true')
 p.add_argument('--action-review-file');p.add_argument('--action-review-sha256');a=p.parse_args();root=Path(a.directory)
 require(root.is_absolute() and not root.is_symlink() and root.stat().st_mode&0o077==0,'protected issuer custody required')
 receipt=json.loads(read(root,'permission-receipt.json'));params=json.loads(read(root,'seed-parameters.json'));seed=read(root,'seed.sql')
 require(params['synthetic_scenario']==NATIVE_TRIGGER_SCENARIO and receipt['purpose']==NATIVE_TRIGGER_SCENARIO and receipt['job_id']==str(fixed_scenario(NATIVE_TRIGGER_SCENARIO).run),'new test identity required')
 expected=compile_seed(params)[0].replace('invented amber parcel','invented violet envelope').encode()
 require(seed==expected and hashlib.sha256(seed).hexdigest()==receipt['seed_sha256'],'issuer seed population changed')
 from cryptography import x509
 from cryptography.hazmat.primitives import hashes
 ca=Path(a.database_ca_file);cert=x509.load_pem_x509_certificate(ca.read_bytes())
 require(cert.fingerprint(hashes.SHA256()).hex()=='807025ad50d4ed219d2c9c7d299c004f824eb00cf7f65afef607d07b72e6cafa','trusted Supabase issuer CA required')
 raw=os.environ['ORACLE_NATIVE_ADMIN_URL'];u=urlsplit(raw)
 require(u.hostname=='aws-0-us-east-1.pooler.supabase.com' and u.port==5432 and u.username=='postgres.wfdrklofsczspazshaib' and u.path=='/postgres','exact S03 administrative target required')
 kw={'sslmode':'verify-full','sslrootcert':str(ca),'connect_timeout':10}
 with psycopg.connect(raw,autocommit=True,**kw) as c:
  require(c.pgconn.ssl_in_use and c.execute('SELECT current_database(),current_user').fetchone()==('postgres','postgres'),'authenticated actual S03 administrative identity required')
  require(c.execute('SELECT rolcreatedb AND rolcreaterole FROM pg_roles WHERE rolname=current_user').fetchone()[0],'new isolated DB issuer capability required')
  require(not c.execute('SELECT 1 FROM pg_database WHERE datname=%s',(DATABASE,)).fetchall(),'new DB already exists; never replay or reissue')
  require(not c.execute('SELECT rolname FROM pg_roles WHERE rolname=ANY(%s)',(list(ROLES),)).fetchall(),'native role collision; no existing role alteration permitted')
  migration_root=Path(__file__).resolve().parents[3]/'services/oracle-brain/sql'
  scripts=[(migration_root/n).read_bytes() for n in MIGRATIONS]
  summary={'target_project':'wfdrklofsczspazshaib','new_database':DATABASE,'job_id':receipt['job_id'],'new_roles':list(ROLES),
      'seed_sha256':receipt['seed_sha256'],'migration_sha256':{n:hashlib.sha256(b).hexdigest() for n,b in zip(MIGRATIONS,scripts)},'mode':'apply' if a.apply else 'dry-run'}
  if not a.apply:print(json.dumps(summary));return
  require(a.action_review_file and a.action_review_sha256 and re.fullmatch('[a-f0-9]{64}',a.action_review_sha256),'exact independent action review required')
  review=Path(a.action_review_file).read_bytes();require(hashlib.sha256(review).hexdigest()==a.action_review_sha256 and review.decode().strip().splitlines()[-1]=='APPROVE','exact independent action APPROVE required')
  # The target was absent. Preserve even partial new DB state on any error.
  c.execute(sql.SQL('CREATE DATABASE {} OWNER postgres TEMPLATE template0 ENCODING \'UTF8\'').format(sql.Identifier(DATABASE)))
  c.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM PUBLIC').format(sql.Identifier(DATABASE)))
 new_url=psycopg.conninfo.make_conninfo(raw,dbname=DATABASE,**kw)
 with psycopg.connect(new_url) as c:
  require(c.execute('SELECT current_database(),current_user').fetchone()==(DATABASE,'postgres'),'new installer actual database differs')
  require(c.execute("SELECT count(*) FROM pg_namespace WHERE nspname='oracle2'").fetchone()[0]==0,'empty new native namespace required')
  for b in scripts:c.execute(b.decode())
  c.execute(seed.decode())
  for r in ('oracle_synthetic_gateway','oracle_synthetic_executor','oracle_synthetic_projector'):
   c.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(DATABASE),sql.Identifier(r)))
  for r in ('oracle2_checkpoint','oracle2_extract','oracle2_holistic','oracle2_pilot_web','oracle2_project'):
   require(c.execute('SELECT has_database_privilege(%s,%s,\'CONNECT\')',(r,DATABASE)).fetchone()[0] is False,'old pilot role unexpectedly connects to new DB')
  require(c.execute('SELECT run_id FROM oracle2.operating_view_runs').fetchall()==[(fixed_scenario(NATIVE_TRIGGER_SCENARIO).run,)],'new native job population differs')
 print(json.dumps(summary))

if __name__=='__main__':main()
