"""Retained contract/adversarial checks, not actual SQL/provider proof."""
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4
import pytest
import psycopg
from oracle_brain.meetings import participation_authority_v1 as module
from oracle_brain.meetings.participation_authority_v1 import (
    ParticipationSQLBindingV1, ParticipationAuthorityV1, ParticipationOutcomeUnknown,
)


@pytest.fixture
def installation(tmp_path):
    ca=tmp_path/'ca.pem';ca.write_bytes(b'invented CA bytes for pure contract only');ca.chmod(0o600)
    now=datetime.now(timezone.utc)
    binding=ParticipationSQLBindingV1(uuid4(),'a'*64,uuid4(),uuid4(),uuid4(),'invented_sender','oracle2_admin','sender','b'*64,'c'*64,
        str(ca),sha256(ca.read_bytes()).hexdigest(),now+timedelta(minutes=2),tuple((s,'d'*64) for s in module.CAPABILITIES))
    url='postgresql://invented_sender:invented@127.0.0.1:5432/invented?sslmode=verify-full&sslrootcert='+str(ca)
    return binding,url,now+timedelta(seconds=20)


def context(binding,deadline):
    return dict(principal_id=str(binding.principal_id),workspace_id=str(binding.workspace_id),session_role=binding.session_login,
        runtime_hash=binding.runtime_hash,source_registry_hash=binding.registry_hash,checked_at=(datetime.now(timezone.utc)-timedelta(milliseconds=1)).isoformat(),valid_until=deadline.isoformat())


def status(binding,deadline,intent,claim,request_hash):
    frame = dict(capture_event_id=str(uuid4()),capture_event_sha256='a'*64,capture_revision=1,
        raw_sha256='b'*64,normalized_sha256='c'*64,participant_epoch_id=str(uuid4()),
        participant_epoch_revision=1,participant_epoch_sha256='d'*64,participant_set_sha256='e'*64,
        provider_speaker_id='invented-participant',actor_id=str(uuid4()))
    return dict(meeting_id=str(binding.meeting_id),head_revision=1,generation=1,host_enabled=True,proactive_enabled=False,proactive_count=0,
        intent_id=str(intent),state='inflight',outcome='UNKNOWN',delivery_revision=1,claim_event_id=str(claim),claim_current=True,
        turn_binding=frame,intent_proactive=False,intent_current=True,receipt_permitted=True,receipt_bot_id='12345678-1234-1234-1234-123456789abc',prepare_binding=None,reconcile_intent_id=str(intent),observation_id=None,observation_revision=0,observation_sha256=None,observation_valid_until=None,request_sha256=request_hash,visible_message_proven=False,remote_stop_proven=False,executable=False,valid_until=deadline.isoformat(),context=context(binding,deadline))


class Connection:
    def __init__(self,binding,write_result,status_result,events,on_close=None):
        self.binding=binding;self.write_result=write_result;self.status_result=status_result;self.events=events
        self.pgconn=SimpleNamespace(ssl_in_use=True);self.on_close=on_close;self.result=None
        self.info=SimpleNamespace(host='127.0.0.1',hostaddr='127.0.0.1',dbname='invented',user=binding.session_login,port=5432)
    def __enter__(self):return self
    def __exit__(self,*exc):
        self.events.append('close')
        if self.on_close:self.on_close()
    def execute(self,query,args=None):
        if query=='BEGIN ISOLATION LEVEL READ COMMITTED':self.result=None
        elif query.startswith('SELECT pg_catalog.set_config'):self.result=None
        elif query=='SELECT SESSION_USER,CURRENT_USER':self.result=(self.binding.session_login,self.binding.session_login)
        elif 'FROM pg_catalog.unnest' in query:
            self.result=[]
            for sig in module.CAPABILITIES:
                acl=[self.binding.expected_owner+':EXECUTE:false']
                if sig.split('.',1)[1] in module._PUBLIC:acl+=['oracle2_replacement_requester:EXECUTE:false']
                self.result.append((sig,'oracle2',sig.split('(',1)[0].split('.')[1],self.binding.expected_owner,
                    sig!='oracle2._meeting_participation_revoke_lock_v1()',
                    ['search_path=pg_catalog, oracle2'],'d'*64,sorted(acl)))
        elif 'meeting_participation_claim_v1' in query:self.events.append('claim');self.result=(self.write_result,)
        elif 'meeting_participation_status_v1' in query:self.events.append('status');self.result=(self.status_result,)
        else:raise AssertionError('unexpected pure contract SQL')
        return self
    def fetchone(self):return self.result
    def fetchall(self):return self.result


