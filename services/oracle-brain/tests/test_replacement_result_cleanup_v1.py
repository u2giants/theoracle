"""Owned fake pools test resource lifecycle only, never serving authority."""
import asyncio,hashlib,threading,time
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from uuid import uuid4
import pytest
from oracle_brain.hosting import replacement_result_service_v1 as svc_mod
from oracle_brain.hosting.replacement_result_service_v1 import (
    ProtectedReplacementResultServiceV1,_ResultOwnedLoopV1,_target_identity,
    _admit_owned_result_v1)
from oracle_brain.hosting.replacement_result_settings_v1 import ProtectedReplacementResultSettingsV1
from oracle_brain.hosting.replacement_result_v1 import ProtectedReplacementResultRequestV1,PROTOCOL
from oracle_brain.operating_model.contracts import (
    ReplacementExecutorTargetV1,ReplacementConfirmationTargetV1,canonical_bytes)
from oracle_brain.operating_model.source_receipts import SourceRef


def service():
    # No request is permitted to use these deliberately uninitialized settings.
    return ProtectedReplacementResultServiceV1(object.__new__(ProtectedReplacementResultSettingsV1))


@pytest.mark.parametrize('expired',[False,True])
def test_close_is_initiated_even_after_original_operation_expiry(expired):
    async def run():
        s=service();seen=[]
        async def close():seen.append('closed')
        projection=SimpleNamespace(connection=SimpleNamespace(close=close))
        end=datetime.now(timezone.utc)+timedelta(seconds=-1 if expired else 10)
        if expired:
            with pytest.raises(PermissionError,match='original deadline'):await s._close_owned_projection(projection,end)
        else:await s._close_owned_projection(projection,end)
        assert seen==['closed'] and not s._owned_closes
    asyncio.run(run())


def test_exception_path_still_closes_owned_pool():
    async def run():
        s=service();seen=[]
        async def close():seen.append('closed')
        projection=SimpleNamespace(connection=SimpleNamespace(close=close))
        with pytest.raises(ValueError,match='invented operation failure'):
            try:raise ValueError('invented operation failure')
            finally:await s._close_owned_projection(projection,datetime.now(timezone.utc)+timedelta(seconds=10))
        assert seen==['closed'] and not s._owned_closes
    asyncio.run(run())


def test_caller_cancellation_does_not_cancel_owned_close():
    async def run():
        s=service();started=asyncio.Event();release=asyncio.Event();seen=[]
        async def close():started.set();await release.wait();seen.append('closed')
        task=asyncio.create_task(s._close_owned_projection(SimpleNamespace(connection=SimpleNamespace(close=close)),
            datetime.now(timezone.utc)+timedelta(seconds=10)))
        await started.wait();task.cancel();await asyncio.sleep(0);release.set()
        with pytest.raises(asyncio.CancelledError):await task
        assert seen==['closed'] and not s._owned_closes
    asyncio.run(run())


def test_close_failure_retains_exact_task_and_connection_unknown():
    async def run():
        s=service()
        async def close():raise OSError('invented close failure')
        projection=SimpleNamespace(connection=SimpleNamespace(close=close))
        with pytest.raises(PermissionError,match='cleanup failed'):
            await s._close_owned_projection(projection,datetime.now(timezone.utc)+timedelta(seconds=10))
        assert s._cleanup_unknown and tuple(s._owned_closes.values())==(projection,)
        assert next(iter(s._owned_closes)).done()
    asyncio.run(run())


