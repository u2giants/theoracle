"""Recording subprocess seams; no Docker, nativeSQL or custody authority proof."""
from datetime import datetime,timedelta,timezone
import json,time
import pytest
from oracle_brain.hosting import forward_recovery as native
from oracle_brain.operating_model.recovery_authority_v1 import RecoverySQLAuthorityV1
from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
from test_recovery_backup_custody_v1 import custody


def owner(monkeypatch,*,response=None):
 # Bypass construction ONLY in this explicitly recording-owner seam. Production
 # construction requires exact protected settings and actual own SQL readback.
 authority=object.__new__(RecoverySQLAuthorityV1);authority.target=False;authority.purpose='capture'
 d,p=custody();observed=[];reads=[]
 monkeypatch.setattr(RecoverySQLAuthorityV1,'custody_v1',lambda self,**kw:(reads.append('own-current-custody') or (b'actual protected seam bytes',p)))
 container=p.native_participants[0].source
 actual={'id':container.container_id,'image':'sha256:'+container.image_id,'name':'/'+container.container_name,'running':True}
 def execute(args,**kw):
  observed.append((args,kw));return response if response is not None else json.dumps(actual).encode()+b'\n'
 monkeypatch.setattr(native,'_bounded_docker_execution_v1',execute)
 return native._ReplacementNativeDockerV1(authority,deadline=datetime.now(timezone.utc)+timedelta(seconds=20)),observed,reads


def test_only_four_fixed_nonsecret_container_fields_are_requested(monkeypatch):
 o,calls,reads=owner(monkeypatch)
 with _request_fence_v1(time.monotonic()+20):result=o.inspect_participants_v1()
 assert len(result)==1 and len(reads)==3 and len(calls)==1
 args,kw=calls[0]
 assert args[:2]==['inspect','--format'] and args[2]==native._REPLACEMENT_CONTAINER_TEMPLATE_V1
 assert '.Config' not in args[2] and '.Env' not in args[2] and kw['data'] is None and kw['bound']==8192 and 0<kw['timeout']<=20
 assert result[0]['running'] is True

@pytest.mark.parametrize('raw',[b'{}\n',b'{}\n{}\n',b'{"id":1,"id":2}\n',b'{"Env":["secret"]}\n',b'{}',b'{"id":NaN}\n'])
def test_unknown_duplicate_secret_and_incomplete_inspection_output_refuses(monkeypatch,raw):
 o,calls,_=owner(monkeypatch,response=raw)
 with _request_fence_v1(time.monotonic()+20),pytest.raises(PermissionError):o.inspect_participants_v1()
 assert len(calls)==1


def test_missing_or_expired_original_fence_has_zero_native_effect(monkeypatch):
 o,calls,_=owner(monkeypatch)
 with pytest.raises(PermissionError):o.inspect_participants_v1()
 assert calls==[]
 with pytest.raises(PermissionError),_request_fence_v1(time.monotonic()-1):o.inspect_participants_v1()
 assert calls==[]


def test_native_inspector_cannot_accept_arbitrary_runner_or_container_selector(monkeypatch):
 o,calls,_=owner(monkeypatch)
 with pytest.raises(TypeError):o.inspect_participants_v1(container='foreign')
 with pytest.raises(PermissionError):native._ReplacementNativeDockerV1(lambda:True,deadline=datetime.now(timezone.utc))
 assert calls==[]


def test_tagged_native_location_refuses_host_pointer_or_missing_ancestor_tuple():
 from pydantic import ValidationError
 from test_recovery_contracts_v1 import change
 d,p=custody();c=p.native_participants[0].source;i=c.native_sql_identity
 with pytest.raises(ValidationError):change(i,location='host')
 with pytest.raises(ValidationError):change(i,ancestors=())
 with pytest.raises(PermissionError):change(p,native_participants=(change(p.native_participants[0],source=change(c,native_sql_identity=change(i,database_url=change(i.database_url,path='/host/secret')))),)).bind_descriptive_operation(d)