def arrange(installation,monkeypatch,*,second_error=None,close_hook=None,restrictive=None):
    b,url,deadline=installation;intent,claim,operation=uuid4(),uuid4(),uuid4();body=b'{"message":"You asked: invented turn","to":"everyone"}'
    request_hash=sha256(body).hexdigest()
    initial=dict(intent_id=str(intent),state='inflight',created=True,executable=True,claim_event_id=str(claim),revision=1,
        body=body.decode(),request_sha256=request_hash,bot_id=str(uuid4()),valid_until=deadline.isoformat(),context=context(b,deadline))
    fresh=status(b,deadline,intent,claim,request_hash);events=[];connections=[]
    def connect(*args,**kwargs):
        events.append('connect')
        if len(connections)==1 and second_error:raise second_error
        c=Connection(b,initial,fresh,events,close_hook if not connections else None);connections.append(c);return c
    monkeypatch.setattr(module.psycopg,'connect',connect)
    authority=ParticipationAuthorityV1(url,binding=b,_runtime_recheck=restrictive)
    return authority,deadline,intent,operation,body,initial,fresh,events,connections


def test_claim_body_only_after_commit_close_and_fresh_own_current_status(installation,monkeypatch):
    a,end,intent,op,body,initial,fresh,events,_=arrange(installation,monkeypatch)
    claim=a.claim_v1(intent_id=intent,expected_revision=0,operation=op,deadline=end)
    assert claim.body==body and claim.metadata['executable'] is False
    assert events==['connect','claim','close','connect','status','close']
    assert 'receipt_bot_id' not in claim.metadata
    assert 'context' not in claim.metadata and 'body' not in claim.metadata and 'turn_binding' not in claim.metadata
    assert claim.metadata['state']=='inflight' and claim.metadata['outcome']=='UNKNOWN'
    assert not claim.metadata['visible_message_proven'] and not claim.metadata['remote_stop_proven']


@pytest.mark.parametrize('error',[psycopg.OperationalError('invented readback loss'),PermissionError('invented current root revoked')])
def test_committed_claim_readback_failure_unknown_one_write_no_retry(installation,monkeypatch,error):
    a,end,intent,op,_,_,_,events,_=arrange(installation,monkeypatch,second_error=error)
    with pytest.raises(ParticipationOutcomeUnknown,match='no resend'):
        a.claim_v1(intent_id=intent,expected_revision=0,operation=op,deadline=end)
    assert events==['connect','claim','close','connect']


def test_settings_change_at_write_close_unknown_before_next_connection(installation,monkeypatch):
    state={'closed':False}
    def guard():
        if state['closed']:raise PermissionError('invented protected installation replaced')
    a,end,intent,op,_,_,_,events,_=arrange(installation,monkeypatch,close_hook=lambda:state.update(closed=True),restrictive=guard)
    with pytest.raises(ParticipationOutcomeUnknown):a.claim_v1(intent_id=intent,expected_revision=0,operation=op,deadline=end)
    assert events==['connect','claim','close']


@pytest.mark.parametrize('field,value',[('claim_current',False),('claim_event_id',str(uuid4())),('request_sha256','e'*64),('delivery_revision',2)])
def test_fresh_claim_mismatch_never_releases_body(installation,monkeypatch,field,value):
    a,end,intent,op,_,_,fresh,events,_=arrange(installation,monkeypatch);fresh[field]=value
    with pytest.raises(ParticipationOutcomeUnknown):a.claim_v1(intent_id=intent,expected_revision=0,operation=op,deadline=end)
    assert events.count('claim')==1


