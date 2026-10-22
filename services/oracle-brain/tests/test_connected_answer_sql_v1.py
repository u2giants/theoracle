"""Actual owned SQL lease/ACK/history controls; synthetic records are not D proof."""
from datetime import datetime,timezone,timedelta
from uuid import uuid4
import hashlib,time
from dataclasses import replace
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.consolidated_delivery_v1 import ConsolidatedReadDeliveryV1,DELIVERY_SIGNATURE,DELIVERY_FUNCTIONS
from oracle_brain.operating_model.consolidation_authority_v1 import ConsolidationAuthorityV1
from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
from test_consolidation_sql_v1 import processing,revision,call_revision,history_actor,adapter,RUNTIME,REGISTRY


def acknowledge(f,m,*,lease_seconds=30):
 with psycopg.connect(f['url']) as c:
  c.execute("SET LOCAL statement_timeout='5s'")
  lease=c.execute('SELECT oracle2.lease_processing_projection(%s,%s,%s,%s)',(f['workspace'],RUNTIME,REGISTRY,lease_seconds)).fetchone()[0]
 assert lease is not None and lease['assertion_id']==str(m.artifact_id)
 body=dict(schema_version=3,event_id=lease['event_id'],workspace_id=str(m.workspace_id),artifact_id=str(m.artifact_id),version=m.version,
  content_hash=m.content_hash,source_digest=m.source_digest,permission_digest=m.permission_digest,
  graph_name=f'oracle_processing_v1_{m.workspace_id.hex}_{m.artifact_id.hex}_{m.version}_'+uuid4().hex,
  record_digest='b'*64,sdk_version='1.4.0',projector_id='invented-canonical-ACK-only-no-graph-claim',
  lease_role=f['login'],lease_token=lease['lease_token'],lease_attempt=lease['attempts'],lease_until=lease['lease_until'],
  projection_schema='qualified-evidence-projection-v1',projection_digest='d'*64,embedding_protocol='paid-sdk-embedding-v3',
  **{key:'e'*64 for key in ('embedding_inventory_hash','embedding_context_hash','embedding_native_receipt_hash','embedding_wire_hash','embedding_commit_hash','embedding_vectors_hash','embedding_coverage_hash')})
 with psycopg.connect(f['url']) as c:
  result=c.execute('SELECT oracle2.ack_processing_projection(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
   (lease['event_id'],f['workspace'],lease['lease_token'],lease['attempts'],Jsonb(body),'c'*64,RUNTIME,REGISTRY,datetime.now(timezone.utc)+timedelta(seconds=20))).fetchone()[0]
 assert result['receipt']==body
 return body


def own_history(admin,f,*,principal=None):
 h=history_actor(admin,f,principal=principal)
 # NEW installed recipient URL explicitly pins the exact numeric address; the
 # canonical parent worker URL/allowed fields remain unchanged.
 target=psycopg.conninfo.conninfo_to_dict(h['url'])
 h['url']=psycopg.conninfo.make_conninfo(h['url'],hostaddr=target['host'])
 with psycopg.connect(admin) as c:
  c.execute(sql.SQL('GRANT EXECUTE ON FUNCTION oracle2.'+DELIVERY_SIGNATURE+' TO {}').format(sql.Identifier(h['login'])))
  pins=tuple(c.execute("SELECT proname,encode(sha256(convert_to(prosrc,'UTF8')),'hex') FROM pg_proc WHERE oid=to_regprocedure(%s)",('oracle2.'+sig,)).fetchone() for sig in DELIVERY_FUNCTIONS)
 original=adapter(admin,f,h)
 authority=ConsolidationAuthorityV1(h['url'],binding=original.binding,delivery_capability_body_hashes=pins)
 return h,authority


