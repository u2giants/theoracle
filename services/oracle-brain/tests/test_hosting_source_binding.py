"""Actual SCRAM source-role admission is distinct from custody/key/documentary pins."""
import hashlib,json,os
from uuid import uuid4
import psycopg
import pytest
from oracle_brain.hosting.source_binding import SourceRoleBinding
from oracle_brain.hosting.runtime import settings,execute_one
from oracle_brain.operating_model.authority_adapter import PostgresSources
from test_hosting_candidate_permissions import scoped
from test_hosting_runtime_permissions import runtime_scope


def binding():return SourceRoleBinding('c'*64,'d'*64,synthetic=True)


def test_actual_self_binding_matches_and_has_no_catalog_privileges(admin_url,runtime_scope):
 url=runtime_scope[0][0]
 with psycopg.connect(url) as conn:
  binding().check(conn)
  assert conn.execute('SELECT session_user=current_user').fetchone()[0] is True
  assert conn.execute("SELECT has_table_privilege(current_user,'oracle2.hosting_role_runtime_admissions','SELECT')").fetchone()[0] is False
 with psycopg.connect(admin_url) as conn:
  login=runtime_scope[0][6]
  assert conn.execute("SELECT rolpassword LIKE 'SCRAM-SHA-256$%%' FROM pg_authid WHERE rolname=%s",(login,)).fetchone()[0] is True
  assert conn.execute("SELECT EXISTS(SELECT 1 FROM pg_hba_file_rules WHERE type='host' AND auth_method='scram-sha-256')").fetchone()[0] is True

@pytest.mark.parametrize('runtime,registry',[('0'*64,'d'*64),('c'*64,'0'*64),('d'*64,'c'*64),('c'*64,'e'*64)])
def test_distinct_wrong_external_pins_deny(runtime_scope,runtime,registry):
 with psycopg.connect(runtime_scope[0][0]) as conn:
  with pytest.raises(PermissionError):SourceRoleBinding(runtime,registry,synthetic=True).check(conn)


def test_production_plaintext_refused_even_when_registry_matches(runtime_scope):
 url=psycopg.conninfo.make_conninfo(runtime_scope[0][0],sslmode='disable')
 with psycopg.connect(url) as conn:
  with pytest.raises(PermissionError):SourceRoleBinding('c'*64,'d'*64).check(conn)


def test_source_read_rechecks_pins_after_startup_before_reading(admin_url,runtime_scope):
 scoped=runtime_scope[0];url,workspace,other,source,appointment,artifact,login=scoped
 source_adapter=PostgresSources(url,source_binding=binding());binding().check_url(url)
 with psycopg.connect(admin_url) as conn:
  # Internal catalog consistency stays true; independently sealed external pin
  # must still reject the new registry, rather than comparing DB rows to itself.
  conn.execute("UPDATE oracle2.hosting_role_runtime_admissions SET registry_hash=repeat('0',64) WHERE role_name=%s",(login,))
  conn.execute("UPDATE oracle2.hosting_role_source_admissions SET registry_hash=repeat('0',64) WHERE role_name=%s",(login,))
 with psycopg.connect(url) as conn:
  assert conn.execute('SELECT oracle2.hosting_runtime_registered()').fetchone()[0] is True
 with pytest.raises(PermissionError):source_adapter.current(workspace,source)
 with pytest.raises(PermissionError):source_adapter.can_read(workspace,uuid4(),source)

@pytest.mark.parametrize('target',['runtime','source'])
def test_expiry_denies_actual_projection(admin_url,runtime_scope,target):
 scoped=runtime_scope[0]
 with psycopg.connect(admin_url) as conn:
  conn.execute('UPDATE oracle2.hosting_role_'+target+'_admissions SET expires_at=now()-interval \'1 second\' WHERE role_name=%s',(scoped[6],))
 with pytest.raises(PermissionError):binding().check_url(scoped[0])