def test_explicit_claim_replay_has_no_executable_body(installation,monkeypatch):
    a,end,intent,op,_,initial,_,events,_=arrange(installation,monkeypatch)
    initial.pop('body');initial['created']=False;initial['executable']=False
    claim=a.claim_v1(intent_id=intent,expected_revision=0,operation=op,deadline=end)
    assert claim.body is None and claim.metadata['outcome']=='UNKNOWN' and events.count('claim')==1


@pytest.mark.parametrize('bad',[None,True,0,'intent-id'])
def test_selector_contract_refuses_before_connection(installation,monkeypatch,bad):
    b,url,end=installation
    monkeypatch.setattr(module.psycopg,'connect',lambda *a,**k:pytest.fail('contract failed before mutation'))
    a=ParticipationAuthorityV1(url,binding=b)
    with pytest.raises(PermissionError):a.claim_v1(intent_id=bad,expected_revision=0,operation=uuid4(),deadline=end)


def test_expiry_refuses_before_connection(installation,monkeypatch):
    b,url,_=installation;monkeypatch.setattr(module.psycopg,'connect',lambda *a,**k:pytest.fail('expired contract reached SQL'))
    a=ParticipationAuthorityV1(url,binding=b)
    with pytest.raises(PermissionError):a.claim_v1(intent_id=uuid4(),expected_revision=0,operation=uuid4(),deadline=datetime.now(timezone.utc)-timedelta(seconds=1))


@pytest.mark.parametrize('change',[dict(kind='administrator'),dict(expected_owner='invented_sender'),dict(capability_hashes=()),dict(runtime_hash='self-appointed')])
def test_installation_cannot_self_appoint_or_widen_catalog(installation,change):
    b,_,_=installation
    with pytest.raises(PermissionError):replace(b,**change)

@pytest.mark.parametrize('text',['Oracle, what did I just ask?','@Oracle: keep this original wording','ORACLE! question','Oracle'])
def test_exact_current_address_preserves_original_words_and_claim_limits(text):
    from oracle_brain.meetings.participation_runtime_v1 import compose_current_turn_v1
    reply=compose_current_turn_v1(text)
    assert reply.message=='You asked: '+text
    assert reply.normalized_sha256==sha256(text.encode()).hexdigest()
    assert reply.reported_only and not reply.qualification and not reply.employee_identity_verified and not reply.shared_source_permission

@pytest.mark.parametrize('text',['The Oracle database','Not addressed to Oracle','OracleDatabase question',' @Oracle question','Оracle question'])
def test_other_mentions_and_lookalikes_decline_without_alternate_answer(text):
    from oracle_brain.meetings.participation_runtime_v1 import compose_current_turn_v1,ParticipationDeclined
    with pytest.raises(ParticipationDeclined):compose_current_turn_v1(text)

def test_proactive_content_is_only_exact_turn_clarification_never_permission():
    from oracle_brain.meetings.participation_runtime_v1 import compose_current_turn_v1,ParticipationDeclined
    text='Original words without an address'
    with pytest.raises(ParticipationDeclined):compose_current_turn_v1(text)
    assert compose_current_turn_v1(text,proactive=True).message=='Could you clarify: '+text

@pytest.mark.parametrize('text',['Oracle '+('x'*4096),'Oracle '+('U0001f600'*4096),'\0Oracle',''])
def test_overlimit_or_empty_reply_refuses_instead_of_slicing(text):
    from oracle_brain.meetings.participation_runtime_v1 import compose_current_turn_v1,ParticipationDeclined
    with pytest.raises(ParticipationDeclined):compose_current_turn_v1(text)


