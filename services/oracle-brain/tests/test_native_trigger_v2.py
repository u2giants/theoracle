"""Fixed v2 source/role/protocol tests. All databases are disposable local fixtures."""
import base64,hashlib,json,os
from dataclasses import asdict
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import UUID
import pytest
from oracle_brain.operating_model.native_proof_v2_identity import IDENTITY as I
from oracle_brain.hosting.native_trigger_v2 import (decode_bundle,validate_payload,database_url,tls_config,SCENARIO,NativeSourceRoleBindingV2)
from oracle_brain.hosting.synthetic_fixture import fixture,fixed_scenario,NATIVE_TRIGGER_V2_SCENARIO,NATIVE_TRIGGER_SCENARIO,LEGACY_SCENARIO,FORWARD_SCENARIO
from oracle_brain.hosting.native_trigger_v2_sql import compile_v2_seed,compile_v2_migration,MIGRATIONS,ROLE_MAP
from test_native_trigger_v1 import native_sql,sealed

ROOT=Path(__file__).resolve().parents[3]

def body():
 return {'schema_version':1,'purpose':I['purpose'],'issued_at':1000,'expires_at':4600,'runtime_hash':'a'*64,'review_hash':'b'*64,'source_role_registry_hash':'c'*64,'files':{k:base64.b64encode(b'invented').decode() for k in ('database_url','database_ca','graph_url','graph_ca','graph_cert','graph_key')}}

def test_v2_fixed_identity_disjoint():
 def thaw(x):
  from collections.abc import Mapping
  return {k:thaw(v) for k,v in x.items()} if isinstance(x,Mapping) else [thaw(v) for v in x] if isinstance(x,tuple) else x
 assert thaw(I)==json.loads((ROOT/'dev/oracle2/native-v2-fixed-identities.json').read_text())
 def ids(s):
  return {v for v in (s.workspace,s.actor,s.owner,s.artifact,s.generation,s.release,s.run,s.root_appointment,s.grantor,*s.draft_ids,*s.appointment_ids,*s.block_ids,*(r[0] for r in s.sources))}
 new=ids(SCENARIO);assert len(new)==19
 for name in (LEGACY_SCENARIO,FORWARD_SCENARIO,NATIVE_TRIGGER_SCENARIO):assert not new&ids(fixed_scenario(name))
 assert SCENARIO.parser==hashlib.sha256(I['parser_label'].encode()).hexdigest()
 _,_,payload,manifest,release=fixture('a'*64,'b'*64,NATIVE_TRIGGER_V2_SCENARIO)
 assert release.graph_name==I['graph_name']
 assert tuple(text for _,text in SCENARIO.sources)==I['source_texts']
 assert all('silver envelopes' in x['value'] for x in payload['observations'])
 with pytest.raises(TypeError):I['run']='foreign'

@pytest.mark.parametrize('mutation',[
 lambda b:b.update(schema_version=True),lambda b:b.update(purpose=NATIVE_TRIGGER_SCENARIO),lambda b:b.update(expires_at=4599),lambda b:b.update(expires_at=4601),lambda b:b.update(issued_at=2001),lambda b:b.update(runtime_hash='z'*64),lambda b:b['files'].update(admin_key='aW52ZW50ZWQ='),lambda b:b['files'].update(graph_key='')])
def test_v2_bundle_expired_and_tampered_denied(mutation):
 b=body();mutation(b)
 with pytest.raises((PermissionError,ValueError)):decode_bundle(*sealed(b),now=2000)

def test_v2_bundle_seal_expiry_and_duplicate_keys():
 raw,seal=sealed(body());assert decode_bundle(raw,seal,now=2000)[0]['purpose']==I['purpose']
 for value,stamp,now in ((raw,seal,4600),(raw+b' ',seal,2000)):
  with pytest.raises(PermissionError):decode_bundle(value,stamp,now=now)
 duplicate=raw.replace(b'"schema_version":1',b'"schema_version":1,"schema_version":1')
 with pytest.raises(PermissionError):decode_bundle(duplicate,hashlib.sha256(duplicate).hexdigest(),now=2000)

