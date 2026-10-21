"""Actual own worker/thread/purpose admissions, including explicit empty sources."""
from datetime import datetime,timezone,timedelta
from pathlib import Path
from uuid import uuid4,UUID
import hashlib,json
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.hosting.conversation_processing_v1 import ConversationProcessingConfigV1,ProtectedConversationProcessingV1
from oracle_brain.hosting.original_intake_v1 import ProtectedInputV1
from test_durable_interview_sql import conversation,create,command
from test_replacement_requester_sql import owned_admin

@pytest.fixture
def processing_worker(conversation,tmp_path,request):
 x=conversation;_,snapshot=create(x,mode=getattr(request,'param','ordinary'));_,snapshot=command(x,snapshot)
 login='conversation_worker_'+uuid4().hex[:12];principal=uuid4();admission=uuid4();dispatch=uuid4();runtime='c'*64;registry='d'*64
 target=psycopg.conninfo.conninfo_to_dict(x['url']);url=tmp_path/'conversation-worker-url';url.write_text(psycopg.conninfo.make_conninfo(x['url'],user=login,password='invented-worker-only',sslrootcert=x['control'].settings.config.database_ca.path));url.chmod(0o600)
 ca=Path(x['control'].settings.config.database_ca.path);pinned=lambda p:ProtectedInputV1(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
 c=ConversationProcessingConfigV1(admission_id=admission,worker_principal_id=principal,workspace_id=x['workspace'],thread_id=UUID(snapshot['thread_id']),thread_revision=snapshot['revision'],employee_event_id=UUID(snapshot['events'][-1]['event_id']),enduser_principal_id=x['actor'],dispatch_id=dispatch,expected_session_role=login,expected_owner_role=x['control'].settings.config.expected_owner_role,runtime_hash=runtime,registry_hash=registry,model_id='openai/gpt-6.1-sol',qualified_population=(),qualified_population_sha256=digest({'source_refs':[]}),database_url=pinned(url),database_ca=pinned(ca),original_horizon=x['until'],expires_at=x['until'])
 # JSON boundary deliberately matches actual protected startup parsing.
 c=ConversationProcessingConfigV1.model_validate_json(json.dumps(c.model_dump(mode='json')))
 raw=canonical_bytes(c.model_dump(mode='json'));path=tmp_path/'conversation-worker-config';path.write_bytes(raw);path.chmod(0o600);pin=pinned(path);leaf=uuid4()
 with owned_admin(x) as conn:
  conn.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(login),sql.Literal('invented-worker-only')))
  conn.execute(sql.SQL('GRANT oracle2_source_reader TO {}').format(sql.Identifier(login)))
  conn.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',(login,runtime,registry,x['until']))
  conn.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(leaf,x['workspace'],principal,'employee-conversation-thread:'+snapshot['thread_id'],x['owner'],x['root'],x['until']))
  conn.execute('''INSERT INTO oracle2.conversation_processing_admissions_v1(admission_id,role_name,principal_id,workspace_id,thread_id,thread_revision,employee_event_id,enduser_principal_id,enduser_role,runtime_hash,registry_hash,config_sha256,dispatch_id,model_id,qualified_population,qualified_population_sha256,issuer_actor,reviewer_actor,original_horizon,expires_at)
   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',(admission,login,principal,x['workspace'],snapshot['thread_id'],snapshot['revision'],snapshot['events'][-1]['event_id'],x['actor'],x['login'],runtime,registry,pin.sha256,dispatch,c.model_id,Jsonb([]),c.qualified_population_sha256,uuid4(),uuid4(),x['until'],x['until']))
 try:yield x|dict(worker=ProtectedConversationProcessingV1(pin),worker_config=c,worker_pin=pin,worker_leaf=leaf,snapshot=snapshot,worker_login=login)
 finally:
  with owned_admin(x) as conn:
   conn.execute('DELETE FROM oracle2.hosting_role_runtime_admissions WHERE role_name=%s',(login,));conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(login)))

def test_actual_empty_population_still_requires_own_worker_thread_admission(processing_worker):
 x=processing_worker;actual=x['worker'].current_v1()
 assert actual.worker_principal_id==x['worker_config'].worker_principal_id and actual.qualified_population==() and actual.qualified_readings==()
 assert actual.snapshot['events'][-1]['original_text']=='不允许未经复核就发货。仅限样品。'
 assert actual.worker_principal_id!=actual.enduser_principal_id

@pytest.mark.parametrize('drift',['thread-scope','worker-runtime','employee-scope','config-pin','foreign-selected-admission','expired-runtime'])
def test_actual_worker_currentness_drift_denies_before_input_return(processing_worker,drift):
 x=processing_worker;x['worker'].current_v1()
 if drift=='config-pin':Path(x['worker_pin'].path).write_bytes(b'{}')
 else:
  with owned_admin(x) as c:
   if drift=='thread-scope':c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(x['worker_leaf'],))
   elif drift=='worker-runtime':c.execute('UPDATE oracle2.hosting_role_runtime_admissions SET runtime_hash=%s WHERE role_name=%s',('0'*64,x['worker_login']))
   elif drift=='employee-scope':c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(x['conversation_leaf'],))
   elif drift=='foreign-selected-admission':
    c.execute('UPDATE oracle2.hosting_request_principal_admissions SET principal_id=%s WHERE role_name=%s',(uuid4(),x['login']))
   else:c.execute("UPDATE oracle2.hosting_role_runtime_admissions SET expires_at=clock_timestamp()-interval '1 second' WHERE role_name=%s",(x['worker_login'],))
 with pytest.raises((PermissionError,psycopg.Error,ValueError)):x['worker'].current_v1()

def test_empty_population_without_independent_admission_is_not_default_authority(processing_worker):
 x=processing_worker
 c=x['worker_config']
 with pytest.raises(psycopg.Error),owned_admin(x) as conn:conn.execute('DELETE FROM oracle2.conversation_processing_admissions_v1 WHERE admission_id=%s',(c.admission_id,))
 wrong=c.model_copy(update={'admission_id':uuid4()})
 path=Path(x['worker_pin'].path).with_name('foreign-admission');raw=canonical_bytes(wrong.model_dump(mode='json'));path.write_bytes(raw);path.chmod(0o600)
 pin=ProtectedInputV1(path=str(path),sha256=hashlib.sha256(raw).hexdigest())
 x['worker']=ProtectedConversationProcessingV1(pin)
 with pytest.raises((PermissionError,psycopg.Error)):x['worker'].current_v1()

from test_replacement_source_intake_sql import requester


def test_canonical_019_catalog_drift_is_detected_without_fixture_replay(processing_worker,admin_url):
 from dev.oracle2.test_canonical_schema import assert_canonical_test_schema
 with psycopg.connect(admin_url) as c:
  assert_canonical_test_schema(c,admin_url)
  c.execute('ALTER FUNCTION oracle2._purpose_source_v2(uuid,uuid,uuid,text,text,text,boolean) SET search_path=public,oracle2')
  with pytest.raises(PermissionError,match='no fixture downgrade'):assert_canonical_test_schema(c,admin_url)
  c.rollback()
  assert_canonical_test_schema(c,admin_url)

@pytest.mark.parametrize('change',['head','population'])
def test_worker_cannot_reuse_appointment_for_changed_thread_or_population(processing_worker,change):
 x=processing_worker;x['worker'].current_v1()
 if change=='head':command(x,x['snapshot'])
 else:
  with pytest.raises(psycopg.Error),owned_admin(x) as c:c.execute("UPDATE oracle2.conversation_processing_admissions_v1 SET qualified_population_sha256=%s WHERE admission_id=%s",('0'*64,x['worker_config'].admission_id))
  Path(x['worker_pin'].path).write_bytes(b'{}')
 with pytest.raises((PermissionError,psycopg.Error)):x['worker'].current_v1()


@pytest.mark.parametrize('processing_worker',['interview'],indirect=True)
def test_native_worker_cannot_return_free_text_for_an_uncounted_interview(processing_worker):
 with pytest.raises(PermissionError):processing_worker['worker'].current_v1()

def test_existing_source_binding_still_denies_empty_population_without_a_source(processing_worker):
 from oracle_brain.operating_model.authority_adapter import ProcessingSourceResolver,ProcessingSourceBinding
 x=processing_worker;c=x['worker_config']
 with pytest.raises(PermissionError):
  ProcessingSourceResolver(Path(c.database_url.path).read_text(),binding=ProcessingSourceBinding(c.runtime_hash,c.registry_hash,c.expected_owner_role,c.expected_session_role,c.worker_principal_id,'source-reader',c.expires_at))
