"""Offline fixture mechanics only: recording SQL, no DB/TLS/Next authority.

Actual role/current-source behavior remains covered by the retained45 SQL cases.
These checks never open a socket or substitute a production permission guard.
"""
from contextlib import contextmanager
from datetime import datetime,timezone
from types import SimpleNamespace
from uuid import uuid4
import re

import psycopg
import pytest

import test_recommendation_actions_sql as setup


class SetupFailure(RuntimeError):
    pass


class RecordingSetup:
    def __init__(self,*,failure=None):
        self.failure=failure
        self.events=[]
        self.pending=[]
        self.committed=[]
        self.connections=0
        self.constructed=[]
        self.owner=uuid4()
        self.fingerprints=tuple(sorted((signature.split('(')[0],'a'*64,'b'*64)
            for signature in setup.FUNCTIONS))
        self.closed=False

    def execute(self,query,params=()):
        assert not self.closed
        text=query.as_string() if hasattr(query,'as_string') else query
        self.events.append(('sql',text,params))
        if text.startswith('SELECT actor_id FROM oracle2.appointments'):
            return SimpleNamespace(fetchone=lambda:(self.owner,))
        if text.startswith('SELECT p.proname'):
            return SimpleNamespace(fetchall=lambda:list(self.fingerprints))
        if text.startswith('INSERT INTO oracle2.recommendation_action_admissions_v1'):
            if self.failure=='third-admission' and len(self.pending)==2:
                raise SetupFailure('invented third operation setup failure')
            self.pending.append(params)
        return SimpleNamespace()

    @contextmanager
    def admin(self,url):
        assert url=='invented-owned-admin'
        self.connections+=1
        assert self.connections==1, 'setup must never retry or fall back'
        # The existing real admin owner is unchanged; these are recording events,
        # not a claim that this offline test proved an actual TLS/role/DB check.
        self.events.extend([('owned-guard',),('tls-session-db-check',),('begin',)])
        try:
            try:
                yield self
            except BaseException:
                self.pending.clear()
                self.events.append(('rollback',))
                raise
            else:
                self.events.append(('commit-attempt',))
                if self.failure=='commit':
                    raise SetupFailure('invented commit acknowledgement failure')
                self.committed=list(self.pending)
                self.events.append(('committed',))
        finally:
            self.closed=True
            self.events.append(('closed',))
            if self.failure=='close':
                raise SetupFailure('invented close failure after commit')

    def construct(self,original,stage,operation,login,aid,fingerprints):
        assert self.closed and self.committed
        assert self.events[-1][0]=='closed' or self.events[-1][0]=='construct'
        assert fingerprints==self.fingerprints
        self.constructed.append(operation)
        self.events.append(('construct',operation))
        return original(stage,operation,login,aid,fingerprints)


@pytest.fixture
def stage(tmp_path):
    ca=tmp_path/'invented-ca.pem'
    ca.write_bytes(b'invented fixture CA bytes; never used for a connection')
    ca.chmod(0o600)
    original_expiry=datetime(2030,1,1,tzinfo=timezone.utc)
    workspace,actor,model=uuid4(),uuid4(),uuid4()
    reference={'workspace_id':str(workspace),'source_id':str(uuid4()),'revision':1,
        'original_sha256':'1'*64,'reading_sha256':'2'*64,'parser_id':'invented'}
    return dict(login='invented_compiler',schema_owner='oracle2_admin',f=dict(
        root=uuid4(),workspace=workspace,actor=actor,model=model,expiry=original_expiry,
        all_refs=(SimpleNamespace(model_dump=lambda **kwargs:reference),),
        url=psycopg.conninfo.make_conninfo(host='127.0.0.1',port='5432',dbname='invented',
            user='invented_compiler',password='invented-compiler-only',
            sslmode='verify-full',sslrootcert=str(ca))))


def install_recording(monkeypatch,recording):
    original=setup._installed_advice_authority_v1
    monkeypatch.setattr(setup,'admin',recording.admin)
    monkeypatch.setattr(setup,'_installed_advice_authority_v1',
        lambda *args:recording.construct(original,*args))
    def no_socket(*args,**kwargs):
        raise AssertionError('offline setup regression must never connect')
    monkeypatch.setattr(psycopg,'connect',no_socket)