def test_actual_private_docker_file_bytes_use_installed_container_uid_not_host_uid():
 import io,tarfile,hashlib
 from test_recovery_contracts_v1 import change
 _,p=custody();pin=p.native_participants[0].source.service_file;raw=b'invented private service bytes'
 pin=change(pin,sha256=hashlib.sha256(raw).hexdigest(),uid=12345)
 out=io.BytesIO()
 with tarfile.open(fileobj=out,mode='w') as archive:
  member=tarfile.TarInfo(pin.path.rsplit('/',1)[1]);member.uid=12345;member.mode=0o600;member.size=len(raw);archive.addfile(member,io.BytesIO(raw))
 assert native._container_private_file_bytes_v1(out.getvalue(),pin)==raw
 for changed in (change(pin,uid=999),change(pin,sha256='b'*64),change(pin,path=pin.path+'foreign')):
  with pytest.raises(PermissionError):native._container_private_file_bytes_v1(out.getvalue(),changed)


def service_bytes():
 _,p=custody();container=p.native_participants[0].source;i=container.native_sql_identity
 fields={'host':i.host,'hostaddr':i.hostaddr,'port':str(i.port),'dbname':i.database_name,'user':i.session_role,'sslmode':'verify-full','sslrootcert':i.tls_ca.path,'password':'invented-no-real-credential'}
 raw=('[oracle_recovery_v1]\n'+''.join(k+'='+v+'\n' for k,v in fields.items())).encode()
 from psycopg.conninfo import make_conninfo
 return container,raw,make_conninfo(**dict(sorted(fields.items()))).encode()


def test_complete_private_service_matches_exact_native_tls_and_physical_selectors():
 c,raw,url=service_bytes()
 assert native._validate_native_service_bytes_v1(raw,url,c)=={'service_validated':True,'location':'container-local','credential_material_exported':False,'source_authenticated':False}

@pytest.mark.parametrize('mutation',[lambda x:x.replace(b'verify-full',b'require'),lambda x:x.replace(b'127.0.0.1',b'127.0.0.2'),lambda x:x+b'options=-c role=owner\n',lambda x:x+b'password=duplicate\n',lambda x:x+b'\n[other]\npassword=x\n',lambda x:x.replace(b'password=',b'sslkey='),lambda x:b'[DEFAULT]\nhost=x\n'+x])
def test_service_unknown_ambient_duplicate_foreign_and_unpinned_clientkey_refuse_without_secret_output(mutation):
 c,raw,url=service_bytes()
 with pytest.raises(PermissionError) as caught:native._validate_native_service_bytes_v1(mutation(raw),url,c)
 assert 'invented-no-real-credential' not in str(caught.value)


def service_reader(monkeypatch,attack=None):
 import io,tarfile,hashlib
 from test_recovery_contracts_v1 import change
 o,_,_=owner(monkeypatch);_,p=custody();container,service,url=service_bytes();ca=b'invented public CA bytes'
 i=container.native_sql_identity
 i=change(i,database_url=change(i.database_url,sha256=hashlib.sha256(url).hexdigest()),tls_ca=change(i.tls_ca,sha256=hashlib.sha256(ca).hexdigest()))
 container=change(container,service_file=change(container.service_file,sha256=hashlib.sha256(service).hexdigest()),native_sql_identity=i)
 p=change(p,native_participants=(change(p.native_participants[0],source=container),))
 monkeypatch.setattr(RecoverySQLAuthorityV1,'custody_v1',lambda *a,**kw:(b'protected owned seam bytes',p))
 actual={container.service_file.path:service,i.database_url.path:url,i.tls_ca.path:ca};calls=[];stats=0
 def execute(args,**kwargs):
  nonlocal stats
  calls.append((args,kwargs))
  if args[0]=='inspect':return json.dumps({'id':container.container_id,'image':'sha256:'+container.image_id,'name':'/'+container.container_name,'running':True}).encode()+b'\n'
  if args[0]=='exec':
   assert args[2:5]==['stat','--printf','%d:%i:%u:%a:%F\n'];stats+=1
   pins=[(v,'directory') for v in i.ancestors]+[(v,'regular file') for v in (container.service_file,i.database_url,i.tls_ca)]
   raw=''.join(f'{v.device}:{v.inode}:{v.uid}:{v.mode:o}:{kind}\n' for v,kind in pins).encode()
   if attack=='symlink' or (attack=='post-drift' and stats==2):raw=raw.replace(b'regular file',b'symbolic link',1)
   return raw
  assert args[0]=='cp' and args[2]=='-';path=args[1].split(':',1)[1];pin=next(v for v in (container.service_file,i.database_url,i.tls_ca) if v.path==path)
  data=actual[path]
  out=io.BytesIO()
  with tarfile.open(fileobj=out,mode='w') as archive:
   m=tarfile.TarInfo(path.rsplit('/',1)[1]);m.uid=pin.uid;m.mode=0o600;m.size=len(data);archive.addfile(m,io.BytesIO(data))
  return out.getvalue()
 monkeypatch.setattr(native,'_bounded_docker_execution_v1',execute)
 return o,calls