@pytest.mark.parametrize('old',[LEGACY_SCENARIO,FORWARD_SCENARIO,NATIVE_TRIGGER_SCENARIO])
def test_v2_payload_denies_old_and_extra(old):
 prior=fixed_scenario(old)
 with pytest.raises(PermissionError):validate_payload({'jobId':str(prior.run),'workspaceId':str(SCENARIO.workspace)})
 with pytest.raises(PermissionError):validate_payload({'jobId':I['run'],'workspaceId':I['workspace'],'endpoint':'foreign'})
 validate_payload({'jobId':I['run'],'workspaceId':I['workspace']})

def test_v2_database_and_graph_targets_fixed():
 url=('postgresql://'+I['executor']+'.wfdrklofsczspazshaib:invented@aws-0-us-east-1.pooler.supabase.com:5432/'+I['database']).encode()
 assert 'sslmode=verify-full' in database_url(url,Path('/private/ca'))
 for bad in (url.replace(I['database'].encode(),b'oracle_native_proof_v1'),url.replace(I['executor'].encode(),b'oracle_synthetic_executor'),url+b'?sslmode=disable'):
  with pytest.raises(PermissionError):database_url(bad,Path('/private/ca'))
 paths={k:Path('/private')/k for k in ('graph_ca','graph_cert','graph_key')}
 graph=('rediss://'+I['graph_executor']+':invented@oracle-graph.designflow.app:16391').encode()
 assert tls_config(graph,paths)[1].graph_name==I['graph_name']
 for bad in (graph.replace(b'16391',b'16390'),graph.replace(I['graph_executor'].encode(),b'oracle_native_proof_executor_v1'),graph+b'?ssl=false'):
  with pytest.raises(PermissionError):tls_config(bad,paths)

@pytest.fixture(scope='module')
def v2_sql(native_sql):
 import psycopg
 oldadmin,*_=native_sql
 oldrun=fixed_scenario(NATIVE_TRIGGER_SCENARIO).run
 with psycopg.connect(oldadmin,autocommit=True) as c:
  before=c.execute('SELECT row_to_json(r)::text FROM oracle2.operating_view_runs r WHERE run_id=%s',(oldrun,)).fetchone()[0]
  c.execute('REVOKE ALL ON DATABASE oracle_native_proof_v1 FROM PUBLIC')
  c.execute('CREATE DATABASE oracle_native_proof_v2')
  c.execute('REVOKE ALL ON DATABASE oracle_native_proof_v2 FROM PUBLIC')
 admin=psycopg.conninfo.make_conninfo(oldadmin,dbname=I['database'])
 from test_hosting_synthetic_fixture import parameters
 p=parameters();p.update(runtime_hash='a'*64,review_hash='a'*64,source_role_registry_hash='a'*64,expires_at=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat(),synthetic_scenario=I['purpose'],synthetic_scenario_seal=SCENARIO.seal())
 # Native-v1's fixture uses real SCRAM, and this helper's verifier binds the same
 # explicitly invented local fixture password without touching any old role.
 import secrets,hmac
 def scram():
  salt=secrets.token_bytes(16);v=hashlib.pbkdf2_hmac('sha256',b'invented-v2-test-only',salt,4096)
  stored=hashlib.sha256(hmac.new(v,b'Client Key',hashlib.sha256).digest()).digest();server=hmac.new(v,b'Server Key',hashlib.sha256).digest()
  return 'SCRAM-SHA-256$4096:'+base64.b64encode(salt).decode()+'$'+base64.b64encode(stored).decode()+':'+base64.b64encode(server).decode()
 p.update({r+'_scram':scram() for r in ('gateway','executor','projector')})
 with psycopg.connect(admin) as c:
  for n in MIGRATIONS:c.execute(compile_v2_migration(n))
  c.execute((ROOT/'services/oracle-brain/sql/016_native_trigger_proof_v2.sql').read_text())
  c.execute(compile_v2_seed(p)[0])
  for role in ('gateway','executor','projector'):c.execute(psycopg.sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(psycopg.sql.Identifier(I['database']),psycopg.sql.Identifier(I[role])))
 connections={role:psycopg.conninfo.make_conninfo(admin,user=I[role],password='invented-v2-test-only') for role in ('gateway','executor','projector')}
 yield admin,connections,fixture('a'*64,'a'*64,I['purpose'])[-1]
 with psycopg.connect(oldadmin) as c:assert c.execute('SELECT row_to_json(r)::text FROM oracle2.operating_view_runs r WHERE run_id=%s',(oldrun,)).fetchone()[0]==before