def test_pending_close_keeps_owned_loop_alive_then_observed_shutdown_joins():
    s=service();owner=_ResultOwnedLoopV1(s);started=threading.Event();release=threading.Event();seen=[]
    async def close():
        started.set()
        while not release.is_set():await asyncio.sleep(.01)
        seen.append('closed')
    projection=SimpleNamespace(connection=SimpleNamespace(close=close))
    future=asyncio.run_coroutine_threadsafe(s._close_owned_projection(projection,
        datetime.now(timezone.utc)+timedelta(seconds=20)),owner.loop)
    try:
        assert started.wait(1)
        with pytest.raises(PermissionError,match='cleanup remains unknown'):future.result(timeout=6)
        actual=next(iter(s._owned_closes))
        assert s._cleanup_unknown and not actual.done() and owner.thread.is_alive()
        with pytest.raises(PermissionError,match='cleanup requires observation'):
            owner.result(b'not-a-peer',b'{}',absolute_monotonic_deadline=time.monotonic()+10)
        assert tuple(s._owned_closes.values())==(projection,)
        with pytest.raises(PermissionError,match='tasks remain pending'):owner.close()
        assert owner.thread.is_alive() and not actual.done() and not owner.loop.is_closed()
    finally:
        # Mandatory release: no test leaves a deliberate non-daemon owner alive.
        release.set();owner.close()
    assert seen==['closed'] and actual.done() and owner.loop.is_closed() and not owner.thread.is_alive()
    owner.close()  # Idempotent, settled-only shutdown.


def test_fixed_loop_rejects_foreign_service_without_thread():
    with pytest.raises(PermissionError,match='exact owned result service'):_ResultOwnedLoopV1(object())


def _request_bytes(*,expires_in=20.0,nonce=None):
    now=datetime.now(timezone.utc)
    nonce=nonce or hashlib.sha256(str(time.monotonic_ns()).encode()).hexdigest()
    request=ProtectedReplacementResultRequestV1(schema_version=1,protocol=PROTOCOL,
        journey_id=uuid4(),expected_journey_revision=1,model_id=uuid4(),model_version=1,
        content_hash='a'*64,projection_digest='b'*64,ack_event_id=uuid4(),
        summary_artifact_id=uuid4(),summary_version=1,summary_content_hash='c'*64,
        nonce=nonce,expires_at=now+timedelta(seconds=expires_in))
    return canonical_bytes(request.model_dump(mode='json')),request


def _target(**overrides):
    now=datetime.now(timezone.utc)
    workspace,source,model,run,actor,ack=(uuid4() for _ in range(6))
    data=dict(schema_version=1,run_id=run,journey_revision=1,state='delivered',
        answer_hold=False,cancelled=False,population_sha256='a'*64,
        requester_principal_id=actor,workspace_id=workspace,model_id=model,
        model_version=1,model_content_hash='b'*64,ack_event_id=ack,projection_digest='c'*64,
        source_refs=(SourceRef(workspace_id=workspace,source_id=source,revision=1,
            original_sha256='d'*64,reading_sha256='e'*64,parser_id='f'*64),),
        current_confirmation=None,summary_targets=(),
        checked_at=now,valid_until=now+timedelta(seconds=30))
    data.update(overrides)
    return ReplacementExecutorTargetV1.model_validate(data)


def _client_der_and_uri():
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    uri='spiffe://oracle/result-client'
    key=ec.generate_private_key(ec.SECP256R1())
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'result-client')])
    now=datetime.now(timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.UniformResourceIdentifier(uri)]),critical=False)
        .sign(key,hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.DER),uri

_CLIENT_DER,_CLIENT_URI=_client_der_and_uri()


