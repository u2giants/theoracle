"""Single original monotonic request fence shared by transport and core.

Owner: protected control lifecycle. Pure stdlib context; grants no identity,
source, SQL or operation permission. Hosting retains the old forwarding API.
Retire with that lifecycle; no second deadline/context owner is permitted.
"""
import time
from contextvars import ContextVar
from contextlib import contextmanager
import math
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

