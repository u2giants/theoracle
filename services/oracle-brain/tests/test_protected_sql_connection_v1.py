"""One actual connection owner: original guards, no libpq environment target."""
from datetime import datetime,timedelta,timezone
import os
import pytest
from oracle_brain.operating_model import protected_sql_connection_v1 as owner
from oracle_brain.operating_model import request_deadline_v1 as window

URL='host=127.0.0.1 port=55432 dbname=invented user=invented password=invented-only sslmode=verify-full sslrootcert=/invented/ca.pem'

@pytest.fixture
def recorded(monkeypatch):
 for key in tuple(os.environ):
  if key.startswith('PG'):monkeypatch.delenv(key)
 tick=[10.];monkeypatch.setattr(window.time,'monotonic',lambda:tick[0])
 class Connection:
  def __init__(self):self.sent=[];self.closed=False;self.on_execute=None;self.on_close=None
  def __enter__(self):return self
  def execute(self,*args):
   self.sent.append(args)
   if self.on_execute:self.on_execute()
   return self
  def __exit__(self,kind,error,tb):
   self.closed=True
   if self.on_close:self.on_close()
 c=Connection();calls=[]
 def connect(*args,**kwargs):calls.append((args,kwargs));return c
 monkeypatch.setattr(owner.psycopg,'connect',connect)
 return c,calls,tick

@pytest.mark.parametrize('key',['PGHOSTADDR','PGSERVICE','PGSERVICEFILE','PGOPTIONS','PGPASSWORD','PGUNKNOWN'])
def test_environment_refusal_precedes_socket(recorded,monkeypatch,key):
 c,calls,tick=recorded;monkeypatch.setenv(key,'invented')
 with window._request_fence_v1(30.),pytest.raises(PermissionError,match='environment'):
  with owner._connection_v1(URL,datetime.now(timezone.utc)+timedelta(seconds=20)):pass
 assert not calls and not c.sent

@pytest.mark.parametrize('field',['host','port','dbname','user','password','sslmode','sslrootcert'])
def test_incomplete_target_refuses_before_socket(recorded,field):
 c,calls,tick=recorded;url=' '.join(x for x in URL.split() if not x.startswith(field+'='))
 with window._request_fence_v1(30.),pytest.raises(PermissionError):
  with owner._connection_v1(url,datetime.now(timezone.utc)+timedelta(seconds=20)):pass
 assert calls==[]

@pytest.mark.parametrize('url',[URL.replace('/invented/ca.pem','relative.pem'),URL.replace('127.0.0.1','localhost'),URL+' hostaddr=127.000.0.1',URL+' options=-cx=y'])
def test_no_dns_relative_ca_noncanonical_or_extra_option(recorded,url):
 c,calls,tick=recorded
 with window._request_fence_v1(30.),pytest.raises(PermissionError):
  with owner._connection_v1(url,datetime.now(timezone.utc)+timedelta(seconds=20)):pass
 assert calls==[]

def test_explicit_target_and_startup_bounds_and_actual_close(recorded):
 c,calls,tick=recorded
 with window._request_fence_v1(30.):
  with owner._connection_v1(URL,datetime.now(timezone.utc)+timedelta(seconds=20)) as actual:
   assert actual is c and not c.closed
   owner.require_protected_sql_window_v1(c)
  assert c.closed
 kwargs=calls[0][1]
 assert {key:kwargs[key] for key in ('host','hostaddr','port','dbname','user','sslmode','sslrootcert')}==dict(host='127.0.0.1',hostaddr='127.0.0.1',port='55432',dbname='invented',user='invented',sslmode='verify-full',sslrootcert='/invented/ca.pem')
 assert kwargs['connect_timeout']==2 and kwargs['autocommit'] is True
 assert kwargs['options']=='-c statement_timeout=2000ms -c lock_timeout=2000ms'
 assert len(c.sent)==1 and c.sent[0][0]=='BEGIN ISOLATION LEVEL READ COMMITTED'

@pytest.mark.parametrize('phase',['connect','sql','commit','close'])
def test_no_late_success_or_subsequent_send(recorded,monkeypatch,phase):
 c,calls,tick=recorded;deadline=datetime.now(timezone.utc)+timedelta(seconds=20)
 if phase=='connect':
  def connect(*a,**kw):calls.append((a,kw));tick[0]=30.;return c
  monkeypatch.setattr(owner.psycopg,'connect',connect)
 if phase=='sql':c.on_execute=lambda:tick.__setitem__(0,30.)
 if phase=='close':c.on_close=lambda:tick.__setitem__(0,30.)
 with window._request_fence_v1(30.),pytest.raises(PermissionError):
  with owner._connection_v1(URL,deadline):
   if phase=='commit':tick[0]=28.1
 assert c.closed and len(calls)==1
 assert len(c.sent)==(0 if phase=='connect' else 1)

