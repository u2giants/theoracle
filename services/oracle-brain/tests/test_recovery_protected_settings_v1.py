"""Actual invented protected files; no SQL/provider/platform authorization."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import hashlib,os,stat
from uuid import UUID
import pytest
from oracle_brain.operating_model.recovery_contracts_v1 import *
from oracle_brain.operating_model.recovery_authority_v1 import *
from test_recovery_contracts_v1 import descriptor,change,uid,profile,H

def write_pin(path,raw):
 path.write_bytes(raw);path.chmod(0o600);s=path.stat()
 return RecoveryPrivateFileV1(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),device=s.st_dev,inode=s.st_ino,uid=s.st_uid,mode=384)

def installed(tmp_path,*,postrestore=False):
 now=datetime.now(timezone.utc);d=change(descriptor('restore'),issued_at=now-timedelta(seconds=5),expires_at=now+timedelta(seconds=3500),original_horizon=now+timedelta(seconds=3500));ca=write_pin(tmp_path/'ca',b'invented CA - no network use')
 def identity(old,n):
  url=f'host=localhost hostaddr=127.0.0.1 port=5432 dbname={old.database_name} user={old.session_role} sslmode=verify-full sslrootcert={ca.path}'
  return change(old,database_url=write_pin(tmp_path/f'url{n}',url.encode()),tls_ca=ca)
 bindings=tuple(change(b,sql_identity=identity(b.sql_identity,i)) for i,b in enumerate(d.purpose_bindings))
 d=change(d,purpose_bindings=bindings,current_control_source=identity(d.current_control_source,90))
 p=None;pp=None
 if postrestore:
  # Exact actual descriptor/claim metadata only; no SQL claim is manufactured.
  old,claim,p=profile(d)
  p=change(p,master_claimed_at=now-timedelta(seconds=2),original_phase_deadline=now+timedelta(seconds=3500),issued_at=now-timedelta(seconds=1),expires_at=now+timedelta(seconds=3400),original_horizon=now+timedelta(seconds=3500))
  p=change(p,purpose_bindings=tuple(change(b,sql_identity=identity(b.sql_identity,100+i)) for i,b in enumerate(p.purpose_bindings)))
  pp=write_pin(tmp_path/'postrestore.json',canonical_bytes(p.model_dump(mode='json')))
 dp=write_pin(tmp_path/'descriptor.json',canonical_bytes(d.model_dump(mode='json')))
 c=RecoveryStartupConfigV1(descriptor=dp,postrestore_binding=pp,issuer_actor=uid(80),reviewer_actor=uid(81))
 cp=write_pin(tmp_path/'startup.json',canonical_bytes(c.model_dump(mode='json')))
 settings=ProtectedRecoverySettingsV1(cp,expected_issuer_actor=uid(80),expected_reviewer_actor=uid(81))
 return settings,d,p

def test_actual_protected_settings_and_url_pin_are_reread(tmp_path):
 settings,d,_=installed(tmp_path)
 identity,url=settings.identity_v1('current-denials')
 assert identity==d.purpose_bindings[0].sql_identity and 'verify-full' in url
 Path(identity.database_url.path).write_bytes(b'host=foreign')
 with pytest.raises(PermissionError):settings.identity_v1('current-denials')

@pytest.mark.parametrize('part',['config','descriptor','ca','url'])
def test_each_actual_protected_file_drift_refuses_before_any_connection(tmp_path,monkeypatch,part):
 settings,d,_=installed(tmp_path)
 pins={'config':settings.pin,'descriptor':settings.current_v1()[0].descriptor,'ca':d.purpose_bindings[0].sql_identity.tls_ca,'url':d.purpose_bindings[0].sql_identity.database_url}
 calls=[];monkeypatch.setattr(psycopg,'connect',lambda *a,**kw:calls.append((a,kw)))
 Path(pins[part].path).write_bytes(b'tampered')
 with pytest.raises(PermissionError):settings.identity_v1('current-denials')
 assert calls==[]

@pytest.mark.parametrize('field,value',[('inode',1),('device',999),('uid',999),('mode',384)])
def test_protected_pointer_actual_tuple_cannot_be_borrowed(tmp_path,field,value):
 pin=write_pin(tmp_path/'file',b'actual invented retained bytes')
 if field=='mode':Path(pin.path).chmod(0o644)
 else:pin=change(pin,**{field:value})
 with pytest.raises(PermissionError):read_recovery_pin_v1(pin)

def test_symlink_same_bytes_and_noncanonical_json_do_not_authenticate_settings(tmp_path):
 pin=write_pin(tmp_path/'source',b'bytes');alias=tmp_path/'alias';alias.symlink_to(Path(pin.path))
 with pytest.raises(PermissionError):read_recovery_pin_v1(change(pin,path=str(alias)))
 settings,d,_=installed(tmp_path)
 # Byte-level pointer equality is necessary but a new caller-chosen issuer is
 # not an installed role or permission. No socket occurs during this refusal.
 with pytest.raises(PermissionError):ProtectedRecoverySettingsV1(settings.pin,expected_issuer_actor=uid(900),expected_reviewer_actor=uid(81))

def test_target_missing_profile_denies_without_reusing_source_role(tmp_path):
 settings,_,_=installed(tmp_path)
 with pytest.raises(PermissionError):RecoverySQLAuthorityV1(settings,'deny-only-target',target=True)


def test_postrestore_current_profile_pins_actual_separate_target_credentials(tmp_path):
 settings,d,p=installed(tmp_path,postrestore=True)
 source,_=settings.identity_v1('deny-only-target')
 target,_=settings.identity_v1('deny-only-target',target=True)
 assert source.physical()!=target.physical() and target==p.purpose_bindings[0].sql_identity
 pp=settings.current_v1()[0].postrestore_binding
 Path(pp.path).write_bytes(b'changed after startup')
 with pytest.raises(PermissionError):settings.identity_v1('deny-only-target',target=True)


def test_current_metadata_requires_actual_retained_claim_and_no_freshness_mint(tmp_path):
 settings,d,_=installed(tmp_path)
 now=datetime.now(timezone.utc)
 # Constructor date is descriptive. Actual authority is still the own TLS getter.
 claim=RecoveryClaimV1(operation_id=d.operation_id,phase='restore',descriptor_sha256=digest(d.model_dump(mode='json')),claimed_at=now-timedelta(seconds=1),original_phase_deadline=now+timedelta(seconds=60),fresh=False)
 raw=canonical_bytes(d.model_dump(mode='json'))
 c=RecoveryCurrentV1(admission_id=uid(700),operation_id=d.operation_id,phase_authority='deny-only-target',principal_id=d.purpose_bindings[1].principal_id,session_role=d.purpose_bindings[1].sql_identity.session_role,descriptor_bytes_hex=raw.hex(),descriptor_sha256=hashlib.sha256(raw).hexdigest(),postrestore_binding_bytes_hex=None,postrestore_binding_sha256=None,checked_at=now,valid_until=now+timedelta(seconds=10),original_horizon=now+timedelta(seconds=60),census=None,retained_claims=(claim,),imported_census_sha256s=())
 assert not c.retained_claims[0].fresh and not c.serving_authorized
 for bad in (change(claim,fresh=True),change(claim,operation_id=uid(999))):
  with pytest.raises(ValueError):change(c,retained_claims=(bad,))
 with pytest.raises(ValueError):change(c,imported_census_sha256s=(H,))


def test_no_original_request_context_means_zero_connections(tmp_path,monkeypatch):
 settings,_,_=installed(tmp_path);owner=RecoverySQLAuthorityV1(settings,'deny-only-target')
 calls=[];monkeypatch.setattr(psycopg,'connect',lambda *a,**kw:calls.append((a,kw)))
 with pytest.raises(PermissionError):owner.current_v1(deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
 assert calls==[]


def test_catalog_fingerprint_fixes_same_connection_context_before_query(monkeypatch):
 from types import SimpleNamespace
 import oracle_brain.operating_model.recovery_authority_v1 as owner
 class Recording:pass
 connection=Recording();deadline=datetime.now(timezone.utc)+timedelta(seconds=15);calls=[]
 monkeypatch.setattr(owner,'psycopg',SimpleNamespace(Connection=Recording))
 def execute(actual,original,query):
  calls.append((actual,original,query))
  return SimpleNamespace(fetchone=lambda:('pg_catalog, oracle2',) if len(calls)==1 else ({'actual':'catalog'},))
 monkeypatch.setattr(owner,'sql_execute_v1',execute)
 assert owner.recovery_catalog_fingerprint_v1(connection,deadline)==digest({'actual':'catalog'})
 assert calls==[(connection,deadline,"SELECT pg_catalog.set_config('search_path','pg_catalog, oracle2',true)"),(connection,deadline,owner._CATALOG_SQL_V1)]


@pytest.mark.parametrize('result',[None,('public',),('pg_catalog, oracle2','extra')])
def test_catalog_context_bad_readback_stops_before_catalog(monkeypatch,result):
 from types import SimpleNamespace
 import oracle_brain.operating_model.recovery_authority_v1 as owner
 class Recording:pass
 calls=[];monkeypatch.setattr(owner,'psycopg',SimpleNamespace(Connection=Recording))
 def execute(connection,deadline,query):
  calls.append(query);return SimpleNamespace(fetchone=lambda:result)
 monkeypatch.setattr(owner,'sql_execute_v1',execute)
 with pytest.raises(PermissionError,match='rendering context'):owner.recovery_catalog_fingerprint_v1(Recording(),datetime.now(timezone.utc))
 assert len(calls)==1 and calls[0].startswith('SELECT pg_catalog.set_config(')


def test_catalog_context_guard_failure_never_queries_or_falls_back(monkeypatch):
 from types import SimpleNamespace
 import oracle_brain.operating_model.recovery_authority_v1 as owner
 class Recording:pass
 calls=[];monkeypatch.setattr(owner,'psycopg',SimpleNamespace(Connection=Recording))
 def execute(connection,deadline,query):
  calls.append(query);raise PermissionError('original SQL fence expired')
 monkeypatch.setattr(owner,'sql_execute_v1',execute)
 with pytest.raises(PermissionError,match='original SQL fence'):owner.recovery_catalog_fingerprint_v1(Recording(),datetime.now(timezone.utc))
 assert len(calls)==1
 with pytest.raises(TypeError):owner.recovery_catalog_fingerprint_v1(object(),datetime.now(timezone.utc))
 assert len(calls)==1