def delivery(h,m,*,valid_at=None,known_at=None):
 with psycopg.connect(h['url']) as c:
  c.execute("SET LOCAL statement_timeout='5s'")
  return c.execute('SELECT oracle2.hosting_consolidated_projection_delivery_v1(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
   (m.artifact_id,m.version,valid_at,known_at,h['aid'],RUNTIME,REGISTRY,'f'*64,datetime.now(timezone.utc)+timedelta(seconds=15))).fetchone()[0]


def test_actual_missing_ACK_refuses_then_same_current_and_historical_receipt(admin_url,processing,tmp_path):
 f=processing();aid,m,args,_=revision(admin_url,f,tmp_path);committed=call_revision(f,aid,args);h,_=own_history(admin_url,f)
 known=datetime.fromisoformat(committed['recordedAt'])
 with pytest.raises(psycopg.errors.InsufficientPrivilege):delivery(h,m,valid_at=known,known_at=known)
 receipt=acknowledge(f,m)
 current=ConsolidatedReadDeliveryV1.model_validate_json(canonical_bytes(delivery(h,m)))
 historical=ConsolidatedReadDeliveryV1.model_validate_json(canonical_bytes(delivery(h,m,valid_at=known,known_at=known)))
 assert current.retained_receipt.model_dump(mode='json')==historical.retained_receipt.model_dump(mode='json')==receipt
 assert current.business_decisions_as_of==historical.business_decisions_as_of==()
 assert historical.known_at==known and historical.retained_receipt.lease_until==receipt['lease_until']
 assert current.retained_receipt_body_sha256==digest(receipt)


@pytest.mark.parametrize('damage',['history-leaf','source-read','source-history','admission','withdrawal','foreign-version','future-known'])
def test_actual_current_retained_permissions_and_exact_time_required(admin_url,processing,tmp_path,damage):
 f=processing();aid,m,args,_=revision(admin_url,f,tmp_path);committed=call_revision(f,aid,args);h,_=own_history(admin_url,f);acknowledge(f,m)
 known=datetime.fromisoformat(committed['recordedAt'])
 if damage=='foreign-version':m=m.model_copy(update={'version':m.version+1})
 elif damage=='future-known':known=datetime.now(timezone.utc)+timedelta(days=1)
 else:
  with psycopg.connect(admin_url) as c:
   if damage=='admission':c.execute('INSERT INTO oracle2.processing_model_admission_revocations_v1 VALUES(%s,clock_timestamp())',(h['aid'],))
   elif damage=='withdrawal':c.execute("INSERT INTO oracle2.source_original_withdrawals_v1(event_id,workspace_id,source_id,revision,original_sha256,principal_id,session_role,runtime_hash,reason,idempotency_key,request_sha256) VALUES(%s,%s,%s,1,%s,%s,%s,%s,'invented withdrawal',%s,%s)",(uuid4(),f['workspace'],f['source'],h['ref'].original_sha256,h['actor'],h['login'],RUNTIME,uuid4(),'a'*64))
   else:
    leaf='processing-history' if damage=='history-leaf' else 'source-read:'+str(f['source']) if damage=='source-read' else 'source-history:'+str(f['source'])+':1'
    c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE workspace_id=%s AND actor_id=%s AND scope=%s',(f['workspace'],h['actor'],leaf))
 with pytest.raises(psycopg.Error):delivery(h,m,valid_at=known,known_at=known)


def test_actual_consumer_catalog_pins_and_single_original_fence(admin_url,processing,tmp_path,monkeypatch):
 f=processing();aid,m,args,_=revision(admin_url,f,tmp_path);committed=call_revision(f,aid,args);h,authority=own_history(admin_url,f);acknowledge(f,m)
 known=datetime.fromisoformat(committed['recordedAt'])
 with _request_fence_v1(float(time.monotonic()+20)):
  value=authority.projection_delivery_v1(m.artifact_id,m.version,deadline=datetime.now(timezone.utc)+timedelta(seconds=10),valid_at=known,known_at=known)
  assert value.model_content_hash==m.content_hash
 with pytest.raises(PermissionError):authority.projection_delivery_v1(m.artifact_id,m.version,deadline=datetime.now(timezone.utc)+timedelta(seconds=10),valid_at=known,known_at=known)


