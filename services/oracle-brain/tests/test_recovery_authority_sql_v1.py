"""Whole actual SQL026 source proof on independently owned synthetic TLS DB.

No dump, child, provider, company original, positive restored role or activation.
This fixture is an invented external installer, never a runtime grant route.
"""
import hashlib
import secrets
import time
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.recovery_contracts_v1 import (
 RecoveryScopeV1,RecoveryPurposeBindingV1,RecoveryMigrationV1,RecoveryStartupConfigV1,
 RecoveryCurrentV1,REQUIRED_CANONICAL_MIGRATIONS_V1)
from oracle_brain.operating_model.recovery_authority_v1 import (
 ProtectedRecoverySettingsV1,RecoverySQLAuthorityV1,PUBLIC_RECOVERY_SIGNATURES_V1,
 PRIVATE_RECOVERY_SIGNATURES_V1,recovery_catalog_fingerprint_v1)
from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
from test_recovery_contracts_v1 import descriptor,change,H,uid
from test_recovery_protected_settings_v1 import write_pin

ROOT=Path(__file__).resolve().parents[3]

def capture_bindings(capture_identity,observe_identity,capture_principal,observe_principal):
 """Same closed constructor used by the actual invented installer and pure check."""
 return (RecoveryPurposeBindingV1(phase_authority='capture',principal_id=capture_principal,sql_identity=capture_identity),
         RecoveryPurposeBindingV1(phase_authority='observe',principal_id=observe_principal,sql_identity=observe_identity))

