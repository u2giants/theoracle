"""Zero-effect refusal in new meeting owners under original-fence loss."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import time
import pytest
from oracle_brain.hosting.meeting_capture_v1 import MeetingCaptureFactoryV1,MeetingHeadV1
from oracle_brain.research.fetch import _InstalledArtifactGET
from oracle_brain.hosting._protected_control_listener_v1 import _request_fence_v1

def test_missing_original_fence_refuses_before_sql_or_private_config(monkeypatch):
    import psycopg
    import oracle_brain.hosting.meeting_capture_v1 as owner
    calls=[];monkeypatch.setattr(psycopg,'connect',lambda *a,**kw:calls.append('sql'))
    monkeypatch.setattr(owner,'_pinned',lambda *a,**kw:calls.append('private'))
    factory=object.__new__(MeetingCaptureFactoryV1);factory.settings=SimpleNamespace(host=SimpleNamespace(config=object()),current=lambda:calls.append('settings'))
    with pytest.raises(PermissionError,match='fence required'):factory._call('read',('status',),MeetingHeadV1,datetime.now(timezone.utc)+timedelta(seconds=20))
    assert calls==[]

def test_original_monotonic_end_not_renewed_by_utc_rollback_before_next_effect(monkeypatch):
    import psycopg
    import oracle_brain.hosting.meeting_capture_v1 as owner
    import oracle_brain.hosting._protected_control_listener_v1 as fence
    calls=[];now=datetime.now(timezone.utc);tick=time.monotonic()
    class RolledBack(datetime):
        @classmethod
        def now(cls,tz=None):return now-timedelta(seconds=60)
    monkeypatch.setattr(owner,'datetime',RolledBack)
    monkeypatch.setattr(psycopg,'connect',lambda *a,**kw:calls.append('sql'))
    monkeypatch.setattr(owner,'_pinned',lambda *a,**kw:calls.append('private'))
    factory=object.__new__(MeetingCaptureFactoryV1);factory.settings=SimpleNamespace(host=SimpleNamespace(config=object()),current=lambda:calls.append('settings'))
    with _request_fence_v1(float(tick+1)):
        monkeypatch.setattr(fence.time,'monotonic',lambda:tick+2)
        with pytest.raises(PermissionError,match='fence elapsed'):factory._call('read',('status',),MeetingHeadV1,now+timedelta(seconds=20))
    assert calls==[]

def test_artifact_missing_context_refuses_before_current_dns_or_connect(monkeypatch):
    calls=[];owner=object.__new__(_InstalledArtifactGET);owner.current=lambda:calls.append('current')
    with pytest.raises(PermissionError,match='fence required'):owner.fetch(caller_deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
    assert calls==[]

@pytest.mark.parametrize('url',[
 'postgresql://reader:invented@dns.example.test/oracle2?sslmode=verify-full&sslrootcert=/invented/ca',
 'postgresql://reader:invented@127.0.0.1,127.0.0.2/oracle2?sslmode=verify-full&sslrootcert=/invented/ca',
])
def test_new_meeting_sql_refuses_dns_or_multihost_before_connect(monkeypatch,url):
    import psycopg
    import oracle_brain.hosting.meeting_capture_v1 as owner
    calls=[];monkeypatch.setattr(psycopg,'connect',lambda *a,**kw:calls.append('connect'))
    monkeypatch.setattr(owner,'_pinned',lambda path,*args:url.encode() if path=='/invented/url' else b'invented CA')
    h=SimpleNamespace(database_url=SimpleNamespace(path='/invented/url',sha256='a'*64),database_ca=SimpleNamespace(path='/invented/ca',sha256='b'*64),expected_session_role='reader')
    f=object.__new__(MeetingCaptureFactoryV1);f.settings=SimpleNamespace(host=SimpleNamespace(config=h),current=lambda:datetime.now(timezone.utc)+timedelta(seconds=30))
    with _request_fence_v1(float(time.monotonic()+10)):
        with pytest.raises(PermissionError):f._call('read',('status',),MeetingHeadV1,datetime.now(timezone.utc)+timedelta(seconds=10))
    assert calls==[]

def test_new_meeting_sql_refuses_actual_sub_two_second_connect_budget(monkeypatch):
    import psycopg
    import oracle_brain.hosting.meeting_capture_v1 as owner
    calls=[];monkeypatch.setattr(psycopg,'connect',lambda *a,**kw:calls.append(kw))
    raw=b'postgresql://reader:invented@127.0.0.1:5432/oracle2?sslmode=verify-full&sslrootcert=/invented/ca'
    monkeypatch.setattr(owner,'_pinned',lambda path,*args:raw if path=='/invented/url' else b'invented CA')
    h=SimpleNamespace(database_url=SimpleNamespace(path='/invented/url',sha256='a'*64),database_ca=SimpleNamespace(path='/invented/ca',sha256='b'*64),expected_session_role='reader')
    f=object.__new__(MeetingCaptureFactoryV1);f.settings=SimpleNamespace(host=SimpleNamespace(config=h),current=lambda:datetime.now(timezone.utc)+timedelta(seconds=30))
    with _request_fence_v1(float(time.monotonic()+1.9)):
        with pytest.raises(PermissionError,match='two-second connection bound'):f._call('read',('status',),MeetingHeadV1,datetime.now(timezone.utc)+timedelta(seconds=10))
    assert calls==[]

@pytest.mark.parametrize('url',[
 'postgresql://reader:invented@127.0.0.1:5432/oracle2?sslmode=verify-full&sslrootcert=/invented/ca',
 'postgresql://reader:invented@db.example.test:5432/oracle2?hostaddr=127.0.0.1&sslmode=verify-full&sslrootcert=/invented/ca',
])
def test_new_meeting_connect_prearms_all_bounds_from_same_original_remaining(monkeypatch,url):
    import psycopg
    import oracle_brain.hosting.meeting_capture_v1 as owner
    calls=[]
    def connect(*args,**options):
        calls.append((args,options));raise LookupError('invented recording connector, no socket')
    monkeypatch.setattr(psycopg,'connect',connect)
    monkeypatch.setattr(owner,'_pinned',lambda path,*args:url.encode() if path=='/invented/url' else b'invented CA')
    h=SimpleNamespace(database_url=SimpleNamespace(path='/invented/url',sha256='a'*64),database_ca=SimpleNamespace(path='/invented/ca',sha256='b'*64),expected_session_role='reader')
    f=object.__new__(MeetingCaptureFactoryV1);f.settings=SimpleNamespace(host=SimpleNamespace(config=h),current=lambda:datetime.now(timezone.utc)+timedelta(seconds=30))
    with _request_fence_v1(float(time.monotonic()+2.9)):
        with pytest.raises(LookupError,match='recording connector'):f._call('read',('status',),MeetingHeadV1,datetime.now(timezone.utc)+timedelta(seconds=10))
    assert len(calls)==1 and calls[0][0]==(url,)
    options=calls[0][1];assert options['connect_timeout']==2
    assert 1<=options['tcp_user_timeout']<900
    assert options['hostaddr']=='127.0.0.1' and options['port']=='5432' and options['autocommit'] is True
    import re
    bounds=[int(v) for v in re.findall(r'=(\d+)ms',options['options'])]
    assert len(bounds)==2 and 1<=bounds[0]<900 and bounds[1]==bounds[0]

def test_local_startup_never_exceeds_canonical_five_second_statement_ceiling(monkeypatch):
    import psycopg,re
    import oracle_brain.hosting.meeting_capture_v1 as owner
    calls=[]
    def connect(*args,**options):
        calls.append(options);raise LookupError('invented recorded startup, no socket')
    monkeypatch.setattr(psycopg,'connect',connect)
    raw=b'postgresql://reader:invented@127.0.0.1:5432/oracle2?sslmode=verify-full&sslrootcert=/invented/ca'
    monkeypatch.setattr(owner,'_pinned',lambda path,*args:raw if path=='/invented/url' else b'invented CA')
    h=SimpleNamespace(database_url=SimpleNamespace(path='/invented/url',sha256='a'*64),database_ca=SimpleNamespace(path='/invented/ca',sha256='b'*64),expected_session_role='reader')
    f=object.__new__(MeetingCaptureFactoryV1);f.settings=SimpleNamespace(host=SimpleNamespace(config=h),current=lambda:datetime.now(timezone.utc)+timedelta(seconds=30))
    with _request_fence_v1(float(time.monotonic()+20)):
        with pytest.raises(LookupError,match='recorded startup'):f._call('read',('status',),MeetingHeadV1,datetime.now(timezone.utc)+timedelta(seconds=20))
    bounds=[int(v) for v in re.findall(r'=(\d+)ms',calls[0]['options'])]
    assert 1<=bounds[0]<=2000 and 1<=bounds[1]<=2000


def test_caller_narrowed_original_monotonic_window_survives_mid_sql_utc_rollback(monkeypatch):
    import psycopg
    import oracle_brain.hosting.meeting_capture_v1 as owner
    import oracle_brain.hosting._protected_control_listener_v1 as fence
    now=datetime.now(timezone.utc);tick=[time.monotonic()];initial=tick[0];rolled=[False];commands=[]
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return now-timedelta(seconds=60) if rolled[0] else now
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def execute(self,query,*args):
            commands.append(query)
            if len(commands)==2:tick[0]=initial+4;rolled[0]=True
        def fetchone(self):return ('reader','reader','owner')
        def fetchall(self):raise AssertionError('no later query may run')
    class Connection:
        info=SimpleNamespace(host='127.0.0.1',dbname='oracle2',user='reader',port=5432)
        pgconn=SimpleNamespace(ssl_in_use=True)
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def execute(self,*args):
            cursor=Cursor();cursor.execute(*args);return cursor
        def commit(self):raise AssertionError('expired request cannot commit')
    import oracle_brain.operating_model.request_deadline_v1 as shared_deadline
    monkeypatch.setattr(shared_deadline,'datetime',Clock)
    monkeypatch.setattr(owner,'datetime',Clock);monkeypatch.setattr(fence.time,'monotonic',lambda:tick[0])
    monkeypatch.setattr(psycopg,'connect',lambda *args,**options:Connection())
    raw=b'postgresql://reader:invented@127.0.0.1:5432/oracle2?sslmode=verify-full&sslrootcert=/invented/ca'
    monkeypatch.setattr(owner,'_pinned',lambda path,*args:raw if path=='/invented/url' else b'invented CA')
    h=SimpleNamespace(database_url=SimpleNamespace(path='/invented/url',sha256='a'*64),database_ca=SimpleNamespace(path='/invented/ca',sha256='b'*64),expected_session_role='reader',expected_owner_role='owner')
    f=object.__new__(MeetingCaptureFactoryV1);f.settings=SimpleNamespace(host=SimpleNamespace(config=h),current=lambda:now+timedelta(seconds=30))
    with _request_fence_v1(float(initial+25)):
        with pytest.raises(PermissionError,match='original protected request fence elapsed'):f._call('read',('status',),MeetingHeadV1,Clock.fromtimestamp(now.timestamp()+3,timezone.utc))
    assert len(commands)==2 and 'SESSION_USER' in commands[-1]
    assert commands[0]=='BEGIN ISOLATION LEVEL READ COMMITTED'


@pytest.mark.parametrize('name',['PGHOST','PGPASSFILE','PGOPTIONS','PGSERVICEFILE'])
def test_meeting_common_connection_refuses_environment_before_socket(monkeypatch,name):
    import psycopg
    import oracle_brain.hosting.meeting_capture_v1 as owner
    calls=[];monkeypatch.setattr(psycopg,'connect',lambda *a,**kw:calls.append(1));monkeypatch.setenv(name,'invented must not become a target')
    raw=b'postgresql://reader:invented@127.0.0.1:5432/oracle2?sslmode=verify-full&sslrootcert=/invented/ca'
    monkeypatch.setattr(owner,'_pinned',lambda path,*args:raw if path=='/invented/url' else b'invented CA')
    h=SimpleNamespace(database_url=SimpleNamespace(path='/invented/url',sha256='a'*64),database_ca=SimpleNamespace(path='/invented/ca',sha256='b'*64),expected_session_role='reader')
    f=object.__new__(MeetingCaptureFactoryV1);f.settings=SimpleNamespace(host=SimpleNamespace(config=h),current=lambda:datetime.now(timezone.utc)+timedelta(seconds=30))
    with _request_fence_v1(float(time.monotonic()+10)):
        with pytest.raises(PermissionError,match='PG environment'):f._call('read',('status',),MeetingHeadV1,datetime.now(timezone.utc)+timedelta(seconds=10))
    assert calls==[]