def test_all_four_independent_bindings_follow_one_final_catalog_commit_and_close(stage,monkeypatch):
    recording=RecordingSetup()
    install_recording(monkeypatch,recording)
    authorities=setup._install_all_advice_authorities_v1('invented-owned-admin',stage)
    assert tuple(a.binding.operation for a in authorities)==('register','read','feedback','measurement')
    assert recording.connections==1 and len(recording.committed)==4
    assert len({a.binding.session_login for a in authorities})==4
    assert len({a.binding.appointment_id for a in authorities})==4
    assert len({row[9] for row in recording.committed})==4
    assert len({row[11] for row in recording.committed})==4
    assert len({row[12] for row in recording.committed})==4
    assert all(row[11]!=row[12] and row[11]!=stage['f']['actor'] and row[12]!=stage['f']['actor']
        for row in recording.committed)
    for authority,row in zip(authorities,recording.committed,strict=True):
        binding=authority.binding
        assert row[0]==binding.appointment_id and row[1]==binding.session_login
        assert row[2:5]==(binding.principal_id,binding.workspace_id,binding.model_id)
        assert row[5]==binding.operation and row[6:9]==(setup.RUNTIME,setup.REGISTRY,'f'*64)
        assert row[10].obj==[r.model_dump(mode='json') for r in stage['f']['all_refs']]
        assert row[-2:]==(stage['f']['expiry'],stage['f']['expiry'])
        assert binding.original_horizon==stage['f']['expiry']
        assert binding.capability_fingerprints==recording.fingerprints
        assert authority.params['user']==binding.session_login
        assert authority.params['hostaddr']=='127.0.0.1'
        assert authority.params['sslmode']=='verify-full'
        assert authority.params['sslrootcert']==psycopg.conninfo.conninfo_to_dict(stage['f']['url'])['sslrootcert']
    appointments=[event[2] for event in recording.events if event[0]=='sql'
        and event[1].startswith('INSERT INTO oracle2.appointments')]
    assert len(appointments)==4
    for appointment,admission in zip(appointments,recording.committed,strict=True):
        assert appointment==(admission[9],stage['f']['workspace'],stage['f']['actor'],
            'recommendation-'+admission[5]+':'+str(stage['f']['model']),
            recording.owner,stage['f']['root'],stage['f']['expiry'])
    statements=[(index,event[1]) for index,event in enumerate(recording.events) if event[0]=='sql']
    grants=[(index,text) for index,text in statements if text.startswith('GRANT EXECUTE')]
    pins=[index for index,text in statements if text.startswith('SELECT p.proname')]
    assert len(pins)==1 and max(index for index,_ in grants)<pins[0]
    assert pins[0]<next(i for i,event in enumerate(recording.events) if event[0]=='commit-attempt')
    assert next(i for i,event in enumerate(recording.events) if event[0]=='closed')<next(i for i,event in enumerate(recording.events) if event[0]=='construct')
    for authority in authorities:
        granted=[text for _,text in grants if text.endswith('TO "'+authority.binding.session_login+'"')]
        expected=[signature for signature in setup.FUNCTIONS if signature.startswith(setup.PUBLIC[authority.binding.operation]+'(')
            or authority.binding.operation=='read' and signature.startswith('list_recommendation_actions_v1(')
            or authority.binding.operation!='read' and signature.startswith('reconcile_recommendation_action_v1(')]
        assert len(granted)==len(expected)
        assert all(any('oracle2.'+signature+' TO ' in text for text in granted) for signature in expected)
        assert all('oracle2._' not in text for text in granted)
    creates=[text for _,text in statements if text.startswith('CREATE ROLE')]
    assert len(creates)==3 and all('NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS' in text for text in creates)
    assert all(stage['login'] not in text for text in creates)