def test_v2_actual_default_roles_source_binding_and_original_denials(v2_sql):
 import psycopg
 admin,urls,_=v2_sql
 for role in ('executor','projector'):
  NativeSourceRoleBindingV2('a'*64,'a'*64,synthetic=True,expected_login=I[role]).check_url(urls[role])
 with psycopg.connect(urls['gateway']) as c:
  assert c.execute('SELECT session_user,current_user').fetchone()==(I['gateway'],I['groups']['gateway'])
  with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT text FROM oracle2.source_blocks')
 for url in (urls['gateway'],admin):
  with pytest.raises(PermissionError):NativeSourceRoleBindingV2('a'*64,'a'*64,synthetic=True).check_url(url)

@pytest.mark.parametrize('flag',['CREATEDB','CREATEROLE','REPLICATION','BYPASSRLS','INHERIT','SUPERUSER'])
def test_v2_actual_role_binding_refusals(v2_sql,flag):
 import psycopg
 admin,urls,_=v2_sql;binding=NativeSourceRoleBindingV2('a'*64,'a'*64,synthetic=True)
 try:
  with psycopg.connect(admin) as c:c.execute(psycopg.sql.SQL('ALTER ROLE {} '+flag).format(psycopg.sql.Identifier(I['executor'])))
  with pytest.raises(PermissionError,match='privileges changed'):binding.check_url(urls['executor'])
 finally:
  with psycopg.connect(admin) as c:c.execute(psycopg.sql.SQL('ALTER ROLE {} NO'+flag).format(psycopg.sql.Identifier(I['executor'])))
 binding.check_url(urls['executor'])

def test_v2_actual_membership_registry_expiry_and_tls_refusals(v2_sql,tmp_path):
 import psycopg
 admin,urls,_=v2_sql;binding=NativeSourceRoleBindingV2('a'*64,'a'*64,synthetic=True)
 try:
  with psycopg.connect(admin) as c:c.execute(psycopg.sql.SQL('GRANT {} TO {}').format(psycopg.sql.Identifier(I['groups']['reader']),psycopg.sql.Identifier(I['executor'])))
  with pytest.raises(PermissionError,match='memberships changed'):binding.check_url(urls['executor'])
 finally:
  with psycopg.connect(admin) as c:c.execute(psycopg.sql.SQL('REVOKE {} FROM {}').format(psycopg.sql.Identifier(I['groups']['reader']),psycopg.sql.Identifier(I['executor'])))
 with psycopg.connect(admin) as c:expiry=c.execute('SELECT expires_at FROM oracle2.hosting_role_runtime_admissions WHERE role_name=%s',(I['executor'],)).fetchone()[0]
 try:
  with psycopg.connect(admin) as c:c.execute("UPDATE oracle2.hosting_role_runtime_admissions SET expires_at=clock_timestamp()-interval '1 second' WHERE role_name=%s",(I['executor'],))
  with pytest.raises(PermissionError):binding.check_url(urls['executor'])
 finally:
  with psycopg.connect(admin) as c:c.execute('UPDATE oracle2.hosting_role_runtime_admissions SET expires_at=%s WHERE role_name=%s',(expiry,I['executor']))
 with pytest.raises(psycopg.OperationalError):binding.check_url(psycopg.conninfo.make_conninfo(urls['executor'],sslmode='disable'))
 wrong=tmp_path/'wrong-ca.pem';wrong.write_text('not a trusted certificate')
 with pytest.raises(psycopg.OperationalError):binding.check_url(psycopg.conninfo.make_conninfo(urls['executor'],sslrootcert=str(wrong)))

