"""Fixed per-service file materialization; production actions require exact review.
One networkless one-shot container, one owned named-volume mount, env bundle only.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from cryptography import x509
from cryptography.hazmat.primitives import serialization

FILES={
 'gateway':({'settings.json','registry.json','database-url','ca.crt','server.crt','server.key','hmac-key'},10001),
 'executor':({'settings.json','registry.json','database-url','ca.crt','graph-url'},10001),
 'ledger':({'admin-password','ca.crt','server.crt','server.key','pg_hba.conf'},70),
 'candidate':({'server.conf'},999),
 'confirmed':({'server.conf'},999),
 'candidate-data':(set(),999),
 'confirmed-data':(set(),999),
 'spool':(set(),10001),
 'blobs':(set(),10001),
 'ledger-init':({'seed-parameters.json'},70),
 'synthetic-project':({'settings.json','registry.json','database-url','ca.crt','graph-url','synthetic-review-hash'},10001),
}
ROOT=Path('/run/oracle-assets')
SQL_ROOT=Path('/app/services/oracle-brain/sql')

def _unique_object(pairs):
 result={}
 for name,value in pairs:
  if name in result:raise PermissionError('duplicate bundle fields denied')
  result[name]=value
 return result

def materialize(profile, encoded, seal, root=ROOT):
 expected,uid=FILES[profile]
 if len(encoded)>2_800_000:raise PermissionError('bounded reviewed bundle required')

 raw=base64.b64decode(encoded,validate=True)
 if len(raw)>2_000_000 or not re.fullmatch('[a-f0-9]{64}',seal) or hashlib.sha256(raw).hexdigest()!=seal:
  raise PermissionError('external reviewed bundle pin required')
 bundle=json.loads(raw,object_pairs_hook=_unique_object)
 if set(bundle)!={'schema','profile','files'} or bundle['schema']!='oracle-hosted-files/v1' or bundle['profile']!=profile:
  raise PermissionError('fixed credential profile required')
 if not isinstance(bundle['files'],dict) or set(bundle['files'])!=expected:
  raise PermissionError('exact credential population required')
 values={}
 for name,entry in bundle['files'].items():
  if set(entry)!={'bytes_b64','sha256'}:raise PermissionError('exact sealed file metadata required')
  content=base64.b64decode(entry['bytes_b64'],validate=True)
  if not content or len(content)>1_000_000 or hashlib.sha256(content).hexdigest()!=entry['sha256']:
   raise PermissionError('sealed file mismatch')
  values[name]=content
 if profile=='ledger-init':
  from .synthetic_seed import compile_seed
  parameters=json.loads(values['seed-parameters.json'],object_pairs_hook=_unique_object)
  seed,_,_,_=compile_seed(parameters)
  sqlroot=SQL_ROOT
  names=('001_foundation.sql','002_pilot.sql','004_workflow_integrity.sql','006_hosting_gateway_authority.sql','007_hosting_candidate_permissions.sql','008_hosting_runtime_permissions.sql','009_hosting_result_permissions.sql')
  values={f'{index+1:02d}-{name}':(sqlroot/name).read_bytes() for index,name in enumerate(names)}
  values['00-empty-owned-preflight.sql']=b"DO $$ BEGIN IF current_database()<>'oracle_synthetic' OR current_user<>'oracle_bootstrap' OR (SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database())<>current_user OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_toast' AND c.relkind IN ('r','p','v','m','S')) THEN RAISE EXCEPTION 'new empty owned synthetic ledger required'; END IF; END $$;\n"
  values['90-public-invented-seed.sql']=seed.encode()
  expected=set(values)
 if 'server.crt' in values:
  cert=x509.load_pem_x509_certificate(values['server.crt'])
  if cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
   raise PermissionError('issuer certificate/key denied in runtime')
  key=serialization.load_pem_private_key(values['server.key'],password=None)
  if cert.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)!=key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo):
   raise PermissionError('leaf key mismatch')
 if 'hmac-key' in values and len(values['hmac-key'])<32:raise PermissionError('strong worker HMAC required')
 if root.is_symlink() or not root.is_dir():raise PermissionError('owned named volume required')
 if any(path.name not in expected for path in root.iterdir()):raise PermissionError('foreign credential volume refused')
 # Preflight the ENTIRE population before creating a single file.
 for name,content in values.items():
  path=root/name
  if path.is_symlink():raise PermissionError('symlink credential denied')
  if path.exists() and (not path.is_file() or path.read_bytes()!=content or path.stat().st_mode&0o077 or path.stat().st_uid!=uid):
   raise PermissionError('existing credential change requires separate exact review')
 for name,content in values.items():
  path=root/name
  if path.exists():
   if path.is_symlink() or not path.is_file() or path.read_bytes()!=content or path.stat().st_mode&0o077 or path.stat().st_uid!=uid:
    raise PermissionError('existing credential change requires separate exact review')
   continue
  # Publish only a fully written/fsynced inode. Link is atomic and cannot
  # overwrite a file another process created after the population preflight.
  fd,staged=tempfile.mkstemp(prefix='.oracle-staged-',dir=root)
  with os.fdopen(fd,'wb') as stream:
   os.fchmod(stream.fileno(),0o600);os.fchown(stream.fileno(),uid,uid)
   stream.write(content);stream.flush();os.fsync(stream.fileno())
  os.link(staged,path,follow_symlinks=False)
  os.unlink(staged)
 os.chown(root,uid,uid);os.chmod(root,0o700)
 fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
 # No private values, URLs, keys, exception details or content hashes in logs.
 return {'profile':profile,'materialized':True,'file_count':len(expected)}

def main(argv=None):
 parser=argparse.ArgumentParser();parser.add_argument('profile',choices=sorted(FILES));args=parser.parse_args(argv)
 result=materialize(args.profile,os.environ.pop('ORACLE_BOOTSTRAP_BUNDLE',''),os.environ.pop('ORACLE_BOOTSTRAP_BUNDLE_SHA256',''))
 print('reviewed profile files materialized')

if __name__=='__main__':
 try:main()
 except Exception:
  print('profile bootstrap denied',file=__import__('sys').stderr);raise SystemExit(1)
