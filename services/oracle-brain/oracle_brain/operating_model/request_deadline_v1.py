"""Single original monotonic request fence shared by transport and core.

Owner: protected control lifecycle. Pure stdlib context; grants no identity,
source, SQL or operation permission. Hosting retains the old forwarding API.
Retire with that lifecycle; no second deadline/context owner is permitted.
"""
import time
from contextvars import ContextVar
from contextlib import contextmanager
import math
from dataclasses import dataclass
from datetime import datetime, timezone
_request_end_v1=ContextVar('oracle_protected_control_original_end_v1',default=None)

def request_remaining_v1(*,required=True):
    """Same original listener fence; no UTC rollback or nested renewal."""
    end=_request_end_v1.get()
    if end is None:
        if required:raise PermissionError('original protected request fence required')
        return None
    remaining=end-time.monotonic()
    if remaining<=0:raise PermissionError('original protected request fence elapsed')
    return remaining

@contextmanager
def _request_fence_v1(original_monotonic_end):
    # Private trusted startup/test owner only, never a wire/HTTP field. Threads
    # do not inherit this ContextVar; explicit trusted carry is required.
    if type(original_monotonic_end) is not float or not math.isfinite(original_monotonic_end):
        raise PermissionError('exact original monotonic fence required')
    prior=_request_end_v1.get()
    token=_request_end_v1.set(min(prior,original_monotonic_end) if prior is not None else original_monotonic_end)
    try:
        request_remaining_v1();yield
    finally:_request_end_v1.reset(token)


def sql_remaining_v1(deadline):
    """Wall deadline narrowed by the SAME original monotonic request fence."""
    if type(deadline) is not datetime or deadline.tzinfo is None or deadline.utcoffset() is None:
        raise PermissionError('aware original SQL deadline required')
    remaining=(deadline-datetime.now(timezone.utc)).total_seconds()
    original=request_remaining_v1(required=False)
    if original is not None:remaining=min(remaining,original)
    if not math.isfinite(remaining) or remaining<=0:
        raise PermissionError('original SQL request window elapsed')
    return remaining


@dataclass
class _SQLWindowV1:
    connection: object
    deadline: datetime
    armed_ms: int


_sql_windows_v1=ContextVar('oracle_original_request_sql_windows_v1',default=())


@contextmanager
def _sql_window_v1(connection,deadline,*,armed_timeout_ms):
    """Trusted connection owner records ACTUAL prearmed server timeout.

    No connection, clock, transaction or authority is manufactured here. The
    owner must install this timeout before the first query (libpq startup).
    Each send must fit the already installed timeout; a setter is itself a
    send under the OLD timeout. This deliberately refuses near the end rather
    than renewing the original request or relying on a late timeout setter.
    """
    if type(armed_timeout_ms) is not int or not 1<=armed_timeout_ms<=30000:
        raise PermissionError('bounded actual SQL timeout required')
    sql_remaining_v1(deadline)
    prior=_sql_windows_v1.get()
    if any(w.connection is connection for w in prior):
        raise PermissionError('SQL connection window already captured')
    window=_SQLWindowV1(connection,deadline,armed_timeout_ms)
    token=_sql_windows_v1.set((*prior,window))
    try:yield
    finally:_sql_windows_v1.reset(token)


def _sql_send_window_v1(connection,deadline):
    matches=[w for w in _sql_windows_v1.get() if w.connection is connection]
    if len(matches)!=1:raise PermissionError('original prearmed SQL connection window required')
    window=matches[0]
    if deadline>window.deadline:raise PermissionError('SQL deadline cannot be extended')
    # Strictly reserve the captured server statement bound before EVERY send.
    # A small guard also avoids integer truncation putting the timeout on the
    # exact boundary. A slow connect/catalog read never renews this budget.
    if sql_remaining_v1(min(deadline,window.deadline))<=window.armed_ms/1000+.001:
        raise PermissionError('original SQL window cannot fit the already armed timeout')
    return window


def sql_execute_v1(connection,deadline,*args,**kwargs):
    _sql_send_window_v1(connection,deadline)
    result=connection.execute(*args,**kwargs)
    sql_remaining_v1(deadline)
    return result


def sql_execute_current_v1(connection,*args,**kwargs):
    """Existing catalog owner: narrow an ACTUAL captured window if present.

    Legacy callers with no captured SQL window keep their original API. An
    active window for another connection never permits an unguarded fallback.
    This selects no identity/role and cannot create a connection or admission.
    """
    windows=_sql_windows_v1.get()
    if not windows:return connection.execute(*args,**kwargs)
    matches=[w for w in windows if w.connection is connection]
    if len(matches)!=1:raise PermissionError('SQL connection differs from captured original window')
    return sql_execute_v1(connection,matches[0].deadline,*args,**kwargs)


def sql_rearm_v1(connection,deadline,*,timeout_ms):
    if type(timeout_ms) is not int or not 1<=timeout_ms<=30000:
        raise PermissionError('bounded exact SQL timeout required')
    window=_sql_send_window_v1(connection,deadline)
    # The old bound remains authoritative until the real setter succeeds.
    result=sql_execute_v1(connection,deadline,
        "SELECT pg_catalog.set_config('statement_timeout',%s,true),pg_catalog.set_config('lock_timeout',%s,true)",
        (str(timeout_ms)+'ms',str(timeout_ms)+'ms'))
    window.armed_ms=timeout_ms
    return result