def test_connected_native_private_reader_uses_only_fixed_stat_copy_and_protected_pipes(monkeypatch):
 o,calls=service_reader(monkeypatch)
 with _request_fence_v1(time.monotonic()+20):result=o.validate_services_v1()
 assert len(result)==1 and result[0]['source_authenticated'] is False and result[0]['credential_material_exported'] is False
 assert [args[0] for args,_ in calls]==['inspect','exec','cp','cp','cp','exec']
 assert 'invented-no-real-credential' not in repr(calls) and 'invented-no-real-credential' not in repr(result)
 assert all(kwargs['data'] is None for _,kwargs in calls)

@pytest.mark.parametrize('attack',['symlink','post-drift'])
def test_actual_native_custody_refusal_withholds_service_result(monkeypatch,attack):
 o,calls=service_reader(monkeypatch,attack=attack)
 with _request_fence_v1(time.monotonic()+20),pytest.raises(PermissionError):o.validate_services_v1()
 assert sum(args[0]=='cp' for args,_ in calls)==(0 if attack=='symlink' else 3)


def physical_reader(monkeypatch,change=None):
 o,calls=service_reader(monkeypatch);old=native._bounded_docker_execution_v1
 def execute(args,**kwargs):
  if args[:2]!=['exec','-i']:return old(args,**kwargs)
  calls.append((args,kwargs))
  value={'system_identifier':'110','database_oid':10,'database_name':'db10','database_owner':'oracle2_admin','session_role':'recovery_owner','effective_role':'none','tls':True}
  if change:value.update(change)
  return json.dumps(value).encode()+b'\n'
 monkeypatch.setattr(native,'_bounded_docker_execution_v1',execute)
 return o,calls


def test_fixed_native_physical_readback_uses_exact_actual_session_tls_and_no_ambient_defaults(monkeypatch):
 o,calls=physical_reader(monkeypatch)
 with _request_fence_v1(time.monotonic()+20):result=o.verify_physical_identities_v1()
 assert len(result)==1 and result[0]['database_oid']==10 and result[0]['tls'] is True and not result[0]['serving_authorized']
 identity=[(args,kw) for args,kw in calls if args[:2]==['exec','-i']]
 assert len(identity)==1
 args,kw=identity[0]
 assert args[3:5]==['env','-i'] and 'PGCONNECT_TIMEOUT=2' in args and 'PGOPTIONS=-c statement_timeout=5000 -c lock_timeout=2000' in args
 assert args[-1]=='--dbname=service=oracle_recovery_v1' and kw['data']==native._REPLACEMENT_NATIVE_IDENTITY_SQL_V1
 assert b'password' not in kw['data'] and 'invented-no-real-credential' not in repr(calls)

