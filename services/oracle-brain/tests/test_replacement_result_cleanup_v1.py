"""Owned fake pools test resource lifecycle only, never serving authority."""
import asyncio,threading
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from oracle_brain.hosting.replacement_result_service_v1 import ProtectedReplacementResultServiceV1,_ResultOwnedLoopV1
from oracle_brain.hosting.replacement_result_settings_v1 import ProtectedReplacementResultSettingsV1


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
        with pytest.raises(PermissionError,match='lifecycle unavailable'):owner.result(b'not-a-peer',b'{}')
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