def _drive_handle(monkeypatch,tmp_path,before,changed):
    """Fixture-only handle_result_v1; identity change is applied only after owned close."""
    until=datetime.now(timezone.utc)+timedelta(seconds=30)
    state={'closed':False}
    c=SimpleNamespace(
        client_certificate_sha256=hashlib.sha256(_CLIENT_DER).hexdigest(),
        client_uri=_CLIENT_URI,model_id=before.model_id,model_version=before.model_version,
        model_content_hash=before.model_content_hash,projection_digest=before.projection_digest,
        ack_event_id=before.ack_event_id,summary_artifact_id=uuid4(),summary_version=1,
        summary_content_hash='e'*64,journey_id=before.run_id,workspace_id=before.workspace_id,
        nonce_root=str(tmp_path/'nonces'),
        expires_at=until,original_horizon=until,workflow_id='invented-flow')
    settings=object.__new__(ProtectedReplacementResultSettingsV1)
    object.__setattr__(settings,'config',c)
    object.__setattr__(settings,'executor',SimpleNamespace(
        read_target=lambda:(None,{'operating_models':[{}],'observations':[],'findings':[]}),
        read_summary=lambda *a,**k:None,guard=object(),ledger=object(),
        config=SimpleNamespace(source_refs=before.source_refs)))
    def current_target(self):
        return (before if not state['closed'] else changed),until
    monkeypatch.setattr(ProtectedReplacementResultSettingsV1,'current_target',current_target)
    class FakeProjection:
        def __init__(self):
            self.connection=SimpleNamespace(close=self._close)
        async def _close(self):
            state['closed']=True
        async def load(self,*a,**k):
            return None
    class FakeResponse:
        def __init__(self,**kw):
            self._data=kw
        def model_dump(self,mode='python'):
            return dict(self._data)
    class FakeView:
        def model_dump(self,mode='json'):
            return {'view':'fixture'}
    monkeypatch.setattr(svc_mod,'build_paid_executor_projection_v3',lambda e:FakeProjection())
    monkeypatch.setattr(svc_mod,'qualified_map_view_v1',lambda *a,**k:FakeView())
    monkeypatch.setattr(svc_mod,'serve_summary',lambda *a,**k:object())
    monkeypatch.setattr(svc_mod,'answer_from_summary',lambda *a,**k:object())
    monkeypatch.setattr(svc_mod,'documentary_answer_public_v1',lambda *a,**k:None)
    monkeypatch.setattr(svc_mod,'public_snapshot_v1',lambda **k:FakeView())
    monkeypatch.setattr(svc_mod,'ProtectedReplacementResultResponseV1',FakeResponse)
    monkeypatch.setattr(svc_mod,'encode_result_response_v1',lambda r:b'encoded-result')
    monkeypatch.setattr(svc_mod,'_durable_nonce',lambda *a,**k:None)
    monkeypatch.setattr(svc_mod,'BusinessOperatingModel',SimpleNamespace(model_validate_json=lambda b:FakeView()))
    monkeypatch.setattr(svc_mod,'Observation',SimpleNamespace(model_validate_json=lambda b:FakeView()))
    monkeypatch.setattr(svc_mod,'Finding',SimpleNamespace(model_validate_json=lambda b:FakeView()))
    request=ProtectedReplacementResultRequestV1(schema_version=1,protocol=PROTOCOL,
        journey_id=before.run_id,expected_journey_revision=before.journey_revision,
        model_id=c.model_id,model_version=c.model_version,content_hash=c.model_content_hash,
        projection_digest=c.projection_digest,ack_event_id=c.ack_event_id,
        summary_artifact_id=c.summary_artifact_id,summary_version=c.summary_version,
        summary_content_hash=c.summary_content_hash,nonce='1'*64,
        expires_at=datetime.now(timezone.utc)+timedelta(seconds=25))
    raw=canonical_bytes(request.model_dump(mode='json'))
    return ProtectedReplacementResultServiceV1(settings),raw,state


def test_slowbody_wait_uses_original_deadline_not_a_fresh_35s_clock():
    s=service();release=threading.Event();started=threading.Event()
    async def slow(peer,raw):
        started.set()
        while not release.is_set():await asyncio.sleep(.01)
        raise ValueError('invented slow body failure')
    s.handle_result_v1=slow
    owner=_ResultOwnedLoopV1(s)
    try:
        raw,_=_request_bytes(expires_in=0.3)
        begin=time.monotonic()
        with pytest.raises(PermissionError,match='remains unknown'):
            owner.result(b'peer',raw,absolute_monotonic_deadline=time.monotonic()+20)
        elapsed=time.monotonic()-begin
        assert started.wait(1)
        assert elapsed<12,f'handler wait lasted {elapsed:.2f}s; expected original_end+5 grace, not 35s'
        end=time.monotonic()+2
        while not s._cleanup_unknown and time.monotonic()<end:time.sleep(.01)
        assert s._cleanup_unknown
    finally:
        release.set();owner.close()