def test_markup_escaped_only_for_provider_presentation():
    from oracle_brain.meetings.participation_runtime_v1 import compose_current_turn_v1
    text='Oracle, <a href="https://invented.invalid">A&B</a>'
    reply=compose_current_turn_v1(text)
    assert reply.message=='You asked: Oracle, &lt;a href="https://invented.invalid"&gt;A&amp;B&lt;/a&gt;'
    assert reply.normalized_sha256==sha256(text.encode()).hexdigest()
    assert reply.body_sha256==sha256(reply.message.encode()).hexdigest()


def test_expanded_markup_overlimit_declines_without_truncation():
    from oracle_brain.meetings.participation_runtime_v1 import compose_current_turn_v1,ParticipationDeclined
    with pytest.raises(ParticipationDeclined):compose_current_turn_v1('Oracle '+('<'*1100))


@pytest.mark.parametrize('field,value',[('meeting_id','foreign'),('claim_event_id','BAD'),('observation_revision',True),
    ('observation_sha256','e'*64),('turn_binding',{}),('request_sha256','BAD')])
def test_bad_fresh_private_metadata_never_releases_provider_body(installation,monkeypatch,field,value):
    a,end,intent,op,_,_,fresh,events,_=arrange(installation,monkeypatch);fresh[field]=value
    with pytest.raises(ParticipationOutcomeUnknown):a.claim_v1(intent_id=intent,expected_revision=0,operation=op,deadline=end)
    assert events.count('claim')==1


def test_current_turn_selector_is_own_readonly_private_frame(installation,monkeypatch):
    a,end,intent,_,_,_,fresh,events,_=arrange(installation,monkeypatch)
    frame,proactive,until=a._current_turn_binding_v1(intent,deadline=end)
    assert frame==fresh['turn_binding'] and until<=end
    assert proactive is False
    assert events==['connect','status','close']
    assert 'turn_binding' not in a._public_metadata(fresh)


@pytest.mark.parametrize('change',[dict(proactive_enabled='yes'),dict(cooldown_seconds=119),dict(cooldown_seconds=True),
    dict(max_proactive=4),dict(max_proactive=True),dict(observation_id='invented'),dict(enabled=False,proactive_enabled=True)])
def test_host_contract_before_any_connection(installation,monkeypatch,change):
    b,url,end=installation;b=replace(b,kind='host')
    monkeypatch.setattr(module.psycopg,'connect',lambda *a,**k:pytest.fail('bad host contract reached SQL'))
    a=ParticipationAuthorityV1(url,binding=b)
    values=dict(expected_head=0,operation=uuid4(),enabled=True,observation_id=uuid4(),deadline=end);values.update(change)
    with pytest.raises(PermissionError):a.control_v1(**values)


def test_wrong_bot_identity_in_claim_never_releases_bytes(installation,monkeypatch):
    a,end,intent,op,_,initial,_,events,_=arrange(installation,monkeypatch)
    initial['bot_id']='invented-not-a-provider-uuid'
    with pytest.raises(ParticipationOutcomeUnknown):a.claim_v1(intent_id=intent,expected_revision=0,operation=op,deadline=end)
    assert events.count('claim')==1


def test_sender_cannot_write_observation_facts(installation,monkeypatch):
    b,url,end=installation
    monkeypatch.setattr(module.psycopg,'connect',lambda *a,**k:pytest.fail('sender wrote observer facts'))
    a=ParticipationAuthorityV1(url,binding=b)
    with pytest.raises(PermissionError):a.observe_audience_v1(expected_revision=0,observation_id=uuid4(),observation={},deadline=end)


def test_caller_content_substitution_denied_before_prepare_sql(installation,monkeypatch):
    b,url,end=installation
    monkeypatch.setattr(module.psycopg,'connect',lambda *a,**k:pytest.fail('substituted plaintext reached SQL'))
    a=ParticipationAuthorityV1(url,binding=b)
    frame=status(b,end,uuid4(),uuid4(),'f'*64)['turn_binding']
    with pytest.raises(PermissionError):a._prepare_current_turn_v1(expected_head=1,operation=uuid4(),intent_id=uuid4(),
        frame=frame,text='Oracle different bytes',proactive=False,observation_id=uuid4(),composer_sha256='a'*64,deadline=end)


