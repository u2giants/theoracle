"""Pure additive ACL compilation; no runtime or secrets touched."""
import copy,hashlib,importlib.util,json
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[3]
def load(name):
 spec=importlib.util.spec_from_file_location(name,ROOT/'dev/oracle2/hosting'/f'{name}.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
V1=load('compile_falkor_proof_acl');V2=load('falkor_native_proof_acl_v2')
def raw_v1():
 raw=(ROOT/'dev/oracle2/hosting/golden/falkordb-candidate.json').read_bytes()
 return json.dumps(V1.compile_delta(raw,hashlib.sha256(raw).hexdigest())['compose']).encode()
def compile(raw):return V2.compile_delta(raw,hashlib.sha256(raw).hexdigest())['compose']

def test_additive_v2_preserves_every_existing_user_and_compose_field():
 raw=raw_v1();before=json.loads(raw);after=compile(raw)
 b=before['services']['falkordb'];a=after['services']['falkordb']
 assert {k:v for k,v in after.items() if k!='services'}=={k:v for k,v in before.items() if k!='services'}
 assert {k:v for k,v in after['services'].items() if k!='falkordb'}=={k:v for k,v in before['services'].items() if k!='falkordb'}
 assert {k:v for k,v in a.items() if k not in ('entrypoint','command','environment')}=={k:v for k,v in b.items() if k not in ('entrypoint','command','environment')}
 assert all(a['environment'][k]==v for k,v in b['environment'].items())
 old='\n'.join(b['entrypoint'])+'\n'+'\n'.join(b.get('command',[]));new='\n'.join(a['entrypoint'])+'\n'+'\n'.join(a.get('command',[]))
 for line in old.splitlines():
  if 'echo "user ' in line:assert line in new
 for user,(env,commands) in V2.USERS.items():
  line=next(l for l in new.splitlines() if 'echo "user '+user+' ' in l)
  assert '~'+V2.GRAPH+' ~'+V2.GRAPH+'__ontology -@all '+commands in line
  assert '~*' not in line and '+graph.list' not in line and '+@' not in line
  assert '"$${#'+env+'}" -eq 64' in new
  assert env in new.split('unset FALKORDB_PASSWORD')[1].splitlines()[0]
 executor=next(l for l in new.splitlines() if 'echo "user oracle_native_proof_executor_v2 ' in l)
 assert '+graph.query' not in executor
 assert V1.GRAPH!=V2.GRAPH


def test_v2_reinstall_and_changed_input_refused():
 raw=raw_v1()
 with pytest.raises(ValueError,match='reviewed compose bytes differ'):V2.compile_delta(raw,'0'*64)
 with pytest.raises(ValueError,match='fresh proof environment'):compile(json.dumps(compile(raw)).encode())


def test_confirmed_resource_and_missing_worker_anchor_refused():
 raw=(ROOT/'dev/oracle2/hosting/golden/falkordb-confirmed.json').read_bytes()
 with pytest.raises(ValueError,match='candidate-only'):compile(raw)
 raw=raw_v1().replace(b'user worker on',b'user changed-worker on')
 with pytest.raises(ValueError,match='worker ACL'):compile(raw)