def test_two_actual_recipients_do_not_change_canonical_catalog_or_share_revocation(admin_url,processing,tmp_path):
 from dev.oracle2.test_canonical_schema import _catalog
 f=processing();aid,m,args,_=revision(admin_url,f,tmp_path);committed=call_revision(f,aid,args);acknowledge(f,m)
 with psycopg.connect(admin_url) as c:before=_catalog(c)
 h1,a1=own_history(admin_url,f)
 with psycopg.connect(admin_url) as c:after_first=_catalog(c)
 h2,a2=own_history(admin_url,f)
 with psycopg.connect(admin_url) as c:assert _catalog(c)==before==after_first
 known=datetime.fromisoformat(committed['recordedAt'])
 with _request_fence_v1(float(time.monotonic()+20)):
  for a in (a1,a2):assert a.projection_delivery_v1(m.artifact_id,m.version,deadline=datetime.now(timezone.utc)+timedelta(seconds=10),valid_at=known,known_at=known)
 with psycopg.connect(admin_url) as c:c.execute('INSERT INTO oracle2.processing_model_admission_revocations_v1 VALUES(%s,clock_timestamp())',(h1['aid'],))
 with _request_fence_v1(float(time.monotonic()+20)):
  with pytest.raises(psycopg.errors.InsufficientPrivilege):a1.projection_delivery_v1(m.artifact_id,m.version,deadline=datetime.now(timezone.utc)+timedelta(seconds=10),valid_at=known,known_at=known)
  assert a2.projection_delivery_v1(m.artifact_id,m.version,deadline=datetime.now(timezone.utc)+timedelta(seconds=10),valid_at=known,known_at=known)


@pytest.mark.parametrize('damage',['PUBLIC','group','grant-option','createdb','membership'])
def test_canonical_and_actual_consumer_reject_unsafe_cumulative_getter_ACL(admin_url,processing,tmp_path,damage):
 from dev.oracle2.test_canonical_schema import _catalog
 f=processing();aid,m,args,_=revision(admin_url,f,tmp_path);committed=call_revision(f,aid,args);acknowledge(f,m);h,authority=own_history(admin_url,f)
 role='bad_s09_'+uuid4().hex[:10];target='PUBLIC' if damage=='PUBLIC' else role
 with psycopg.connect(admin_url) as c:
  if damage!='PUBLIC':
   c.execute(sql.SQL('CREATE ROLE {} '+('NOLOGIN' if damage=='group' else 'LOGIN')+(' CREATEDB' if damage=='createdb' else '')).format(sql.Identifier(role)))
   if damage=='membership':c.execute(sql.SQL('GRANT pg_monitor TO {}').format(sql.Identifier(role)))
  grant=sql.SQL('GRANT EXECUTE ON FUNCTION oracle2.'+DELIVERY_SIGNATURE+' TO ')+ (sql.SQL('PUBLIC') if damage=='PUBLIC' else sql.Identifier(role))
  if damage=='grant-option':grant+=sql.SQL(' WITH GRANT OPTION')
  c.execute(grant)
 try:
  with psycopg.connect(admin_url) as c:
   with pytest.raises(PermissionError):_catalog(c)
  known=datetime.fromisoformat(committed['recordedAt'])
  with _request_fence_v1(float(time.monotonic()+20)):
   with pytest.raises(PermissionError):authority.projection_delivery_v1(m.artifact_id,m.version,deadline=datetime.now(timezone.utc)+timedelta(seconds=10),valid_at=known,known_at=known)
 finally:
  with psycopg.connect(admin_url) as c:c.execute(sql.SQL('REVOKE ALL ON FUNCTION oracle2.'+DELIVERY_SIGNATURE+' FROM ')+(sql.SQL('PUBLIC') if damage=='PUBLIC' else sql.Identifier(role)))