def test_executor_settings_require_separate_pin(tmp_path,runtime_scope):
 ca=tmp_path/'ca';ca.write_text('invented-test-ca');ca.chmod(0o600)
 url=tmp_path/'database';url.write_text(psycopg.conninfo.make_conninfo(runtime_scope[0][0],sslmode='verify-full',sslrootcert=str(ca)));url.chmod(0o600)
 value={'profile':'executor','runtime_hash':'c'*64,'synthetic':True,'allowed_release_hashes':['a'*64],
  'worker_uri':'spiffe://oracle/test','database_url_file':str(url),'registry':'unused','registry_hash':'d'*64,
  'spool':'unused','graph_url_file':'unused','blob_root':'unused'}
 path=tmp_path/'settings';path.write_text(json.dumps(value));path.chmod(0o600)
 with pytest.raises(PermissionError):settings('executor',path,hashlib.sha256(path.read_bytes()).hexdigest())


def test_each_executor_job_requires_actual_binding_before_claim(runtime_scope):
 class Custody:
  def claim(self):pytest.fail('claim must follow admitted source-role check')
 with pytest.raises(PermissionError):execute_one({'_database_url':runtime_scope[0][0]},Custody(),None)
 with pytest.raises(PermissionError):execute_one({'_database_url':runtime_scope[0][0],'_source_binding':SourceRoleBinding('c'*64,'0'*64,synthetic=True)},Custody(),None)


def test_actual_verify_full_ca_tls_and_scram_binding(runtime_scope):
 ca=os.environ.get('ORACLE2_TEST_TLS_ROOT')
 assert ca,'actual owned synthetic TLS CA required'
 url=psycopg.conninfo.make_conninfo(runtime_scope[0][0],sslmode='verify-full',sslrootcert=ca)
 with psycopg.connect(url) as conn:
  assert conn.pgconn.ssl_in_use is True
  assert conn.info.get_parameters()['sslmode']=='verify-full'
  assert conn.execute('SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()').fetchone()[0] is True
  SourceRoleBinding('c'*64,'d'*64).check(conn)
 bad=psycopg.conninfo.make_conninfo(url,password='invented-deliberately-wrong')
 with pytest.raises(psycopg.OperationalError):psycopg.connect(bad)


def test_current_source_factory_reads_only_after_exact_actual_binding(runtime_scope):
 scoped=runtime_scope[0]
 source=PostgresSources(scoped[0],source_binding=binding()).current(scoped[1],scoped[3])
 assert source.reading=='invented-original' and source.ref.revision==2


def test_executor_sealed_settings_bind_distinct_source_registry_actual_tls(tmp_path,runtime_scope):
 ca=os.environ['ORACLE2_TEST_TLS_ROOT'];url=tmp_path/'database'
 url.write_text(psycopg.conninfo.make_conninfo(runtime_scope[0][0],sslmode='verify-full',sslrootcert=ca));url.chmod(0o600)
 value={'profile':'executor','runtime_hash':'c'*64,'source_role_registry_hash':'d'*64,'synthetic':True,'allowed_release_hashes':['a'*64],
  'worker_uri':'spiffe://oracle/test','database_url_file':str(url),'registry':'unused','registry_hash':'e'*64,
  'spool':'unused','graph_url_file':'unused','blob_root':'unused'}
 path=tmp_path/'settings';path.write_text(json.dumps(value));path.chmod(0o600)
 result=settings('executor',path,hashlib.sha256(path.read_bytes()).hexdigest())
 assert result['_source_binding'].source_role_registry_hash=='d'*64 and result['registry_hash']=='e'*64
 value['source_role_registry_hash']=value['registry_hash'];path.write_text(json.dumps(value))
 with pytest.raises(PermissionError):settings('executor',path,hashlib.sha256(path.read_bytes()).hexdigest())


def test_unregistered_session_has_no_external_source_admission(admin_url):
 with psycopg.connect(admin_url) as conn:
  with pytest.raises(PermissionError):binding().check(conn)


def test_registered_role_cannot_use_unbound_synthetic_escape(runtime_scope):
 with pytest.raises(PermissionError):PostgresSources(runtime_scope[0][0],synthetic=True)
 with pytest.raises(PermissionError):PostgresSources(runtime_scope[0][0])

def test_legacy_requires_explicit_synthetic_mode(admin_url):
 with pytest.raises(PermissionError):PostgresSources(admin_url)
 PostgresSources(admin_url,synthetic=True)