def test_queuedexpiry_expires_while_queued_before_handler_runs():
    s=service();handle_calls=[]
    async def never(peer,raw):
        handle_calls.append(raw);return b'unreachable'
    s.handle_result_v1=never
    owner=_ResultOwnedLoopV1(s)
    loop_blocked=threading.Event();release=threading.Event()
    def blocker():
        loop_blocked.set()
        while not release.is_set():time.sleep(.01)
    try:
        owner.loop.call_soon_threadsafe(blocker)
        assert loop_blocked.wait(1)
        raw,_=_request_bytes(expires_in=0.6)
        threading.Timer(1.0,release.set).start()
        with pytest.raises(PermissionError,match='original result handler deadline expired'):
            owner.result(b'peer',raw,absolute_monotonic_deadline=time.monotonic()+20)
        assert handle_calls==[]
        assert not s._cleanup_unknown
    finally:
        release.set();owner.close()


def test_lateexception_after_handler_wait_is_observed_and_owned():
    s=service();release=threading.Event();started=threading.Event()
    async def slow_fail(peer,raw):
        started.set()
        while not release.is_set():await asyncio.sleep(.01)
        raise ValueError('invented late exception')
    s.handle_result_v1=slow_fail
    owner=_ResultOwnedLoopV1(s)
    try:
        raw,_=_request_bytes(expires_in=0.2)
        with pytest.raises(PermissionError,match='remains unknown'):
            owner.result(b'peer',raw,absolute_monotonic_deadline=time.monotonic()+20)
        end=time.monotonic()+2
        while not s._cleanup_unknown and time.monotonic()<end:time.sleep(.01)
        assert s._cleanup_unknown
        assert started.wait(1)
        release.set()
        end=time.monotonic()+3
        while time.monotonic()<end and (owner.observed_outcomes['failed']<1 or owner.records):
            time.sleep(.01)
        assert owner.observed_outcomes['failed']==1
        assert not owner.records
    finally:
        release.set();owner.close()


def test_constructor_failure_leaves_closed_resources_or_owned_unknown(monkeypatch):
    s=service();loops=[];real_new=asyncio.new_event_loop
    def capture():
        loop=real_new();loops.append(loop);return loop
    monkeypatch.setattr(asyncio,'new_event_loop',capture)
    class DeadThread:
        def __init__(self,*a,**k):self._alive=False
        def start(self):raise RuntimeError('invented thread start failure')
        def is_alive(self):return self._alive
        def join(self,timeout=None):pass
    monkeypatch.setattr(threading,'Thread',DeadThread)
    with pytest.raises(RuntimeError,match='invented thread start failure'):
        _ResultOwnedLoopV1(s)
    assert loops and loops[0].is_closed()
    class StuckThread:
        def __init__(self,*a,**k):self._alive=False
        def start(self):self._alive=True
        def is_alive(self):return self._alive
        def join(self,timeout=None):pass
    class NeverReady:
        def set(self):pass
        def wait(self,timeout=None):return False
        def is_set(self):return False
    monkeypatch.setattr(threading,'Thread',StuckThread)
    monkeypatch.setattr(threading,'Event',NeverReady)
    with pytest.raises(PermissionError,match='constructor cleanup remains unknown'):
        _ResultOwnedLoopV1(s)


def test_unchanged_tuple_after_close_still_returns(monkeypatch,tmp_path):
    before=_target()
    service,raw,state=_drive_handle(monkeypatch,tmp_path,before,before)
    assert asyncio.run(service.handle_result_v1(_CLIENT_DER,raw))==b'encoded-result'
    assert state['closed'] and not service._cleanup_unknown and not service._owned_closes


def test_revoked_during_close_refuses_changed_current_tuple(monkeypatch,tmp_path):
    before=_target()
    changed=before.model_copy(update={'state':'cancelled','cancelled':True})
    assert _target_identity(before)!=_target_identity(changed)
    service,raw,state=_drive_handle(monkeypatch,tmp_path,before,changed)
    with pytest.raises(PermissionError,match='result changed during owned cleanup'):
        asyncio.run(service.handle_result_v1(_CLIENT_DER,raw))
    assert state['closed']


def test_hold_appearing_during_cleanup_refuses_tuple(monkeypatch,tmp_path):
    before=_target()
    changed=before.model_copy(update={'answer_hold':True})
    assert _target_identity(before)!=_target_identity(changed)
    service,raw,state=_drive_handle(monkeypatch,tmp_path,before,changed)
    with pytest.raises(PermissionError,match='result changed during owned cleanup'):
        asyncio.run(service.handle_result_v1(_CLIENT_DER,raw))
    assert state['closed']