@pytest.mark.parametrize('damage',['body','owner'])
def test_actual_canonical_receipt_and_consumer_detect_getter_body_owner_drift(admin_url,processing,tmp_path,damage):
 from dev.oracle2.test_canonical_schema import assert_canonical_test_schema
 f=processing();aid,m,args,_=revision(admin_url,f,tmp_path);call_revision(f,aid,args);acknowledge(f,m);h,authority=own_history(admin_url,f)
 role='s09_drift_'+uuid4().hex[:10]
 with psycopg.connect(admin_url) as c:
  definition,body,owner=c.execute('SELECT pg_get_functiondef(oid),prosrc,pg_get_userbyid(proowner) FROM pg_proc WHERE oid=to_regprocedure(%s)',('oracle2.'+DELIVERY_SIGNATURE,)).fetchone()
  assert_canonical_test_schema(c,admin_url)
  if damage=='body':
   assert definition.count(body)==1
   c.execute(definition.replace(body,body+'\n-- invented body drift must not renew the retained proof\n',1))
  else:
   c.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
   c.execute(sql.SQL('ALTER FUNCTION oracle2.'+DELIVERY_SIGNATURE+' OWNER TO {}').format(sql.Identifier(role)))
 try:
  with psycopg.connect(admin_url) as c:
   with pytest.raises(PermissionError):assert_canonical_test_schema(c,admin_url)
  with _request_fence_v1(float(time.monotonic()+20)):
   with pytest.raises(PermissionError):authority.projection_delivery_v1(m.artifact_id,m.version,deadline=datetime.now(timezone.utc)+timedelta(seconds=10))
 finally:
  with psycopg.connect(admin_url) as c:
   if damage=='body':c.execute(definition)
   else:
    c.execute(sql.SQL('ALTER FUNCTION oracle2.'+DELIVERY_SIGNATURE+' OWNER TO {}').format(sql.Identifier(owner)))
    c.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))
  with psycopg.connect(admin_url) as c:assert_canonical_test_schema(c,admin_url)


def test_original_subtwo_second_fence_refuses_before_any_connection(monkeypatch):
 from oracle_brain.operating_model import consolidation_authority_v1 as owner
 monkeypatch.setattr(owner.psycopg,'connect',lambda *a,**kw:pytest.fail('short original window opened a connection'))
 with _request_fence_v1(float(time.monotonic()+1.5)):
  with pytest.raises(PermissionError):
   with owner._connection_v1('host=sql.invalid hostaddr=127.0.0.1 port=5432 dbname=invented user=invented sslmode=verify-full sslrootcert=/invented',datetime.now(timezone.utc)+timedelta(seconds=10)):pass


def test_actual_missing_captured_window_is_denied_but_legacy_source_API_retained(admin_url,processing,tmp_path):
 from test_source_processing_qualification import resolver
 f=processing();aid,m,args,_=revision(admin_url,f,tmp_path);call_revision(f,aid,args);h,authority=own_history(admin_url,f)
 source=resolver(f)
 with psycopg.connect(f['url']) as c:source._check(c)
 # Same REAL TLS connection/role remains required; an arbitrary current
 # connection cannot masquerade as prearmed merely by supplying a deadline.
 with psycopg.connect(h['url']) as c:
  with pytest.raises(PermissionError,match='prearmed'):
   authority._check(c,datetime.now(timezone.utc)+timedelta(seconds=10))