def test_close_failure_is_not_success_and_not_retried(recorded):
 c,calls,tick=recorded
 def fail():raise OSError('invented close ACK loss')
 c.on_close=fail
 with window._request_fence_v1(30.),pytest.raises(OSError,match='ACK loss'):
  with owner._connection_v1(URL,datetime.now(timezone.utc)+timedelta(seconds=20)):pass
 assert len(calls)==1 and c.closed

def test_short_window_refuses_before_socket(recorded):
 c,calls,tick=recorded
 with window._request_fence_v1(11.9),pytest.raises(PermissionError,match='two-second'):
  with owner._connection_v1(URL,datetime.now(timezone.utc)+timedelta(seconds=20)):pass
 assert calls==[]

def test_uncaptured_legacy_guard_stays_optional_but_captured_socket_never_borrowed(recorded):
 c,calls,tick=recorded
 owner.require_protected_sql_window_v1(c)
 with window._request_fence_v1(30.),pytest.raises(PermissionError,match='prearmed'):
  owner.require_protected_sql_window_v1(c)
 assert not calls and not c.sent


def test_resolver_constructor_and_each_optional_shared_getter_close_before_callback(recorded,monkeypatch):
 from uuid import uuid4
 from oracle_brain.operating_model.authority_adapter import ProcessingSourceResolver,ProcessingSourceBinding
 c,calls,tick=recorded;connections=[]
 def connect(*args,**kwargs):
  fresh=type(c)();connections.append(fresh);calls.append((args,kwargs));return fresh
 monkeypatch.setattr(owner.psycopg,'connect',connect)
 # This pure recording DB checks lifecycle only; catalog authority is separately
 # actual SQL tested. No fixture role or appointment is being granted here.
 def check(self,connection):
  owner.require_protected_sql_window_v1(connection)
  window.sql_execute_current_v1(connection,'SELECT recorded_catalog_check')
 monkeypatch.setattr(ProcessingSourceResolver,'_check',check)
 binding=ProcessingSourceBinding(runtime_hash='a'*64,source_registry_hash='b'*64,expected_owner_role='fixture_owner',expected_session_role='fixture_compiler',principal=uuid4(),profile='candidate-compiler',expires_at=datetime.now(timezone.utc)+timedelta(seconds=20))
 with window._request_fence_v1(30.):
  resolver=ProcessingSourceResolver(URL,binding=binding)
  assert len(connections)==1 and connections[0].closed
  with resolver.shared_connection() as optional:
   assert optional is None
   for _ in range(2):
    with resolver._connection(optional) as actual:resolver._check(actual)
    assert all(conn.closed for conn in connections)
    # Actual callback boundary holds no retained or idle socket.
    assert getattr(resolver._shared,'conn',None) is None
  assert len(connections)==3 and all(conn.closed for conn in connections)


def test_resolver_protected_rejects_preheld_legacy_connection_before_any_send(recorded):
 from types import SimpleNamespace
 from oracle_brain.operating_model.authority_adapter import ProcessingSourceResolver
 c,calls,tick=recorded;resolver=object.__new__(ProcessingSourceResolver);resolver._shared=SimpleNamespace(conn=c)
 with window._request_fence_v1(30.):
  with pytest.raises(PermissionError,match='legacy'):
   with resolver.shared_connection():pass
  with pytest.raises(PermissionError,match='legacy'):
   with resolver._connection():pass
  with pytest.raises(PermissionError,match='prearmed'):
   with resolver._connection(c):pass
 assert not calls and not c.sent


def test_legacy_shared_pool_retained_only_outside_original_fence(recorded):
 from types import SimpleNamespace
 from oracle_brain.operating_model.authority_adapter import ProcessingSourceResolver
 c,calls,tick=recorded;resolver=object.__new__(ProcessingSourceResolver);resolver._shared=SimpleNamespace(conn=None);resolver.url='legacy-existing-url'
 with resolver.shared_connection() as actual:
  assert actual is c and not c.closed
  with resolver.shared_connection() as nested:assert nested is c
 assert c.closed and resolver._shared.conn is None
 assert calls==[(('legacy-existing-url',),{'connect_timeout':5,'autocommit':True})]