def test_confirmation_change_during_cleanup_refuses_tuple(monkeypatch,tmp_path):
    before=_target()
    changed=before.model_copy(update={'current_confirmation':ReplacementConfirmationTargetV1(
        workflow_id='other-flow',version=1,content_hash=before.model_content_hash,eligible=True)})
    assert _target_identity(before)!=_target_identity(changed)
    service,raw,state=_drive_handle(monkeypatch,tmp_path,before,changed)
    with pytest.raises(PermissionError,match='result changed during owned cleanup'):
        asyncio.run(service.handle_result_v1(_CLIENT_DER,raw))
    assert state['closed']


def test_settled_unknown_cleanup_does_not_poison_later_requests():
    """PR201: a settled close failure must not permanently deny later valid reads."""
    async def run():
        s=service()
        async def bad_close():raise OSError('invented close failure')
        projection=SimpleNamespace(connection=SimpleNamespace(close=bad_close))
        with pytest.raises(PermissionError,match='cleanup failed'):
            await s._close_owned_projection(projection,datetime.now(timezone.utc)+timedelta(seconds=10))
        assert s._cleanup_unknown
        # Close task is done (observed failure). Later admission must clear the
        # stale deny so an expected negative cannot poison the backend.
        _admit_owned_result_v1(s)
        assert not s._cleanup_unknown
    asyncio.run(run())


def test_pending_unknown_cleanup_still_denies_until_settled():
    """Fail-closed remains while owned cleanup is still in flight and unknown."""
    s=service();owner=_ResultOwnedLoopV1(s);started=threading.Event();release=threading.Event()
    async def slow_close():
        started.set()
        while not release.is_set():await asyncio.sleep(.01)
    projection=SimpleNamespace(connection=SimpleNamespace(close=slow_close))
    future=asyncio.run_coroutine_threadsafe(s._close_owned_projection(projection,
        datetime.now(timezone.utc)+timedelta(seconds=20)),owner.loop)
    try:
        assert started.wait(1)
        with pytest.raises(PermissionError,match='cleanup remains unknown'):future.result(timeout=6)
        assert s._cleanup_unknown
        with pytest.raises(PermissionError,match='cleanup requires observation'):
            owner.result(b'not-a-peer',b'{}',absolute_monotonic_deadline=time.monotonic()+10)
        with pytest.raises(PermissionError,match='cleanup requires observation'):
            _admit_owned_result_v1(s)
    finally:
        release.set();owner.close()
    assert not any(not t.done() for t in s._owned_closes)


def test_foreign_process_expected_negative_then_valid_read_succeeds():
    """PR201 gate: foreignProcess negative + restore must allow a later 200 read.

    The foreign-process case raises PermissionError from the request body while
    the owned projection close succeeds. That expected negative must leave the
    backend able to serve the next valid request (post restore-a 'Read current
    knowledge'). A genuinely corrupted cleanup still denies its own request.
    """
    async def run():
        s=service();seen=[]
        async def close():seen.append('closed')
        projection=SimpleNamespace(connection=SimpleNamespace(close=close))
        with pytest.raises(PermissionError,match='process outside current qualified model'):
            try:raise PermissionError('process outside current qualified model')
            finally:await s._close_owned_projection(projection,datetime.now(timezone.utc)+timedelta(seconds=10))
        assert seen==['closed'] and not s._cleanup_unknown and not s._owned_closes
        # Subsequent valid read admission succeeds (post restore-a).
        _admit_owned_result_v1(s)
        assert not s._cleanup_unknown
        # Genuinely corrupted cleanup still fails closed for that request.
        async def bad_close():raise OSError('invented corruption')
        bad=SimpleNamespace(connection=SimpleNamespace(close=bad_close))
        with pytest.raises(PermissionError,match='cleanup failed'):
            await s._close_owned_projection(bad,datetime.now(timezone.utc)+timedelta(seconds=10))
        assert s._cleanup_unknown
    asyncio.run(run())