def test_actual_guarded_explicit_BEGIN_and_one_COMMIT_keep_same_connection(admin_url,processing,tmp_path,monkeypatch):
 from oracle_brain.operating_model.consolidation_authority_v1 import _connection_v1,_execute_v1
 f=processing();aid,m,args,_=revision(admin_url,f,tmp_path);call_revision(f,aid,args);h,_=own_history(admin_url,f)
 execute=psycopg.Connection.execute;command=psycopg.Connection._exec_command;queries=[];commands=[]
 def record_query(c,q,*a,**kw):queries.append(str(q));return execute(c,q,*a,**kw)
 def record_command(c,q,*a,**kw):
  commands.append(q.decode() if isinstance(q,bytes) else str(q))
  return (yield from command(c,q,*a,**kw))
 monkeypatch.setattr(psycopg.Connection,'execute',record_query);monkeypatch.setattr(psycopg.Connection,'_exec_command',record_command)
 deadline=datetime.now(timezone.utc)+timedelta(seconds=10)
 with _request_fence_v1(float(time.monotonic()+10)):
  with _connection_v1(h['url'],deadline) as c:
   assert type(c) is psycopg.Connection and c.autocommit is True
   assert _execute_v1(c,deadline,"SELECT current_setting('transaction_isolation')").fetchone()==('read committed',)
 assert c.closed
 assert queries==['BEGIN ISOLATION LEVEL READ COMMITTED',"SELECT current_setting('transaction_isolation')"]
 assert commands==['COMMIT']


def test_actual_connect_finishing_after_original_fence_never_sends_BEGIN(admin_url,processing,tmp_path,monkeypatch):
 from oracle_brain.operating_model import consolidation_authority_v1 as owner,request_deadline_v1 as core
 f=processing();aid,m,args,_=revision(admin_url,f,tmp_path);call_revision(f,aid,args);h,_=own_history(admin_url,f)
 connect=psycopg.connect;execute=psycopg.Connection.execute;clock=time.monotonic;offset=[0.];connections=[];queries=[]
 monkeypatch.setattr(core.time,'monotonic',lambda:clock()+offset[0])
 def late_connect(*a,**kw):
  c=connect(*a,**kw);connections.append(c);offset[0]=100.;return c
 def observed(c,*a,**kw):queries.append(a[0]);return execute(c,*a,**kw)
 monkeypatch.setattr(owner.psycopg,'connect',late_connect);monkeypatch.setattr(psycopg.Connection,'execute',observed)
 with _request_fence_v1(float(clock()+10)):
  with pytest.raises(PermissionError,match='elapsed'):
   with owner._connection_v1(h['url'],datetime.now(timezone.utc)+timedelta(seconds=10)):pytest.fail('expired connection yielded')
 assert len(connections)==1 and connections[0].closed and queries==[]


def test_actual_first_SQL_is_prearmed_before_any_catalog_read(admin_url,processing,tmp_path):
 from oracle_brain.operating_model.consolidation_authority_v1 import _connection_v1
 f=processing();aid,m,args,_=revision(admin_url,f,tmp_path);call_revision(f,aid,args);h,_=own_history(admin_url,f)
 start=time.monotonic()
 with _request_fence_v1(float(start+3)):
  with pytest.raises(psycopg.errors.QueryCanceled):
   with _connection_v1(h['url'],datetime.now(timezone.utc)+timedelta(seconds=3)) as c:
    c.execute('SELECT pg_sleep(3)')
 assert time.monotonic()-start<2.5


@pytest.mark.parametrize('stage',['catalog','setter'])
def test_actual_later_SQL_stall_is_cancelled_under_existing_bound(admin_url,processing,tmp_path,monkeypatch,stage):
 from oracle_brain.operating_model.consolidation_authority_v1 import _connection_v1,_execute_v1
 from oracle_brain.operating_model.request_deadline_v1 import sql_rearm_v1
 f=processing();aid,m,args,_=revision(admin_url,f,tmp_path);call_revision(f,aid,args);h,_=own_history(admin_url,f)
 original=psycopg.Connection.execute;sent=[]
 def observed(c,query,*a,**kw):
  sent.append(str(query))
  if stage=='setter' and str(query).startswith("SELECT pg_catalog.set_config('statement_timeout'"):
   # Actual server stall at the fixed setter boundary, under the OLD timeout.
   # No fabricated successful setter/receipt and no retry after cancellation.
   original(c,'SELECT pg_sleep(3)')
  return original(c,query,*a,**kw)
 monkeypatch.setattr(psycopg.Connection,'execute',observed)
 start=time.monotonic();connection=None
 with _request_fence_v1(float(start+3)):
  with pytest.raises(psycopg.errors.QueryCanceled):
   with _connection_v1(h['url'],datetime.now(timezone.utc)+timedelta(seconds=3)) as c:
    connection=c;_execute_v1(c,datetime.now(timezone.utc)+timedelta(seconds=2.9),'SELECT current_user')
    deadline=datetime.now(timezone.utc)+timedelta(seconds=2.5)
    if stage=='setter':sql_rearm_v1(c,deadline,timeout_ms=100)
    else:_execute_v1(c,deadline,'SELECT pg_sleep(3)')
 assert time.monotonic()-start<2.5
 assert connection.closed
 assert sent[0]=='BEGIN ISOLATION LEVEL READ COMMITTED' and len(sent)==3