@pytest.mark.parametrize('fault',[None,'private_late','hook_late','write_close','fresh_loss','fresh_revoke','fresh_close'])
def test_compiler_preserves_atomic_hook_and_postwrite_unknown_without_resend(recorded,monkeypatch,fault):
 from uuid import uuid4
 from types import SimpleNamespace
 from oracle_brain.operating_model.processing_ledger import ProcessingCompilerLedger,ProcessingCommitUnknown
 from oracle_brain.operating_model.contracts import SourceRef,digest,ArtifactManifest
 c,calls,tick=recorded;connections=[];state={'manifest':None,'writes':0,'hook':False,'fresh':0}
 workspace=uuid4();ref=SourceRef(workspace_id=workspace,source_id=uuid4(),revision=1,original_sha256='a'*64,reading_sha256='b'*64,parser_id='c'*64)
 class Result:
  def __init__(self,row):self.row=row
  def fetchone(self):return self.row
 class Actual(type(c)):
  def execute(self,sql,params=None):
   self.sent.append((sql,params))
   if 'commit_processing_candidate' in sql:
    state['manifest']=ArtifactManifest.model_validate_json(__import__('json').dumps(params[0].obj));state['writes']+=1
    return Result((state['manifest'].model_dump(mode='json'),))
   if sql=='SELECT session_user':return Result(('fixture_compiler',))
   if 'clock_timestamp()<' in sql:return Result((True,))
   return Result((True,))
  def __exit__(self,*args):
   self.closed=True
   if fault=='write_close' and len(connections)==1:raise OSError('write close lost')
   if fault=='fresh_close' and len(connections)==2:raise OSError('fresh close lost')
 def connect(*args,**kwargs):
  calls.append((args,kwargs))
  if fault=='fresh_loss' and len(connections)==1:raise OSError('fresh connection lost')
  result=Actual();connections.append(result);return result
 monkeypatch.setattr(owner.psycopg,'connect',connect)
 def check(connection):owner.require_protected_sql_window_v1(connection)
 expiry=datetime.now(timezone.utc)+timedelta(seconds=20)
 def metadata(*args,connection=None):
  if connection is not None:
   assert not connection.closed and state['hook'];return state['manifest'],(ref,)
  assert connections[0].closed
  state['fresh']+=1
  if fault=='fresh_revoke':raise PermissionError('current source revoked after commit')
  with owner._connection_v1(URL,expiry) as fresh:check(fresh)
  return state['manifest'],(ref,)
 source=SimpleNamespace(binding=SimpleNamespace(runtime_hash='d'*64,source_registry_hash='e'*64,expires_at=expiry,expected_session_role='fixture_compiler'),_check=check,artifact_metadata=metadata)
 ledger=object.__new__(ProcessingCompilerLedger);ledger.url=URL;ledger.principal=uuid4();ledger.processing_sources=source
 ledger.clock=lambda:datetime.now(timezone.utc);ledger.processing_extraction_guard=None
 ledger.authorize_refs=lambda *a:{ref:SimpleNamespace(model_dump=lambda **kwargs:{})}
 ledger.validate_reported_payload=lambda *a:None
 class Blobs:
  def put(self,selected,payload):
   assert selected==workspace and not connections
   if fault=='private_late':tick[0]=30.
   seal=digest(payload);return f'operating-model/{workspace}/{seal}.json',seal
 ledger.blobs=Blobs()
 def hook():
  assert state['writes']==1 and len(connections)==1 and not connections[0].closed
  state['hook']=True
  if fault=='hook_late':tick[0]=30.
 kwargs=dict(workspace_id=workspace,artifact_id=uuid4(),version=1,kind='processing_extraction_v1',payload={'source_refs':[ref.model_dump(mode='json')]},refs=(ref,),permission_digest='f'*64,compiler_digest='d'*64,before_commit=hook)
 with window._request_fence_v1(30.):
  if fault:
   expected=PermissionError if fault=='private_late' else ProcessingCommitUnknown
   with pytest.raises(expected):ledger.persist(**kwargs)
  else:
   result=ledger.persist(**kwargs);assert result==state['manifest']
 assert state['writes']==(0 if fault=='private_late' else 1)
 assert state['hook'] is (fault!='private_late')
 assert all(conn.closed for conn in connections)
 if fault=='private_late':assert calls==[]
 else:assert len(connections)<=2


def test_explicit_empty_password_cannot_consume_password_file(recorded):
 c,calls,tick=recorded
 with window._request_fence_v1(30.),pytest.raises(PermissionError):
  with owner._connection_v1(URL.replace('password=invented-only', "password=''"),datetime.now(timezone.utc)+timedelta(seconds=20)):pass
 assert calls==[] and c.sent==[]