def latest_status(b,end,*,available=True,prior=None):
    value=status(b,end,uuid4(),uuid4(),'f'*64)
    for k in ('intent_id','state','outcome','delivery_revision','claim_event_id','request_sha256','turn_binding','intent_proactive','receipt_bot_id'):
        value[k]=None
    value.update(claim_current=False,intent_current=False,reconcile_intent_id=prior)
    if available:
        value.update(observation_id=str(uuid4()),observation_revision=1,observation_sha256='a'*64,observation_valid_until=end.isoformat())
        value['prepare_binding']=dict(capture_event_id=str(uuid4()),head_revision=1,generation=1,existing_intent_id=prior,valid_until=end.isoformat())
    return value


def arrange_latest(installation,monkeypatch,*,available=True,prior=None):
    b,url,end=installation;events=[];fresh=latest_status(b,end,available=available,prior=prior)
    monkeypatch.setattr(module.psycopg,'connect',lambda *a,**k:Connection(b,{},fresh,events))
    return ParticipationAuthorityV1(url,binding=b),end,fresh,events


def test_latest_preparation_selector_is_from_actual_own_sql_only(installation,monkeypatch):
    a,end,fresh,events=arrange_latest(installation,monkeypatch)
    binding,proactive=a._latest_prepare_binding_v1(deadline=end)
    assert binding==fresh['prepare_binding'] and proactive is False
    assert events==['status','close']
    public=a._public_metadata(fresh)
    assert 'prepare_binding' not in public and 'reconcile_intent_id' not in public


def test_missing_chat_host_or_source_binding_declines_no_mutation(installation,monkeypatch):
    from oracle_brain.meetings.participation_runtime_v1 import ParticipationDeclined
    a,end,_,events=arrange_latest(installation,monkeypatch,available=False)
    with pytest.raises(ParticipationDeclined):a._latest_prepare_binding_v1(deadline=end)
    assert events==['status','close']


@pytest.mark.parametrize('change',[dict(head_revision=2),dict(generation=0),dict(valid_until=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()),
    dict(capture_event_id='caller-supplied'),dict(existing_intent_id='foreign')])
def test_bad_actual_latest_binding_fails_closed(installation,monkeypatch,change):
    a,end,fresh,events=arrange_latest(installation,monkeypatch)
    fresh['prepare_binding'].update(change)
    with pytest.raises(PermissionError):a._latest_prepare_binding_v1(deadline=end)
    assert events==['status','close']


def test_expired_claim_never_reopens_source_bytes(installation,monkeypatch):
    a,end,intent,_,_,_,fresh,events,_=arrange(installation,monkeypatch)
    fresh.update(intent_current=False,claim_current=False)
    with pytest.raises(PermissionError):a._current_turn_binding_v1(intent,deadline=end)
    assert events==['connect','status','close']


def test_closed_body_policy_fingerprint_exact_canonical_descriptor():
    from oracle_brain.operating_model.contracts import digest
    values=tuple((signature,'e'*64) for signature in module.CAPABILITIES)
    descriptor=dict(purpose='meeting-participation-body-policy-v1',composer_sha256='a'*64,
        sql_capability_sha256s=dict(sorted(values)),to='everyone',max_codepoints=4096,
        presentation='escape-amp-lt-gt-v1',max_proactive=3,cooldown_seconds=120)
    expected=digest(descriptor)
    assert module.participation_operation_policy_sha256_v1('a'*64,values)==expected
    assert module.participation_operation_policy_sha256_v1('a'*64,tuple(reversed(values)))==expected
    assert module.participation_operation_policy_sha256_v1('b'*64,values)!=expected
    changed=((values[0][0],'f'*64),)+values[1:]
    assert module.participation_operation_policy_sha256_v1('a'*64,changed)!=expected