@pytest.mark.parametrize('stage',['catalog','setter'])
def test_actual_shortened_window_refuses_later_SQL_before_send_and_closes(admin_url,processing,tmp_path,monkeypatch,stage):
 from oracle_brain.operating_model.consolidation_authority_v1 import _connection_v1,_execute_v1
 from oracle_brain.operating_model.request_deadline_v1 import sql_rearm_v1
 f=processing();aid,m,args,_=revision(admin_url,f,tmp_path);call_revision(f,aid,args);h,_=own_history(admin_url,f)
 original=psycopg.Connection.execute;sent=[]
 def observed(c,*a,**kw):sent.append(a[0]);return original(c,*a,**kw)
 monkeypatch.setattr(psycopg.Connection,'execute',observed)
 connection=None;start=time.monotonic();deadline=datetime.now(timezone.utc)+timedelta(seconds=3)
 with _request_fence_v1(float(start+3)):
  with pytest.raises(PermissionError,match='already armed'):
   with _connection_v1(h['url'],deadline) as c:
    connection=c;_execute_v1(c,deadline,'SELECT current_user')
    time.sleep(2.05)
    if stage=='setter':sql_rearm_v1(c,deadline,timeout_ms=50)
    else:_execute_v1(c,deadline,'SELECT pg_sleep(3)')
 assert connection.closed
 assert sent[0]=='BEGIN ISOLATION LEVEL READ COMMITTED' and len(sent)==2


def test_actual_postwrite_original_fence_loss_is_UNKNOWN_no_retry_and_no_commit(admin_url,processing,tmp_path,monkeypatch):
 from oracle_brain.operating_model import request_deadline_v1 as core
 from oracle_brain.operating_model.consolidation_authority_v1 import ConsolidationOutcomeUnknown
 f=processing();aid,m,args,payload=revision(admin_url,f,tmp_path);call_revision(f,aid,args)
 scope=payload['consolidation_core']['assertions'][0]['scope'];scope_bytes=canonical_bytes(scope)
 b=history_actor(admin_url,f,operation='business-review',scope_hash=hashlib.sha256(scope_bytes).hexdigest())
 base=adapter(admin_url,f,b);authority=ConsolidationAuthorityV1(base.url,binding=replace(base.binding,operation='business-review'))
 original_execute=psycopg.Connection.execute;original_clock=time.monotonic;offset=[0.];writes=[];connections=[]
 monkeypatch.setattr(core.time,'monotonic',lambda:original_clock()+offset[0])
 def observed(c,query,*a,**kw):
  result=original_execute(c,query,*a,**kw)
  if str(query).startswith('SELECT oracle2.record_processing_model_review_v1('):
   writes.append(str(query));connections.append(c);offset[0]=100.
  return result
 monkeypatch.setattr(psycopg.Connection,'execute',observed)
 assertion=payload['consolidation_core']['assertions'][0]
 with _request_fence_v1(float(original_clock()+20)):
  with pytest.raises(ConsolidationOutcomeUnknown,match='UNKNOWN'):
   authority.review_v1(model=m.artifact_id,version=1,content_hash=m.content_hash,decision='accept',scope=scope,
    assertions=[{'assertion_id':assertion['assertion_id'],'revision':assertion['revision']}],bundle_hash='a'*64,
    idempotency=uuid4(),deadline=datetime.now(timezone.utc)+timedelta(seconds=15))
 assert len(writes)==1 and connections[0].closed
 with psycopg.connect(admin_url) as c:
  assert c.execute("SELECT count(*) FROM oracle2.processing_model_events_v1 WHERE artifact_id=%s AND kind='business-accept'",(m.artifact_id,)).fetchone()[0]==0


