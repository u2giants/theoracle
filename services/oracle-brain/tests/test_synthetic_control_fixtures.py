"""Invented fixture guards refuse before graph/ACL mutation; real certificates are qualified."""
import importlib.util,os
from pathlib import Path
from unittest.mock import patch
import pytest

ROOT=Path(__file__).resolve().parents[3]
@pytest.fixture(autouse=True)
def project_env(monkeypatch):monkeypatch.setenv('COMPOSE_PROJECT_NAME','oracle2-synthetic-unit')

def module(name):
 spec=importlib.util.spec_from_file_location(name,ROOT/'dev/oracle2'/('test_'+name+'.py'))
 value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def details():return {'Id':'invented-container','Config':{'Labels':{'oracle.operating.synthetic':'true','com.docker.compose.project':'oracle2-synthetic-unit','com.docker.compose.service':'falkor-candidate'}},'NetworkSettings':{'Networks':{'oracle2-synthetic-unit_default':{}},'Ports':{'6379/tcp':[{'HostIp':'127.0.0.1','HostPort':'12345'}]}}}
URL='redis://:oracle2_candidate_local_only@127.0.0.1:12345'
GRAPH='oracle_ro_fixture_graph_'+'a'*32
USER='oracle_ro_fixture_user_'+'b'*32

@pytest.mark.parametrize('case',['no-label','non-loopback','foreign-owner','malformed-graph','malformed-user','foreign-project','foreign-network'])
def test_graph_foreign_fixture_refuses_without_any_redis_connection(tmp_path,case):
 helper=module('readonly_graph_fixture');state=details();url=URL;graph=GRAPH;user=USER
 if case=='no-label':state['Config']['Labels']={}
 if case=='non-loopback':state['NetworkSettings']['Ports']['6379/tcp'][0]['HostIp']='0.0.0.0'
 if case=='foreign-owner':url=URL.replace('oracle2_candidate_local_only','foreign-owner')
 if case=='malformed-graph':graph='other_actor_graph'
 if case=='malformed-user':user='default'
 if case=='foreign-project':state['Config']['Labels']['com.docker.compose.project']='foreign'
 if case=='foreign-network':state['NetworkSettings']['Networks']={'foreign':{}}
 with patch.object(helper,'inspect',return_value=state),patch.object(helper.redis.Redis,'from_url') as connect:
  with pytest.raises(PermissionError):helper.initialize('invented',url,tmp_path/'new',graph_name=graph,username=user)
  connect.assert_not_called()

@pytest.mark.parametrize('occupied',['graph','key','user'])
def test_graph_existing_identity_refuses_before_mutation(tmp_path,occupied):
 helper=module('readonly_graph_fixture')
 with patch.object(helper,'inspect',return_value=details()),patch.object(helper.redis.Redis,'from_url') as connect:
  client=connect.return_value
  client.execute_command.side_effect=[[GRAPH] if occupied=='graph' else [], {'flags':['on']} if occupied=='user' else None]
  client.exists.return_value=occupied=='key'
  with pytest.raises(PermissionError):helper.initialize('invented',URL,tmp_path/'new',graph_name=GRAPH,username=USER)
  assert all(call.args[0] in {'GRAPH.LIST','ACL'} for call in client.execute_command.call_args_list)
  assert all(call.args[:2]!=('ACL','SETUSER') for call in client.execute_command.call_args_list)

def test_fresh_output_guard_refuses_before_connect(tmp_path):
 helper=module('readonly_graph_fixture');(tmp_path/'environment.json').write_text('invented existing evidence')
 with patch.object(helper,'inspect',return_value=details()),patch.object(helper.redis.Redis,'from_url') as connect:
  with pytest.raises(PermissionError):helper.initialize('invented',URL,tmp_path,graph_name=GRAPH,username=USER)
  connect.assert_not_called()

def test_actual_separate_leaf_and_networkless_issuer_receipt():
 import json,subprocess
 path=os.environ.get('ORACLE2_TEST_TLS_QUALIFICATION')
 assert path,'actual separated issuer qualification receipt required'
 proof=json.loads(Path(path).read_text())
 assert proof['issuer_actual_network_modes']==['none']*3
 assert proof['issuer_network_mode']=='none' and proof['issuer_key_runtime_path_absent'] and proof['issuer_mount_absent']
 assert proof['leaf_ca'] is False and proof['leaf_server_auth'] and proof['plaintext_refused'] and proof['wrong_password_refused']
 leaf=Path(os.environ['ORACLE2_TEST_TLS_ROOT']).with_name('server.crt')
 text=subprocess.check_output(['openssl','x509','-in',str(leaf),'-noout','-text'],text=True,timeout=10)
 assert 'CA:FALSE' in text and 'X509v3 Key Usage: critical' in text and 'TLS Web Server Authentication' in text

@pytest.mark.parametrize('case',['no-label','foreign-owner','non-loopback'])
def test_tls_foreign_fixture_refuses_before_issuer_or_runtime_write(tmp_path,case):
 helper=module('tls_bootstrap')
 state={'Config':{'Labels':{'oracle.operating.synthetic':'true'},'Env':['POSTGRES_USER=oracle2_admin','POSTGRES_PASSWORD=oracle2_local_admin_only','POSTGRES_DB=oracle2']},'NetworkSettings':{'Ports':{'5432/tcp':[{'HostIp':'127.0.0.1','HostPort':'12345'}]}}}
 url='postgresql://oracle2_admin:oracle2_local_admin_only@127.0.0.1:12345/oracle2'
 if case=='no-label':state['Config']['Labels']={}
 if case=='foreign-owner':url=url.replace('oracle2_admin','foreign')
 if case=='non-loopback':state['NetworkSettings']['Ports']['5432/tcp'][0]['HostIp']='0.0.0.0'
 with patch.object(helper,'run',return_value=__import__('json').dumps([state])) as run:
  with pytest.raises(PermissionError):helper.bootstrap('invented',url,tmp_path/'new')
  assert run.call_count==1 and run.call_args.args[:2]==('docker','inspect')
 assert not (tmp_path/'new').exists()