@pytest.mark.parametrize('change',[{'system_identifier':'999'},{'database_oid':True},{'database_oid':11},{'database_name':'foreign'},{'database_owner':'foreign'},{'session_role':'foreign'},{'effective_role':'owner'},{'tls':False},{'tls':1},{'extra':'denied'}])
def test_physical_metadata_never_substitutes_foreign_target_or_unverified_tls(monkeypatch,change):
 o,calls=physical_reader(monkeypatch,change)
 with _request_fence_v1(time.monotonic()+20),pytest.raises(PermissionError):o.verify_physical_identities_v1()
 assert sum(args[:2]==['exec','-i'] for args,_ in calls)==1


def test_native_first_query_requires_original_connection_plus_statement_window(monkeypatch):
 o,calls=physical_reader(monkeypatch)
 o._deadline=datetime.now(timezone.utc)+timedelta(seconds=6)
 with _request_fence_v1(time.monotonic()+20),pytest.raises(PermissionError):o.verify_physical_identities_v1()
 assert not any(args[:2]==['exec','-i'] for args,_ in calls)


@pytest.mark.parametrize('change',[lambda v:v+b' password=duplicate',lambda v:v+b' ',lambda v:v+b'\n',lambda v:b'host=foreign '+v])
def test_private_conninfo_duplicate_or_normalized_bytes_never_hide_drift(change):
 c,service,url=service_bytes()
 with pytest.raises(PermissionError) as caught:native._validate_native_service_bytes_v1(service,change(url),c)
 assert 'invented-no-real-credential' not in str(caught.value)


def test_fresh_restore_uses_only_current_target_not_expired_old_capture_credentials():
 _,p=custody('restore')
 active=native._active_native_participants_v1(p)
 assert len(active)==1 and active[0][1]=='target' and active[0][2]==p.native_participants[0].target
 assert p.native_participants[0].source not in [v[2] for v in active]


def test_actual_recorded_native_full_inventory_is_bound_to_same_protected_pin(monkeypatch):
 from test_recovery_dump_catalog_v1 import catalog
 from test_recovery_contracts_v1 import change
 from oracle_brain.operating_model.contracts import digest
 from oracle_brain.operating_model.recovery_authority_v1 import _DUMP_CATALOG_SQL_V1
 o,calls=physical_reader(monkeypatch);_,p=o._authority.custody_v1(deadline=o._deadline)
 c=catalog();pin=digest(c)
 p=change(p,native_participants=(change(p.native_participants[0],source=change(p.native_participants[0].source,dump_inventory_sha256=pin)),))
 monkeypatch.setattr(RecoverySQLAuthorityV1,'custody_v1',lambda *a,**kw:(b'independently protected recording seam',p))
 prior=native._bounded_docker_execution_v1
 def execute(args,**kwargs):
  if kwargs.get('data')==(_DUMP_CATALOG_SQL_V1+';\n').encode():
   calls.append((args,kwargs));return json.dumps(c).encode()+b'\n'
  return prior(args,**kwargs)
 monkeypatch.setattr(native,'_bounded_docker_execution_v1',execute)
 with _request_fence_v1(time.monotonic()+20):result=o.verify_dump_inventories_v1()
 assert len(result)==1 and result[0]['actual_inventory_sha256']==pin and result[0]['tables']==('oracle2.events',)
 assert result[0]['capture_snapshot_verified'] is False and result[0]['serving_authorized'] is False
 assert sum(kw.get('data')==(_DUMP_CATALOG_SQL_V1+';\n').encode() for _,kw in calls)==1


def test_missing_inventory_pin_refuses_before_any_catalog_query(monkeypatch):
 from oracle_brain.operating_model.recovery_authority_v1 import _DUMP_CATALOG_SQL_V1
 o,calls=physical_reader(monkeypatch)
 with _request_fence_v1(time.monotonic()+20),pytest.raises(PermissionError):o.verify_dump_inventories_v1()
 assert not any(kw.get('data')==(_DUMP_CATALOG_SQL_V1+';\n').encode() for _,kw in calls)