def test_v2_cross_database_privileges_denied(v2_sql,native_sql):
 import psycopg
 admin,urls,_=v2_sql;oldadmin,oldgateway,oldexecutor,oldprojector,_=native_sql
 for role,url in urls.items():
  with pytest.raises(psycopg.OperationalError):psycopg.connect(psycopg.conninfo.make_conninfo(url,dbname='oracle_native_proof_v1')).close()
 for url in (oldgateway,oldexecutor,oldprojector):
  with pytest.raises(psycopg.OperationalError):psycopg.connect(psycopg.conninfo.make_conninfo(url,dbname=I['database'])).close()
 # Catalog proofs complement connection refusals, including retained pilot roles.
 with psycopg.connect(admin) as c:
  for role in ('oracle_synthetic_gateway','oracle_synthetic_executor','oracle_synthetic_projector','oracle2_checkpoint'):
   assert not c.execute("SELECT has_database_privilege(%s,%s,'CONNECT')",(role,I['database'])).fetchone()[0]

def test_v2_claims_refuse_replay_and_unknown_retry(v2_sql):
 import psycopg
 admin,u,release=v2_sql;run=SCENARIO.run
 with psycopg.connect(admin) as c:original_expiry=c.execute('SELECT expires_at FROM oracle2.operating_view_runs WHERE run_id=%s',(run,)).fetchone()[0]
 try:
  with psycopg.connect(admin) as c:c.execute("UPDATE oracle2.operating_view_runs SET expires_at=clock_timestamp()-interval '1 second' WHERE run_id=%s",(run,))
  with psycopg.connect(u['projector']) as c:
   with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT oracle2.native_trigger_projection(%s,false)',(run,))
 finally:
  with psycopg.connect(admin) as c:c.execute('UPDATE oracle2.operating_view_runs SET expires_at=%s WHERE run_id=%s',(original_expiry,run))
 with psycopg.connect(admin) as c:assert c.execute('SELECT count(*) FROM oracle2.native_trigger_projections').fetchone()==(0,)
 for url in (u['gateway'],u['executor']):
  with psycopg.connect(url) as c:
   with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT oracle2.native_trigger_projection(%s,false)',(run,))
 with psycopg.connect(u['projector']) as c:
  with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT oracle2.native_trigger_projection(%s,true)',(run,))
 with psycopg.connect(u['projector']) as c:c.execute('SELECT oracle2.native_trigger_projection(%s,false)',(run,))
 with psycopg.connect(u['projector']) as c:
  with pytest.raises(psycopg.errors.UniqueViolation):c.execute('SELECT oracle2.native_trigger_projection(%s,false)',(run,))
 with psycopg.connect(u['projector']) as c:c.execute('SELECT oracle2.native_trigger_projection(%s,true)',(run,))
 with psycopg.connect(u['projector']) as c:
  with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT oracle2.native_trigger_projection(%s,true)',(run,))
 for old in (LEGACY_SCENARIO,FORWARD_SCENARIO,NATIVE_TRIGGER_SCENARIO):
  with psycopg.connect(u['gateway']) as c:
   with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT oracle2.native_trigger_dispatch(%s,%s,%s)',(fixed_scenario(old).run,'a'*64,release.documentary_gate_hash))
 with psycopg.connect(u['gateway']) as c:c.execute('SELECT oracle2.native_trigger_dispatch(%s,%s,%s)',(run,'a'*64,release.documentary_gate_hash))
 with psycopg.connect(u['gateway']) as c:
  with pytest.raises(psycopg.errors.UniqueViolation):c.execute('SELECT oracle2.native_trigger_dispatch(%s,%s,%s)',(run,'a'*64,release.documentary_gate_hash))
 for role in ('projector','gateway'):
  with psycopg.connect(u[role]) as c:
   with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT oracle2.native_trigger_claim(%s,%s)',(run,'run_v2inventedAttempt01'))
 with psycopg.connect(u['executor']) as c:c.execute('SELECT oracle2.native_trigger_claim(%s,%s)',(run,'run_v2inventedAttempt01'))
 with psycopg.connect(u['executor']) as c:
  with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT oracle2.native_trigger_claim(%s,%s)',(run,'run_v2inventedAttempt01'))
 with psycopg.connect(u['gateway']) as c:
  c.execute('SELECT oracle2.native_trigger_bind(%s,%s)',(run,'run_v2inventedAttempt01'));assert c.execute('SELECT oracle2.native_trigger_run(%s)',(run,)).fetchone()[0]=='run_v2inventedAttempt01'
  c.execute('SELECT oracle2.native_trigger_session_create(%s,%s,%s)',('1'*64,'2'*64,'3'*64));assert c.execute('SELECT oracle2.native_trigger_session_live(%s,%s,%s)',('1'*64,'2'*64,'3'*64)).fetchone()[0]
  c.execute('SELECT oracle2.native_trigger_session_revoke(%s)',('1'*64,));assert not c.execute('SELECT oracle2.native_trigger_session_live(%s,%s,%s)',('1'*64,'2'*64,'3'*64)).fetchone()[0]