def test_actual_asof_decisions_keep_recording_time_and_later_withdrawal_separate(admin_url,processing,tmp_path):
 f=processing();aid,m,args,payload=revision(admin_url,f,tmp_path);committed=call_revision(f,aid,args);acknowledge(f,m);h,_=own_history(admin_url,f)
 original=datetime.fromisoformat(committed['recordedAt'])
 scope=canonical_bytes(payload['consolidation_core']['assertions'][0]['scope'])
 b=history_actor(admin_url,f,operation='business-review',scope_hash=hashlib.sha256(scope).hexdigest())
 a=payload['consolidation_core']['assertions'][0];selection=[{'assertion_id':a['assertion_id'],'revision':a['revision']}]
 with psycopg.connect(b['url']) as c:
  event=c.execute('SELECT oracle2.record_processing_model_review_v1(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(m.artifact_id,1,m.content_hash,'accept',scope,Jsonb(selection),'a'*64,uuid4(),b['aid'],RUNTIME,REGISTRY,'f'*64,datetime.now(timezone.utc)+timedelta(seconds=15))).fetchone()[0]
 with psycopg.connect(admin_url) as c:
  recorded=c.execute('SELECT recorded_at FROM oracle2.processing_model_events_v1 WHERE event_id=%s',(event['eventId'],)).fetchone()[0]
  c.execute(sql.SQL('GRANT EXECUTE ON FUNCTION oracle2.record_processing_model_decision_change_v1(uuid,text,uuid,uuid,text,text,text,timestamptz) TO {}').format(sql.Identifier(b['login'])))
 before=ConsolidatedReadDeliveryV1.model_validate_json(canonical_bytes(delivery(h,m,valid_at=original,known_at=original)))
 accepted=ConsolidatedReadDeliveryV1.model_validate_json(canonical_bytes(delivery(h,m,valid_at=original,known_at=recorded)))
 assert before.business_decisions_as_of==()
 assert len(accepted.business_decisions_as_of)==1 and not accepted.business_decisions_as_of[0].withdrawn_as_of
 with psycopg.connect(b['url']) as c:
  change=c.execute('SELECT oracle2.record_processing_model_decision_change_v1(%s,%s,%s,%s,%s,%s,%s,%s)',(event['eventId'],'withdraw',uuid4(),b['aid'],RUNTIME,REGISTRY,'f'*64,datetime.now(timezone.utc)+timedelta(seconds=15))).fetchone()[0]
 with psycopg.connect(admin_url) as c:
  withdrawn=c.execute('SELECT recorded_at FROM oracle2.processing_model_events_v1 WHERE event_id=%s',(change['eventId'],)).fetchone()[0]
 old=ConsolidatedReadDeliveryV1.model_validate_json(canonical_bytes(delivery(h,m,valid_at=original,known_at=recorded)))
 later=ConsolidatedReadDeliveryV1.model_validate_json(canonical_bytes(delivery(h,m,valid_at=original,known_at=withdrawn)))
 assert old.business_decisions_as_of==accepted.business_decisions_as_of
 assert later.business_decisions_as_of[0].withdrawn_as_of and later.valid_at==original
 assert later.business_decisions_as_of[0].recorded_at==recorded
 assert later.retained_receipt==accepted.retained_receipt


@pytest.mark.parametrize('damage',['scope_hash','decision_kind','model_content_hash','version'])
def test_actual_matching_decision_change_with_wrong_retained_scope_or_version_denies(admin_url,processing,tmp_path,damage):
 f=processing();aid,m,args,payload=revision(admin_url,f,tmp_path);first=call_revision(f,aid,args);acknowledge(f,m);h,_=own_history(admin_url,f)
 scope=canonical_bytes(payload['consolidation_core']['assertions'][0]['scope']);scope_hash=hashlib.sha256(scope).hexdigest()
 b=history_actor(admin_url,f,operation='business-review',scope_hash=scope_hash)
 assertion=payload['consolidation_core']['assertions'][0];selected=[{'assertion_id':assertion['assertion_id'],'revision':assertion['revision']}]
 with psycopg.connect(b['url']) as c:
  accepted=c.execute('SELECT oracle2.record_processing_model_review_v1(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
   (m.artifact_id,1,m.content_hash,'accept',scope,Jsonb(selected),'a'*64,uuid4(),b['aid'],RUNTIME,REGISTRY,'f'*64,datetime.now(timezone.utc)+timedelta(seconds=10))).fetchone()[0]
 forged={'target_event_id':accepted['eventId'],'scope_hash':scope_hash,'decision_kind':'employee-account','model_content_hash':m.content_hash}
 if damage!='version':forged[damage]='f'*64 if damage!='decision_kind' else 'company-policy'
 known=datetime.now(timezone.utc)
 if damage=='version':
  aid,m2,args2,_=revision(admin_url,f,tmp_path,aid=aid,artifact=m.artifact_id,version=2,previous_hash=m.content_hash);call_revision(f,aid,args2)
 with psycopg.connect(admin_url) as c:
  # Explicit fixture-owner corruption, never a runtime backdating capability:
  # a wrong-version change targeting the exact retained v1 event must deny.
  c.execute('INSERT INTO oracle2.processing_model_events_v1(event_id,workspace_id,artifact_id,version,kind,actor_id,admission_id,payload,idempotency,recorded_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
   (uuid4(),f['workspace'],m.artifact_id,2 if damage=='version' else 1,'business-withdraw',b['actor'],b['aid'],Jsonb(forged),uuid4(),known))
 with pytest.raises(psycopg.errors.InsufficientPrivilege):
  delivery(h,m,valid_at=datetime.fromisoformat(first['recordedAt']),known_at=known)


def test_actual_retained_ack_not_renewed_and_old_current_max_version_guard_remains(admin_url,processing,tmp_path):
 f=processing();aid,m,args,_=revision(admin_url,f,tmp_path);first=call_revision(f,aid,args);receipt=acknowledge(f,m,lease_seconds=1);h,_=own_history(admin_url,f)
 known=datetime.fromisoformat(first['recordedAt'])
 aid,m2,args2,_=revision(admin_url,f,tmp_path,aid=aid,artifact=m.artifact_id,version=2,previous_hash=m.content_hash);call_revision(f,aid,args2)
 time.sleep(max(0,(datetime.fromisoformat(receipt['lease_until'])-datetime.now(timezone.utc)).total_seconds())+.02)
 with pytest.raises(psycopg.errors.InsufficientPrivilege):delivery(h,m)
 retained=ConsolidatedReadDeliveryV1.model_validate_json(canonical_bytes(delivery(h,m,valid_at=known,known_at=known)))
 assert retained.retained_receipt.model_dump(mode='json')==receipt
 assert retained.checked_at>retained.retained_delivered_at and retained.retained_receipt.lease_until==receipt['lease_until']
 assert retained.checked_at>datetime.fromisoformat(retained.retained_receipt.lease_until)
 with psycopg.connect(f['url']) as c:
  c.execute("SET LOCAL statement_timeout='5s'")
  with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT oracle2.hosting_processing_projection_receipt_v3(%s,%s,%s,%s,%s,%s)',(m.workspace_id,m.artifact_id,1,f['actor'],RUNTIME,REGISTRY))