@pytest.mark.parametrize('variant',['omit','duplicate','unknown','bad_hash','list','bad_composer'])
def test_body_policy_does_not_accept_partial_or_self_stated_map(variant):
    values=tuple((signature,'e'*64) for signature in module.CAPABILITIES);composer='a'*64
    if variant=='omit':values=values[:-1]
    elif variant=='duplicate':values=values[:-1]+values[:1]
    elif variant=='unknown':values=(('oracle2.self_appointed()','e'*64),)+values[1:]
    elif variant=='bad_hash':values=((values[0][0],'caller-label'),)+values[1:]
    elif variant=='list':values=list(values)
    elif variant=='bad_composer':composer='caller-label'
    with pytest.raises(PermissionError):module.participation_operation_policy_sha256_v1(composer,values)


@pytest.mark.parametrize('variable',['PGHOSTADDR','PGSERVICE','PGOPTIONS','PGPASSFILE'])
def test_protected_connection_refuses_environment_before_socket(installation,monkeypatch,variable):
    b,url,end=installation
    a=ParticipationAuthorityV1(url,binding=b)
    monkeypatch.setenv(variable,'invented-untrusted-default')
    monkeypatch.setattr(module.psycopg,'connect',lambda *a,**k:pytest.fail('environment reached socket'))
    with pytest.raises(PermissionError,match='environment'):
        a.status_v1(None,deadline=end)


@pytest.mark.parametrize('change',[dict(port=None),dict(password=None),dict(host='invented.invalid'),dict(port='0')])
def test_complete_pinned_target_refuses_before_socket(installation,monkeypatch,change):
    b,url,_=installation
    params=psycopg.conninfo.conninfo_to_dict(url)
    for key,value in change.items():
        if value is None:params.pop(key,None)
        else:params[key]=value
    monkeypatch.setattr(module.psycopg,'connect',lambda *a,**k:pytest.fail('invalid target reached socket'))
    with pytest.raises(PermissionError):
        ParticipationAuthorityV1(psycopg.conninfo.make_conninfo(**params),binding=b)


def test_same_common_connection_pins_numeric_target_and_startup_bound(installation,monkeypatch):
    a,end,intent,op,body,_,_,_,connections=arrange(installation,monkeypatch)
    original=module.psycopg.connect;calls=[]
    def record(*args,**kwargs):
        calls.append(kwargs)
        return original(*args,**kwargs)
    monkeypatch.setattr(module.psycopg,'connect',record)
    assert a.claim_v1(intent_id=intent,expected_revision=0,operation=op,deadline=end).body==body
    assert len(connections)==len(calls)==2
    for call in calls:
        assert call['host']==call['hostaddr']=='127.0.0.1'
        assert call['port']=='5432' and call['dbname']=='invented'
        assert call['user']==a.binding.session_login and call['sslmode']=='verify-full'
        assert call['sslrootcert']==a.binding.ca_path and call['autocommit'] is True
        assert call['connect_timeout']==2 and call['tcp_user_timeout']<=2000
        assert call['options']=='-c statement_timeout=2000ms -c lock_timeout=2000ms'


def test_short_original_monotonic_window_refuses_before_socket(installation,monkeypatch):
    import time
    from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
    b,url,end=installation;a=ParticipationAuthorityV1(url,binding=b)
    monkeypatch.setattr(module.psycopg,'connect',lambda *a,**k:pytest.fail('short original window reached socket'))
    with _request_fence_v1(time.monotonic()+1.0):
        with pytest.raises(PermissionError,match='two-second'):
            a.status_v1(None,deadline=end)