@pytest.mark.parametrize('failure',('third-admission','commit','close'))
def test_any_setup_commit_or_close_failure_returns_no_authority_and_never_retries(stage,monkeypatch,failure):
    recording=RecordingSetup(failure=failure)
    install_recording(monkeypatch,recording)
    with pytest.raises(SetupFailure):
        setup._install_all_advice_authorities_v1('invented-owned-admin',stage)
    assert recording.connections==1 and recording.closed and recording.constructed==[]
    if failure=='third-admission':
        assert recording.pending==recording.committed==[]
        assert sum(e[0]=='rollback' for e in recording.events)==1
        assert not any(e[0]=='sql' and e[1].startswith('SELECT p.proname') for e in recording.events)
    elif failure=='close':
        # A recorded commit is not falsely treated as rollback or retried.
        assert len(recording.committed)==4 and not any(e[0]=='rollback' for e in recording.events)
    else:
        assert sum(e[0]=='commit-attempt' for e in recording.events)==1


@pytest.mark.parametrize('operation',('register','read','feedback','measurement'))
def test_single_install_api_retains_separate_operation_binding_and_closed_connection(stage,monkeypatch,operation):
    recording=RecordingSetup()
    install_recording(monkeypatch,recording)
    kwargs={'login':stage['login']} if operation=='register' else {}
    authority=setup.install('invented-owned-admin',stage,operation,**kwargs)
    assert authority.binding.operation==operation
    assert authority.binding.original_horizon==stage['f']['expiry']
    assert recording.connections==1 and len(recording.committed)==1
    assert recording.constructed==[operation]
    assert sum(e[0]=='sql' and e[1].startswith('SELECT p.proname') for e in recording.events)==1
    if operation=='register':assert authority.binding.session_login==stage['login']
    else:assert re.fullmatch('advice_'+operation+'_[a-f0-9]{10}',authority.binding.session_login)


def test_duplicate_installed_identity_refuses_before_any_admin_context(stage,monkeypatch):
    recording=RecordingSetup()
    install_recording(monkeypatch,recording)
    repeated=uuid4()
    monkeypatch.setattr(setup,'uuid4',lambda:repeated)
    with pytest.raises(AssertionError):setup._install_all_advice_authorities_v1('invented-owned-admin',stage)
    assert recording.connections==0 and recording.events==recording.constructed==[]


@pytest.mark.parametrize('denial',('owned-target','tls','session-user','database'))
def test_existing_actual_admin_guard_refuses_before_any_setup_mutation(stage,monkeypatch,denial):
    import dev.oracle2.test_worker_postgres_fixture as owned
    events=[];queries=[]
    monkeypatch.setenv('ORACLE2_SYNTHETIC_POSTGRES_CONTAINER','invented-owned')
    def guard(container,url):
        assert container=='invented-owned'
        events.append('owned-check')
        if denial=='owned-target':raise PermissionError('invented target mismatch')
    class Connection:
        pgconn=SimpleNamespace(ssl_in_use=denial!='tls')
        def __enter__(self):return self
        def __exit__(self,*args):events.append('closed')
        def execute(self,query,params=()):
            queries.append(query)
            if query!='SELECT SESSION_USER,current_database()':
                raise RuntimeError('denied setup attempted a SQL mutation')
            events.append('identity-check')
            return SimpleNamespace(fetchone=lambda:(
                'wrong' if denial=='session-user' else 'oracle2_admin',
                'wrong' if denial=='database' else 'invented'))
    monkeypatch.setattr(owned,'owned_worker_database',guard)
    monkeypatch.setattr(psycopg,'connect',lambda *args:Connection())
    def no_authority(*args):raise RuntimeError('denied setup constructed an authority')
    monkeypatch.setattr(setup,'_installed_advice_authority_v1',no_authority)
    with pytest.raises(PermissionError if denial=='owned-target' else AssertionError):
        setup._install_all_advice_authorities_v1(stage['f']['url'],stage)
    assert events[0]=='owned-check'
    assert (events[-1]=='closed')==(denial!='owned-target')
    assert queries==([] if denial in ('owned-target','tls') else ['SELECT SESSION_USER,current_database()'])
