"""Actual protected text intake→distinct byte programs→SQL014 qualification.

Invented fixture appointments are not target authority or semantic acceptance.
"""
from dataclasses import replace
from datetime import datetime,timezone,timedelta
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4,UUID
import hashlib,json
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.original_qualification_v1 import RawOriginalRefV1,RawOriginalPopulationV1
from oracle_brain.hosting.original_intake_v1 import OriginalIntakeFactoryV1,load_original_intake_settings_v1,ProtectedInputV1
from oracle_brain.hosting.conversation_original_v1 import (ConversationOriginalConfigV1,ConversationOriginalAppointmentV1,
 load_conversation_original_settings_v1,NativeConversationOriginalFactoryV1,program_identity_v1)
from test_replacement_requester_sql import owned_admin,configured_settings
from test_replacement_source_intake_sql import requester

def pin(path):return ProtectedInputV1(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
def write(path,value):
 raw=canonical_bytes(value.model_dump(mode='json'));path.write_bytes(raw);path.chmod(0o600);return hashlib.sha256(raw).hexdigest()

@pytest.fixture
def native_original(requester,tmp_path):
 x=requester;s=configured_settings(tmp_path,x)
 a=s.appointment.model_copy(update={'media_types':('application/pdf','text/plain')});ah=write(s.appointment_path,a)
 s=load_original_intake_settings_v1(s.config_path,s.config_sha256,s.appointment_path,ah,s.expected_issuer_actor,s.expected_reviewer_actor)
 data='不允许未经复核就发货。仅限样品。'.encode();snapshot=OriginalIntakeFactoryV1(s).intake_text_v1(source_id=None,expected_head=0,idempotency_key=uuid4(),filename='invented-conversation.txt',original_sha256=hashlib.sha256(data).hexdigest(),data=data)
 with appointed_native_original_phases_v1(x,snapshot,data,s,tmp_path) as observed:yield observed

@contextmanager
def appointed_native_original_phases_v1(x,snapshot,data,s,tmp_path):
 with owned_admin(x) as c:
  custody=c.execute('SELECT custody_locator_seal_sha256 FROM oracle2.source_original_revisions WHERE source_id=%s',(snapshot.sourceId,)).fetchone()[0]
 ref=RawOriginalRefV1(workspace_id=x['workspace'],source_id=snapshot.sourceId,revision=1,original_sha256=snapshot.originalSha256,byte_count=len(data),media_type='text/plain',filename=snapshot.filename,custody_locator_seal_sha256=custody)
 settings={};roles=[];leaves=[]
 for phase in ('reading','review'):
  purpose='source-original-'+phase;login='native_byte_'+phase+'_'+uuid4().hex[:10];principal=uuid4();population=uuid4();runtime='8'*64;registry='9'*64
  pop=RawOriginalPopulationV1(population_id=population,workspace_id=x['workspace'],original_root_hash='1'*64,operation_registry_hash=digest({'program':program_identity_v1(purpose)}),runtime_hash=runtime,source_registry_hash=registry,raw_refs=(ref,),population_digest=digest({'raw_refs':[ref.model_dump(mode='json')]}),issuer_actor=uuid4(),reviewer_actor=uuid4(),expires_at=s.config.expires_at)
  folder=tmp_path/phase;folder.mkdir(mode=0o700);db=folder/'database';db.write_text(psycopg.conninfo.make_conninfo(x['url'],user=login,password='invented-byte-only',sslrootcert=s.config.database_ca.path));db.chmod(0o600)
  cfg=ConversationOriginalConfigV1(schema_version=1,purpose='conversation-native-utf8-original-v1',phase=purpose,principal_id=principal,expected_session_role=login,expected_owner_role=s.config.expected_owner_role,population=pop,original_allocation_hash='3'*64,original_horizon=s.config.original_horizon,expires_at=s.config.expires_at,database_url=pin(db),database_ca=s.config.database_ca,program_sha256=program_identity_v1(purpose),storage_root=s.config.storage_root,storage_device=s.config.storage_device,storage_inode=s.config.storage_inode,storage_uid=s.config.storage_uid,storage_profile_hash=s.config.storage_profile_hash,reading_commit_sha256=None if phase=='reading' else '0'*64)
  cp=folder/'config';ch=write(cp,cfg)
  appointment=ConversationOriginalAppointmentV1(schema_version=1,purpose='conversation-native-utf8-original-v1',config_sha256=ch,phase=purpose,principal_id=principal,population_id=population,program_sha256=cfg.program_sha256,issuer_actor=uuid4(),reviewer_actor=uuid4(),valid_from=datetime.now(timezone.utc)-timedelta(seconds=1),expires_at=cfg.expires_at,original_horizon=cfg.original_horizon)
  ap=folder/'appointment';ah=write(ap,appointment)
  settings[phase]=load_conversation_original_settings_v1(cp,ch,ap,ah,appointment.issuer_actor,appointment.reviewer_actor)
  model=('oracle/native-utf8-reader-v1:' if phase=='reading' else 'oracle/native-utf8-reviewer-v1:')+cfg.program_sha256
  with owned_admin(x) as c:
   c.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(login),sql.Literal('invented-byte-only')))
   c.execute(sql.SQL('GRANT {} TO {}').format(sql.Identifier('oracle2_source_original_reader' if phase=='reading' else 'oracle2_source_original_reviewer'),sql.Identifier(login)))
   c.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',(login,runtime,registry,cfg.expires_at))
   c.execute('''INSERT INTO oracle2.original_source_populations_v1 VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',(population,x['workspace'],purpose,pop.original_root_hash,pop.population_digest,pop.operation_registry_hash,runtime,registry,cfg.original_allocation_hash,cfg.original_horizon,pop.issuer_actor,pop.reviewer_actor,pop.expires_at))
   c.execute('INSERT INTO oracle2.hosting_original_population_admissions_v1 VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',(login,population,principal,purpose,runtime,registry,pop.operation_registry_hash,cfg.expires_at,model))
   c.execute('INSERT INTO oracle2.original_source_population_members_v1 VALUES(%s,%s,%s,%s,%s,%s)',(population,0,x['workspace'],ref.source_id,ref.revision,digest(ref.model_dump(mode='json'))))
   c.execute('INSERT INTO oracle2.hosting_original_source_admissions VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(login,x['workspace'],ref.source_id,1,principal,ref.original_sha256,purpose,runtime,registry,population,cfg.expires_at))
   for scope in ('source-read:',purpose+':'):
    leaf=uuid4();leaves.append(leaf);c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(leaf,x['workspace'],principal,scope+str(ref.source_id),x['owner'],x['root'],cfg.expires_at))
  roles.append(login)
 from oracle_brain.hosting._protected_control_listener_v1 import _request_fence_v1
 import time
 try:
  with _request_fence_v1(float(time.monotonic()+30)):
   yield x|dict(settings=settings,ref=ref,data=data,roles=roles,leaves=leaves,intake=s)
 finally:
  with owned_admin(x) as c:
   for role in roles:
    c.execute('DELETE FROM oracle2.hosting_original_source_admissions WHERE role_name=%s',(role,));c.execute('DELETE FROM oracle2.hosting_original_population_admissions_v1 WHERE role_name=%s',(role,));c.execute('DELETE FROM oracle2.hosting_role_runtime_admissions WHERE role_name=%s',(role,));c.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))

def reading_then_review(x,*,expire_reader=False):
 reader=NativeConversationOriginalFactoryV1(x['settings']['reading']);seal=reader.execute_v1()
 if expire_reader:
  with owned_admin(x) as c:c.execute("UPDATE oracle2.hosting_role_runtime_admissions SET expires_at=clock_timestamp()-interval '1 second' WHERE role_name=%s",(x['roles'][0],))
 s=x['settings']['review'];cfg=s.config.model_copy(update={'reading_commit_sha256':seal.commit_sha256});ch=write(s.config_path,cfg)
 app=s.appointment.model_copy(update={'config_sha256':ch});ah=write(s.appointment_path,app)
 s=load_conversation_original_settings_v1(s.config_path,ch,s.appointment_path,ah,s.expected_issuer_actor,s.expected_reviewer_actor)
 x['settings']['review']=s
 return seal,NativeConversationOriginalFactoryV1(s).execute_v1()

def test_actual_text_custody_distinct_byte_programs_and_sole_sql_finalizer(native_original):
 x=native_original;reader,qualified=reading_then_review(x,expire_reader=True)
 assert qualified.source_ref.original_sha256==hashlib.sha256(x['data']).hexdigest() and qualified.source_ref.reading_sha256==qualified.source_ref.original_sha256
 with owned_admin(x) as c:
  assert c.execute("SELECT receipt->>'reading' FROM oracle2.operating_model_source_receipts WHERE source_id=%s",(x['ref'].source_id,)).fetchone()==(x['data'].decode(),)
  assert c.execute('SELECT count(*) FROM oracle2.operating_dispatch_reservations WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)
  assert c.execute('SELECT count(*) FROM oracle2.source_reading_qualifications WHERE source_id=%s',(x['ref'].source_id,)).fetchone()==(1,)

@pytest.mark.parametrize('drift',['wrong-program','revoked','foreign-population','changed-bytes'])
def test_actual_native_byte_phase_refuses_before_any_commit(native_original,drift):
 x=native_original;s=x['settings']['reading']
 if drift=='changed-bytes':
  p=next(Path(s.config.storage_root).glob('source-originals/*/*/*/*'));p.chmod(0o600);p.write_bytes(b'changed')
 else:
  with owned_admin(x) as c:
   if drift=='wrong-program':c.execute('UPDATE oracle2.hosting_original_population_admissions_v1 SET model_id=%s WHERE role_name=%s',('oracle/native-utf8-reader-v1:'+'0'*64,x['roles'][0]))
   elif drift=='revoked':c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(x['leaves'][0],))
   else:c.execute('DELETE FROM oracle2.original_source_population_members_v1 WHERE population_id=%s',(s.config.population.population_id,))
 with pytest.raises((PermissionError,ValueError,psycopg.Error)):NativeConversationOriginalFactoryV1(s).execute_v1()
 with owned_admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.original_phase_response_commits WHERE source_id=%s',(x['ref'].source_id,)).fetchone()==(0,)


def test_generic_one_mib_text_original_actual_intake_and_independent_qualification(requester,tmp_path):
 x=requester;s=configured_settings(tmp_path,x)
 a=s.appointment.model_copy(update={'media_types':('application/pdf','text/plain')});ah=write(s.appointment_path,a)
 s=load_original_intake_settings_v1(s.config_path,s.config_sha256,s.appointment_path,ah,s.expected_issuer_actor,s.expected_reviewer_actor)
 data='不允许未经复核就发货。仅限样品。'.encode()+b'x'*(1024*1024-len('不允许未经复核就发货。仅限样品。'.encode()))
 snapshot=OriginalIntakeFactoryV1(s).intake_text_v1(source_id=None,expected_head=0,idempotency_key=uuid4(),filename='invented-meeting-limit.txt',original_sha256=hashlib.sha256(data).hexdigest(),data=data)
 with appointed_native_original_phases_v1(x,snapshot,data,s,tmp_path) as observed:
  _,qualified=reading_then_review(observed,expire_reader=True)
  assert qualified.source_ref.original_sha256==hashlib.sha256(data).hexdigest()
  with owned_admin(x) as c:
   row=c.execute("SELECT octet_length(receipt->>'reading'),receipt->>'reading' FROM oracle2.operating_model_source_receipts WHERE source_id=%s",(snapshot.sourceId,)).fetchone()
   assert row==(1024*1024,data.decode())


def test_generic_text_over_limit_refuses_before_reservation_or_write(requester,tmp_path,monkeypatch):
 x=requester;s=configured_settings(tmp_path,x);factory=OriginalIntakeFactoryV1(s)
 monkeypatch.setattr(factory,'_intake_v1',lambda **kwargs:pytest.fail('oversize text reached reserve/custody'))
 data=b'x'*(1024*1024+1)
 with pytest.raises(ValueError):factory.intake_text_v1(source_id=None,expected_head=0,idempotency_key=uuid4(),filename='oversize.txt',original_sha256=hashlib.sha256(data).hexdigest(),data=data)
 with owned_admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)