@pytest.mark.parametrize('variable',['ORACLE2_NATIVE_TRIGGER_BUNDLE','ORACLE2_NATIVE_TRIGGER_BUNDLE_SHA256','ORACLE_NATIVE_ADMIN_URL','ORACLE_NATIVE_GRAPH_PROJECTOR_PASSWORD','ORACLE_NATIVE_PROJECTOR_DATABASE_URL','ORACLE2_PROJECTOR_DATABASE_URL','TRIGGER_ACCESS_TOKEN','TRIGGER_PAT'])
def test_v2_entrypoint_rejects_old_or_privileged_environment_before_work(monkeypatch,capsys,variable):
 from oracle_brain.hosting import native_trigger_v2 as module
 monkeypatch.setenv(variable,'invented-sensitive-marker')
 with pytest.raises(SystemExit) as failure:module.main()
 assert failure.value.code==1
 output=capsys.readouterr();assert output.out=='{"state":"denied"}\n' and output.err==''


def test_v2_actual_admin_option_and_group_trait_drift_denied(v2_sql):
 import psycopg
 admin,urls,_=v2_sql;binding=NativeSourceRoleBindingV2('a'*64,'a'*64,synthetic=True)
 group=psycopg.sql.Identifier(I['groups']['executor']);login=psycopg.sql.Identifier(I['executor'])
 try:
  with psycopg.connect(admin) as c:c.execute(psycopg.sql.SQL('GRANT {} TO {} WITH ADMIN OPTION').format(group,login))
  with pytest.raises(PermissionError,match='admin option changed'):binding.check_url(urls['executor'])
 finally:
  with psycopg.connect(admin) as c:c.execute(psycopg.sql.SQL('REVOKE ADMIN OPTION FOR {} FROM {}').format(group,login))
 try:
  with psycopg.connect(admin) as c:c.execute(psycopg.sql.SQL('ALTER ROLE {} LOGIN').format(group))
  with pytest.raises(PermissionError,match='effective group privileges changed'):binding.check_url(urls['executor'])
 finally:
  with psycopg.connect(admin) as c:c.execute(psycopg.sql.SQL('ALTER ROLE {} NOLOGIN').format(group))
 binding.check_url(urls['executor'])