@pytest.mark.parametrize('boundary',['connect','catalog','write','commit','close'])
def test_same_original_fence_at_every_io_never_releases_or_retries(installation,monkeypatch,boundary):
    from oracle_brain.operating_model import request_deadline_v1 as fence
    now=[100.0];monkeypatch.setattr(fence.time,'monotonic',lambda:now[0])
    a,end,intent,op,_,_,_,events,connections=arrange(installation,monkeypatch)
    original_connect=module.psycopg.connect;original_execute=Connection.execute
    catalogs=[0]
    def connect(*args,**kwargs):
        c=original_connect(*args,**kwargs)
        if boundary=='connect':now[0]=121.0
        if boundary=='close':c.on_close=lambda:now.__setitem__(0,121.0)
        return c
    def execute(c,query,args=None):
        result=original_execute(c,query,args)
        if 'FROM pg_catalog.unnest' in query:
            catalogs[0]+=1
            if boundary=='catalog':now[0]=121.0
            # Still unexpired, but the already armed two-second COMMIT cannot fit.
            if boundary=='commit' and catalogs[0]==2:now[0]=119.0
        if boundary=='write' and 'SELECT oracle2.meeting_participation_claim_v1(' in query:now[0]=121.0
        return result
    monkeypatch.setattr(module.psycopg,'connect',connect)
    monkeypatch.setattr(Connection,'execute',execute)
    with fence._request_fence_v1(120.0):
        expected=ParticipationOutcomeUnknown if boundary in {'write','commit','close'} else PermissionError
        with pytest.raises(expected):
            a.claim_v1(intent_id=intent,expected_revision=0,operation=op,deadline=end)
    assert len(connections)==1 and events.count('claim')<=1
    assert events.count('claim')==(1 if boundary in {'write','commit','close'} else 0)
    assert events.count('close')==1 and 'status' not in events


def test_commit_close_failure_after_claim_is_unknown_no_readback_or_retry(installation,monkeypatch):
    def fail():raise OSError('invented commit-close acknowledgement lost')
    a,end,intent,op,_,_,_,events,_=arrange(installation,monkeypatch,close_hook=fail)
    with pytest.raises(ParticipationOutcomeUnknown,match='no resend'):
        a.claim_v1(intent_id=intent,expected_revision=0,operation=op,deadline=end)
    assert events==['connect','claim','close']


def test_dns_label_requires_and_uses_exact_pinned_numeric_address(installation,monkeypatch):
    b,url,end=installation;params=psycopg.conninfo.conninfo_to_dict(url)
    params.update(host='invented.invalid',hostaddr='127.0.0.1')
    url=psycopg.conninfo.make_conninfo(**params);calls=[];events=[]
    fresh=latest_status(b,end)
    def connect(*args,**kwargs):
        calls.append(kwargs)
        c=Connection(b,{},fresh,events);c.info.host='invented.invalid';return c
    monkeypatch.setattr(module.psycopg,'connect',connect)
    ParticipationAuthorityV1(url,binding=b).status_v1(None,deadline=end)
    assert len(calls)==1 and calls[0]['host']=='invented.invalid' and calls[0]['hostaddr']=='127.0.0.1'
    assert events==['status','close']


@pytest.mark.parametrize('field,value',[('host','foreign.invalid'),('dbname','foreign'),('user','foreign'),('port',5433),('ssl',False)])
def test_retained_actual_role_tls_target_checks_precede_mutation(installation,monkeypatch,field,value):
    a,end,intent,op,_,_,_,events,_=arrange(installation,monkeypatch)
    original=module.psycopg.connect
    def connect(*args,**kwargs):
        c=original(*args,**kwargs)
        if field=='ssl':c.pgconn.ssl_in_use=value
        else:setattr(c.info,field,value)
        return c
    monkeypatch.setattr(module.psycopg,'connect',connect)
    with pytest.raises(ParticipationOutcomeUnknown,match='no resend'):
        a.claim_v1(intent_id=intent,expected_revision=0,operation=op,deadline=end)
    assert events==['connect','close']


def test_authority_has_no_unguarded_sql_or_second_connection_owner():
    import ast
    import inspect
    tree=ast.parse(inspect.getsource(module.ParticipationAuthorityV1))
    assert not [n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
        and n.func.attr in {'execute','connect','commit'}]
    sends=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
        and n.func.id=='sql_execute_v1']
    assert len(sends)==5
    assert all(isinstance(n.args[1],ast.Name) and n.args[1].id=='deadline' for n in sends)