@pytest.fixture
def recovery_install(admin_url,tmp_path):
 """Real own LOGIN/actual DB identity/protected files, externally installed."""
 from dev.oracle2.test_worker_postgres_fixture import owned_worker_database
 import os
 container=os.environ.get('ORACLE2_WORKER_CONTAINER_ID','')
 owned_worker_database(container,admin_url)
 def install():
  op=uuid4();principal=uuid4();workspace=uuid4();root=uuid4();issuer=uuid4();reviewer=uuid4()
  name='recovery_'+uuid4().hex;password=secrets.token_urlsafe(32)
  observe_name='recovery_observe_'+uuid4().hex;observe_password=secrets.token_urlsafe(32);observe_principal=uuid4()
  now=datetime.now(timezone.utc);until=now+timedelta(seconds=120)
  with psycopg.connect(admin_url) as c:
   for role,credential,signatures in ((name,password,PUBLIC_RECOVERY_SIGNATURES_V1),(observe_name,observe_password,(PUBLIC_RECOVERY_SIGNATURES_V1[0],PUBLIC_RECOVERY_SIGNATURES_V1[2]))):
    c.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION').format(sql.Identifier(role),sql.Literal(credential)))
    c.execute(sql.SQL('GRANT USAGE ON SCHEMA oracle2 TO {}').format(sql.Identifier(role)))
    for signature in signatures:
     c.execute(sql.SQL('GRANT EXECUTE ON FUNCTION '+signature+' TO {}').format(sql.Identifier(role)))
    c.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',(role,H,H,until))
   physical=c.execute("SELECT (SELECT system_identifier::text FROM pg_control_system()),oid,datname,pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()").fetchone()
   c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,expires_at) VALUES(%s,%s,%s,%s,%s,%s)',(root,workspace,issuer,'root',reviewer,until))
   coverage=[]
   for prefix,holder in (('recovery-capture:',principal),('recovery-deny-census:',principal),('recovery-observe:',observe_principal)):
    aid=uuid4();scope=prefix+str(op)
    c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(aid,workspace,holder,scope,issuer,root,until))
    coverage.append(RecoveryScopeV1(workspace_id=workspace,appointment_id=aid,root_appointment_id=root,scope=scope))
   catalog={}
   for signature in PUBLIC_RECOVERY_SIGNATURES_V1+PRIVATE_RECOVERY_SIGNATURES_V1:
    oid,body=c.execute("SELECT oid,encode(sha256(convert_to(prosrc,'UTF8')),'hex') FROM pg_proc WHERE oid=to_regprocedure(%s)",(signature,)).fetchone()
    catalog[signature]={'oid':oid,'body_sha256':body}
  params=psycopg.conninfo.conninfo_to_dict(admin_url)
  url=psycopg.conninfo.make_conninfo(admin_url,user=name,password=password,hostaddr=params['host'])
  observe_url=psycopg.conninfo.make_conninfo(admin_url,user=observe_name,password=observe_password,hostaddr=params['host'])
  folder=tmp_path/name;folder.mkdir(mode=0o700)
  urlpin=write_pin(folder/'database-url',url.encode())
  observe_urlpin=write_pin(folder/'observe-database-url',observe_url.encode())
  ca=Path(params['sslrootcert']);s=ca.stat()
  # Preserve exact protected fixture CA bytes/identity; no credential copying.
  from oracle_brain.operating_model.recovery_contracts_v1 import RecoveryPrivateFileV1
  capin=RecoveryPrivateFileV1(path=str(ca),device=s.st_dev,inode=s.st_ino,uid=s.st_uid,mode=s.st_mode&0o777,sha256=hashlib.sha256(ca.read_bytes()).hexdigest())
  from oracle_brain.operating_model.protected_sql_connection_v1 import _connection_v1
  with _request_fence_v1(time.monotonic()+20.0):
   with _connection_v1(url,datetime.now(timezone.utc)+timedelta(seconds=20),require_pinned_address=True) as c:
    catalog_sha=recovery_catalog_fingerprint_v1(c,datetime.now(timezone.utc)+timedelta(seconds=15))
  d=descriptor();identity=change(d.current_control_source,system_identifier=physical[0],database_oid=physical[1],database_name=physical[2],database_owner=physical[3],session_role=name,host=params['host'],hostaddr=params['host'],port=int(params['port']),database_url=urlpin,tls_ca=capin,schema_catalog_sha256=catalog_sha)
  observe_identity=change(identity,session_role=observe_name,database_url=observe_urlpin)
  migrations=tuple(RecoveryMigrationV1(name=n,sha256=hashlib.sha256((ROOT/'services/oracle-brain/sql'/n).read_bytes()).hexdigest()) for n in REQUIRED_CANONICAL_MIGRATIONS_V1)
  d=change(d,operation_id=op,workspace_ids=(workspace,),scope_coverage=tuple(sorted(coverage,key=lambda v:(str(v.workspace_id),v.scope,str(v.appointment_id)))),current_control_source=identity,purpose_bindings=capture_bindings(identity,observe_identity,principal,observe_principal),databases=(change(d.databases[0],source=identity),),migrations=migrations,issued_at=now,expires_at=until,original_horizon=until)
  raw=canonical_bytes(d.model_dump(mode='json'))
  with psycopg.connect(admin_url) as c:
   admission=uuid4();observe_admission=uuid4()
   for aid,role,holder,purpose in ((admission,name,principal,'capture'),(observe_admission,observe_name,observe_principal,'observe')):
    c.execute('''INSERT INTO oracle2.recovery_operation_admissions_v1(admission_id,operation_id,role_name,principal_id,phase_authority,runtime_hash,registry_hash,descriptor_bytes,descriptor_sha256,catalog,scope_coverage,issuer_actor,reviewer_actor,issued_at,expires_at,original_horizon) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',(aid,op,role,holder,purpose,H,H,raw,hashlib.sha256(raw).hexdigest(),Jsonb(catalog),Jsonb(d.model_dump(mode='json')['scope_coverage']),issuer,reviewer,now,until,until))
  dp=write_pin(folder/'descriptor.json',raw)
  config=RecoveryStartupConfigV1(descriptor=dp,postrestore_binding=None,issuer_actor=issuer,reviewer_actor=reviewer)
  cp=write_pin(folder/'startup.json',canonical_bytes(config.model_dump(mode='json')))
  settings=ProtectedRecoverySettingsV1(cp,expected_issuer_actor=issuer,expected_reviewer_actor=reviewer)
  return dict(authority=RecoverySQLAuthorityV1(settings,'capture'),observer=RecoverySQLAuthorityV1(settings,'observe'),observe_principal=observe_principal,observe_login=observe_name,descriptor=d,admission=admission,principal=principal,workspace=workspace,root=root,url=url,login=name,admin=admin_url)
 return install


def current(f):
 with _request_fence_v1(time.monotonic()+20.0):
  return f['authority'].current_v1(deadline=datetime.now(timezone.utc)+timedelta(seconds=15))


def test_actual_complete_current_census_has_all56_owners_and_no_permission(recovery_install):
 f=recovery_install()
 # Actual client producer and existing SECDEF consumer must agree before any
 # phase effect; no new test function or caller-supplied catalog hash.
 from oracle_brain.operating_model.protected_sql_connection_v1 import _connection_v1
 from oracle_brain.operating_model.request_deadline_v1 import sql_execute_v1
 deadline=datetime.now(timezone.utc)+timedelta(seconds=15)
 with _request_fence_v1(time.monotonic()+20.0):
  with _connection_v1(f['url'],deadline,require_pinned_address=True) as c:
   sql_execute_v1(c,deadline,"SELECT pg_catalog.set_config('search_path','public',true)")
   assert recovery_catalog_fingerprint_v1(c,deadline)==f['descriptor'].current_control_source.schema_catalog_sha256
   assert sql_execute_v1(c,deadline,"SELECT pg_catalog.current_setting('search_path')").fetchone()==('pg_catalog, oracle2',)
 value=current(f)
 assert type(value) is RecoveryCurrentV1 and value.census.complete
 assert len(value.census.watermarks)>56
 assert value.census.workspace_ids==(f['workspace'],)
 assert value.serving_authorized is False and value.dispatch_authorized is False


def test_actual_phase_claim_is_once_even_after_connection_restart(recovery_install):
 f=recovery_install()
 def claim():
  with _request_fence_v1(time.monotonic()+20.0):return f['authority']._claim_v1('capture',deadline=datetime.now(timezone.utc)+timedelta(seconds=15))
 first=claim();second=claim()
 assert first.fresh and not second.fresh
 assert first.claimed_at==second.claimed_at and first.original_phase_deadline==second.original_phase_deadline
 assert not first.automatic_retry_allowed


def test_actual_revoked_current_appointment_denies_after_previous_positive(recovery_install):
 f=recovery_install();current(f)
 with psycopg.connect(f['admin']) as c:c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(f['root'],))
 with pytest.raises(psycopg.errors.InsufficientPrivilege):current(f)


def test_actual_recovery_admission_and_phase_rows_are_immutable(recovery_install):
 f=recovery_install()
 with psycopg.connect(f['admin']) as c:
  with pytest.raises(psycopg.Error,match='append-only'):
   with c.transaction():c.execute('DELETE FROM oracle2.recovery_operation_admissions_v1 WHERE admission_id=%s',(f['admission'],))
 with psycopg.connect(f['url'],connect_timeout=2,options='-c statement_timeout=5000 -c lock_timeout=2000') as c:
  with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT * FROM oracle2.recovery_operation_admissions_v1')


def test_actual_denied_unqualified_source_and_foreign_workspace_do_not_leak_body(recovery_install):
 f=recovery_install();source=uuid4();foreign=uuid4();private='invented private filename is not recovery metadata'
 with psycopg.connect(f['admin']) as c:
  for sid,workspace in ((source,f['workspace']),(foreign,uuid4())):
   c.execute('INSERT INTO oracle2.sources(source_id,workspace_id,uploaded_by,filename,content_type,status) VALUES(%s,%s,%s,%s,%s,%s)',(sid,workspace,f['principal'],private,'text/plain','error'))
 value=current(f)
 assert [s.source_id for s in value.census.sources]==[source]
 assert value.census.sources[0].denied and value.census.sources[0].original_sha256 is None
 assert private.encode() not in canonical_bytes(value.model_dump(mode='json'))


def test_actual_foreign_operation_and_recovery_private_helper_are_denied(recovery_install):
 f=recovery_install()
 with psycopg.connect(f['url'],connect_timeout=2,options='-c statement_timeout=5000 -c lock_timeout=2000') as c:
  for query,args in [('SELECT oracle2.recovery_current_v1(%s,%s)',(uuid4(),datetime.now(timezone.utc)+timedelta(seconds=10))),('SELECT oracle2._recovery_census_v1(%s,%s)',(f['descriptor'].operation_id,datetime.now(timezone.utc)+timedelta(seconds=10)))]:
   with pytest.raises(psycopg.errors.InsufficientPrivilege):
    with c.transaction():c.execute(query,args)


def test_actual_public_acl_drift_blocks_current_before_any_phase_claim(recovery_install):
 f=recovery_install();current(f)
 with psycopg.connect(f['admin']) as c:c.execute('GRANT EXECUTE ON FUNCTION oracle2.recovery_current_v1(uuid,timestamptz) TO PUBLIC')
 try:
  with pytest.raises(PermissionError,match='catalog'):current(f)
  with psycopg.connect(f['admin']) as c:
   assert c.execute('SELECT count(*) FROM oracle2.recovery_phase_claims_v1 WHERE operation_id=%s',(f['descriptor'].operation_id,)).fetchone()[0]==0
 finally:
  with psycopg.connect(f['admin']) as c:c.execute('REVOKE EXECUTE ON FUNCTION oracle2.recovery_current_v1(uuid,timestamptz) FROM PUBLIC')


def assert_all_direct_calls_refuse(f,*,message="actual complete recovery catalog differs from installed binding",marker=None):
 """Direct SQL only: deliberately bypass the Python catalog client guard."""
 op=f['descriptor'].operation_id
 calls=[('SELECT oracle2.recovery_current_v1(%s,%s)',(op,)),('SELECT oracle2.claim_recovery_phase_v1(%s,%s,%s)',(op,'capture')),('SELECT oracle2.observe_recovery_phase_v1(%s,%s,%s,%s)',(op,'capture',b'{}')),('SELECT oracle2.import_recovery_denials_v1(%s,%s,%s)',(op,b'{}'))]
 for query,args in calls:
  with psycopg.connect(f['url'],connect_timeout=2,options='-c statement_timeout=5000 -c lock_timeout=2000') as c:
   with pytest.raises(psycopg.errors.InsufficientPrivilege) as caught:c.execute(query,(*args,datetime.now(timezone.utc)+timedelta(seconds=10)))
   assert caught.value.sqlstate=='42501'
   if message is not None:assert caught.value.diag.message_primary==message
   if marker is not None:
    import re
    source=(ROOT/'services/oracle-brain/sql/026_operational_recovery.sql').read_text()
    body=source.split('CREATE FUNCTION oracle2._recovery_context_v1',1)[1].split('AS $f$',1)[1].split('END $f$;',1)[0]
    assert body.count(marker)==1
    line=body[:body.index(marker)].count('\n')+1
    assert re.search(r'(?:oracle2\.)?_recovery_context_v1\(uuid,timestamp with time zone\) line '+str(line)+r' at RAISE',caught.value.diag.context),caught.value.diag.context
 with psycopg.connect(f['admin']) as c:
  assert c.execute('SELECT count(*) FROM oracle2.recovery_phase_claims_v1 WHERE operation_id=%s',(op,)).fetchone()[0]==0
  assert c.execute('SELECT count(*) FROM oracle2.recovery_phase_observations_v1 WHERE operation_id=%s',(op,)).fetchone()[0]==0
  assert c.execute('SELECT count(*) FROM oracle2.recovery_denial_imports_v1 WHERE operation_id=%s',(op,)).fetchone()[0]==0


@pytest.mark.parametrize('signature',[
 'oracle2._replacement_metadata_json(jsonb)',
 'oracle2._migration_iso_v1(timestamptz)',
 'oracle2.deny_operating_model_mutation()',
 'oracle2._meeting_created_bot_v1(oracle2.meeting_capture_admissions_v1)'])
def test_actual_external_body_drift_denied_by_every_direct_sql_entry(recovery_install,signature):
 f=recovery_install();current(f)
 with psycopg.connect(f['admin']) as c:
  original,body=c.execute('SELECT pg_get_functiondef(oid),prosrc FROM pg_proc WHERE oid=to_regprocedure(%s)',(signature,)).fetchone()
  changed=original.replace(body,body+'\n-- bounded invented source drift\n',1)
  assert changed!=original
  c.execute(changed)
 try:
  message='exact independent retained canonicalizer body required' if signature=='oracle2._replacement_metadata_json(jsonb)' else 'actual complete recovery catalog differs from installed binding'
  assert_all_direct_calls_refuse(f,message=message)
 finally:
  with psycopg.connect(f['admin']) as c:c.execute(original)
 assert current(f).admission_id==f['admission']


@pytest.mark.parametrize('change_kind',['column','trigger','policy','owner','acl','enum'])
def test_actual_catalog_shape_drift_denied_before_all_direct_mutators(recovery_install,change_kind):
 f=recovery_install();current(f)
 # Each change is to the exact fresh owned synthetic schema. Explicit repair
 # restores that test object only; no migration replay, grant bypass or repin.
 setups={
  'column':('ALTER TABLE oracle2.recovery_deny_overlay_v1 ADD COLUMN invented_drift integer','ALTER TABLE oracle2.recovery_deny_overlay_v1 DROP COLUMN invented_drift'),
  'trigger':('ALTER TABLE oracle2.recovery_deny_overlay_v1 DISABLE TRIGGER immutable_recovery_deny_overlay_v1','ALTER TABLE oracle2.recovery_deny_overlay_v1 ENABLE TRIGGER immutable_recovery_deny_overlay_v1'),
  'policy':('CREATE POLICY invented_recovery_drift ON oracle2.recovery_deny_overlay_v1 USING(false)','DROP POLICY invented_recovery_drift ON oracle2.recovery_deny_overlay_v1'),
  'owner':('ALTER TABLE oracle2.recovery_deny_overlay_v1 OWNER TO oracle2_source_reader','ALTER TABLE oracle2.recovery_deny_overlay_v1 OWNER TO oracle2_admin'),
  'acl':('GRANT SELECT ON oracle2.recovery_deny_overlay_v1 TO oracle2_source_reader','REVOKE SELECT ON oracle2.recovery_deny_overlay_v1 FROM oracle2_source_reader'),
  'enum':("CREATE TYPE oracle2.invented_recovery_drift AS ENUM('one')",'DROP TYPE oracle2.invented_recovery_drift')}
 setup,cleanup=setups[change_kind]
 with psycopg.connect(f['admin']) as c:c.execute(setup)
 try:assert_all_direct_calls_refuse(f)
 finally:
  with psycopg.connect(f['admin']) as c:c.execute(cleanup)



def test_actual_simultaneous_requests_get_one_global_phase_claim(recovery_install):
 from concurrent.futures import ThreadPoolExecutor
 f=recovery_install()
 def claim():
  with _request_fence_v1(time.monotonic()+20.0):return f['authority']._claim_v1('capture',deadline=datetime.now(timezone.utc)+timedelta(seconds=15))
 with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:claim(),range(2)))
 assert sum(v.fresh for v in results)==1
 assert len({v.claimed_at for v in results})==1
 assert len({v.original_phase_deadline for v in results})==1
 with psycopg.connect(f['admin']) as c:
  assert c.execute('SELECT count(*) FROM oracle2.recovery_phase_claims_v1 WHERE operation_id=%s',(f['descriptor'].operation_id,)).fetchone()[0]==1


def test_actual_reinstalled_admission_cannot_reset_spent_original_phase(recovery_install):
 f=recovery_install()
 def claim():
  with _request_fence_v1(time.monotonic()+20.0):return f['authority']._claim_v1('capture',deadline=datetime.now(timezone.utc)+timedelta(seconds=15))
 first=claim();replacement=uuid4()
 with psycopg.connect(f['admin']) as c:
  c.execute('INSERT INTO oracle2.recovery_admission_revocations_v1 VALUES(%s,clock_timestamp())',(f['admission'],))
  c.execute('''INSERT INTO oracle2.recovery_operation_admissions_v1 SELECT %s,operation_id,role_name,principal_id,phase_authority,runtime_hash,registry_hash,descriptor_bytes,descriptor_sha256,postrestore_binding_bytes,postrestore_binding_sha256,backup_custody_sha256,catalog,scope_coverage,issuer_actor,reviewer_actor,issued_at,expires_at,original_horizon FROM oracle2.recovery_operation_admissions_v1 WHERE admission_id=%s''',(replacement,f['admission']))
 second=claim()
 assert not second.fresh and (second.claimed_at,second.original_phase_deadline)==(first.claimed_at,first.original_phase_deadline)
 assert current(f).admission_id==replacement


def delegate_capture(f,*,fault=None):
 leaf=next(v for v in f['descriptor'].scope_coverage if v.scope.startswith('recovery-capture:'))
 middle=uuid4();delegate=uuid4()
 with psycopg.connect(f['admin']) as c:
  root_actor,root_grantor=c.execute('SELECT actor_id,granted_by FROM oracle2.appointments WHERE appointment_id=%s',(f['root'],)).fetchone()
  workspace=uuid4() if fault=='foreign-workspace' else f['workspace']
  scope='unrelated-scope' if fault=='unrelated-scope' else leaf.scope
  c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(middle,workspace,delegate,scope,root_actor,f['root'],f['descriptor'].expires_at))
  c.execute('UPDATE oracle2.appointments SET parent_id=%s,granted_by=%s WHERE appointment_id=%s',(middle,uuid4() if fault=='broken-actor' else delegate,leaf.appointment_id))
  if fault=='wrong-root':
   other=uuid4()
   c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,expires_at) VALUES(%s,%s,%s,%s,%s,%s)',(other,f['workspace'],root_actor,'root',root_grantor,f['descriptor'].expires_at))
   c.execute('UPDATE oracle2.appointments SET parent_id=%s WHERE appointment_id=%s',(other,middle))
  elif fault=='cycle':c.execute('UPDATE oracle2.appointments SET parent_id=%s,granted_by=%s WHERE appointment_id=%s',(leaf.appointment_id,f['principal'],middle))
 return middle


@pytest.mark.parametrize('fault',['broken-actor','unrelated-scope','foreign-workspace','wrong-root','cycle'])
def test_actual_invalid_appointment_chain_denies_all_direct_calls(recovery_install,fault):
 f=recovery_install();current(f);delegate_capture(f,fault=fault)
 marker="IF NOT rooted THEN RAISE insufficient_privilege;END IF;" if fault=='wrong-root' else "IF appointment_row.appointment_id IS NULL THEN RAISE insufficient_privilege;END IF;"
 message=None
 if fault=='cycle':
  marker="RAISE insufficient_privilege USING MESSAGE='actual current rooted recovery coverage required';END IF;"
  message='actual current rooted recovery coverage required'
 assert_all_direct_calls_refuse(f,message=message,marker=marker)


def test_actual_valid_same_scope_delegation_keeps_original_horizon(recovery_install):
 f=recovery_install();before=current(f);delegate_capture(f)
 after=current(f)
 assert after.admission_id==before.admission_id and after.original_horizon==before.original_horizon
 with _request_fence_v1(time.monotonic()+20.0):
  claim=f['authority']._claim_v1('capture',deadline=datetime.now(timezone.utc)+timedelta(seconds=15))
 assert claim.fresh and claim.original_phase_deadline==f['descriptor'].expires_at


def test_actual_census_retains_broken_foreign_leaf_as_missing_current_root(recovery_install):
 f=recovery_install();other=uuid4()
 with psycopg.connect(f['admin']) as c:
  c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(other,f['workspace'],uuid4(),'source-read:'+str(uuid4()),uuid4(),f['root'],f['descriptor'].expires_at))
 value=current(f)
 denials=[v for v in value.census.authority_denials if v.appointment_id==other]
 assert len(denials)==1 and denials[0].reason=='missing-current-root'



def test_actual_capture_claim_then_separately_current_observer_metadata(recovery_install):
 from oracle_brain.operating_model.recovery_contracts_v1 import RecoveryObservationV1
 f=recovery_install()
 with _request_fence_v1(time.monotonic()+20.0):
  claim=f['authority']._claim_v1('capture',deadline=datetime.now(timezone.utc)+timedelta(seconds=15))
  observer=f['observer'].current_v1(deadline=datetime.now(timezone.utc)+timedelta(seconds=15))
 assert observer.session_role==f['observe_login'] and observer.principal_id==f['observe_principal']
 assert observer.phase_authority=='observe' and observer.census is None
 observation=RecoveryObservationV1(observation_id=uuid4(),operation_id=f['descriptor'].operation_id,phase='capture',status='UNKNOWN',original_phase_deadline=claim.original_phase_deadline,phase_started_at=claim.claimed_at,observed_at=datetime.now(timezone.utc),backup_manifest_sha256=None,source_census_sha256=None,observed_result_sha256=None,observed_file_count=None,observed_bytes=None,quarantine_reasons=('once-cost-tail-unproved',))
 with _request_fence_v1(time.monotonic()+20.0):result=f['observer']._observe_actual_v1(observation,deadline=datetime.now(timezone.utc)+timedelta(seconds=15))
 assert result['observation_only'] and not result['serving_authorized'] and not result['dispatch_authorized'] and not result['automatic_retry_allowed']
 with psycopg.connect(f['admin']) as c:
  raw,phase=c.execute('SELECT observation_bytes,claimed_phase FROM oracle2.recovery_phase_observations_v1 WHERE observation_id=%s',(observation.observation_id,)).fetchone()
 assert bytes(raw)==canonical_bytes(observation.model_dump(mode='json')) and phase=='capture'
