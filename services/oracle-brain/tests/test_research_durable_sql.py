"""Actual owned SQL023 scheduling/rights/currentness; invented sources, no fetch."""
from datetime import datetime,timezone,timedelta
from uuid import uuid4,UUID
from concurrent.futures import ThreadPoolExecutor
import hashlib
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from test_hosting_boundary import certificates
from oracle_brain.operating_model.contracts import canonical_bytes

RUNTIME='a'*64;REGISTRY='b'*64;CONFIG='c'*64

@pytest.fixture
def research(admin_url,request):
    return installed_research_fixture_v1(admin_url,request)

def installed_research_fixture_v1(admin_url,request,*,workspace=None,source=None,read_principal=None):
    now=datetime.now(timezone.utc);until=now+timedelta(minutes=10)
    workspace,owner,root,source=workspace or uuid4(),uuid4(),uuid4(),source or uuid4()
    definition=dict(source_id='invented-industry',publisher='Invented Publisher',url='https://industry.example.test/reference',
        jurisdiction='US',scope='home-decor',access='public',cadence='weekly',enabled=True,rights_confirmed=False)
    definition.update(getattr(request,'param',None) or {})
    credentials={};admissions={};leaves={};actors={}
    with psycopg.connect(admin_url) as c:
        c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,expires_at) VALUES(%s,%s,%s,%s,%s,%s)',
            (root,workspace,owner,'root',uuid4(),until))
        c.execute('INSERT INTO oracle2.research_registrations_v1 VALUES(%s,%s,1,%s,%s,%s)',
            (workspace,source,Jsonb(definition),hashlib.sha256(canonical_bytes(definition)).hexdigest(),now))
        for op in ('schedule','fetch','read'):
            login='research_'+op+'_'+uuid4().hex[:12];actor,leaf,admission,issuer,reviewer=uuid4(),uuid4(),uuid4(),uuid4(),uuid4()
            if op=='read' and read_principal is not None:actor=read_principal
            c.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(login),sql.Literal('invented-research-only')))
            c.execute(sql.SQL('GRANT USAGE ON SCHEMA oracle2 TO {}').format(sql.Identifier(login)))
            for signature in ('research_claim_due_v1(uuid,text,text,text,timestamptz)',
                'research_force_due_v1(uuid,text,text,text,timestamptz)',
                'research_pending_queue_v1(uuid,text,text,text,timestamptz)',
                'research_claim_fetch_v1(uuid,uuid,text,text,text,timestamptz)',
                'research_fetch_current_v1(uuid,uuid,uuid,text,text,text,timestamptz)',
                'research_observe_fetch_v1(uuid,uuid,bytea,uuid,text,text,text,timestamptz)',
                'research_current_v1(uuid,text,text,text,timestamptz)',
                'research_latest_reference_v1(uuid,text,text,text,timestamptz)',
                'research_retained_fetch_v1(uuid,uuid,text,text,text,timestamptz)',
                'research_status_v1(uuid,text,text,text,timestamptz)'):
                c.execute(sql.SQL('GRANT EXECUTE ON FUNCTION oracle2.'+signature+' TO {}').format(sql.Identifier(login)))
            c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                (leaf,workspace,actor,'research-'+op+':'+str(source),owner,root,until))
            c.execute('''INSERT INTO oracle2.research_admissions_v1(admission_id,role_name,principal_id,workspace_id,source_id,source_revision,operation,membership_appointment,
                runtime_hash,registry_hash,config_hash,issuer_actor,reviewer_actor,issued_at,original_horizon,expires_at)
                VALUES(%s,%s,%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (admission,login,actor,workspace,source,op,leaf,RUNTIME,REGISTRY,CONFIG,issuer,reviewer,now-timedelta(seconds=1),until,until))
            credentials[op]=psycopg.conninfo.make_conninfo(admin_url,user=login,password='invented-research-only')
            admissions[op]=admission;leaves[op]=leaf;actors[op]=actor
    # All objects belong to this exact ephemeral database/cluster. Individual
    # fixtures never delete another test's rows or recycle an old identity.
    return dict(admin=admin_url,workspace=workspace,source=source,root=root,owner=owner,definition=definition,
        credentials=credentials,admissions=admissions,leaves=leaves,actors=actors,until=until)

def invoke(f,operation,function,*prefix,deadline=None,config=CONFIG):
    with psycopg.connect(f['credentials'][operation],options='-c statement_timeout=5000 -c lock_timeout=2000') as c:
        args=(*prefix,f['admissions'][operation],RUNTIME,REGISTRY,config,deadline or datetime.now(timezone.utc)+timedelta(seconds=20))
        return c.execute(sql.SQL('SELECT oracle2.{}({})').format(sql.Identifier(function),sql.SQL(',').join(sql.Placeholder() for _ in args)),args).fetchone()[0]

def pending(f):return invoke(f,'schedule','research_claim_due_v1')
def claim(f,run,**kwargs):return invoke(f,'fetch','research_claim_fetch_v1',UUID(str(run)),**kwargs)
def observe(f,c,state='observed',**changes):
    body=dict(schema_version=1,state=state,http_status=200,wire_sha256='d'*64,wire_byte_count=100,body_sha256='e'*64,body_byte_count=20,
        private_key=f"research/{f['workspace']}/{f['source']}/{c['run_id']}/{c['claim_id']}.wire",
        trace_sha256='f'*64,trace_byte_count=100,retrieved_at=f.setdefault('fixture_observed_at',{}).setdefault(c['claim_id'],datetime.now(timezone.utc).isoformat()),
        trace_private_key=f"research/{f['workspace']}/{f['source']}/{c['run_id']}/{c['claim_id']}.trace.json")
    body.update(changes)
    return invoke(f,'fetch','research_observe_fetch_v1',UUID(c['run_id']),UUID(c['claim_id']),canonical_bytes(body))

def test_actual_concurrent_scheduler_one_durable_run_and_restart_no_repeat(research):
    f=research
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:pending(f),range(2)))
    assert {x['state'] for x in results}=={'pending','existing'}
    assert len({x['run_id'] for x in results})==1
    assert sum(x['dispatch_authorized'] is True for x in results)==1
    assert pending(f)['state']=='existing'
    with psycopg.connect(f['admin']) as c:
        assert c.execute('SELECT count(*) FROM oracle2.research_attempts_v1 WHERE workspace_id=%s',(f['workspace'],)).fetchone()==(1,)

def test_actual_once_claim_expiry_does_not_renew_or_redispatch(research):
    f=research;p=pending(f);deadline=datetime.now(timezone.utc)+timedelta(seconds=10);first=claim(f,p['run_id'],deadline=deadline)
    assert first['fetch_authorized'] is True and first['definition']==f['definition']
    again=claim(f,p['run_id']);assert again['state']=='UNKNOWN' and again['fetch_authorized'] is False and 'definition' not in again
    with psycopg.connect(f['admin']) as c:
        # Fixture advances the observed original lease, never runtime authority.
        c.execute("UPDATE oracle2.research_run_heads_v1 SET claim_deadline=clock_timestamp()-interval '1 second' WHERE run_id=%s",(p['run_id'],))
    fresh=invoke(f,'fetch','research_fetch_current_v1',UUID(first['run_id']),UUID(first['claim_id']))
    assert fresh['current'] is False and fresh['resend_authorized'] is False
    assert invoke(f,'read','research_status_v1')['state']=='UNKNOWN'
    assert pending(f)['state']=='existing'

def test_actual_success_has_retained_receipt_weekly_due_and_no_policy_or_semantic_claim(research):
    f=research;c=claim(f,pending(f)['run_id']);first=observe(f,c)
    assert first['state']=='observed' and observe(f,c)['state']=='duplicate'
    s=invoke(f,'read','research_status_v1')
    assert s['last_success'] is not None and not s['company_policy'] and not s['semantically_reviewed']
    assert datetime.fromisoformat(s['next_due'])-datetime.fromisoformat(s['last_success'])==timedelta(days=7)
    assert pending(f)['state']=='not_due'
    with pytest.raises(psycopg.errors.UniqueViolation):observe(f,c,body_sha256='f'*64)

@pytest.mark.parametrize('change',['config','revoked','role-borrow','root','selected-leaf','old-revision'])
def test_actual_research_current_admission_source_and_exact_path_refusals(research,change):
    f=research
    if change=='config':
        with pytest.raises(psycopg.errors.InsufficientPrivilege):invoke(f,'schedule','research_claim_due_v1',config='f'*64)
        return
    if change=='role-borrow':
        with pytest.raises(psycopg.errors.InsufficientPrivilege):invoke(f,'read','research_claim_due_v1')
        return
    with psycopg.connect(f['admin']) as c:
        if change=='revoked':c.execute('INSERT INTO oracle2.research_admission_revocations_v1(admission_id) VALUES(%s)',(f['admissions']['schedule'],))
        elif change in ('root','selected-leaf'):
            c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(f['root'] if change=='root' else f['leaves']['schedule'],))
            if change=='selected-leaf':
                c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                    (uuid4(),f['workspace'],f['actors']['schedule'],'research-schedule:'+str(f['source']),f['owner'],f['root'],f['until']))
        else:c.execute('INSERT INTO oracle2.research_registrations_v1 VALUES(%s,%s,2,%s,%s,clock_timestamp())',
            (f['workspace'],f['source'],Jsonb(f['definition']),hashlib.sha256(canonical_bytes(f['definition'])).hexdigest()))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):pending(f)
    with psycopg.connect(f['admin']) as c:
        assert c.execute('SELECT count(*) FROM oracle2.research_attempts_v1 WHERE workspace_id=%s',(f['workspace'],)).fetchone()==(0,)

def test_actual_unknown_remains_same_run_but_original_late_receipt_can_reconcile(research):
    f=research;c=claim(f,pending(f)['run_id'])
    assert observe(f,c,state='UNKNOWN',http_status=None,wire_sha256=None,wire_byte_count=None,body_sha256=None,body_byte_count=None,private_key=None,trace_sha256=None,trace_byte_count=None,trace_private_key=None,retrieved_at=None)['state']=='UNKNOWN'
    assert pending(f)['state']=='existing' and claim(f,c['run_id'])['fetch_authorized'] is False
    assert observe(f,c)['state']=='observed'
    with psycopg.connect(f['admin']) as connection:
        assert connection.execute("SELECT count(*) FROM oracle2.research_events_v1 WHERE run_id=%s AND kind IN('UNKNOWN','observed')",(c['run_id'],)).fetchone()==(2,)

@pytest.mark.parametrize('field',['state','wire_sha256','body_sha256','wire_byte_count','body_byte_count','http_status'])
def test_actual_malformed_json_null_never_becomes_success(research,field):
    f=research;c=claim(f,pending(f)['run_id'])
    with pytest.raises((psycopg.errors.InvalidParameterValue,psycopg.errors.NotNullViolation)):
        observe(f,c,**{field:None})
    assert pending(f)['state']=='existing'

def test_actual_private_tables_and_immutable_registration_cannot_be_runtime_written(research):
    f=research
    with psycopg.connect(f['credentials']['fetch']) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT * FROM oracle2.research_registrations_v1')
    with psycopg.connect(f['admin']) as c:
        with pytest.raises(psycopg.errors.RaiseException,match="append-only"):c.execute("UPDATE oracle2.research_registrations_v1 SET definition=definition||'{\"enabled\":false}' WHERE workspace_id=%s",(f['workspace'],))


def installed_core(f,directory,operation,*,fetch_profile=None,read_profile=None):
    """Independent invented fixture installer, never runtime issuance."""
    from pathlib import Path
    from oracle_brain.research.durable_authority_v1 import ResearchConfigV1,SIGNATURES,load_research_settings_v1,ResearchAuthorityV1
    directory.mkdir(mode=0o700)
    original=psycopg.conninfo.conninfo_to_dict(f['credentials'][operation]);ca=directory/'db-ca.pem'
    ca.write_bytes(Path(original['sslrootcert']).read_bytes());ca.chmod(0o600)
    url=directory/'connection';url.write_text(psycopg.conninfo.make_conninfo(f['credentials'][operation],hostaddr=original['host'],sslrootcert=str(ca)));url.chmod(0o600)
    admission=uuid4()
    with psycopg.connect(f['admin']) as connection:
        owner=connection.execute("SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='oracle2'").fetchone()[0]
        hashes=connection.execute("SELECT proname,encode(sha256(convert_to(prosrc,'UTF8')),'hex') FROM pg_proc WHERE oid IN(SELECT to_regprocedure(x) FROM unnest(%s::text[]) x)",(['oracle2.'+x for x in SIGNATURES],)).fetchall()
        issuer,reviewer=connection.execute('SELECT issuer_actor,reviewer_actor FROM oracle2.research_admissions_v1 WHERE admission_id=%s',(f['admissions'][operation],)).fetchone()
    config=ResearchConfigV1(schema_version=1,purpose='maintained-research-v1',admission_id=admission,
        principal_id=f['actors'][operation],workspace_id=f['workspace'],source_id=f['source'],source_revision=1,operation=operation,
        session_role=original['user'],expected_owner=owner,runtime_hash=RUNTIME,registry_hash=REGISTRY,
        issuer_actor=issuer,reviewer_actor=reviewer,
        database_url=dict(path=str(url),sha256=hashlib.sha256(url.read_bytes()).hexdigest()),
        database_ca=dict(path=str(ca),sha256=hashlib.sha256(ca.read_bytes()).hexdigest()),
        database_host=original['host'],database_hostaddr=original['host'],database_port=int(original['port']),database_name=original['dbname'],
        capability_body_hashes=tuple(sorted(hashes)),original_horizon=f['until'],expires_at=f['until'],fetch_profile=fetch_profile,read_profile=read_profile)
    raw=canonical_bytes(config.model_dump(mode='json'));path=directory/'research-config.json';path.write_bytes(raw);path.chmod(0o600)
    seal=hashlib.sha256(raw).hexdigest()
    with psycopg.connect(f['admin']) as connection:
        connection.execute('''INSERT INTO oracle2.research_admissions_v1 SELECT %s,role_name,principal_id,workspace_id,source_id,source_revision,
            operation,membership_appointment,runtime_hash,registry_hash,%s,issuer_actor,reviewer_actor,issued_at,original_horizon,expires_at
            FROM oracle2.research_admissions_v1 WHERE admission_id=%s''',(admission,seal,f['admissions'][operation]))
    return ResearchAuthorityV1(load_research_settings_v1(path,seal))


def test_actual_core_uses_private_pins_real_sql_role_and_unknown_no_body_replay(research,tmp_path):
    import time
    from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
    f=research;scheduler=installed_core(f,tmp_path/'schedule','schedule');worker=installed_core(f,tmp_path/'fetch','fetch')
    deadline=datetime.now(timezone.utc)+timedelta(seconds=20)
    with _request_fence_v1(float(time.monotonic()+20)):
        scheduled=scheduler.schedule_due_v1(deadline=deadline)
        first=worker.claim_fetch_v1(UUID(scheduled['run_id']),deadline=deadline)
        assert first['fetch_authorized'] is True and first['definition']==f['definition']
        assert worker.current_fetch_v1(UUID(first['run_id']),UUID(first['claim_id']),deadline=deadline)<=deadline
        repeated=worker.claim_fetch_v1(UUID(first['run_id']),deadline=deadline)
        assert repeated['fetch_authorized'] is False and 'definition' not in repeated


def test_actual_core_short_original_window_refuses_before_connect(research,tmp_path,monkeypatch):
    import time
    from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
    core=installed_core(research,tmp_path/'schedule','schedule')
    def forbidden(*args,**kwargs):raise AssertionError('libpq cannot fit its two-second minimum')
    monkeypatch.setattr(psycopg,'connect',forbidden)
    with _request_fence_v1(float(time.monotonic()+1.5)):
        with pytest.raises(PermissionError,match='too short'):
            core.schedule_due_v1(deadline=datetime.now(timezone.utc)+timedelta(seconds=1.5))


def test_actual_time_sensitive_force_cannot_reclaim_unknown_or_reset_spent_retry_budget(research):
    f=research;c=claim(f,pending(f)['run_id'])
    assert invoke(f,'schedule','research_force_due_v1')['state']=='existing'
    assert pending(f)['run_id']==c['run_id']
    with psycopg.connect(f['admin']) as connection:
        connection.execute('UPDATE oracle2.research_state_v1 SET inflight=NULL,attempts=4,exhausted=true,next_due=clock_timestamp()+interval \'7 days\' WHERE workspace_id=%s',(f['workspace'],))
    assert invoke(f,'schedule','research_force_due_v1')['state']=='exhausted'
    assert pending(f)['state']=='not_due'


def test_actual_core_revocation_after_committed_close_withholds_claim_and_keeps_unknown(research,tmp_path,monkeypatch):
    import time
    from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
    from oracle_brain.research.durable_authority_v1 import ResearchOutcomeUnknown
    f=research;p=pending(f);worker=installed_core(f,tmp_path/'fetch','fetch');real=psycopg.connect;calls=[]
    class ObservedConnection:
        def __init__(self,connection,first):self.connection,self.first=connection,first
        def __getattr__(self,name):return getattr(self.connection,name)
        def __enter__(self):return self.connection.__enter__()
        def __exit__(self,*args):
            value=self.connection.__exit__(*args)
            if self.first:
                with real(f['admin']) as admin:
                    admin.execute('INSERT INTO oracle2.research_admission_revocations_v1(admission_id) VALUES(%s)',(worker.settings.config.admission_id,))
            return value
    def connect(*args,**kwargs):
        actual=real(*args,**kwargs);calls.append(actual)
        return ObservedConnection(actual,len(calls)==1)
    monkeypatch.setattr(psycopg,'connect',connect)
    with _request_fence_v1(float(time.monotonic()+20)):
        with pytest.raises(ResearchOutcomeUnknown):
            worker.claim_fetch_v1(UUID(p['run_id']),deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
    assert len(calls)==2 and all(c.closed for c in calls)
    with real(f['admin']) as connection:
        assert connection.execute('SELECT state FROM oracle2.research_run_heads_v1 WHERE run_id=%s',(p['run_id'],)).fetchone()==('INFLIGHT',)


def installed_fetcher(f,directory,certificates):
    from oracle_brain.research.maintained_fetch_v1 import ResearchNetworkProfileV1,MaintainedResearchFetcherV1
    directory.mkdir(mode=0o700);storage=directory/'private';storage.mkdir(mode=0o700)
    ca=directory/'publisher-ca.pem';ca.write_bytes((certificates/'ca.pem').read_bytes());ca.chmod(0o600)
    stat=storage.stat()
    profile=ResearchNetworkProfileV1(schema_version=1,purpose='registered-public-research-get-v1',workspace_id=f['workspace'],source_id=f['source'],
        source_revision=1,registered_url=f['definition']['url'],ca_path=str(ca),ca_sha256=hashlib.sha256(ca.read_bytes()).hexdigest(),
        storage_root=str(storage),storage_dev=stat.st_dev,storage_ino=stat.st_ino,storage_uid=stat.st_uid,
        original_horizon=f['until'],expires_at=f['until'])
    raw=canonical_bytes(profile.model_dump(mode='json'));path=directory/'source-network.json';path.write_bytes(raw);path.chmod(0o600)
    core=installed_core(f,directory/'core','fetch',fetch_profile=dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest()))
    return MaintainedResearchFetcherV1(core),storage


def test_actual_sql_factory_retains_owned_tls_bytes_before_receipt_and_never_repeats_claim(research,tmp_path,certificates,monkeypatch):
    # Explicit separately owned loopback adapter; actual production public-DNS
    # owner is unmodified and its private-target refusal has its own test.
    import time,json
    from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
    from test_research_public_wire import read_owned,BODY
    f=research;run=UUID(pending(f)['run_id']);factory,storage=installed_fetcher(f,tmp_path/'factory',certificates);calls=[]
    def owned_fetch(*,caller_deadline):
        calls.append(caller_deadline)
        return ((f['definition']['url'],read_owned(certificates,'chunked')),)
    monkeypatch.setattr(factory._transport,'fetch',owned_fetch)
    with _request_fence_v1(float(time.monotonic()+25)):
        deadline=datetime.now(timezone.utc)+timedelta(seconds=25)
        assert factory.execute_v1(run,deadline=deadline)['state']=='observed'
        assert factory.execute_v1(run,deadline=deadline)['state']=='UNKNOWN'
    assert len(calls)==1
    with psycopg.connect(f['admin']) as c:
        row=c.execute("SELECT payload->'observation' FROM oracle2.research_events_v1 WHERE run_id=%s AND kind='observed'",(run,)).fetchone()[0]
        assert c.execute('SELECT state FROM oracle2.research_run_heads_v1 WHERE run_id=%s',(run,)).fetchone()==('observed',)
    raw=(storage/row['trace_private_key']).read_bytes();assert hashlib.sha256(raw).hexdigest()==row['trace_sha256']
    trace=json.loads(raw);assert trace['semantically_reviewed'] is False and trace['company_policy'] is False
    assert (storage/trace['hops'][0]['body_private_key']).read_bytes()==BODY
    assert b'Transfer-Encoding: chunked' in (storage/row['private_key']).read_bytes()


def test_actual_factory_lost_receipt_reconciles_same_private_bytes_without_network_or_new_claim(research,tmp_path,certificates,monkeypatch):
    import time
    from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
    from oracle_brain.research.durable_authority_v1 import ResearchOutcomeUnknown
    from test_research_public_wire import read_owned
    f=research;run=UUID(pending(f)['run_id']);factory,storage=installed_fetcher(f,tmp_path/'factory',certificates);calls=[]
    def owned_fetch(*,caller_deadline):
        calls.append(1);return ((f['definition']['url'],read_owned(certificates)),)
    monkeypatch.setattr(factory._transport,'fetch',owned_fetch)
    actual=factory._authority.observe_fetch_v1
    def lost(*args,**kwargs):
        actual(*args,**kwargs)
        raise ResearchOutcomeUnknown('invented lost post-commit receipt')
    monkeypatch.setattr(factory._authority,'observe_fetch_v1',lost)
    with _request_fence_v1(float(time.monotonic()+25)):
        deadline=datetime.now(timezone.utc)+timedelta(seconds=25)
        with pytest.raises(ResearchOutcomeUnknown):factory.execute_v1(run,deadline=deadline)
    monkeypatch.setattr(factory._authority,'observe_fetch_v1',actual)
    with _request_fence_v1(float(time.monotonic()+25)):
        assert factory.reconcile_retained_v1(run,deadline=datetime.now(timezone.utc)+timedelta(seconds=25))['state']=='duplicate'
    assert len(calls)==1
    with psycopg.connect(f['admin']) as c:
        assert c.execute("SELECT count(*) FROM oracle2.research_events_v1 WHERE run_id=%s AND kind='claimed'",(run,)).fetchone()==(1,)
        assert c.execute('SELECT state FROM oracle2.research_run_heads_v1 WHERE run_id=%s',(run,)).fetchone()==('observed',)


def test_actual_factory_partial_response_unknown_keeps_bounded_wire_without_retry(research,tmp_path,certificates,monkeypatch):
    import time
    from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
    from oracle_brain.research.durable_authority_v1 import ResearchOutcomeUnknown
    from test_research_public_wire import read_owned
    f=research;run=UUID(pending(f)['run_id']);factory,storage=installed_fetcher(f,tmp_path/'factory',certificates);calls=[]
    def owned_fetch(*,caller_deadline):calls.append(1);return read_owned(certificates,'truncated')
    monkeypatch.setattr(factory._transport,'fetch',owned_fetch)
    with _request_fence_v1(float(time.monotonic()+25)):
        deadline=datetime.now(timezone.utc)+timedelta(seconds=25)
        with pytest.raises(ResearchOutcomeUnknown):factory.execute_v1(run,deadline=deadline)
        assert factory.execute_v1(run,deadline=deadline)['state']=='UNKNOWN'
    assert len(calls)==1
    partial=list(storage.rglob('*.partial.wire'));assert len(partial)==1 and partial[0].read_bytes().startswith(b'HTTP/1.1 200')
    with psycopg.connect(f['admin']) as c:
        assert c.execute('SELECT state FROM oracle2.research_run_heads_v1 WHERE run_id=%s',(run,)).fetchone()==('UNKNOWN',)
    with _request_fence_v1(float(time.monotonic()+20)):
        with pytest.raises(ResearchOutcomeUnknown):factory.reconcile_retained_v1(run,deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
    assert len(calls)==1


def installed_reader(f,directory,storage):
    from oracle_brain.research.maintained_read_v1 import ResearchReadProfileV1,MaintainedResearchReaderV1
    directory.mkdir(mode=0o700);info=storage.stat()
    p=ResearchReadProfileV1(schema_version=1,purpose='retained-industry-reference-read-v1',workspace_id=f['workspace'],source_id=f['source'],
        source_revision=1,storage_root=str(storage),storage_dev=info.st_dev,storage_ino=info.st_ino,storage_uid=info.st_uid,
        original_horizon=f['until'],expires_at=f['until'])
    raw=canonical_bytes(p.model_dump(mode='json'));path=directory/'reader.json';path.write_bytes(raw);path.chmod(0o600)
    a=installed_core(f,directory/'core','read',read_profile=dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest()))
    return MaintainedResearchReaderV1(a)


def test_actual_reference_reader_separate_role_actual_bytes_current_revocation_and_no_invented_metadata(research,tmp_path,certificates,monkeypatch):
    import time
    from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
    from test_research_public_wire import read_owned,BODY
    f=research;run=UUID(pending(f)['run_id']);factory,storage=installed_fetcher(f,tmp_path/'factory',certificates)
    monkeypatch.setattr(factory._transport,'fetch',lambda **kw:((f['definition']['url'],read_owned(certificates)),))
    reader=installed_reader(f,tmp_path/'reader',storage)
    with _request_fence_v1(float(time.monotonic()+25)):
        deadline=datetime.now(timezone.utc)+timedelta(seconds=25)
        factory.execute_v1(run,deadline=deadline)
        result=reader.latest_v1(deadline=deadline)
    assert result['original_text']==BODY.decode() and result['reference']['content_sha256']==hashlib.sha256(BODY).hexdigest()
    assert result['reference']['source_version'] is result['reference']['publication_date'] is result['reference']['reviewed_at'] is None
    assert result['reference']['applicability']=='UNKNOWN' and result['company_policy'] is result['semantically_reviewed'] is False
    with psycopg.connect(f['admin']) as c:c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(f['leaves']['read'],))
    def forbidden(*args,**kwargs):raise AssertionError('revoked reader cannot open private original bytes')
    monkeypatch.setattr('oracle_brain.research.maintained_read_v1._read_private_at',forbidden)
    with _request_fence_v1(float(time.monotonic()+20)):
        with pytest.raises(PermissionError):reader.latest_v1(deadline=datetime.now(timezone.utc)+timedelta(seconds=20))


def test_actual_reference_body_tamper_is_withheld_and_never_fetches_again(research,tmp_path,certificates,monkeypatch):
    import time,json
    from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
    from test_research_public_wire import read_owned
    f=research;run=UUID(pending(f)['run_id']);factory,storage=installed_fetcher(f,tmp_path/'factory',certificates);calls=[]
    def fetch(**kwargs):calls.append(1);return ((f['definition']['url'],read_owned(certificates)),)
    monkeypatch.setattr(factory._transport,'fetch',fetch);reader=installed_reader(f,tmp_path/'reader',storage)
    with _request_fence_v1(float(time.monotonic()+25)):
        deadline=datetime.now(timezone.utc)+timedelta(seconds=25);factory.execute_v1(run,deadline=deadline)
        trace=json.loads(next(storage.rglob('*.trace.json')).read_bytes())
        (storage/trace['hops'][-1]['body_private_key']).write_bytes(b'invented tamper')
        with pytest.raises(PermissionError,match='seal changed'):reader.latest_v1(deadline=deadline)
    assert calls==[1]


@pytest.mark.parametrize('research',[{'access':'licensed','rights_confirmed':False}],indirect=True)
def test_actual_licensed_gap_visible_without_private_original_or_network(research,tmp_path,monkeypatch):
    import time
    from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
    f=research;storage=tmp_path/'private';storage.mkdir(mode=0o700);reader=installed_reader(f,tmp_path/'reader',storage)
    def forbidden(*args,**kwargs):raise AssertionError('licensed gap grants no original read')
    monkeypatch.setattr('oracle_brain.research.maintained_read_v1._read_private_at',forbidden)
    with _request_fence_v1(float(time.monotonic()+20)):
        result=reader.latest_v1(deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
    assert result['refresh']['state']=='rights_gap' and result['state']=='unavailable' and result['reference'] is result['original_text'] is None
    with pytest.raises(psycopg.errors.InsufficientPrivilege):pending(f)


@pytest.mark.parametrize('stamp',['2000-01-01T00:00:00Z','2999-01-01T00:00:00Z','2026-01-01','2026-13-01T00:00:00Z',None])
def test_actual_forged_or_non_utc_retrieval_time_never_freshens_reference(research,stamp):
    f=research;c=claim(f,pending(f)['run_id'])
    with pytest.raises((psycopg.errors.InvalidParameterValue,psycopg.errors.DatetimeFieldOverflow)):
        observe(f,c,retrieved_at=stamp)
    assert invoke(f,'read','research_status_v1')['last_success'] is None
    assert pending(f)['state']=='existing'


def test_actual_delayed_receipt_retains_original_retrieval_time_for_freshness(research):
    import time
    f=research;c=claim(f,pending(f)['run_id'])
    retrieved=datetime.now(timezone.utc)
    time.sleep(.03)
    assert observe(f,c,retrieved_at=retrieved.isoformat())['state']=='observed'
    status=invoke(f,'read','research_status_v1')
    assert datetime.fromisoformat(status['last_success'])==retrieved
    assert datetime.fromisoformat(status['next_due'])==retrieved+timedelta(days=7)
    with psycopg.connect(f['admin']) as connection:
        recorded=connection.execute("SELECT recorded_at FROM oracle2.research_events_v1 WHERE run_id=%s AND kind='observed'",(c['run_id'],)).fetchone()[0]
    assert recorded-retrieved>=timedelta(seconds=.03)


from contextlib import contextmanager

@contextmanager
def research_listener(authority,directory,certificates):
    """Independent invented fixture issuer. Real listener, peer and SQL owner."""
    import subprocess,threading
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import Encoding
    from oracle_brain.hosting.research_service_v1 import ResearchPeerV1,protected_research_server_v1
    directory.mkdir(mode=0o700);c=authority.settings.config
    uri='spiffe://oracle/research/'+c.operation+'/invented-fixture'
    def openssl(*args):subprocess.run(['openssl',*args],cwd=directory,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    openssl('req','-newkey','rsa:2048','-nodes','-keyout','client.key','-out','client.csr','-subj','/CN=InventedResearchPeer')
    (directory/'client.ext').write_text('subjectAltName=URI:'+uri+'\nextendedKeyUsage=clientAuth\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer')
    openssl('x509','-req','-in','client.csr','-CA',str(certificates/'ca.pem'),'-CAkey',str(certificates/'ca.key'),'-CAserial',str(certificates/'ca.srl'),'-out','client.pem','-days','1','-extfile','client.ext')
    def pin(name):
        path=directory/name;path.write_bytes((certificates/name).read_bytes());path.chmod(0o600)
        return str(path),hashlib.sha256(path.read_bytes()).hexdigest()
    cert,certsha=pin('server.pem');key,keysha=pin('server.key');ca,casha=pin('ca.pem')
    for path in directory.iterdir():path.chmod(0o600)
    der=x509.load_pem_x509_certificate((directory/'client.pem').read_bytes()).public_bytes(Encoding.DER)
    now=datetime.now(timezone.utc)
    p=ResearchPeerV1(schema_version=1,purpose='maintained-research-service-peer-v1',operation=c.operation,
        research_config_sha256=authority.settings.config_sha256,principal_id=c.principal_id,workspace_id=c.workspace_id,source_id=c.source_id,
        source_revision=c.source_revision,runtime_hash=c.runtime_hash,registry_hash=c.registry_hash,
        client_uri=uri,client_certificate_sha256=hashlib.sha256(der).hexdigest(),listen_host='127.0.0.1',listen_port=0,server_hostname='localhost',
        server_certificate_file=cert,server_certificate_sha256=certsha,server_key_file=key,server_key_sha256=keysha,
        client_ca_file=ca,client_ca_sha256=casha,issuer_actor=c.issuer_actor,reviewer_actor=c.reviewer_actor,
        valid_from=now-timedelta(seconds=1),expires_at=c.expires_at,original_horizon=c.original_horizon)
    raw=canonical_bytes(p.model_dump(mode='json'));path=directory/'peer.json';path.write_bytes(raw);path.chmod(0o600)
    server=protected_research_server_v1(authority.settings,path,hashlib.sha256(raw).hexdigest())
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01});thread.start()
    try:yield server,directory,path
    finally:
        server.shutdown();server.server_close();thread.join(2)
        assert not thread.is_alive() and not server._active and server.socket.fileno()==-1


def research_http(server,directory,operation,*,run_id=None,identity=None,seconds=20,changes=None):
    import http.client,ssl
    context=ssl.create_default_context(cafile=str(directory/'ca.pem'))
    prefix=directory/'client' if identity is None else identity
    context.load_cert_chain(str(prefix)+'.pem',str(prefix)+'.key')
    payload=dict(schema_version=1,operation=operation,run_id=str(run_id) if run_id else None,
        caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat())
    payload.update(changes or {})
    connection=http.client.HTTPSConnection('localhost',server.server_port,context=context,timeout=25)
    try:
        connection.request('POST','/v1/replacement/research',body=canonical_bytes(payload),headers={'Content-Type':'application/json'})
        response=connection.getresponse();body=response.read()
        return response.status,body,dict(response.getheaders())
    finally:connection.close()


def test_actual_research_mtls_scheduler_one_pending_and_purpose_peer_window_refusals(research,tmp_path,certificates):
    import json
    f=research;a=installed_core(f,tmp_path/'core','schedule')
    with research_listener(a,tmp_path/'listener',certificates) as (server,tls,profile):
        # Actual trusted but unrelated certificate is denied before an attempt.
        assert research_http(server,tls,'tick',identity=certificates/'other')[0]==503
        assert research_http(server,tls,'status')[0]==503
        assert research_http(server,tls,'tick',changes={'actor':str(uuid4())})[0]==503
        assert research_http(server,tls,'tick',seconds=-1)[0]==503
        with psycopg.connect(f['admin']) as connection:
            assert connection.execute('SELECT count(*) FROM oracle2.research_attempts_v1 WHERE workspace_id=%s',(f['workspace'],)).fetchone()==(0,)
        first=research_http(server,tls,'tick');assert first[0]==200
        body=json.loads(first[1]);assert body['state']=='pending' and body['dispatch_authorized'] is True
        second=research_http(server,tls,'tick');assert second[0]==200
        other=json.loads(second[1]);assert other['run_id']==body['run_id'] and other['state']=='existing' and other['dispatch_authorized'] is False
        assert first[2]['Cache-Control']=='no-store'
        profile.write_bytes(profile.read_bytes()+b' ')
        assert research_http(server,tls,'tick')[0]==503
    with psycopg.connect(f['admin']) as connection:
        assert connection.execute('SELECT count(*) FROM oracle2.research_attempts_v1 WHERE workspace_id=%s',(f['workspace'],)).fetchone()==(1,)


def test_actual_research_mtls_fetch_then_separate_read_original_bytes_and_revocation(research,tmp_path,certificates,monkeypatch):
    import json
    from test_research_public_wire import read_owned,BODY
    from oracle_brain.research.fetch import _InstalledResearchGET
    f=research;run=UUID(pending(f)['run_id']);factory,storage=installed_fetcher(f,tmp_path/'fetch',certificates);calls=[]
    # Explicit invented transport composition only: real owned wire response,
    # not qualification of public DNS, real publisher rights or installation.
    def owned_fetch(self,**kwargs):calls.append(1);return ((f['definition']['url'],read_owned(certificates)),)
    monkeypatch.setattr(_InstalledResearchGET,'fetch',owned_fetch)
    with research_listener(factory._authority,tmp_path/'fetch-listener',certificates) as (server,tls,_):
        assert research_http(server,tls,'reference')[0]==503 and calls==[]
        assert research_http(server,tls,'fetch',run_id=run)[0]==200
        again=research_http(server,tls,'fetch',run_id=run)
        assert again[0]==200 and json.loads(again[1])['state']=='UNKNOWN' and len(calls)==1
    reader=installed_reader(f,tmp_path/'read',storage)
    with research_listener(reader._authority,tmp_path/'read-listener',certificates) as (server,tls,_):
        result=research_http(server,tls,'reference');assert result[0]==200
        body=json.loads(result[1]);assert body['original_text']==BODY.decode() and body['reference']['applicability']=='UNKNOWN'
        assert body['semantically_reviewed'] is body['company_policy'] is False
        assert research_http(server,tls,'fetch',run_id=run)[0]==503 and len(calls)==1
        with psycopg.connect(f['admin']) as connection:
            connection.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(f['leaves']['read'],))
        assert research_http(server,tls,'reference')[0]==503 and len(calls)==1


@pytest.mark.parametrize('changes',[{'actor':str(uuid4())},{'source_id':str(uuid4())},{'url':'https://unappointed.example.test'},
    {'schema_version':True},{'operation':'fetch'},{'run_id':str(uuid4())},{'caller_deadline':'tomorrow'}])
def test_closed_research_service_original_request_refuses_extra_authority_or_invalid_shape(changes):
    from oracle_brain.hosting.research_service_v1 import parse_research_request_v1
    value=dict(schema_version=1,operation='tick',run_id=None,caller_deadline=datetime.now(timezone.utc).isoformat());value.update(changes)
    with pytest.raises((PermissionError,ValueError)):parse_research_request_v1(canonical_bytes(value))


def test_closed_research_service_preserves_original_utc_bytes_without_renewing_window():
    from oracle_brain.hosting.research_service_v1 import parse_research_request_v1
    value=dict(schema_version=1,operation='tick',run_id=None,caller_deadline='2026-01-01T00:00:00Z')
    raw=canonical_bytes(value);q=parse_research_request_v1(raw)
    assert q.caller_deadline==datetime(2026,1,1,tzinfo=timezone.utc)
    assert raw==canonical_bytes(value)
    with pytest.raises((PermissionError,ValueError)):parse_research_request_v1(raw.replace(b'"schema_version":1',b'"schema_version":1,"schema_version":1'))


def test_actual_queue_outage_reconciliation_only_existing_pending_id_never_reclaims_fetch(research,tmp_path):
    import time
    from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
    f=research;a=installed_core(f,tmp_path/'scheduler','schedule')
    with _request_fence_v1(float(time.monotonic()+20)):
        deadline=datetime.now(timezone.utc)+timedelta(seconds=20)
        assert a.pending_queue_v1(deadline=deadline)['state']=='idle'
        first=a.schedule_due_v1(deadline=deadline);run=first['run_id']
        # An unavailable external queue has made no fetch claim or receipt.
        for _ in range(2):
            queued=a.pending_queue_v1(deadline=deadline)
            assert queued['run_id']==run and queued['queue_authorized'] is True and queued['fetch_authorized'] is False
    original=claim(f,run)
    with _request_fence_v1(float(time.monotonic()+20)):
        value=a.pending_queue_v1(deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
        assert value['run_id']==run and value['state']=='INFLIGHT' and value['queue_authorized'] is value['fetch_authorized'] is False
    assert claim(f,run)['fetch_authorized'] is False
    with psycopg.connect(f['admin']) as connection:
        assert connection.execute("SELECT count(*) FROM oracle2.research_events_v1 WHERE run_id=%s AND kind='claimed'",(run,)).fetchone()==(1,)
        assert connection.execute('SELECT claim_id FROM oracle2.research_run_heads_v1 WHERE run_id=%s',(run,)).fetchone()==(UUID(original['claim_id']),)



@pytest.mark.parametrize('suffix,value',[('FILE','relative.json'),('SHA256','UPPER'),('SHA256','0'*63)])
def test_fixed_research_startup_requires_independent_absolute_pinned_files(monkeypatch,suffix,value):
    from oracle_brain.hosting.research_main_v1 import _installed_pair
    monkeypatch.setenv('ORACLE2_RESEARCH_CONFIG_FILE','/invented/not-installed.json')
    monkeypatch.setenv('ORACLE2_RESEARCH_CONFIG_SHA256','a'*64)
    monkeypatch.setenv('ORACLE2_RESEARCH_CONFIG_'+suffix,value)
    with pytest.raises(PermissionError):_installed_pair('ORACLE2_RESEARCH_CONFIG')


def test_actual_research_process_missing_installation_has_no_listener_or_secret_output(tmp_path):
    import subprocess,sys,os
    env={k:v for k,v in os.environ.items() if not k.startswith('ORACLE2_RESEARCH_')}
    from pathlib import Path
    env['PYTHONPATH']=str(Path(__file__).resolve().parents[1])
    result=subprocess.run([sys.executable,'-m','oracle_brain.hosting.research_main_v1'],cwd=tmp_path,env=env,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
    assert result.returncode!=0 and result.stdout==b''
    assert result.stderr==b'Research service unavailable\n'


def test_actual_fixed_research_process_starts_from_exact_installed_pins_and_stops_cleanly(research,tmp_path,certificates):
    import subprocess,sys,os,time
    from pathlib import Path
    a=installed_core(research,tmp_path/'core','schedule')
    with research_listener(a,tmp_path/'listener',certificates) as (_,_,peer):
        env={k:v for k,v in os.environ.items() if not k.startswith('ORACLE2_RESEARCH_')}
        env.update(PYTHONPATH=str(Path(__file__).resolve().parents[1]),ORACLE2_RESEARCH_CONFIG_FILE=a.settings.config_path,
            ORACLE2_RESEARCH_CONFIG_SHA256=a.settings.config_sha256,ORACLE2_RESEARCH_PEER_FILE=str(peer),
            ORACLE2_RESEARCH_PEER_SHA256=hashlib.sha256(peer.read_bytes()).hexdigest())
        process=subprocess.Popen([sys.executable,'-m','oracle_brain.hosting.research_main_v1'],cwd=tmp_path,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            end=time.monotonic()+5;listening=False
            while time.monotonic()<end and process.poll() is None:
                try:listening=any(os.readlink(p).startswith('socket:[') for p in Path('/proc',str(process.pid),'fd').iterdir())
                except FileNotFoundError:pass
                if listening:break
                time.sleep(.02)
            assert listening and process.poll() is None
            process.terminate();out,err=process.communicate(timeout=5)
            assert process.returncode==0 and out==err==b''
            assert not Path('/proc',str(process.pid)).exists()
        finally:
            if process.poll() is None:process.kill();process.communicate(timeout=5)




def test_actual_incomplete_redirect_chain_retains_each_original_response_and_never_becomes_reference(research,tmp_path,certificates,monkeypatch):
    import time,json
    from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
    from oracle_brain.research.durable_authority_v1 import ResearchOutcomeUnknown
    from oracle_brain.research.fetch import ResearchTransportUnknown
    from test_research_public_wire import read_owned
    f=research;run=UUID(pending(f)['run_id']);factory,storage=installed_fetcher(f,tmp_path/'factory',certificates);calls=[];original=[]
    def owned_fetch(**kwargs):
        calls.append(1);first=read_owned(certificates,'redirect');original.append(first)
        try:read_owned(certificates,'truncated')
        except ResearchTransportUnknown as error:
            error.prior_responses=((f['definition']['url'],first),);error.failed_url='https://industry.example.test/next';raise
        raise AssertionError('truncated wire must refuse')
    monkeypatch.setattr(factory._transport,'fetch',owned_fetch)
    with _request_fence_v1(float(time.monotonic()+25)):
        deadline=datetime.now(timezone.utc)+timedelta(seconds=25)
        with pytest.raises(ResearchOutcomeUnknown):factory.execute_v1(run,deadline=deadline)
        assert factory.execute_v1(run,deadline=deadline)['state']=='UNKNOWN'
    assert calls==[1]
    trace=json.loads(next(storage.rglob('*.partial.trace.json')).read_bytes())
    assert trace['purpose']=='incomplete-research-http-custody-v1' and trace['resend_authorized'] is False
    assert len(trace['completed_hops'])==1 and trace['failed_url']=='https://industry.example.test/next'
    first=trace['completed_hops'][0]
    assert (storage/first['wire_private_key']).read_bytes()==original[0].wire
    assert (storage/first['body_private_key']).read_bytes()==original[0].body
    partial=(storage/trace['partial_wire_private_key']).read_bytes()
    assert hashlib.sha256(partial).hexdigest()==trace['partial_wire_sha256']
    assert invoke(f,'read','research_latest_reference_v1')['state']=='unavailable'
    with psycopg.connect(f['admin']) as connection:
        assert connection.execute("SELECT count(*) FROM oracle2.research_events_v1 WHERE run_id=%s AND kind='claimed'",(run,)).fetchone()==(1,)



def test_actual_urgency_consumer_due_existing_and_exhausted_closed_responses(research,tmp_path):
    import time
    from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
    f=research;a=installed_core(f,tmp_path/'core','schedule')
    with _request_fence_v1(float(time.monotonic()+25)):
        deadline=datetime.now(timezone.utc)+timedelta(seconds=25)
        due=a.force_due_v1(deadline=deadline);assert due['state']=='due' and 'run_id' not in due
        for attempt in range(4):
            p=a.schedule_due_v1(deadline=deadline)
            existing=a.force_due_v1(deadline=deadline)
            assert existing['state']=='existing' and existing['run_id']==p['run_id']
            c=claim(f,p['run_id']);observe(f,c,state='known_failure',http_status=404)
            force=a.force_due_v1(deadline=deadline)
            assert force['state']==('exhausted' if attempt==3 else 'due')
            assert force['dispatch_authorized'] is False
        assert a.pending_queue_v1(deadline=deadline)['state']=='idle'
    with psycopg.connect(f['admin']) as connection:
        assert connection.execute('SELECT count(*) FROM oracle2.research_attempts_v1 WHERE workspace_id=%s',(f['workspace'],)).fetchone()==(4,)


def test_actual_urgency_mtls_route_uses_same_closed_due_and_existing_states(research,tmp_path,certificates):
    import json
    a=installed_core(research,tmp_path/'core','schedule')
    with research_listener(a,tmp_path/'listener',certificates) as (server,tls,_):
        first=research_http(server,tls,'force');assert first[0]==200 and json.loads(first[1])['state']=='due'
        p=research_http(server,tls,'tick');assert p[0]==200
        next=research_http(server,tls,'force');assert next[0]==200
        assert json.loads(next[1])['state']=='existing' and json.loads(next[1])['run_id']==json.loads(p[1])['run_id']
